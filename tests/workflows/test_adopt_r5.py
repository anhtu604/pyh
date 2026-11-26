"""Tests for R5.3.11a: adopting R5 on a project, staging licensed assets, and R5 prompt injection."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from healthvideo.approver_pin import PinError, set_pin
from healthvideo.cli import app
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.quality_standards import R5_COMPONENT_IDS
from healthvideo.domain.queue import QueueEntry
from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic
from healthvideo.storage.revisions import create_revision
from healthvideo.visuals.medanim_assets import copy_used_assets, load_asset_catalog
from healthvideo.workflows.adopt_r5 import adopt_r5_project, r5_active, stage_r5_assets
from healthvideo.workflows.dashboard import PinLimiter
from healthvideo.workflows.dashboard_operations import post_route
from healthvideo.workflows.factory_standards import pin_standards
from healthvideo.workflows.runner import RunDeps, _build_step_prompt, next_step

REPO_ROOT = Path(__file__).resolve().parents[2]
LIVER_CATALOG = REPO_ROOT / "library" / "medanim" / "liver-anatomy" / "assets.yaml"


def _seed_v2_project(
    root: Path,
    slug: str = "men-gan-tang",
    *,
    state: WorkflowState = WorkflowState.AWAITING_VIDEO_REVIEW,
    with_evidence: bool = True,
    with_approvals: bool = True,
    pin_r5: bool = False,
) -> Path:
    project_dir = root / "projects" / slug
    rev = project_dir / "revisions" / "001"
    for sub in ("topic", "evidence", "script", "storyboard", "assets", "reviews", "renders", "workflow"):
        (rev / sub).mkdir(parents=True, exist_ok=True)
    write_yaml_atomic(
        rev / "topic" / "card.yaml",
        {"slug": slug, "title": "Men gan tăng", "question": "Men gan tăng có nên uống thuốc bổ gan?"},
    )
    if with_evidence:
        write_yaml_atomic(rev / "evidence" / "ledger.yaml", {"claims": [{"id": "C01"}], "records": []})
    write_yaml_atomic(
        rev / "script" / "script.yaml",
        {
            "schema_version": "2.0",
            "lines": [{"id": "L01", "text": "Câu mẫu kiểm thử.", "claim_ids": ["C01"]}],
        },
    )
    if with_approvals:
        write_yaml_atomic(rev / "reviews" / "medical-approval.yaml", {"kind": "medical", "reviewer": "Dr"})
        write_yaml_atomic(rev / "reviews" / "video-approval.yaml", {"kind": "video", "reviewer": "Dr"})
    manifest = ProjectManifestV2(
        slug=slug,
        state=state,
        active_revision="001",
        artifact_hashes={"renders/video.mp4": "a" * 64},
    )
    write_yaml_atomic(project_dir / "project.yaml", manifest.model_dump(mode="json"))
    if pin_r5:
        pin_standards(root, project_dir, quality_profile="r5_v1")
    else:
        pin_standards(root, project_dir)
    return project_dir


def _minimal_run_deps(*, reject_note: str | None = None) -> RunDeps:
    return RunDeps(
        create_project=lambda root, entry: root / "projects" / entry.slug,
        read_state=lambda project_dir: WorkflowState.EVIDENCE_READY,
        reject_note=lambda project_dir: reject_note,
        python_steps={},
        changed_code_paths=lambda root: [],
    )


def test_liver_anatomy_library_catalog_valid_and_hashes_match(tmp_path: Path) -> None:
    records = load_asset_catalog(LIVER_CATALOG)
    assert len(records) == 5
    by_id = {record.id: record for record in records}
    assert set(by_id) == {
        "niaid-human-anatomy-519",
        "servier-digestive-system",
        "servier-liver-gallbladder",
        "servier-liver-lobule",
        "servier-bile-secretion",
    }
    assert by_id["niaid-human-anatomy-519"].license == "Public Domain"
    for record in records:
        if record.id != "niaid-human-anatomy-519":
            assert record.license == "CC BY 4.0"
        assert record.retrieved_at is None
        png_path = LIVER_CATALOG.parent / record.file
        assert png_path.is_file()
        assert sha256_file(png_path) == record.sha256

    copied = copy_used_assets(
        records,
        ["niaid-human-anatomy-519", "servier-liver-lobule"],
        LIVER_CATALOG.parent,
        tmp_path,
    )
    assert len(copied) == 2


def test_adopt_r5_requires_pin_and_does_not_mutate_on_failure(tmp_path: Path) -> None:
    project_dir = _seed_v2_project(tmp_path)
    pin_file = tmp_path / "approver-pin.json"

    with pytest.raises(PinError, match="Chưa đặt PIN"):
        adopt_r5_project(
            tmp_path, "men-gan-tang", reason="Chuyển sang R5", pin="123456", pin_file=pin_file
        )

    set_pin("654321", path=pin_file)
    with pytest.raises(PinError, match="PIN không đúng"):
        adopt_r5_project(
            tmp_path, "men-gan-tang", reason="Chuyển sang R5", pin="000000", pin_file=pin_file
        )

    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    assert manifest.active_revision == "001"
    assert not (project_dir / "revisions" / "002").exists()


def test_adopt_r5_creates_r5_revision_preserves_parent_and_resets_to_writer(tmp_path: Path) -> None:
    project_dir = _seed_v2_project(tmp_path)
    pin_file = tmp_path / "approver-pin.json"
    set_pin("654321", path=pin_file)

    rev1 = project_dir / "revisions" / "001"
    rev1_before = {
        p.relative_to(rev1).as_posix(): p.read_bytes()
        for p in sorted(rev1.rglob("*"))
        if p.is_file()
    }

    now = datetime(2026, 11, 24, 19, 0, tzinfo=UTC)
    result = adopt_r5_project(
        tmp_path,
        "men-gan-tang",
        reason="Hoàn thiện theo chuẩn R5",
        pin="654321",
        now=now,
        pin_file=pin_file,
    )

    assert result == {
        "ok": True,
        "slug": "men-gan-tang",
        "parent_revision": "001",
        "revision": "002",
        "state": "evidence_ready",
        "quality_profile": "r5_v1",
        "recovered": False,
    }

    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    assert manifest.active_revision == "002"
    assert manifest.state is WorkflowState.EVIDENCE_READY
    assert manifest.side_state is None
    assert manifest.artifact_hashes == {}
    assert next_step(manifest.state) == "draft"

    rev2 = project_dir / "revisions" / "002"
    assert r5_active(rev2) is True
    assert r5_active(rev1) is False
    assert (rev2 / "evidence" / "ledger.yaml").is_file()
    assert (rev2 / "script" / "script.yaml").is_file()
    assert not (rev2 / "reviews" / "medical-approval.yaml").exists()
    assert not (rev2 / "reviews" / "video-approval.yaml").exists()

    # Parent revision 001 is completely untouched byte-for-byte.
    rev1_after = {
        p.relative_to(rev1).as_posix(): p.read_bytes()
        for p in sorted(rev1.rglob("*"))
        if p.is_file()
    }
    assert rev1_after == rev1_before
    # Never writes profiles/doctor-feedback.yaml or profiles/factory-standards.yaml.
    assert not (tmp_path / "profiles" / "doctor-feedback.yaml").exists()
    assert not (tmp_path / "profiles" / "factory-standards.yaml").exists()


def test_adopt_r5_rejects_missing_evidence_and_recovers_idempotently(tmp_path: Path) -> None:
    pin_file = tmp_path / "approver-pin.json"
    set_pin("654321", path=pin_file)

    _seed_v2_project(tmp_path, slug="no-evidence", with_evidence=False)
    with pytest.raises(ValueError, match="evidence/ledger.yaml"):
        adopt_r5_project(
            tmp_path, "no-evidence", reason="Adopt R5", pin="654321", pin_file=pin_file
        )

    # Simulate partial crash after create_revision promoted 002 but before project.yaml switched.
    project_dir = _seed_v2_project(tmp_path, slug="recover-case")
    now = datetime(2026, 11, 24, 19, 5, tzinfo=UTC)
    reason = "Chuyển R5 phục hồi"
    create_revision(project_dir, reason, now=now)
    # Roll back project.yaml to 001 while leaving promoted 002 on disk.
    manifest_data = read_yaml(project_dir / "project.yaml")
    manifest_data["active_revision"] = "001"
    write_yaml_atomic(project_dir / "project.yaml", manifest_data)

    recovered = adopt_r5_project(
        tmp_path,
        "recover-case",
        reason=reason,
        pin="654321",
        now=now,
        pin_file=pin_file,
        recover=True,
    )
    assert recovered["revision"] == "002"
    assert r5_active(project_dir / "revisions" / "002") is True

    # Calling recover=True again is idempotent and does not create revision 003.
    again = adopt_r5_project(
        tmp_path,
        "recover-case",
        reason=reason,
        pin="654321",
        now=now,
        pin_file=pin_file,
        recover=True,
    )
    assert again["revision"] == "002"
    assert again["recovered"] is True
    assert not (project_dir / "revisions" / "003").exists()


@pytest.mark.parametrize("step", ["draft", "revise_medical", "storyboard_design", "shorts_plan"])
def test_runner_prompt_injects_r5_block_only_when_r5_pinned(tmp_path: Path, step: str) -> None:
    legacy_dir = _seed_v2_project(tmp_path, slug="legacy-proj", pin_r5=False)
    r5_dir = _seed_v2_project(tmp_path, slug="r5-proj", pin_r5=True)
    deps = _minimal_run_deps(reject_note="Sửa L01 theo góp ý" if step == "revise_medical" else None)

    legacy_entry = QueueEntry(
        slug="legacy-proj", title="T", question="Q", added=date(2026, 11, 24)
    )
    r5_entry = QueueEntry(slug="r5-proj", title="T", question="Q", added=date(2026, 11, 24))

    legacy_prompt = _build_step_prompt(tmp_path, deps, legacy_entry, legacy_dir, step)
    r5_prompt = _build_step_prompt(tmp_path, deps, r5_entry, r5_dir, step)

    assert "Revision này dùng chuẩn R5" not in legacy_prompt
    assert "## Revision này dùng chuẩn R5 (quality_profile: r5_v1)" in r5_prompt
    assert r5_prompt.index("## Revision này dùng chuẩn R5") < r5_prompt.index("## Quy tắc cứng")

    if step == "storyboard_design":
        assert "quality_profile: r5_v1" in r5_prompt
        assert "r5_contract" in r5_prompt
        assert "assets/r5/catalog.yaml" in r5_prompt
        assert "healthvideo step stage-r5-assets r5-proj" in r5_prompt
        for comp in R5_COMPONENT_IDS:
            assert comp in r5_prompt

    # Legacy revision without workflow/standards.yaml produces byte-identical prompt to non-R5 standards.yaml.
    (legacy_dir / "revisions" / "001" / "workflow" / "standards.yaml").unlink()
    legacy_no_std = _build_step_prompt(tmp_path, deps, legacy_entry, legacy_dir, step)
    assert legacy_no_std == legacy_prompt


def test_stage_r5_assets_copies_verifies_merges_and_blocks_unsafe_paths(tmp_path: Path) -> None:
    # Copy real liver-anatomy library into tmp_path/library/medanim/liver-anatomy
    lib_dst = tmp_path / "library" / "medanim" / "liver-anatomy"
    lib_dst.mkdir(parents=True)
    for src_file in LIVER_CATALOG.parent.iterdir():
        if src_file.is_file():
            (lib_dst / src_file.name).write_bytes(src_file.read_bytes())

    project_dir = _seed_v2_project(tmp_path, slug="liver-r5", with_approvals=False, pin_r5=True)

    first = stage_r5_assets(
        tmp_path,
        "liver-r5",
        catalog=Path("library/medanim/liver-anatomy/assets.yaml"),
        asset_ids=["servier-liver-lobule", "niaid-human-anatomy-519"],
    )
    assert first["revision"] == "001"
    assert [item["id"] for item in first["staged"]] == [
        "servier-liver-lobule",
        "niaid-human-anatomy-519",
    ]
    rev = project_dir / "revisions" / "001"
    rev_catalog = load_asset_catalog(rev / "assets" / "r5" / "catalog.yaml")
    assert {r.file for r in rev_catalog} == {
        "assets/r5/servier-liver-lobule.png",
        "assets/r5/niaid-human-anatomy-519.png",
    }
    for r in rev_catalog:
        assert sha256_file(rev / r.file) == r.sha256

    # Second staging merges cleanly.
    stage_r5_assets(
        tmp_path,
        "liver-r5",
        catalog=Path("library/medanim/liver-anatomy/assets.yaml"),
        asset_ids=["servier-bile-secretion"],
    )
    merged = load_asset_catalog(rev / "assets" / "r5" / "catalog.yaml")
    assert len(merged) == 3

    # Rejects catalog outside library/medanim.
    outside = tmp_path / "outside.yaml"
    outside.write_text(LIVER_CATALOG.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ValueError, match="library/medanim"):
        stage_r5_assets(tmp_path, "liver-r5", catalog=outside, asset_ids=["servier-liver-lobule"])

    # Rejects unknown ID.
    with pytest.raises(ValueError, match="Unknown used asset"):
        stage_r5_assets(
            tmp_path,
            "liver-r5",
            catalog=Path("library/medanim/liver-anatomy/assets.yaml"),
            asset_ids=["does-not-exist"],
        )

    # Refuses to stage after medical approval.
    write_yaml_atomic(rev / "reviews" / "medical-approval.yaml", {"kind": "medical"})
    with pytest.raises(ValueError, match="đã duyệt y khoa"):
        stage_r5_assets(
            tmp_path,
            "liver-r5",
            catalog=Path("library/medanim/liver-anatomy/assets.yaml"),
            asset_ids=["servier-digestive-system"],
        )


def test_cli_adopt_r5_and_stage_r5_assets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_v2_project(tmp_path, slug="cli-r5", with_approvals=True, pin_r5=False)
    lib_dst = tmp_path / "library" / "medanim" / "liver-anatomy"
    lib_dst.mkdir(parents=True)
    for src_file in LIVER_CATALOG.parent.iterdir():
        if src_file.is_file():
            (lib_dst / src_file.name).write_bytes(src_file.read_bytes())

    pin_file = tmp_path / "approver-pin.json"
    set_pin("123456", path=pin_file)
    monkeypatch.setattr("healthvideo.cli.pin_path", lambda: pin_file)
    monkeypatch.setattr("healthvideo.workflows.adopt_r5.pin_path", lambda: pin_file)

    runner = CliRunner()
    # Non-TTY fails closed before PIN.
    fail_res = runner.invoke(
        app, ["project", "adopt-r5", "cli-r5", "--reason", "Lên R5", "--root", str(tmp_path)]
    )
    assert fail_res.exit_code != 0
    assert "TTY" in fail_res.output

    # With TTY + valid PIN succeeds.
    monkeypatch.setattr("healthvideo.cli._require_tty", lambda: None)
    monkeypatch.setattr("healthvideo.cli.getpass.getpass", lambda _prompt: "123456")
    ok_res = runner.invoke(
        app, ["project", "adopt-r5", "cli-r5", "--reason", "Lên R5", "--root", str(tmp_path)]
    )
    assert ok_res.exit_code == 0, ok_res.output
    assert "r5_v1" in ok_res.output
    assert "001 -> 002" in ok_res.output

    stage_res = runner.invoke(
        app,
        [
            "step",
            "stage-r5-assets",
            "cli-r5",
            "--catalog",
            "library/medanim/liver-anatomy/assets.yaml",
            "--ids",
            "servier-liver-lobule,niaid-human-anatomy-519",
            "--root",
            str(tmp_path),
        ],
    )
    assert stage_res.exit_code == 0, stage_res.output
    payload = json.loads(stage_res.output)
    assert payload["revision"] == "002"
    assert len(payload["staged"]) == 2


def test_dashboard_adopt_r5_route_enforces_confirm_and_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_v2_project(tmp_path, slug="dash-r5", with_approvals=True, pin_r5=False)
    pin_file = tmp_path / "approver-pin.json"
    set_pin("987654", path=pin_file)
    monkeypatch.setattr("healthvideo.workflows.dashboard.pin_path", lambda: pin_file)

    class _Server:
        root = tmp_path
        limiter = PinLimiter()

    # Missing confirmed flag rejected.
    with pytest.raises(ValueError, match="xác nhận"):
        post_route(
            _Server(),
            ["api", "project", "dash-r5", "adopt-r5"],
            {"expected_revision": "001", "pin": "987654", "reason": "R5", "confirmed": False},
        )

    # Wrong PIN rejected.
    with pytest.raises(PermissionError, match="PIN"):
        post_route(
            _Server(),
            ["api", "project", "dash-r5", "adopt-r5"],
            {"expected_revision": "001", "pin": "111111", "reason": "R5", "confirmed": True},
        )

    # Valid PIN succeeds.
    res = post_route(
        _Server(),
        ["api", "project", "dash-r5", "adopt-r5"],
        {"expected_revision": "001", "pin": "987654", "reason": "Lên chuẩn R5", "confirmed": True},
    )
    assert res is not None
    assert res["revision"] == "002"
    assert res["state"] == "evidence_ready"
    assert res["quality_profile"] == "r5_v1"


def test_adopt_r5_releases_old_revision_repair_holds(tmp_path: Path) -> None:
    from healthvideo.workflows import doctor_questions

    _seed_v2_project(tmp_path)
    pin_file = tmp_path / "approver-pin.json"
    set_pin("654321", path=pin_file)
    logs = tmp_path / "topics" / "logs" / "men-gan-tang"
    logs.mkdir(parents=True)
    for name in ("blocked.txt", "agent-retry.yaml", "leader-guidance.yaml"):
        (logs / name).write_text("revision: '001'\n", encoding="utf-8")
    (logs / "leader-repair.yaml").write_text("revision: '001'\nphase: needs_attention\n", encoding="utf-8")
    doctor_questions.ask(tmp_path, "men-gan-tang", station="repair", kind="escalation",
                         question="Kẹt storyboard", options=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}])

    adopt_r5_project(tmp_path, "men-gan-tang", reason="R5", pin="654321", pin_file=pin_file)

    assert sorted(p.name for p in logs.iterdir() if p.name != "doctor-questions-history.yaml") == []
    assert doctor_questions.open_question(tmp_path, "men-gan-tang") is None


def test_overview_projects_include_r5_flag(tmp_path: Path) -> None:
    from healthvideo.workflows.dashboard import overview

    _seed_v2_project(tmp_path, slug="r5-topic", pin_r5=True)
    _seed_v2_project(tmp_path, slug="legacy-topic", pin_r5=False)
    broken_dir = _seed_v2_project(tmp_path, slug="broken-snap", pin_r5=False)
    (broken_dir / "revisions" / "001" / "workflow" / "standards-snapshot.yaml").write_text(
        ":\n  - [bad yaml", encoding="utf-8"
    )

    data = overview(tmp_path)
    by_slug = {p["slug"]: p for p in data["projects"]}
    assert by_slug["r5-topic"]["r5"] is True
    assert by_slug["legacy-topic"]["r5"] is False
    assert by_slug["broken-snap"]["r5"] is False
