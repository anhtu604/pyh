"""M7 process-boundary E2E: real CLI subprocesses, pipe barriers, no sleeps.

Every run is offline under `tmp_path`: TTS is silent, Remotion is the worker's
fake renderer, the only AI clip is fake bytes authored before the medical gate,
and nothing publishes. Exactly two human gates are approved per project.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.domain.brand import LogoVariant
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.hook_outro import OUTRO_TEXT
from healthvideo.domain.lease import LeaseOwner
from healthvideo.domain.project import ProjectManifest, ProjectState
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.review import ReviewKind
from healthvideo.render.input import MAX_DURATION_FRAMES, MIN_DURATION_FRAMES
from healthvideo.storage.backup import tree_files
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.lease import acquire_write_lease
from healthvideo.video_ai.base import VeoRequest, VeoResult, VideoProbeResult
from healthvideo.workflows.ai_clips import AIClipRights, generate_ai_clip
from healthvideo.workflows.backup import is_backup_excluded, validate_project_tree
from healthvideo.workflows.hook_outro import author_hook_outro
from healthvideo.workflows.package import _ensure_v2_gate_approval
from healthvideo.workflows.review import approval_is_stale
from healthvideo.workflows.visual_assets import (
    bind_chart_asset,
    create_brand_logo_asset,
    create_evidence_chart,
)
from tests.helpers import (
    _advance_v2_state,
    create_v2_project_fixture,
    synthesize_fixture_audio,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("subprocess_worker.py")
FIXTURES = REPOSITORY_ROOT / "tests" / "fixtures"
LEASE = Path(".healthvideo/write-lease.yaml")
ENTERED_AT = datetime(2026, 9, 10, 7, 30, tzinfo=UTC)


@pytest.mark.parametrize(("ai", "duration_ms"), [(False, 48000), (True, 63000)])
def test_golden_v2_crosses_process_boundaries_to_a_restorable_package(
    tmp_path: Path, ai: bool, duration_ms: int
) -> None:
    project, provider_requests = _prepare_v2_awaiting_medical(tmp_path, ai=ai)
    revision = project / "revisions/001"

    for arguments in (
        ("review", "approve", project, "--gate", "medical", "--reviewer", "doctor", "--yes"),
        ("produce", project),
        ("review", "approve", project, "--gate", "video", "--reviewer", "doctor", "--yes"),
        ("package", project),
    ):
        _assert_cli_ok(*arguments)

    scenes = json.loads((revision / "renders/render-input.json").read_text(encoding="utf-8"))[
        "scenes"
    ]
    assert scenes[0]["start_frame"] == 0
    assert not any("intro" in f"{scene['id']} {scene['visual']}".lower() for scene in scenes)
    assert (scenes[-1]["visual"], scenes[-1]["narration"]) == ("brand_outro", OUTRO_TEXT)
    assert "pyh-logo.svg" in json.dumps(scenes[-1])
    qa = json.loads((revision / "reviews/video-qa.json").read_text(encoding="utf-8"))
    assert qa["composition_duration_ms"] == duration_ms
    assert sorted(path.name for path in (revision / "reviews").glob("*-approval.yaml")) == [
        "medical-approval.yaml",
        "video-approval.yaml",
    ]
    assert (revision / "publish/ai-disclosure.json").is_file() is ai
    assert read_yaml(project / "project.yaml")["state"] == "packaged"

    backups, restored = tmp_path / "backups", tmp_path / "restored"
    _assert_cli_ok("backup", "create", project, backups, "--id", "golden")
    _assert_cli_ok("backup", "restore", backups / "golden", restored)

    assert _tree(restored) == _tree(project)
    assert read_yaml(restored / "project.yaml")["state"] == "packaged"
    validate_project_tree(restored)
    for kind in GateKind:
        _ensure_v2_gate_approval(restored / "revisions/001", kind)
    assert len(provider_requests) == (1 if ai else 0)


def test_racing_writers_admit_one_and_backup_waits_for_the_writer(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path / "source")
    backups = tmp_path / "backups"
    before = _tree(project)
    racers = [_spawn("race", project), _spawn("race", project)]
    try:
        assert [_event(racer) for racer in racers] == ["armed", "armed"]
        for racer in racers:
            _send(racer, "go")
        outcomes = [_event(racer) for racer in racers]
        assert sorted(outcomes) == ["acquired", "busy"]
        winner = racers[outcomes.index("acquired")]

        write = _cli("agent", "review-request", project, "--reason", "conflicting_evidence")
        backup = _cli("backup", "create", project, backups, "--id", "contended")
        assert (write.returncode, backup.returncode) == (1, 1)
        assert "Project busy" in write.stdout and "Project busy" in backup.stdout
        assert not (backups / "contended").exists()
        assert _tree(project) == before

        _send(winner, "release")
        assert _event(winner) == "released"
    finally:
        _finish(*racers)

    _assert_cli_ok("backup", "create", project, backups, "--id", "after-release")
    assert not (project / LEASE).exists()


def test_restore_from_a_snapshot_leaves_a_busy_source_untouched(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path / "source")
    backups, restored = tmp_path / "backups", tmp_path / "restored"
    _assert_cli_ok("backup", "create", project, backups, "--id", "base")
    before = _tree(project)
    holder = _spawn("hold", project)
    try:
        assert _event(holder) == "ready"
        _assert_cli_ok("backup", "restore", backups / "base", restored)
        assert _tree(restored) == before
        assert _tree(project) == before
        _send(holder, "release")
        assert _event(holder) == "released"
    finally:
        _finish(holder)


def test_killed_holder_blocks_writes_until_same_host_recovery(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path / "source")
    holder = _spawn("hold", project, "--expired")
    try:
        assert _event(holder) == "ready"
        alive = _cli("lease", "recover", project)
        assert alive.returncode == 1 and "still active" in alive.stdout
    finally:
        holder.kill()
        _finish(holder)
    # Windows keeps a dead process identifiable while any handle is open.
    del holder

    before = (project / "project.yaml").read_bytes()
    blocked = _cli("agent", "review-request", project, "--reason", "conflicting_evidence")
    assert blocked.returncode == 1 and "Project busy" in blocked.stdout
    assert (project / "project.yaml").read_bytes() == before

    _assert_cli_ok("lease", "recover", project)
    assert list((project / ".healthvideo/stale-leases").glob("*.yaml"))
    _assert_cli_ok("agent", "review-request", project, "--reason", "conflicting_evidence")
    assert not (project / LEASE).exists()


def test_expired_foreign_host_lease_needs_explicit_recovery(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path / "source")
    acquire_write_lease(
        project,
        operation="other_machine",
        active_revision="001",
        owner=LeaseOwner(
            host_id="foreign-host", pid=4242, process_start_fingerprint="foreign-start"
        ),
        now=datetime(2026, 9, 15, 8, 0, tzinfo=UTC),
        ttl_seconds=60,
    )
    lease = read_yaml(project / LEASE)
    before = (project / "project.yaml").read_bytes()

    refused = _cli("lease", "recover", project)
    blocked = _cli("agent", "review-request", project, "--reason", "conflicting_evidence")
    assert refused.returncode == 1 and "foreign-host" in refused.stdout
    assert blocked.returncode == 1 and "Project busy" in blocked.stdout
    assert (project / "project.yaml").read_bytes() == before

    _assert_cli_ok("lease", "recover", project, "--allow-foreign-host")
    [stale] = (project / ".healthvideo/stale-leases").glob("*.yaml")
    assert read_yaml(stale) == lease
    assert not (project / LEASE).exists()


def test_v1_golden_packages_and_restores_without_migration(tmp_path: Path) -> None:
    project = tmp_path / "golden-project"
    shutil.copytree(FIXTURES / "golden-project", project)
    synthesize_fixture_audio(project)
    manifest = read_yaml(project / "project.yaml")
    manifest["state"] = ProjectState.AWAITING_MEDICAL_REVIEW.value
    write_yaml_atomic(project / "project.yaml", manifest)

    for arguments in (
        ("review", "medical", project, "--reviewer", "BS An", "--yes"),
        ("produce", project),
        ("review", "video", project, "--reviewer", "BS An", "--yes"),
        ("package", project),
    ):
        _assert_cli_ok(*arguments)
    run = project / "renders" / read_yaml(project / "project.yaml")["artifact_hashes"]["production"]
    last = json.loads((run / "render-input.json").read_text(encoding="utf-8"))["scenes"][-1]
    assert MIN_DURATION_FRAMES <= last["start_frame"] + last["duration_frames"] <= MAX_DURATION_FRAMES

    backups, restored = tmp_path / "backups", tmp_path / "restored"
    _assert_cli_ok("backup", "create", project, backups, "--id", "v1")
    _assert_cli_ok("backup", "restore", backups / "v1", restored)

    assert _tree(restored) == _tree(project)
    assert not (restored / "revisions").exists()
    restored_manifest = ProjectManifest.model_validate(read_yaml(restored / "project.yaml"))
    assert restored_manifest.schema_version == "1.0"
    assert restored_manifest.state is ProjectState.APPROVED_TO_PUBLISH
    for kind in ReviewKind:
        assert not approval_is_stale(restored, restored_manifest, kind)


def _prepare_v2_awaiting_medical(
    tmp_path: Path, *, ai: bool
) -> tuple[Path, list[VeoRequest]]:
    """Author a v2 project up to the medical gate in-process; AI bytes are fake."""
    if not ai:
        project = create_v2_project_fixture(
            tmp_path / "source", state=WorkflowState.AWAITING_MEDICAL_REVIEW
        )
        board_path = project / "revisions/001/storyboard/storyboard.yaml"
        board = read_yaml(board_path)
        board["scenes"][0]["duration_frames"] = 1350
        write_yaml_atomic(board_path, board)
        author_hook_outro(project, duration_frames=90)
        create_brand_logo_asset(
            project, scene_id="OUTRO", asset_name="pyh-logo", variant=LogoVariant.MONOGRAM
        )
        return project, []

    project = tmp_path / "golden-project-v2"
    shutil.copytree(FIXTURES / "golden-project-v2", project)
    _advance_v2_state(project, WorkflowState.AWAITING_MEDICAL_REVIEW)
    revision = project / "revisions/001"
    ledger = read_yaml(revision / "evidence/ledger.yaml")
    ledger["claims"][0]["chart_data"] = [
        {"id": "bp-count", "source_id": "R01", "label": "Mẫu thử tổng hợp",
         "value": 12, "denominator": 40, "unit": "người"}
    ]
    write_yaml_atomic(revision / "evidence/ledger.yaml", ledger)
    board = read_yaml(revision / "storyboard/storyboard.yaml")
    board["visual_budget_profile"] = "m6_5_v1"
    board["scenes"][1]["visual"] = "ai_clip"
    durations = {"ai_clip": 180, "chart": 225, "evidence_highlight": 225, "whiteboard": 390}
    start = 0
    for scene in board["scenes"]:
        scene["start_frame"], scene["duration_frames"] = start, durations[scene["visual"]]
        start += scene["duration_frames"]
    write_yaml_atomic(revision / "storyboard/storyboard.yaml", board)
    author_hook_outro(project, duration_frames=90)
    create_brand_logo_asset(
        project, scene_id="OUTRO", asset_name="pyh-logo", variant=LogoVariant.MONOGRAM
    )
    create_evidence_chart(
        project, claim_id="C01", datum_id="bp-count", asset_name="chart-count",
        license="synthetic_test_only", rights_basis="fixture nội bộ", creator="repository_fixture",
    )
    bind_chart_asset(project, scene_id="S04", asset_path="assets/chart-count.svg")

    requests: list[VeoRequest] = []

    class FakeVeo:
        def generate(self, request: VeoRequest) -> VeoResult:
            requests.append(request)
            return VeoResult(video_bytes=b"synthetic-e2e-ai-clip", mime_type="video/mp4")

    generate_ai_clip(
        project, scene_id="S02", prompt="Minh họa tổng hợp: nêm ít muối",
        duration_seconds=6, requested_seed=None,
        rights=AIClipRights(
            source="Google Vertex AI generation", creator="PYH operator",
            license="synthetic_test_only", rights_basis="fixture nội bộ",
        ),
        transport=FakeVeo(), now=ENTERED_AT,
        probe=lambda _path: VideoProbeResult(
            mime_type="video/mp4", container="mp4", width=1080, height=1920,
            source_fps=24, duration_ms=6000, source_frame_count=144, video_stream_count=1,
        ),
    )
    return project, requests


def _tree(root: Path) -> dict[str, bytes]:
    return {
        relative: (root / relative).read_bytes()
        for relative in tree_files(root, skip=is_backup_excluded)
    }


def _cli(*arguments: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(WORKER), "cli", *map(str, arguments)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPOSITORY_ROOT,
        check=False,
        timeout=120,
    )


def _assert_cli_ok(*arguments: object) -> None:
    result = _cli(*arguments)
    assert result.returncode == 0, f"{arguments[:2]}: {result.stdout}{result.stderr}"


def _spawn(*arguments: object) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, str(WORKER), *map(str, arguments)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        cwd=REPOSITORY_ROOT,
    )


def _event(process: subprocess.Popen[str]) -> str:
    assert process.stdout is not None
    line = process.stdout.readline()
    assert line, f"worker exited early: {process.communicate(timeout=30)[1]}"
    return json.loads(line)["event"]


def _send(process: subprocess.Popen[str], command: str) -> None:
    assert process.stdin is not None
    process.stdin.write(f"{command}\n")
    process.stdin.flush()


def _finish(*processes: subprocess.Popen[str]) -> None:
    for process in processes:
        try:
            process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
