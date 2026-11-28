import shutil
import subprocess
from pathlib import Path

import pytest

from healthvideo.render.frame_qa import measure_frame_qa, parse_frame_qa

BLACK_LOG = """+[Parsed_metadata_1 @ 000001cf9e45b900] lavfi.black_start=0
[Parsed_metadata_1 @ 000001cf9e45b900] lavfi.black_end=0.1
[Parsed_metadata_1 @ 000001cf9e45b900] lavfi.black_start=5
[Parsed_blackdetect_0 @ 000001cf9e45af40] black_start:5 black_end:5.6 black_duration:0.6
[Parsed_metadata_1 @ 000001cf9e45b900] lavfi.black_end=5.6
out_time_us=20000000
progress=end
"""
FREEZE_LOG = """+[Parsed_freezedetect_0 @ 00000258855a4c80] lavfi.freezedetect.freeze_start: 7
[Parsed_freezedetect_0 @ 00000258855a4c80] lavfi.freezedetect.freeze_duration: 7
[Parsed_freezedetect_0 @ 00000258855a4c80] lavfi.freezedetect.freeze_end: 14
"""
SILENCE_LOG = """+[silencedetect @ 00000258855a4c80] silence_start: 12
[silencedetect @ 00000258855a4c80] silence_end: 15 | silence_duration: 3
out_time_us=20000000
progress=end
"""
LOUDNESS_LOG = """+[Parsed_ebur128_0 @ 000001d669683140] Summary:

  Integrated loudness:
    I:         -14.1 LUFS
    Threshold: -24.1 LUFS

  Loudness range:
    LRA:         0.0 LU

  True peak:
    Peak:       -0.2 dBFS
"""


def test_parse_ffmpeg_logs_and_apply_thresholds() -> None:
    report = parse_frame_qa(BLACK_LOG, FREEZE_LOG, SILENCE_LOG, LOUDNESS_LOG)
    assert report["black"] == [[0, 0.1], [5, 5.6]]
    assert report["freeze"] == [[7, 14]]
    assert report["silence"] == [[12, 15]]
    assert report["integrated_lufs"] == -14.1
    assert report["true_peak_db"] == -0.2
    assert [(i["severity"], i["kind"], i["at"]) for i in report["issues"]] == [
        ("block", "black", [5, 5.6]),
        ("warn", "freeze", [7, 14]),
        ("block", "silence", [12, 15]),
        ("block", "true_peak", [0, 20]),
    ]


def test_black_edges_count_only_time_outside_the_allowance() -> None:
    report = parse_frame_qa(
        "lavfi.black_start=0\nlavfi.black_end=0.8\nlavfi.black_start=19.3\nout_time_us=20000000\n",
        "",
        SILENCE_LOG,
        LOUDNESS_LOG,
    )
    assert report["black"] == [[0, 0.8], [19.3, 20]]
    assert [i["at"] for i in report["issues"] if i["kind"] == "black"] == [[0.3, 0.8]]


@pytest.mark.parametrize(("lufs", "warns"), [("-16.1", True), ("-16.0", False), ("-12.0", False), ("-11.9", True)])
def test_terminal_intervals_and_loudness_boundaries(lufs: str, warns: bool) -> None:
    report = parse_frame_qa(
        "lavfi.black_start=3.7\nout_time_us=4000000\n",
        "lavfi.freezedetect.freeze_start: 1",
        "silence_start: 1\nout_time_us=4000000\n",
        LOUDNESS_LOG.replace("-14.1", lufs).replace("-0.2", "-0.5"),
    )
    assert report["black"] == [[3.7, 4]]
    assert report["freeze"] == [[1, 4]]
    assert report["silence"] == [[1, 4]]
    assert [(i["severity"], i["kind"]) for i in report["issues"]] == [
        ("warn", "silence"),  # runs to the end: end screen, not a dropout
        *([("warn", "integrated_lufs")] if warns else []),
    ]


def test_measure_real_mp4(tmp_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("FFmpeg is not installed")
    path = tmp_path / "black.mp4"
    subprocess.run(
        [ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=black:s=64x64:r=30:d=4",
         "-f", "lavfi", "-i", "sine=frequency=1000:duration=4", "-c:v", "mpeg4", "-c:a", "aac", str(path)],
        check=True, capture_output=True, text=True,
    )
    report = measure_frame_qa(path, ffmpeg=ffmpeg)
    assert report["black"][0] == pytest.approx([0, 4], abs=0.04)
    assert report["freeze"][0] == pytest.approx([0, 4], abs=0.04)
    assert any(i["kind"] == "black" and i["severity"] == "block" for i in report["issues"])
    assert report["silence"] == []
    assert report["integrated_lufs"] is not None
    assert report["true_peak_db"] is not None


def test_short_freeze_is_not_reported_and_mid_video_silence_still_blocks() -> None:
    report = parse_frame_qa(
        "out_time_us=20000000\n",
        "lavfi.freezedetect.freeze_start: 2\nlavfi.freezedetect.freeze_end: 7\n",
        "silence_start: 4\nsilence_end: 8\nout_time_us=20000000\n",
        LOUDNESS_LOG.replace("-0.2", "-3"),
    )
    assert [(i["severity"], i["kind"]) for i in report["issues"]] == [("block", "silence")]
