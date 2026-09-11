import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from healthvideo.storage.files import read_yaml
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.workflows import migrate as migrate_module
from healthvideo.workflows.migrate import migrate_project
from tests.helpers import create_project_fixture

GOLDEN_V1 = Path("tests/fixtures/golden-project")
FROZEN_NOW = datetime(2026, 9, 11, 8, 0, tzinfo=UTC)
MIGRATION_ID = UUID("11111111-1111-1111-1111-111111111111")


def _copy_golden(root: Path) -> Path:
    source = root / "golden-project"
    shutil.copytree(GOLDEN_V1, source)
    return source


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_migration_promotes_new_v2_project_without_changing_v1(
    tmp_path: Path,
) -> None:
    source = _copy_golden(tmp_path)
    before = _snapshot(source)

    destination = migrate_project(
        source, now=FROZEN_NOW, migration_id=MIGRATION_ID
    )

    assert _snapshot(source) == before
    assert destination == source.with_name("golden-project-v2")
    layout = resolve_project_layout(destination)
    assert layout.schema_version == "2.0"
    assert layout.artifact_root == destination / "revisions" / "001"
    assert layout.manifest.state.value == "awaiting_medical_review"
    assert read_yaml(layout.artifact_root / "topic" / "card.yaml")[
        "synthetic_test_record"
    ] is True


def test_migration_refuses_to_replace_a_destination(tmp_path: Path) -> None:
    source = _copy_golden(tmp_path)
    destination = source.with_name("golden-project-v2")
    destination.mkdir()
    sentinel = destination / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError, match="existing"):
        migrate_project(source, now=FROZEN_NOW, migration_id=MIGRATION_ID)

    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert list(tmp_path.glob(".golden-project-v2.migrate-*")) == []


def test_migration_is_idempotent_by_refusal(tmp_path: Path) -> None:
    source = _copy_golden(tmp_path)
    first = migrate_project(source, now=FROZEN_NOW, migration_id=MIGRATION_ID)
    before = _snapshot(first)

    with pytest.raises(FileExistsError, match="existing"):
        migrate_project(source, now=FROZEN_NOW, migration_id=MIGRATION_ID)

    assert _snapshot(first) == before


def test_migration_cleans_its_staging_when_copy_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _copy_golden(tmp_path)
    before = _snapshot(source)
    real_write_yaml = migrate_module.write_yaml_atomic

    def fail_on_script(destination_path: Path, payload: object) -> None:
        if Path(destination_path).name == "script.yaml":
            raise OSError("simulated copy failure")
        real_write_yaml(destination_path, payload)

    monkeypatch.setattr(migrate_module, "write_yaml_atomic", fail_on_script)

    with pytest.raises(OSError, match="simulated copy failure"):
        migrate_project(source, now=FROZEN_NOW, migration_id=MIGRATION_ID)

    assert _snapshot(source) == before
    assert not source.with_name("golden-project-v2").exists()
    assert list(tmp_path.glob(".golden-project-v2.migrate-*")) == []


def test_migration_rejects_naive_time_without_writing(tmp_path: Path) -> None:
    source = _copy_golden(tmp_path)

    with pytest.raises(ValueError, match="timezone-aware"):
        migrate_project(
            source,
            now=FROZEN_NOW.replace(tzinfo=None),
            migration_id=MIGRATION_ID,
        )

    assert not source.with_name("golden-project-v2").exists()


@pytest.mark.parametrize(
    ("source_state", "break_artifact", "expected_state", "expected_reviews"),
    [
        ("script_approved", None, "medically_approved", {"medical"}),
        (
            "awaiting_video_review",
            None,
            "awaiting_video_review",
            {"medical"},
        ),
        (
            "approved_to_publish",
            "render",
            "medically_approved",
            {"medical"},
        ),
        (
            "approved_to_publish",
            None,
            "video_approved",
            {"medical", "video"},
        ),
    ],
)
def test_migration_never_self_approves_unproven_hashes(
    source_state: str,
    break_artifact: str | None,
    expected_state: str,
    expected_reviews: set[str],
    tmp_path: Path,
) -> None:
    source = create_project_fixture(tmp_path, state=source_state)
    if break_artifact == "render":
        manifest = read_yaml(source / "project.yaml")
        run = source / "renders" / manifest["artifact_hashes"]["production"]
        (run / "video.mp4").unlink()

    destination = migrate_project(
        source, now=FROZEN_NOW, migration_id=MIGRATION_ID
    )
    revision = destination / "revisions" / "001"

    assert read_yaml(destination / "project.yaml")["state"] == expected_state
    reviews = {
        path.name.split("-", maxsplit=1)[0]
        for path in (revision / "reviews").glob("*.yaml")
    }
    assert reviews == expected_reviews


def test_changed_medical_artifact_drops_both_approvals(tmp_path: Path) -> None:
    source = create_project_fixture(tmp_path, state="approved_to_publish")
    script = read_yaml(source / "script" / "script.yaml")
    script["lines"][0]["text"] = "Nội dung đã đổi sau duyệt."
    migrate_module.write_yaml_atomic(source / "script" / "script.yaml", script)

    destination = migrate_project(
        source, now=FROZEN_NOW, migration_id=MIGRATION_ID
    )

    assert read_yaml(destination / "project.yaml")["state"] == (
        "awaiting_medical_review"
    )
    assert not (destination / "revisions" / "001" / "reviews").exists()


@pytest.mark.parametrize("failure_point", ["validation", "promotion"])
def test_migration_cleans_staging_on_late_transaction_failure(
    failure_point: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _copy_golden(tmp_path)
    before = _snapshot(source)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError(f"simulated {failure_point} failure")

    target = (
        "validate_asset_manifest"
        if failure_point == "validation"
        else "promote_directory_once"
    )
    monkeypatch.setattr(migrate_module, target, fail)

    with pytest.raises(OSError, match=failure_point):
        migrate_project(source, now=FROZEN_NOW, migration_id=MIGRATION_ID)

    assert _snapshot(source) == before
    assert not source.with_name("golden-project-v2").exists()
    assert list(tmp_path.glob(".golden-project-v2.migrate-*")) == []
