from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from healthvideo.domain.backup import BackupEntry, BackupManifest


def _entry(path: str = "project.yaml") -> BackupEntry:
    return BackupEntry(path=path, size=7, sha256="a" * 64)


def test_manifest_preserves_injected_identity_time_and_canonical_order() -> None:
    now = datetime(2026, 9, 15, 8, 30, tzinfo=UTC)
    manifest = BackupManifest(
        backup_id="nightly-001",
        project_schema_version="2.0",
        slug="muoi-va-huyet-ap",
        active_revision="001",
        created_at=now,
        entries=[_entry("z/file.json"), _entry("a/file.yaml")],
    )

    assert manifest.backup_id == "nightly-001"
    assert manifest.created_at == now
    assert [entry.path for entry in manifest.entries] == [
        "a/file.yaml",
        "z/file.json",
    ]


@pytest.mark.parametrize(
    "path",
    ["/absolute", "C:/drive", "../parent", "a/../b", "a\\windows", "a//b"],
)
def test_entry_rejects_noncanonical_or_unsafe_paths(path: str) -> None:
    with pytest.raises(ValidationError):
        _entry(path)


@pytest.mark.parametrize(
    ("size", "sha256"),
    [(-1, "a" * 64), (1, "A" * 64), (1, "a" * 63), (1, "g" * 64)],
)
def test_entry_rejects_invalid_size_or_hash(size: int, sha256: str) -> None:
    with pytest.raises(ValidationError):
        BackupEntry(path="project.yaml", size=size, sha256=sha256)


@pytest.mark.parametrize("paths", [["a", "a"], ["A/file", "a/file"]])
def test_manifest_rejects_duplicate_or_case_colliding_paths(paths: list[str]) -> None:
    with pytest.raises(ValidationError, match="collision"):
        BackupManifest(
            backup_id="one",
            project_schema_version="1.0",
            slug="muoi",
            active_revision=None,
            created_at=datetime(2026, 9, 15, tzinfo=UTC),
            entries=[_entry(path) for path in paths],
        )

