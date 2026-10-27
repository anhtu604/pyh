"""Unit tests for production retry classification, backoff, fingerprint and corrupt-record safety."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.storage.files import read_yaml
from healthvideo.workflows import production_retry
from healthvideo.workflows.production_retry import (
    clear_retry,
    production_fingerprint,
    record_failure,
    retry_status,
)


def _setup_project(root: Path, slug: str = "gout-test") -> Path:
    project = root / "projects" / slug
    (project / "revisions/001/storyboard").mkdir(parents=True, exist_ok=True)
    (project / "revisions/001/assets").mkdir(parents=True, exist_ok=True)
    (project / "revisions/001/reviews/visual").mkdir(parents=True, exist_ok=True)
    (project / "project.yaml").write_text("active_revision: '001'\n", encoding="utf-8")
    (project / "revisions/001/storyboard/storyboard.yaml").write_text("scenes: []\n", encoding="utf-8")
    (project / "revisions/001/assets/illustration.png").write_bytes(b"png-1")
    (project / "revisions/001/reviews/visual-review.yaml").write_text("status: pending\n", encoding="utf-8")
    (project / "revisions/001/reviews/visual/candidates.yaml").write_text("items: []\n", encoding="utf-8")
    return project


def test_validation_failure_blocks_immediately_until_input_changes(tmp_path: Path) -> None:
    project = _setup_project(tmp_path)
    state = WorkflowState.MEDICALLY_APPROVED

    initial = retry_status(tmp_path, project, state)
    assert initial == {
        "allowed": True,
        "kind": None,
        "attempts": 0,
        "reason": None,
        "retry_after": None,
    }

    record_failure(tmp_path, project, state, ValueError("visual budget failed: chart_crop"))
    retry_file = tmp_path / "topics/logs/gout-test/production-retry.yaml"
    assert retry_file.is_file()
    stored = read_yaml(retry_file)
    assert stored["kind"] == "validation"
    assert stored["attempts"] == 1
    assert stored["retry_after"] is None
    assert "visual budget failed" in stored["reason"]

    blocked = retry_status(tmp_path, project, state)
    assert blocked["allowed"] is False
    assert blocked["kind"] == "validation"
    assert blocked["attempts"] == 1

    # Modifying any tracked input changes the fingerprint and re-allows production.
    (project / "revisions/001/storyboard/storyboard.yaml").write_text("scenes: [changed]\n", encoding="utf-8")
    after_fix = retry_status(tmp_path, project, state)
    assert after_fix["allowed"] is True
    assert after_fix["attempts"] == 0


def test_transient_failures_backoff_120s_then_600s_and_cap_at_three_attempts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _setup_project(tmp_path)
    state = WorkflowState.MEDICALLY_APPROVED
    clock = {"now": datetime(2026, 10, 25, 12, 0, 0, tzinfo=UTC)}
    monkeypatch.setattr(production_retry, "_now", lambda: clock["now"])

    # Attempt 1 fails -> 120s backoff
    record_failure(tmp_path, project, state, OSError("network reset"))
    st1 = retry_status(tmp_path, project, state)
    assert st1["allowed"] is False
    assert st1["kind"] == "transient"
    assert st1["attempts"] == 1
    assert datetime.fromisoformat(st1["retry_after"]) == clock["now"] + timedelta(seconds=120)

    clock["now"] += timedelta(seconds=119)
    assert retry_status(tmp_path, project, state)["allowed"] is False

    clock["now"] += timedelta(seconds=1)
    assert retry_status(tmp_path, project, state)["allowed"] is True

    # Attempt 2 fails -> 600s backoff
    record_failure(tmp_path, project, state, RuntimeError("vibi HTTP 503"))
    st2 = retry_status(tmp_path, project, state)
    assert st2["allowed"] is False
    assert st2["kind"] == "transient"
    assert st2["attempts"] == 2
    assert datetime.fromisoformat(st2["retry_after"]) == clock["now"] + timedelta(seconds=600)

    clock["now"] += timedelta(seconds=599)
    assert retry_status(tmp_path, project, state)["allowed"] is False

    clock["now"] += timedelta(seconds=1)
    assert retry_status(tmp_path, project, state)["allowed"] is True

    # Attempt 3 fails -> permanently blocked for this fingerprint across restarts/time
    record_failure(tmp_path, project, state, RuntimeError("vibi synthesis timed out"))
    st3 = retry_status(tmp_path, project, state)
    assert st3["allowed"] is False
    assert st3["kind"] == "transient"
    assert st3["attempts"] == 3
    assert st3["retry_after"] is None

    clock["now"] += timedelta(days=7)
    assert retry_status(tmp_path, project, state)["allowed"] is False


def test_clear_retry_removes_only_retry_record_not_blocked_note(tmp_path: Path) -> None:
    project = _setup_project(tmp_path)
    state = WorkflowState.MEDICALLY_APPROVED
    blocked_note = tmp_path / "topics/logs/gout-test/blocked.txt"
    blocked_note.parent.mkdir(parents=True, exist_ok=True)
    blocked_note.write_text("other blocker\n", encoding="utf-8")

    record_failure(tmp_path, project, state, ValueError("bad input"))
    retry_file = tmp_path / "topics/logs/gout-test/production-retry.yaml"
    assert retry_file.is_file()

    clear_retry(tmp_path, "gout-test")
    assert not retry_file.exists()
    assert blocked_note.read_text(encoding="utf-8") == "other blocker\n"


@pytest.mark.parametrize(
    "corrupt_content",
    [
        ":::not-valid-yaml:::\n[",
        "- just\n- a\n- list\n",
        "fingerprint: abc\nkind: unknown\nattempts: 1\nreason: err\n",
        "fingerprint: ''\nkind: validation\nattempts: 0\nreason: err\n",
        "fingerprint: abc\nkind: transient\nattempts: 1\nreason: err\nretry_after: null\n",
    ],
)
def test_corrupt_retry_yaml_raises_and_never_allows_paid_calls(
    tmp_path: Path, corrupt_content: str
) -> None:
    project = _setup_project(tmp_path)
    state = WorkflowState.MEDICALLY_APPROVED
    retry_file = tmp_path / "topics/logs/gout-test/production-retry.yaml"
    retry_file.parent.mkdir(parents=True, exist_ok=True)
    retry_file.write_text(corrupt_content, encoding="utf-8")

    with pytest.raises(ValueError, match="production-retry.yaml"):
        retry_status(tmp_path, project, state)
    with pytest.raises(ValueError, match="production-retry.yaml"):
        record_failure(tmp_path, project, state, RuntimeError("new failure"))


def test_reason_sanitizes_secrets_and_fingerprint_tracks_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _setup_project(tmp_path)
    state = WorkflowState.MEDICALLY_APPROVED
    monkeypatch.setenv("VIBI_API_KEY", "super-secret-vibi-key")

    record_failure(
        tmp_path,
        project,
        state,
        RuntimeError("failed with super-secret-vibi-key and xi-api-key=inline-secret"),
    )
    status = retry_status(tmp_path, project, state)
    assert "super-secret-vibi-key" not in status["reason"]
    assert "inline-secret" not in status["reason"]

    fp0 = production_fingerprint(tmp_path, project, state)
    # Generated audio/renders/logs do not change the production fingerprint.
    (project / "revisions/001/renders").mkdir(parents=True, exist_ok=True)
    (project / "revisions/001/renders/video.mp4").write_bytes(b"mp4")
    (project / "revisions/001/audio").mkdir(parents=True, exist_ok=True)
    (project / "revisions/001/audio/tts-usage.json").write_text("{}", encoding="utf-8")
    assert production_fingerprint(tmp_path, project, state) == fp0

    # Asset bytes, visual-review, voice profile, and code changes each change the fingerprint.
    (project / "revisions/001/assets/illustration.png").write_bytes(b"png-2")
    fp1 = production_fingerprint(tmp_path, project, state)
    assert fp1 != fp0

    (project / "revisions/001/reviews/visual-review.yaml").write_text("status: done\n", encoding="utf-8")
    fp2 = production_fingerprint(tmp_path, project, state)
    assert fp2 != fp1

    voice = tmp_path / "profiles/voice.yaml"
    voice.parent.mkdir(parents=True, exist_ok=True)
    voice.write_text("voice_id: v2\n", encoding="utf-8")
    fp3 = production_fingerprint(tmp_path, project, state)
    assert fp3 != fp2

    code = tmp_path / "src/healthvideo/workflows/produce.py"
    code.parent.mkdir(parents=True, exist_ok=True)
    code.write_text("# code update\n", encoding="utf-8")
    fp4 = production_fingerprint(tmp_path, project, state)
    assert fp4 != fp3
