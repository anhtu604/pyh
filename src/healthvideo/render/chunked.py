"""R5 content-addressed, muted frame ranges with one continuous audio encode.

AAC per part introduces encoder priming at every join. Copy only the video
streams and encode the reviewed mixed WAV once, including its intentional tail.
The existing review/publish manifests and final output path stay unchanged.
"""

import json
import logging
import math
import os
import shutil
import subprocess
import time
import uuid
import wave
from collections.abc import Callable, Mapping
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from typing import Any

from healthvideo.render.chapters import ChapterSpan
from healthvideo.render.input import RenderInput
from healthvideo.render.remotion import (
    build_concat_argv,
    build_render_argv,
    chunk_renderer_identity,
)
from healthvideo.render.run import is_mp4_container
from healthvideo.storage.files import canonical_json_hash, sha256_file

logger = logging.getLogger(__name__)
ENCODING = ("--codec=h264", "--crf=18", "--pixel-format=yuv420p", "--x264-preset=medium")


def chunk_spans(value: RenderInput) -> tuple[ChapterSpan, ...]:
    """Exclusive internal ends; group adjacent chapters, otherwise use scene cuts."""
    spans: list[ChapterSpan] = []
    expected = 0
    use_chapters = all(scene.chapter_id for scene in value.scenes)
    for scene in value.scenes:
        if scene.start_frame != expected or scene.duration_frames <= 0:
            raise ValueError("Chunk scenes must be contiguous from frame zero")
        expected += scene.duration_frames
        name = scene.chapter_id if use_chapters else scene.id
        if use_chapters and spans and spans[-1].chapter_id == name:
            spans[-1] = ChapterSpan(name, spans[-1].start_frame, expected)
        else:
            spans.append(ChapterSpan(name, scene.start_frame, expected))
    if not spans or value.youtube_cta is not None:
        raise ValueError("Chunk render requires scenes and no vertical CTA")
    return tuple(spans)


def _paths(value: Any, public_dir: Path) -> set[str]:
    """Known media fields plus any existing file named by future input fields."""
    found: set[str] = set()
    if isinstance(value, dict):
        for name, item in value.items():
            if name in {"path", "image", "mascot_path", "logo_path"} and isinstance(item, str):
                found.add(item)
            elif name == "asset_paths":
                found.update(item)
            found.update(_paths(item, public_dir))
    elif isinstance(value, list):
        for item in value:
            found.update(_paths(item, public_dir))
    elif isinstance(value, str) and len(value) < 240:
        # Ignore arbitrary narration strings that cannot be filesystem paths.
        try:
            if (public_dir / value).is_file():
                found.add(value)
        except OSError:
            pass
    return found


def _audio_hash(audio: Path, span: ChapterSpan, fps: int) -> dict[str, Any]:
    """Hash actual mixed PCM, not global TTS receipts or the whole WAV header."""
    with wave.open(str(audio), "rb") as stream:
        rate = stream.getframerate()
        start = span.start_frame * rate // fps
        end = span.end_frame * rate // fps
        count = stream.getnframes()
        stream.setpos(min(start, count))
        pcm = stream.readframes(max(0, min(end, count) - start))
        return {"rate": rate, "channels": stream.getnchannels(),
                "sample_width": stream.getsampwidth(), "compression": stream.getcomptype(),
                "sha256": sha256(pcm).hexdigest()}


def _transition_context(scene: dict[str, Any] | None) -> Any:
    # sceneTransitionPlan's only cross-scene dependencies. Full render input is
    # still passed to Remotion; this is a fingerprint, not a retimed composition.
    if scene is None:
        return None
    return {"chapter_id": scene.get("chapter_id"), "visual": scene.get("visual"),
            "script_line_id": scene.get("script_line_id"),
            "subject": (scene.get("anatomy") or {}).get("subject"),
            "mascot": any(a.get("role") == "mascot" for a in scene.get("visual_assets", []))}


def chunk_key(data: dict[str, Any], span: ChapterSpan, public_dir: Path, audio: Path,
              renderer: Mapping[str, Any], parameters: Mapping[str, Any]) -> str:
    indices = [i for i, s in enumerate(data["scenes"])
               if span.start_frame <= s["start_frame"] < span.end_frame]
    # Bind the original timeline: Root derives composition duration globally,
    # and HealthVideo's Audio lives outside scene-local Sequences. Do not
    # assume every current/future renderer layer is invariant to a time shift.
    scenes = [data["scenes"][i] for i in indices]
    total_frames = max(s["start_frame"] + s["duration_frames"] for s in data["scenes"])
    total_frames += (data.get("youtube_cta") or {}).get("duration_frames", 0)
    paths = _paths(scenes, public_dir)
    # CreditCard with no explicit paths displays ALL revision asset metadata.
    all_credits = any(shot.get("component") == "CreditCard" and not shot.get("asset_paths")
                      for scene in scenes for shot in scene.get("resolved_shots", []))
    assets = [a for a in data.get("r5_assets", []) if all_credits or a["path"] in paths]
    paths.update(a["path"] for a in assets)
    hashes = {}
    for path in sorted(paths):
        target = (public_dir / path).resolve()
        if not target.is_relative_to(public_dir.resolve()):
            raise ValueError(f"Chunk asset outside public directory: {path}")
        hashes[path] = sha256_file(target)  # Missing files fail closed.
    context = [_transition_context(data["scenes"][indices[0] - 1]) if indices[0] else None,
               _transition_context(data["scenes"][indices[-1] + 1])
               if indices[-1] + 1 < len(data["scenes"]) else None]
    globals_ = {k: v for k, v in data.items() if k not in {"scenes", "r5_assets"}}
    return canonical_json_hash({"version": 2, "input": globals_, "scenes": scenes,
                                "context": context, "assets": assets, "files": hashes,
                                "frames": [span.start_frame, span.end_frame - 1],
                                "total_frames": total_frames,
                                "audio": _audio_hash(audio, span, data["fps"]),
                                "renderer": dict(renderer), "parameters": dict(parameters)})


def validate_media(path: Path, frames: int, fps: int, *, require_audio: bool = False) -> None:
    result = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_streams",
                             "-show_format", "-of", "json", str(path)],
                            capture_output=True, text=True, check=False, timeout=180)
    if result.returncode or result.stderr.strip():
        raise RuntimeError(f"ffprobe failed: {result.stderr.strip()}")
    try:
        streams = json.loads(result.stdout)["streams"]
        video = next(s for s in streams if s["codec_type"] == "video")
        duration = float(video["duration"])
        if (int(video["nb_read_frames"]) != frames
                or Fraction(video["r_frame_rate"]) != fps
                or not math.isfinite(duration) or abs(duration - frames / fps) > 1 / fps
                or abs(float(video.get("start_time", 0))) > 1 / fps):
            raise ValueError("video frame count/timing mismatch")
        if require_audio:
            audio = next(s for s in streams if s["codec_type"] == "audio")
            audio_duration = float(audio["duration"])
            if (not math.isfinite(audio_duration) or abs(audio_duration - duration) > 1 / fps
                    or abs(float(audio.get("start_time", 0))) > 1 / fps):
                raise ValueError("audio/video drift exceeds one frame")
    except (KeyError, ValueError, StopIteration, TypeError) as error:
        raise RuntimeError(f"Invalid chunk media {path}: {error}") from error


def _write_json(path: Path, payload: Any) -> None:
    temporary = path.with_name(f".{uuid.uuid4().hex[:12]}.partial.json")
    try:
        temporary.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _log(cache_dir: Path, message: str, *args: Any) -> None:
    # The CLI does not configure the root logger at INFO. Retain a local log
    # as well so reuse counts/timings are visible in unattended factory runs.
    with (cache_dir / "chunks.log").open("a", encoding="utf-8") as stream:
        stream.write(message % args + "\n")
    logger.info(message, *args)


def _reuse_previous_revision(part: Path, key: str, frames: int, fps: int, verify: bool) -> bool:
    """Import only verified completed parts from this project's older revisions."""
    revisions = part.parent.parent.parent
    if revisions.name != "revisions":
        return False
    current_revision = part.parent.parent.name
    for directory in sorted(revisions.iterdir(), reverse=True):
        if not directory.is_dir() or directory.name >= current_revision:
            continue
        source = directory / "render-chunks" / part.name
        temporary = part.with_name(f".{uuid.uuid4().hex[:12]}.partial.mp4")
        try:
            receipt = json.loads(source.with_suffix(".json").read_text(encoding="utf-8"))
            if receipt != {"key": key, "sha256": sha256_file(source)}:
                continue
            shutil.copyfile(source, temporary)
            if sha256_file(temporary) != receipt["sha256"]:
                continue
            if verify or is_mp4_container(temporary):
                validate_media(temporary, frames, fps)
            os.replace(temporary, part)
            _write_json(part.with_suffix(".json"), receipt)
            return True
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
            continue
        finally:
            temporary.unlink(missing_ok=True)
    return False


def render_chunked(
    *, render_input_path: Path, render_input: RenderInput, public_dir: Path,
    audio: Path, output: Path, cache_dir: Path, asset_hashes: Mapping[str, str],
    renderer_identity: Mapping[str, str], audio_identity: Mapping[str, object],
    runner: Callable[[list[str]], int], verify_media: bool = True,
) -> tuple[str, ...]:
    """Render sequentially under the caller's revision/GPU lock; atomically publish.

    ``verify_media=False`` supports injected stub runners only. Real MP4 files
    are always probed. Hashes are measured from files, never trusted receipts.
    PYH_RENDER_CHUNKS=0 provides the original single-render escape hatch.
    """
    if os.environ.get("PYH_RENDER_CHUNKS", "1").strip().lower() in {"0", "false", "off"}:
        if runner(build_render_argv(render_input_path, output, public_dir)) or not output.is_file():
            raise RuntimeError("Remotion render failed")
        return ()
    if render_input.quality_profile != "r5_v1" or (render_input.width, render_input.height) != (1920, 1080):
        raise ValueError("Chunk rendering requires R5 16:9 input")
    spans = chunk_spans(render_input)
    data = render_input.model_dump(mode="json")
    if json.loads(render_input_path.read_text(encoding="utf-8")) != data:
        raise ValueError("Chunk input file differs from render input")
    cache_dir.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Build once to stage fonts and resolve active bundle/GL options. These
    # primary flags are hashed for every part; the supplied workflow runner
    # retains its ANGLE -> SwiftShader/CPU retry policy on failure.
    template = build_render_argv(render_input_path, output, public_dir,
                                 muted=True, hardware_acceleration="disable",
                                 verify_public=True) + list(ENCODING)
    renderer = chunk_renderer_identity()
    renderer["declared"] = dict(renderer_identity)
    parameters = {"flags": [a for a in template if a.startswith("--") and "=" in a],
                  "fps": render_input.fps, "width": render_input.width, "height": render_input.height}
    rows = []
    parts = []
    reused = 0
    for span in spans:
        started = time.monotonic()
        key = chunk_key(data, span, public_dir, audio, renderer, parameters)
        part = cache_dir / f"{key}.mp4"
        receipt = part.with_suffix(".json")
        valid = False
        try:
            valid = json.loads(receipt.read_text(encoding="utf-8")) == {"key": key, "sha256": sha256_file(part)}
            if valid and (verify_media or is_mp4_container(part)):
                validate_media(part, span.end_frame - span.start_frame, render_input.fps)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
            valid = False
        if not valid:
            valid = _reuse_previous_revision(part, key, span.end_frame - span.start_frame,
                                             render_input.fps, verify_media)
        if not valid:
            part.unlink(missing_ok=True)
            receipt.unlink(missing_ok=True)
            temporary = part.with_name(f".{uuid.uuid4().hex[:12]}.partial.mp4")
            try:
                argv = build_render_argv(render_input_path, temporary, public_dir,
                    frames=(span.start_frame, span.end_frame - 1), muted=True,
                    hardware_acceleration="disable", verify_public=True) + list(ENCODING)
                if runner(argv) or not temporary.is_file() or not temporary.stat().st_size:
                    raise RuntimeError(f"Chunk {span.chapter_id} render failed")
                if verify_media or is_mp4_container(temporary):
                    validate_media(temporary, span.end_frame - span.start_frame, render_input.fps)
                digest = sha256_file(temporary)
                os.replace(temporary, part)
                _write_json(receipt, {"key": key, "sha256": digest})
            except BaseException:
                part.unlink(missing_ok=True)
                receipt.unlink(missing_ok=True)
                raise
            finally:
                temporary.unlink(missing_ok=True)
        else:
            reused += 1
        elapsed = time.monotonic() - started
        rows.append({"id": span.chapter_id, "start_frame": span.start_frame,
                     "end_frame": span.end_frame - 1, "key": key,
                     "sha256": sha256_file(part), "reused": valid, "seconds": elapsed})
        parts.append(part)
        # Keep completed parts discoverable even if a later chunk fails.
        _write_json(cache_dir / "chunks.json", {"chunks": rows})
        _log(cache_dir, "Chunk %s [%d,%d] %s seconds=%.3f", span.chapter_id,
                    span.start_frame, span.end_frame - 1, "reused" if valid else "rendered", elapsed)
    _log(cache_dir, "Chunks reused=%d rendered=%d", reused, len(spans) - reused)
    token = uuid.uuid4().hex
    listing = cache_dir / f".{token}.concat.txt"
    staged_output = output.with_name(f".{output.stem}.{token}.partial.mp4")
    try:
        listing.write_text("".join("file '" + p.resolve().as_posix().replace("'", "'\\''") + "'\n"
                                   for p in parts), encoding="utf-8")
        argv = build_concat_argv(listing, audio, staged_output)
        # Pad intentional visual tail, trim to the exact frame timeline. This
        # single encode avoids AAC priming/pops at every chapter boundary.
        argv[-1:-1] = ["-af", "apad", "-t", f"{spans[-1].end_frame / render_input.fps:.9f}"]
        if runner(argv) or not staged_output.is_file() or not staged_output.stat().st_size:
            raise RuntimeError("FFmpeg chunk concat failed")
        if verify_media or is_mp4_container(staged_output):
            validate_media(staged_output, spans[-1].end_frame, render_input.fps, require_audio=True)
        os.replace(staged_output, output)
    finally:
        listing.unlink(missing_ok=True)
        staged_output.unlink(missing_ok=True)
    return tuple(p.name for p in parts)
