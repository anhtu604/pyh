import copy
import wave
from pathlib import Path

import pytest

from healthvideo.domain.storyboard import Scene, Storyboard
from healthvideo.render.input import audio_timing_qa
from healthvideo.render.timing import (
    concat_scene_audio,
    restore_timed_storyboard,
    retime_storyboard,
)
from healthvideo.tts.audio_checks import inspect_wav


def board(*lines: str | None, durations=None, profile="explain_first_v1", visuals=None):
    durations = durations or [60] * len(lines)
    return Storyboard(title="Timing", visual_budget_profile=profile, scenes=tuple(
        Scene(id=f"S{i}", start_frame=i * 60, duration_frames=duration,
              narration="approved", script_line_id=line,
              visual=(visuals or ["whiteboard"] * len(lines))[i])
        for i, (line, duration) in enumerate(zip(lines, durations, strict=True))
    ))


def wav(path: Path, samples: int, *, rate=1000, width=2, value=1):
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, width, rate, 0, "NONE", "not compressed"))
        stream.writeframes(value.to_bytes(width, "little") * samples)
    return path


def test_retime_preserves_editorial_content_and_silent_duration():
    approved = board("L1", None, "L2", durations=[100, 50, 90])
    timed, record = retime_storyboard(approved, {"L1": 2001, "L2": 1000})
    assert [s.duration_frames for s in timed.scenes] == [70, 50, 39]
    assert [s.start_frame for s in timed.scenes] == [0, 70, 120]
    assert approved.scenes[0].duration_frames == 100
    for original, runtime in zip(approved.scenes, timed.scenes, strict=True):
        assert runtime.model_dump(exclude={"start_frame", "duration_frames"}) == (
            original.model_dump(exclude={"start_frame", "duration_frames"}))
    assert record["schema_version"] == "1.0"
    assert record["scenes"][0]["storyboard_duration_frames"] == 100
    assert restore_timed_storyboard(approved, record) == timed


def test_shared_line_split_once_and_each_scene_positive():
    timed, record = retime_storyboard(board("L", "L", durations=[30, 90]), {"L": 1000})
    assert [s.duration_frames for s in timed.scenes] == [10, 29]
    assert [s["audio_ms"] for s in record["scenes"]] == [1000, 1000]
    tiny, _ = retime_storyboard(board("L", "L", durations=[1, 999]), {"L": 1}, pad_frames=0)
    assert [s.duration_frames for s in tiny.scenes] == [1, 1]


@pytest.mark.parametrize("lines,mapping", [
    (("missing",), {"L": 1000}),
    (("L",), {"L": 1000, "extra": 1000}),
    (("L", None, "L"), {"L": 1000}),
])
def test_reference_failures(lines, mapping):
    with pytest.raises(ValueError):
        retime_storyboard(board(*lines), mapping)


def test_fixed_ai_clip_keeps_duration_and_rejects_overflow():
    approved = board("L", durations=[120], profile="m6_5_v1", visuals=["ai_clip"])
    timed, _ = retime_storyboard(approved, {"L": 1000})
    assert timed.scenes[0].duration_frames == 120
    with pytest.raises(ValueError, match="S0"):
        retime_storyboard(approved, {"L": 5000})


@pytest.mark.parametrize("field,value", [("start_frame", 8), ("audio_ms", 2000),
                                        ("storyboard_duration_frames", 99)])
def test_restore_rejects_tampering(field, value):
    approved = board("L")
    _, record = retime_storyboard(approved, {"L": 1000})
    record["scenes"][0][field] = value
    with pytest.raises(ValueError):
        restore_timed_storyboard(approved, record)


def test_restore_allows_alignment_but_checks_identity():
    approved = board("L")
    timed, record = retime_storyboard(approved, {"L": 1000})
    record["audio_alignment"] = [{"scene_id": "S0", "audio_start_ms": 200,
                                  "video_start_ms": 0}]
    assert restore_timed_storyboard(approved, record) == timed
    bad = copy.deepcopy(record)
    bad["audio_alignment"][0]["scene_id"] = "OTHER"
    with pytest.raises(ValueError):
        restore_timed_storyboard(approved, bad)


def test_concat_shared_audio_continuous_with_silent_scene(tmp_path):
    timed, _ = retime_storyboard(board(None, "L", "L", durations=[10, 30, 90]),
                                {"L": 1000})
    source = wav(tmp_path / "line.wav", 1000)
    output = tmp_path / "combined.wav"
    alignment = concat_scene_audio(timed, {"L": source}, output)
    with wave.open(str(output), "rb") as stream:
        raw = stream.readframes(stream.getnframes())
        assert stream.getnframes() == round(49 * 1000 / 30)
    assert raw[:666] == b"\0" * 666
    assert raw[666:2666] == b"\x01\0" * 1000
    assert raw[2666:] == b"\0" * (len(raw) - 2666)
    assert alignment[1] == {"scene_id": "S1", "audio_start_ms": 333,
                            "video_start_ms": 333, "speech_end_ms": 667}
    assert alignment[0]["speech_end_ms"] is None
    assert alignment[2]["speech_end_ms"] == 1333


def test_restore_refuses_spoofed_speech_end():
    approved = board("L", None, durations=[30, 300])
    _, record = retime_storyboard(approved, {"L": 1000})
    record["audio_alignment"] = [
        {"scene_id": "S0", "audio_start_ms": 0, "video_start_ms": 0, "speech_end_ms": 1000},
        {"scene_id": "S1", "audio_start_ms": 1300, "video_start_ms": 1300, "speech_end_ms": 11300},
    ]
    with pytest.raises(ValueError, match="speech"):
        restore_timed_storyboard(approved, record)


@pytest.mark.parametrize("fixed_ai", [False, True])
def test_padded_terminal_silence_is_rejected_for_unvoiced_and_fixed_ai_scenes(tmp_path, fixed_ai):
    approved = (board("L", durations=[240], profile="m6_5_v1", visuals=["ai_clip"])
                if fixed_ai else board("L", None, durations=[30, 300]))
    timed, record = retime_storyboard(approved, {"L": 1000})
    source = wav(tmp_path / "line.wav", 24000, rate=24000)
    output = tmp_path / "combined.wav"
    record["audio_alignment"] = concat_scene_audio(timed, {"L": source}, output)
    assert restore_timed_storyboard(approved, record) == timed
    with pytest.raises(ValueError, match="trailing visual silence"):
        audio_timing_qa(inspect_wav(output).duration_ms,
                        sum(s.duration_frames for s in timed.scenes), timing_record=record)


def test_normal_measured_speech_breathing_pad_is_reported(tmp_path):
    approved = board("L")
    timed, record = retime_storyboard(approved, {"L": 1000})
    source = wav(tmp_path / "line.wav", 24000, rate=24000)
    output = tmp_path / "combined.wav"
    record["audio_alignment"] = concat_scene_audio(timed, {"L": source}, output)
    assert restore_timed_storyboard(approved, record) == timed
    assert audio_timing_qa(inspect_wav(output).duration_ms, 39,
                           timing_record=record)["trailing_visual_ms"] == 300


def test_concat_refuses_truncation_and_mismatched_parameters(tmp_path):
    short = board("L", durations=[1])
    a = wav(tmp_path / "a.wav", 1000)
    with pytest.raises(ValueError, match="fit"):
        concat_scene_audio(short, {"L": a}, tmp_path / "out.wav")
    b = wav(tmp_path / "b.wav", 10, rate=2000)
    with pytest.raises(ValueError, match="parameters"):
        concat_scene_audio(board("L", "M"), {"L": a, "M": b}, tmp_path / "out.wav")


def test_concat_unsigned_8bit_silence_and_global_sample_rounding(tmp_path):
    timed = board(None, "L", None, durations=[1, 1, 1])
    source = wav(tmp_path / "u8.wav", 1, rate=100, width=1, value=129)
    output = tmp_path / "out.wav"
    concat_scene_audio(timed.model_copy(update={"scenes": tuple(
        s.model_copy(update={"start_frame": i}) for i, s in enumerate(timed.scenes)
    )}), {"L": source}, output)
    with wave.open(str(output), "rb") as stream:
        assert stream.getnframes() == 10
        assert stream.readframes(10) == b"\x80" * 3 + b"\x81" + b"\x80" * 6


@pytest.mark.parametrize("duration", [120, 180, 240])
def test_fixed_clip_supports_all_approved_lengths(duration):
    approved = board("L", durations=[duration], profile="m6_5_v1", visuals=["ai_clip"])
    runtime, record = retime_storyboard(approved, {"L": 1000})
    assert runtime.scenes[0].duration_frames == duration
    assert restore_timed_storyboard(approved, record) == runtime


@pytest.mark.parametrize("duration,audio_ms", [(120, 4000), (180, 6000), (240, 8000)])
def test_fixed_clip_accepts_speech_that_exactly_fits_without_padding(duration, audio_ms):
    approved = board("L", durations=[duration], profile="m6_5_v1", visuals=["ai_clip"])
    runtime, record = retime_storyboard(approved, {"L": audio_ms})
    assert runtime.scenes[0].duration_frames == duration
    assert restore_timed_storyboard(approved, record) == runtime


@pytest.mark.parametrize("mapping,fps,pad", [({"L": -1}, 30, 9),
    ({"L": True}, 30, 9), ({"L": 1.5}, 30, 9),
    ({"L": 100}, 0, 9), ({"L": 100}, 30, -1)])
def test_retime_rejects_invalid_numeric_inputs(mapping, fps, pad):
    with pytest.raises(ValueError):
        retime_storyboard(board("L"), mapping, fps=fps, pad_frames=pad)


def test_restoration_numeric_fields_are_strict_integers():
    approved = board("L")
    _, record = retime_storyboard(approved, {"L": 1000})
    record["scenes"][0]["start_frame"] = False
    with pytest.raises(ValueError):
        restore_timed_storyboard(approved, record)


def test_concat_rounding_does_not_accumulate_across_many_scenes(tmp_path):
    approved = board(*([None] * 100), durations=[1] * 100)
    timed, _ = retime_storyboard(approved, {})
    output = tmp_path / "silent.wav"
    alignment = concat_scene_audio(timed, {}, output)
    with wave.open(str(output), "rb") as source:
        assert source.getnframes() == 160000
    assert alignment[-1]["audio_start_ms"] == 3300


def test_concat_reference_contract_and_empty_wav(tmp_path):
    source = wav(tmp_path / "source.wav", 10)
    for approved, sources in [(board("L"), {}),
                              (board("L", None, "L"), {"L": source}),
                              (board(None), {"L": source})]:
        with pytest.raises(ValueError):
            concat_scene_audio(approved, sources, tmp_path / "out.wav")
    empty = wav(tmp_path / "empty.wav", 0)
    with pytest.raises(ValueError, match="empty"):
        concat_scene_audio(board("L"), {"L": empty}, tmp_path / "out.wav")


def test_concat_clip_reuses_partial_shared_line_and_reordered_pcm(tmp_path):
    source_board, _ = retime_storyboard(
        board("L", "L", durations=[10, 20]), {"L": 1000}, pad_frames=0)
    source = tmp_path / "line.wav"
    with wave.open(str(source), "wb") as stream:
        stream.setparams((1, 2, 1000, 0, "NONE", "not compressed"))
        stream.writeframes(b"\x01\0" * 333 + b"\x02\0" * 667)
    second = source_board.scenes[1].model_copy(update={"start_frame": 0})
    partial = source_board.model_copy(update={"scenes": (second,)})
    output = tmp_path / "partial.wav"
    concat_scene_audio(partial, {"L": source}, output, source_board=source_board)
    with wave.open(str(output), "rb") as stream:
        assert stream.readframes(stream.getnframes()) == b"\x02\0" * 667
    reordered = source_board.model_copy(update={"scenes": (
        second, source_board.scenes[0].model_copy(update={"start_frame": 20}),
    )})
    concat_scene_audio(reordered, {"L": source}, output, source_board=source_board)
    with wave.open(str(output), "rb") as stream:
        assert stream.readframes(stream.getnframes()) == (
            b"\x02\0" * 667 + b"\x01\0" * 333)


def test_concat_source_board_checks_source_identity_and_allows_new_silence(tmp_path):
    source_board, _ = retime_storyboard(board("L", "M"), {"L": 100, "M": 100})
    source = wav(tmp_path / "source.wav", 100)
    selected = source_board.scenes[0]
    silent = Scene(id="CTA", start_frame=selected.duration_frames,
                   duration_frames=3, narration="", visual="whiteboard")
    clip = source_board.model_copy(update={"scenes": (selected, silent)})
    concat_scene_audio(clip, {"L": source}, tmp_path / "out.wav", source_board=source_board)
    bad = clip.model_copy(update={"scenes": (
        selected.model_copy(update={"id": "unknown"}), silent,
    )})
    with pytest.raises(ValueError, match="source"):
        concat_scene_audio(bad, {"L": source}, tmp_path / "out.wav", source_board=source_board)
    oversized = wav(tmp_path / "oversized.wav", 1000)
    with pytest.raises(ValueError, match="fit"):
        concat_scene_audio(clip, {"L": oversized}, tmp_path / "out.wav", source_board=source_board)
