import json

import pytest

from healthvideo.render import motion_report
from healthvideo.storage.files import sha256_file
from healthvideo.workflows import produce, product_review


@pytest.mark.parametrize("failed", [False, True])
def test_motion_qa_never_changes_status_and_promotes_evidence(tmp_path, monkeypatch, failed):
    run = tmp_path / "renders"
    run.mkdir()
    (run / "video.mp4").write_bytes(b"synthetic")
    produce._write_json_atomic(run / "video-qa.json", {"status": "render_complete"})
    produce._write_json_atomic(run / "scene-timing.json", {"scenes": []})
    report = {"passed": False, "max_static_s": 7, "scenes_with_violation": ["S01"],
              "video_sha256": sha256_file(run / "video.mp4"), "static_runs": [
                  {"scene_ids": ["S01"], "start_s": 0, "end_s": 7, "duration_s": 7}]}

    def measure(*args, **kwargs):
        if failed:
            raise RuntimeError("synthetic ffmpeg failure")
        return report

    monkeypatch.setattr(motion_report, "measure_video", measure)
    produce._record_motion_qa(run, {})
    qa = json.loads((run / "video-qa.json").read_text())
    assert qa["status"] == "render_complete"
    if failed:
        assert "synthetic ffmpeg failure" in qa["motion"]["error"]
        assert not (run / "motion-report.json").exists()
    else:
        assert qa["motion"] == {"passed": False, "max_static_s": 7, "violation_count": 1}
        produce._promote_motion_report(tmp_path)
        assert json.loads((tmp_path / "reviews/motion-report.json").read_text()) == report
        evidence = product_review._motion_evidence(tmp_path)
        assert "S01" in evidence and "0" in evidence and "7" in evidence
        (run / "video.mp4").write_bytes(b"changed")
        assert "stale" in product_review._motion_evidence(tmp_path)


def test_critic_incremental_packet_contains_measured_scene_times(tmp_path):
    from tests.workflows.test_product_review import REV, _project, _report

    project = _project(tmp_path)
    root = project / REV
    _report(project, score=6)
    product_review.record_review(project, product_review.render_hash(project))
    (root / "renders/video.mp4").write_bytes(b"synthetic")
    produce._write_json_atomic(root / "reviews/motion-report.json", {
        "video_sha256": sha256_file(root / "renders/video.mp4"),
        "passed": False, "max_static_s": 9.5, "scenes_with_violation": ["S01"],
        "static_runs": [{"scene_ids": ["S01"], "start_s": 4, "end_s": 13.5,
                         "duration_s": 9.5}],
    })
    packet = product_review.incremental_context(project)
    assert "motion-report.json" in packet
    assert '"scene_ids": ["S01"]' in packet
    assert '"start_s": 4' in packet and '"end_s": 13.5' in packet
