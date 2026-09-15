import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from healthvideo.domain.lease import LeaseOwner
from healthvideo.domain.project import ProjectManifest, ProjectState
from healthvideo.domain.review import ReviewKind
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.lease import LeaseBusyError, acquire_write_lease
from healthvideo.workflows.backup import create_backup, restore_backup
from healthvideo.workflows.review import approval_is_stale
from tests.helpers import create_project_fixture, create_v2_project_fixture

NOW = datetime(2026, 9, 15, 8, 30, tzinfo=UTC)


def _manifest(snapshot: Path) -> dict[str, object]:
    return json.loads((snapshot / "backup-manifest.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("version", ["1.0", "2.0"])
def test_create_restore_round_trip_preserves_every_authoritative_byte(
    tmp_path: Path, version: str
) -> None:
    project = (
        create_project_fixture(tmp_path / "source", ProjectState.PRODUCING.value)
        if version == "1.0"
        else create_v2_project_fixture(tmp_path / "source")
    )
    snapshot = create_backup(
        project, tmp_path / "backups", backup_id=f"backup-{version[0]}", now=NOW
    )
    restored = restore_backup(snapshot, tmp_path / f"restored-{version[0]}")
    manifest = _manifest(snapshot)

    for entry in manifest["entries"]:
        relative = entry["path"]
        assert (restored / relative).read_bytes() == (project / relative).read_bytes()
    assert read_yaml(restored / "project.yaml") == read_yaml(project / "project.yaml")
    assert manifest["project_schema_version"] == version


def test_backup_excludes_runtime_secrets_source_fulltext_and_temporary_files(
    tmp_path: Path,
) -> None:
    project = create_v2_project_fixture(tmp_path / "source")
    excluded = [
        ".healthvideo/write-lease-copy.yaml",
        ".env",
        "cache/provider/response.json",
        "source-documents/article.pdf",
        "revisions/001/workflow/pending-render.yaml",
        "revisions/001/assets/model.safetensors",
        "revisions/001/renders/video.mp4.tmp",
    ]
    for relative in excluded:
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"must-not-back-up")

    snapshot = create_backup(project, tmp_path / "backups", backup_id="clean", now=NOW)
    paths = {entry["path"] for entry in _manifest(snapshot)["entries"]}

    assert "project.yaml" in paths
    assert "revisions/001/assets/asset-manifest.yaml" in paths
    assert paths.isdisjoint(excluded)


def test_backup_refuses_an_authoritative_reference_to_forbidden_bytes(
    tmp_path: Path,
) -> None:
    project = create_v2_project_fixture(tmp_path / "source")
    forbidden = project / "revisions/001/cache/provider.bin"
    forbidden.parent.mkdir(parents=True)
    forbidden.write_bytes(b"secret provider cache")
    asset_manifest = project / "revisions/001/assets/asset-manifest.yaml"
    data = read_yaml(asset_manifest)
    data["assets"][0]["path"] = "cache/provider.bin"
    write_yaml_atomic(asset_manifest, data)

    with pytest.raises(ValueError, match="forbidden"):
        create_backup(project, tmp_path / "backups", backup_id="bad-ref", now=NOW)


def test_create_refuses_active_writer_and_existing_snapshot(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path / "source")
    handle = acquire_write_lease(
        project,
        operation="writer",
        active_revision="001",
        owner=LeaseOwner(
            host_id="other", pid=999, process_start_fingerprint="other-start"
        ),
        now=NOW,
        ttl_seconds=60,
    )
    try:
        with pytest.raises(LeaseBusyError):
            create_backup(project, tmp_path / "backups", backup_id="busy", now=NOW)
    finally:
        handle.release()

    create_backup(project, tmp_path / "backups", backup_id="once", now=NOW)
    with pytest.raises(FileExistsError):
        create_backup(project, tmp_path / "backups", backup_id="once", now=NOW)


def test_restore_refuses_missing_extra_tampered_and_existing_destination(
    tmp_path: Path,
) -> None:
    project = create_v2_project_fixture(tmp_path / "source")
    snapshot = create_backup(project, tmp_path / "backups", backup_id="base", now=NOW)
    destination = tmp_path / "exists"
    destination.mkdir()
    with pytest.raises(FileExistsError):
        restore_backup(snapshot, destination)

    (snapshot / "extra.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(ValueError, match="extra"):
        restore_backup(snapshot, tmp_path / "extra-restore")
    (snapshot / "extra.txt").unlink()
    (snapshot / "project.yaml").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="tampered"):
        restore_backup(snapshot, tmp_path / "tampered-restore")


def test_restore_rejects_malformed_approval_and_missing_bound_artifact(
    tmp_path: Path,
) -> None:
    project = create_project_fixture(tmp_path / "source", ProjectState.PRODUCING.value)
    snapshot = create_backup(project, tmp_path / "backups", backup_id="approval", now=NOW)
    approval = next((snapshot / "reviews").glob("medical-*.yaml"))
    original = approval.read_bytes()
    approval.write_text("schema_version: 1.0\nreviewer: ''\n", encoding="utf-8")
    _rehash_manifest_entry(snapshot, approval)
    with pytest.raises((ValidationError, ValueError)):
        restore_backup(snapshot, tmp_path / "malformed")

    approval.write_bytes(original)
    _rehash_manifest_entry(snapshot, approval)
    (snapshot / "script/script.yaml").unlink()
    manifest = _manifest(snapshot)
    manifest["entries"] = [
        item for item in manifest["entries"] if item["path"] != "script/script.yaml"
    ]
    (snapshot / "backup-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(FileNotFoundError, match="approval"):
        restore_backup(snapshot, tmp_path / "missing-bound")


def test_restore_accepts_intact_stale_approval_without_resigning(tmp_path: Path) -> None:
    project = create_project_fixture(tmp_path / "source", ProjectState.PRODUCING.value)
    approval = next((project / "reviews").glob("medical-*.yaml"))
    approval_bytes = approval.read_bytes()
    script = read_yaml(project / "script/script.yaml")
    script["title"] = "Changed after approval"
    write_yaml_atomic(project / "script/script.yaml", script)
    assert approval_is_stale(
        project,
        ProjectManifest.model_validate(read_yaml(project / "project.yaml")),
        ReviewKind.MEDICAL,
    )

    snapshot = create_backup(project, tmp_path / "backups", backup_id="stale", now=NOW)
    restored = restore_backup(snapshot, tmp_path / "restored")

    assert next((restored / "reviews").glob("medical-*.yaml")).read_bytes() == approval_bytes
    assert approval_is_stale(
        restored,
        ProjectManifest.model_validate(read_yaml(restored / "project.yaml")),
        ReviewKind.MEDICAL,
    )


def test_backup_preserves_recovery_journals_and_their_staged_bytes(
    tmp_path: Path,
) -> None:
    project = create_v2_project_fixture(tmp_path / "source")
    preserved = [
        "revisions/001/workflow/pending-ai-clip-generation.yaml",
        "revisions/001/workflow/pending-chart-binding.yaml",
        "revisions/001/workflow/pending-hook-outro.yaml",
        "revisions/001/workflow/staged-ai-clips/S01-fake.mp4",
    ]
    for relative in preserved:
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic-recovery-state")

    snapshot = create_backup(project, tmp_path / "backups", backup_id="journal", now=NOW)

    assert set(preserved) <= {entry["path"] for entry in _manifest(snapshot)["entries"]}


def test_round_trip_keeps_state_and_current_approvals_current(tmp_path: Path) -> None:
    project = create_project_fixture(
        tmp_path / "source", ProjectState.APPROVED_TO_PUBLISH.value
    )
    snapshot = create_backup(project, tmp_path / "backups", backup_id="current", now=NOW)
    restored = restore_backup(snapshot, tmp_path / "restored")
    manifest = ProjectManifest.model_validate(read_yaml(restored / "project.yaml"))

    assert manifest.state is ProjectState.APPROVED_TO_PUBLISH
    for kind in ReviewKind:
        assert list((restored / "reviews").glob(f"{kind.value}-*.yaml"))
        assert not approval_is_stale(restored, manifest, kind)


def test_interrupted_promotion_leaves_no_snapshot_or_staging_and_releases_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = create_v2_project_fixture(tmp_path / "source")
    backups = tmp_path / "backups"

    def interrupted(source: Path, destination: Path) -> None:
        raise OSError("simulated crash during promotion")

    monkeypatch.setattr(
        "healthvideo.workflows.backup.promote_directory_once", interrupted
    )
    with pytest.raises(OSError, match="simulated"):
        create_backup(project, backups, backup_id="crash", now=NOW)

    assert list(backups.iterdir()) == []
    assert not (project / ".healthvideo" / "write-lease.yaml").exists()


def test_restore_rejects_forbidden_entry_without_creating_destination(
    tmp_path: Path,
) -> None:
    project = create_v2_project_fixture(tmp_path / "source")
    snapshot = create_backup(project, tmp_path / "backups", backup_id="secret", now=NOW)
    (snapshot / ".env").write_bytes(b"TOKEN=synthetic-test-value")
    _rehash_manifest_entry(snapshot, snapshot / ".env")

    with pytest.raises(ValueError, match="forbidden"):
        restore_backup(snapshot, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


def test_restore_rejects_unsupported_project_layout(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path / "source")
    snapshot = create_backup(project, tmp_path / "backups", backup_id="layout", now=NOW)
    manifest_path = snapshot / "project.yaml"
    data = read_yaml(manifest_path)
    data["schema_version"] = "9.0"
    write_yaml_atomic(manifest_path, data)
    _rehash_manifest_entry(snapshot, manifest_path)

    with pytest.raises(ValueError, match="Unsupported"):
        restore_backup(snapshot, tmp_path / "restored")


def _rehash_manifest_entry(snapshot: Path, changed: Path) -> None:
    import hashlib

    manifest = _manifest(snapshot)
    relative = changed.relative_to(snapshot).as_posix()
    data = changed.read_bytes()
    manifest["entries"] = [
        item for item in manifest["entries"] if item["path"] != relative
    ] + [
        {
            "path": relative,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    ]
    (snapshot / "backup-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

