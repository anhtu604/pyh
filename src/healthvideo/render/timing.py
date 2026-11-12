"""Runtime timing derived from measured speech; approved storyboards stay immutable.

For consecutive scenes sharing a script line, each timing row records the FULL
line's ``audio_ms``. The source WAV is spoken once, continuously across the group.
"""

import hashlib
import json
import math
import wave
from collections.abc import Mapping
from pathlib import Path

from healthvideo.domain.script import Script
from healthvideo.domain.storyboard import Scene, Storyboard
from healthvideo.storage.files import canonical_json_hash, read_yaml, sha256_file

TIMING_POLICY_VERSION = "1.1"
PAD_FRAMES = 9

# Measured 2026-11-12 on gout revision 001: renders/render-input.json narration
# paired by script_line_id with renders/audio/lines/N01.wav through N30.wav.
# After the same tts_text/apply_pronunciation preprocessing used below:
# 9,254 characters / 564.55 WAV seconds = 16.39181649101054 characters/second.
# One pooled constant (no per-line fitting); absolute scene errors <= 9.642%
# on this calibration set, not an independent validation set. See report-codex-p1.md.
# Voice: vibi_minimax / speech-2.8-hd / 1d90e9bd-a67b-4d63-a415-032eb9ce91b5,
# speed 1.0. This fallback is an estimate, never a medical approval or TTS call.
FALLBACK_CHARACTERS_PER_SECOND = 16.39181649101054
VOICE_PROFILE_PATH = Path(__file__).resolve().parents[3] / 'profiles/voice.yaml'


def estimate_line_ms(script: Script, project_dir: Path, *,
                     voice_profile: dict | None = None) -> dict[str, int]:
    """Character-based estimates calibrated only on verified, matching cache receipts.

    No provider is instantiated. Legacy SHA-only receipts cannot establish voice
    or text provenance and are deliberately excluded from calibration.
    """
    from healthvideo.tts.pronunciation import (
        PRONUNCIATION_PROFILE_PATH,
        apply_pronunciation,
        load_pronunciation_lexicon,
    )

    profile = voice_profile if voice_profile is not None else read_yaml(VOICE_PROFILE_PATH)
    settings = profile.get('settings', {})
    runtime = 'rest-' + hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:24]
    characters, seconds = 0, 0.0
    for receipt in sorted((project_dir / 'cache/tts').glob('*.json')):
        try:
            data = read_yaml(receipt)
            provider, request = data['provider'], data['request']
            if any(provider.get(k) != profile.get(k) for k in ('provider', 'voice_id', 'model_id')):
                continue
            if provider.get('runtime_id') != runtime and provider.get('settings') != settings:
                continue
            # Request speed is additional to the voice profile's speed.
            if request.get('speed', 1.0) != 1.0 or request.get('language') != script.language:
                continue
            if canonical_json_hash({'request': request, 'provider': provider}) != receipt.stem:
                continue
            wav = receipt.with_suffix('.wav')
            if data['sha256'] != sha256_file(wav):
                continue
            with wave.open(str(wav), 'rb') as source:
                duration = source.getnframes() / source.getframerate()
            text = request['text']
            if isinstance(text, str) and text.strip() and duration > 0:
                characters += len(text)
                seconds += duration
        except (OSError, ValueError, TypeError, KeyError, AttributeError, EOFError, wave.Error):
            continue
    rate = characters / seconds if characters and seconds else FALLBACK_CHARACTERS_PER_SECOND
    lexicon = load_pronunciation_lexicon(PRONUNCIATION_PROFILE_PATH)
    if len({line.id for line in script.lines}) != len(script.lines):
        raise ValueError('Script line IDs must be unique for estimated timing')
    return {line.id: max(1, math.ceil(1000 * len(apply_pronunciation(
        line.tts_text(expressive=profile.get('provider') == 'elevenlabs'), lexicon,
    )) / rate)) for line in script.lines}


def _integer(value: object, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _groups(board: Storyboard, lines: Mapping) -> list[tuple[Scene, ...]]:
    groups: list[tuple[Scene, ...]] = []
    seen: set[str] = set()
    ids: set[str] = set()
    for scene in board.scenes:
        if scene.id in ids:
            raise ValueError(f"Duplicate scene id {scene.id}")
        ids.add(scene.id)
        line = scene.script_line_id
        if line is not None and groups and groups[-1][0].script_line_id == line:
            groups[-1] += (scene,)
            continue
        if line is not None:
            if line not in lines:
                raise ValueError(f"Scene {scene.id}: unknown script line {line}")
            if line in seen:
                raise ValueError(f"Scene {scene.id}: nonconsecutive script line {line}")
            seen.add(line)
        groups.append((scene,))
    if set(lines) != seen:
        raise ValueError("All provided script lines must be referenced by the storyboard")
    return groups


def _split(total: int, weights: list[int]) -> list[int]:
    """Largest remainder apportionment, with a minimum of one frame per scene."""
    total = max(total, len(weights))
    result = [max(1, total * weight // sum(weights)) for weight in weights]
    while sum(result) < total:
        index = max(range(len(weights)), key=lambda i: (
            total * weights[i] - result[i] * sum(weights), -i))
        result[index] += 1
    while sum(result) > total:
        index = min((i for i in range(len(weights)) if result[i] > 1), key=lambda i: (
            total * weights[i] - result[i] * sum(weights), i))
        result[index] -= 1
    return result


def retime_storyboard(
    board: Storyboard, line_ms: Mapping[str, int], fps: int = 30,
    pad_frames: int = PAD_FRAMES,
) -> tuple[Storyboard, dict]:
    """Derive contiguous runtime timing without changing approved scene content."""
    _integer(fps, "fps", 1)
    _integer(pad_frames, "pad_frames")
    for line, duration in line_ms.items():
        _integer(duration, f"audio_ms for {line}", 1)
    scenes: list[Scene] = []
    rows: list[dict] = []
    start = 0
    for group in _groups(board, line_ms):
        line = group[0].script_line_id
        audio_ms = line_ms[line] if line is not None else 0
        durations = (
            _split((audio_ms * fps + 999) // 1000 + pad_frames,
                   [s.duration_frames for s in group])
            if line is not None else [group[0].duration_frames]
        )
        speech_durations = (
            _split((audio_ms * fps + 999) // 1000,
                   [s.duration_frames for s in group])
            if line is not None else [0]
        )
        for scene, duration, speech_duration in zip(
            group, durations, speech_durations, strict=True,
        ):
            scenes.append(scene.model_copy(update={
                "start_frame": start, "duration_frames": duration,
            }))
            rows.append({
                "scene_id": scene.id, "script_line_id": line,
                "storyboard_start_frame": scene.start_frame,
                "storyboard_duration_frames": scene.duration_frames,
                "audio_ms": audio_ms, "start_frame": start,
                "duration_frames": duration,
            })
            start += duration
    return board.model_copy(update={"scenes": tuple(scenes)}), {
        "schema_version": "1.0", "fps": fps, "pad_frames": pad_frames, "scenes": rows,
    }


def restore_timed_storyboard(approved: Storyboard, record: dict) -> Storyboard:
    """Recompute, then compare every timing field against the approved content."""
    try:
        fps = _integer(record["fps"], "fps", 1)
        pad = _integer(record["pad_frames"], "pad_frames")
        line_ms: dict[str, int] = {}
        for row in record["scenes"]:
            for field in ("storyboard_start_frame", "storyboard_duration_frames",
                          "audio_ms", "start_frame", "duration_frames"):
                _integer(row[field], field, 1 if field.endswith("duration_frames") else 0)
            line = row["script_line_id"]
            if line is not None:
                duration = _integer(row["audio_ms"], "audio_ms", 1)
                if line in line_ms and line_ms[line] != duration:
                    raise ValueError("Shared line audio_ms differs")
                line_ms[line] = duration
        board, expected = retime_storyboard(approved, line_ms, fps, pad)
        pure = {k: v for k, v in record.items() if k != "audio_alignment"}
        if pure != expected:
            raise ValueError("Timing record does not match the approved storyboard")
        if "audio_alignment" in record:
            alignment = record["audio_alignment"]
            if not isinstance(alignment, list) or len(alignment) != len(board.scenes):
                raise ValueError("Invalid audio alignment scene count")
            expected_speech: dict[str, int | None] = {}
            for group in _groups(board, line_ms):
                line = group[0].script_line_id
                speech_end = (group[0].start_frame * 1000 / fps + line_ms[line]
                              if line is not None else None)
                for scene in group:
                    expected_speech[scene.id] = (
                        round(min((scene.start_frame + scene.duration_frames) * 1000 / fps,
                                  speech_end))
                        if speech_end is not None and speech_end > scene.start_frame * 1000 / fps
                        else None
                    )
            for scene, row in zip(board.scenes, alignment, strict=True):
                base_fields = {"scene_id", "audio_start_ms", "video_start_ms"}
                if set(row) not in (base_fields, base_fields | {"speech_end_ms"}):
                    raise ValueError("Invalid audio alignment fields")
                _integer(row["audio_start_ms"], "audio_start_ms")
                _integer(row["video_start_ms"], "video_start_ms")
                if (row["scene_id"] != scene.id or row["video_start_ms"] !=
                        round(scene.start_frame * 1000 / fps)):
                    raise ValueError("Audio alignment does not match scene")
                if "speech_end_ms" in row:
                    actual, expected_end = row["speech_end_ms"], expected_speech[scene.id]
                    if actual is not None:
                        _integer(actual, "speech_end_ms")
                    if ((actual is None) != (expected_end is None) or
                            (actual is not None and abs(actual - expected_end) > 1)):
                        raise ValueError("Audio speech end does not match measured line timing")
        return board
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("Invalid timing record") from error


def concat_scene_audio(
    board: Storyboard, line_wavs: Mapping[str, Path], output: Path, fps: int = 30,
    *, source_board: Storyboard | None = None,
) -> list[dict]:
    """Concatenate speech once per group, padding at global PCM sample boundaries.

    Unreferenced WAVs, repeated nonconsecutive speech, parameter mismatches, and
    speech exceeding its visual group are errors. No speech samples are dropped.
    With no speech inputs, silence uses mono 48 kHz signed 16-bit PCM. A clip
    may provide ``source_board`` to select and reorder original scene segments
    from shared speech, without repeating the full line or synthesizing again.
    """
    _integer(fps, "fps", 1)
    source_segments: dict[str, tuple[Scene, int]] = {}
    if source_board is None:
        groups = _groups(board, line_wavs)
    else:
        source_lines = {s.script_line_id: None for s in source_board.scenes
                        if s.script_line_id is not None}
        source_groups = _groups(source_board, source_lines)
        selected_lines = {s.script_line_id for s in board.scenes
                          if s.script_line_id is not None}
        if not selected_lines <= set(line_wavs) or not set(line_wavs) <= set(source_lines):
            raise ValueError("Clip WAV mappings must cover selected source lines")
        for group in source_groups:
            for scene in group:
                source_segments[scene.id] = (scene, group[0].start_frame)
        if len({s.id for s in board.scenes}) != len(board.scenes):
            raise ValueError("Clip cannot repeat a source scene")
        groups = [(scene,) for scene in board.scenes]
    start = 0
    for scene in board.scenes:
        _integer(scene.start_frame, "start_frame")
        _integer(scene.duration_frames, "duration_frames", 1)
        if scene.start_frame != start:
            raise ValueError(f"Scene {scene.id}: timing must be contiguous")
        start += scene.duration_frames
    params = None
    payloads: dict[str, bytes] = {}
    for line, path in line_wavs.items():
        try:
            with wave.open(str(path), "rb") as source:
                current = (source.getnchannels(), source.getsampwidth(),
                           source.getframerate(), source.getcomptype())
                if params is not None and params != current:
                    raise ValueError("All WAV parameters must match")
                params = current
                data = source.readframes(source.getnframes())
                if source.getnframes() == 0:
                    raise ValueError(f"WAV for {line} is empty")
                if len(data) != source.getnframes() * current[0] * current[1]:
                    raise ValueError(f"WAV for {line} is truncated")
                payloads[line] = data
        except (OSError, EOFError, wave.Error) as error:
            raise ValueError(f"Unreadable WAV for {line}") from error
    channels, width, rate, compression = params or (1, 2, 48000, "NONE")
    if compression != "NONE":
        raise ValueError("Only PCM WAV is supported")
    sample_bytes = channels * width
    silence = (b"\x80" if width == 1 else b"\0" * width) * channels
    if source_board is not None:
        for source_group in source_groups:
            line = source_group[0].script_line_id
            if line not in payloads:
                continue
            first, last = source_group[0], source_group[-1]
            capacity = (round((last.start_frame + last.duration_frames) * rate / fps)
                        - round(first.start_frame * rate / fps))
            if len(payloads[line]) // sample_bytes > capacity:
                raise ValueError(f"Scene {first.id}: speech cannot fit source timing")
    chunks: list[bytes] = []
    alignment: list[dict] = []
    for group in groups:
        first, last = group[0], group[-1]
        begin = round(first.start_frame * rate / fps)
        end = round((last.start_frame + last.duration_frames) * rate / fps)
        line = first.script_line_id
        if source_board is not None and line is not None:
            if first.id not in source_segments:
                raise ValueError(f"Scene {first.id}: missing source scene")
            source_scene, group_start = source_segments[first.id]
            if (source_scene.script_line_id != line or
                    source_scene.duration_frames != first.duration_frames):
                raise ValueError(f"Scene {first.id}: does not match source timing")
            origin = round(group_start * rate / fps)
            offset = round(source_scene.start_frame * rate / fps) - origin
            limit = round((source_scene.start_frame + source_scene.duration_frames)
                          * rate / fps) - origin
            data = payloads[line][offset * sample_bytes:limit * sample_bytes]
        else:
            data = payloads[line] if line is not None else b""
        count = len(data) // sample_bytes
        if count > end - begin:
            raise ValueError(f"Scene {first.id}: speech cannot fit visual timing")
        chunks.append(data + silence * (end - begin - count))
        speech_end = begin + count
        for scene in group:
            scene_begin = round(scene.start_frame * rate / fps)
            scene_end = round((scene.start_frame + scene.duration_frames) * rate / fps)
            alignment.append({
                "scene_id": scene.id,
                "audio_start_ms": round(scene_begin * 1000 / rate),
                "video_start_ms": round(scene.start_frame * 1000 / fps),
                "speech_end_ms": (round(min(scene_end, speech_end) * 1000 / rate)
                                  if count and speech_end > scene_begin else None),
            })
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as target:
        target.setparams((channels, width, rate, 0, "NONE", "not compressed"))
        for chunk in chunks:
            target.writeframes(chunk)
    return alignment
