import json
import shutil
import subprocess

import pytest

from healthvideo.render import motion_report as motion


def timing(*rows):
    return {"fps": 30, "scenes": [
        {"scene_id": sid, "start_frame": start * 30, "duration_frames": duration * 30}
        for sid, start, duration in rows
    ]}


def test_static_runs_include_first_interval_and_flush_tail():
    assert motion.find_static_runs([0.1, 0.6, 4, 0, 0]) == [
        {"start_s": 0.0, "end_s": 1.0, "duration_s": 1.0},
        {"start_s": 1.5, "end_s": 2.5, "duration_s": 1.0},
    ]
    assert motion.find_static_runs([]) == []
    assert motion.find_static_runs([2, 3]) == []


@pytest.mark.parametrize("differences,kwargs", [
    ([float("nan")], {}), ([-1], {}), ([256], {}),
    ([0], {"sample_interval_s": 0}), ([0], {"threshold": -1}),
])
def test_invalid_measurements_are_rejected(differences, kwargs):
    with pytest.raises(ValueError):
        motion.find_static_runs(differences, **kwargs)


def test_report_maps_overlaps_and_applies_each_scene_limit():
    report = motion.build_motion_report(
        [0] * 36, timing(("S01", 0, 7), ("S02", 7, 11)),
        {"S01": "whiteboard", "S02": "chart"}, video_sha256="a" * 64,
    )
    assert report["static_runs"][0]["scene_ids"] == ["S01", "S02"]
    assert report["static_runs"][0]["visual"] == {"S01": "whiteboard", "S02": "chart"}
    assert report["scenes_with_violation"] == ["S01", "S02"]
    assert report["max_static_s"] == 18
    assert not report["passed"]
    assert json.loads(json.dumps(report)) == report
    assert report["schema_version"] == "1.0"


@pytest.mark.parametrize("visual,limit", [
    ("source_card", 10), ("evidence_highlight", 10), ("chart", 10),
    ("stat_gauge", 10), ("process_animation", 6),
])
def test_limits_are_strict_and_only_measure_overlap(visual, limit):
    report = motion.build_motion_report(
        [0] * (limit * 4), timing(("A", 0, limit), ("B", limit, limit)),
        {"A": visual, "B": visual}, video_sha256="test",
    )
    assert report["passed"]
    report = motion.build_motion_report(
        [0] * (limit * 2 + 1), timing(("A", 0, limit + 1)),
        {"A": visual}, video_sha256="test",
    )
    assert report["scenes_with_violation"] == ["A"]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_ffmpeg_pipe_reads_static_video_and_propagates_errors(tmp_path):
    video = tmp_path / "still.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=160x90:r=30:d=8",
        "-c:v", "libx264", "-y", str(video),
    ], check=True)
    report = motion.measure_video(video, timing(("S01", 0, 8)), {"S01": "whiteboard"})
    assert report["max_static_s"] == 7.5
    assert report["scenes_with_violation"] == ["S01"]
    assert len(report["video_sha256"]) == 64
    with pytest.raises(RuntimeError, match="ffmpeg"):
        motion.measure_video(tmp_path / "missing.mp4", timing(), {})
