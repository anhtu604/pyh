from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from healthvideo.domain.stage import StageManifest, StageStatus
from healthvideo.storage.immutable import write_yaml_once
from healthvideo.storage.stages import append_stage_manifest, stage_manifest_path

STARTED_AT = datetime(2026, 9, 10, 7, 30, 0, 123456, tzinfo=UTC)


def stage_manifest(**overrides: object) -> StageManifest:
    payload = {
        "stage": "evidence_ledger",
        "status": StageStatus.COMPLETE,
        "input_hash": "a" * 64,
        "output_hash": "b" * 64,
        "tool_version": "1.0.0",
        "agent": "claude",
        "model": "claude-sonnet-5",
        "started_at": STARTED_AT,
        "completed_at": STARTED_AT,
        "estimated_input_tokens": 100,
        "estimated_output_tokens": 200,
    }
    payload.update(overrides)
    return StageManifest(**payload)


def test_stage_manifest_path_encodes_stage_started_at_and_input_hash_prefix(
    tmp_path: Path,
) -> None:
    path = stage_manifest_path(tmp_path, stage_manifest())

    assert path == (
        tmp_path
        / "workflow"
        / "stages"
        / "evidence_ledger"
        / "20260910T073000123456Z-aaaaaaaaaaaa.yaml"
    )


def test_stage_manifest_filename_has_no_colon_for_windows(tmp_path: Path) -> None:
    path = stage_manifest_path(tmp_path, stage_manifest())

    assert ":" not in path.name
    assert ":" not in str(path.relative_to(tmp_path))


def test_append_stage_manifest_writes_the_record_at_its_computed_path(
    tmp_path: Path,
) -> None:
    manifest = stage_manifest()

    path = append_stage_manifest(tmp_path, manifest)

    assert path == stage_manifest_path(tmp_path, manifest)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert payload["stage"] == "evidence_ledger"
    assert payload["status"] == "complete"
    assert payload["input_hash"] == "a" * 64
    assert payload["output_hash"] == "b" * 64


def test_stage_record_cannot_be_overwritten(tmp_path: Path) -> None:
    path = append_stage_manifest(tmp_path, stage_manifest())
    original = path.read_bytes()

    with pytest.raises(FileExistsError):
        write_yaml_once(path, {"status": "failed"})

    assert path.read_bytes() == original


def test_two_runs_of_the_same_stage_with_different_input_do_not_collide(
    tmp_path: Path,
) -> None:
    first = append_stage_manifest(tmp_path, stage_manifest())
    second = append_stage_manifest(
        tmp_path,
        stage_manifest(input_hash="c" * 64, output_hash="d" * 64),
    )

    assert first != second
    assert first.is_file()
    assert second.is_file()


def test_two_stages_never_share_a_directory(tmp_path: Path) -> None:
    ledger_path = append_stage_manifest(tmp_path, stage_manifest())
    script_path = append_stage_manifest(
        tmp_path, stage_manifest(stage="script", input_hash="e" * 64)
    )

    assert ledger_path.parent != script_path.parent
