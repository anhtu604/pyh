import json
from collections.abc import Callable
from pathlib import Path

import pytest

import healthvideo.workflows.produce as produce_workflow
from healthvideo.domain.script import Script
from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.tts.base import TTSRequest, TTSResult
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.produce import _input_hash, produce_project
from tests.helpers import create_project_fixture


def test_produce_reuses_matching_artifact_hash(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")
    calls: list[list[str]] = []

    def fake_runner(argv: list[str]) -> int:
        calls.append(argv)
        _write_synthetic_output(argv)
        return 0

    first = produce_project(project_dir, SilentTTS(), fake_runner)
    second = produce_project(project_dir, SilentTTS(), fake_runner)

    assert second == first
    assert first == _active_run(project_dir) / "video.mp4"
    assert len(calls) == 1
    assert read_yaml(project_dir / "project.yaml")["state"] == "awaiting_video_review"


def test_produce_rejects_reviewed_project_when_cached_output_is_missing(
    tmp_path,
) -> None:
    project_dir = create_project_fixture(tmp_path, state="awaiting_video_review")

    with pytest.raises(ValueError, match="script_approved"):
        produce_project(project_dir, SilentTTS(), lambda argv: 0)


def test_produce_dry_run_does_not_mutate_project_or_call_renderer(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")
    original_manifest = (project_dir / "project.yaml").read_bytes()
    calls: list[list[str]] = []

    output = produce_project(project_dir, SilentTTS(), calls.append, dry_run=True)

    assert output.name == "video.mp4"
    assert output.parent.parent == project_dir / "renders"
    assert calls == []
    assert not output.exists()
    assert not (project_dir / "audio" / "narration.wav").exists()
    assert not (project_dir / "render-input.json").exists()
    assert (project_dir / "project.yaml").read_bytes() == original_manifest


def test_produce_dry_run_cache_hit_does_not_call_renderer_or_mutate_project(
    tmp_path,
) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")

    def successful_runner(argv: list[str]) -> int:
        _write_synthetic_output(argv)
        return 0

    output = produce_project(project_dir, SilentTTS(), successful_runner)
    original_manifest = (project_dir / "project.yaml").read_bytes()
    original_output = output.read_bytes()
    calls: list[list[str]] = []

    assert (
        produce_project(project_dir, SilentTTS(), calls.append, dry_run=True) == output
    )
    assert calls == []
    assert (project_dir / "project.yaml").read_bytes() == original_manifest
    assert output.read_bytes() == original_output


def test_produce_writes_render_input_and_manifest_with_canonical_hash(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")

    def fake_runner(argv: list[str]) -> int:
        _write_synthetic_output(argv)
        return 0

    output = produce_project(project_dir, SilentTTS(), fake_runner)

    render_input = json.loads(
        (output.parent / "render-input.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((output.parent / "manifest.json").read_text(encoding="utf-8"))
    assert render_input["audio_file"] == "audio/narration.wav"
    assert len(manifest["input_hash"]) == 64
    assert manifest["provider"] == "silent"


def test_produce_rejects_cached_reviewed_video_after_author_profile_changes(
    tmp_path, monkeypatch
) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")
    profile = tmp_path / "author-voice.vi.yaml"
    profile.write_text("language: vi\ndirectness: clear_and_calm\n", encoding="utf-8")
    monkeypatch.setattr(
        "healthvideo.workflows.produce.AUTHOR_PROFILE_PATH", profile, raising=False
    )

    def fake_runner(argv: list[str]) -> int:
        _write_synthetic_output(argv)
        return 0

    produce_project(project_dir, SilentTTS(), fake_runner)
    profile.write_text("language: vi\ndirectness: direct\n", encoding="utf-8")

    with pytest.raises(ValueError, match="script_approved"):
        produce_project(project_dir, SilentTTS(), fake_runner)


class ExplodingTTS:
    provider_name = "exploding"

    def synthesize(self, request: TTSRequest, output: Path) -> TTSResult:
        raise RuntimeError("synthetic TTS failure")


@pytest.mark.parametrize(
    ("label", "tts", "runner", "error"),
    [
        (
            "tts",
            ExplodingTTS(),
            lambda argv: 0,
            RuntimeError,
        ),
        (
            "runner",
            SilentTTS(),
            lambda argv: 9,
            RuntimeError,
        ),
        (
            "output",
            SilentTTS(),
            lambda argv: 0,
            FileNotFoundError,
        ),
    ],
)
def test_produce_failure_preserves_project_and_allows_retry(
    tmp_path,
    label: str,
    tts: SilentTTS | ExplodingTTS,
    runner: Callable[[list[str]], int],
    error: type[Exception],
) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")
    old_run = _write_existing_production_run(project_dir)
    original_manifest = (project_dir / "project.yaml").read_bytes()
    original_artifacts = _run_artifacts(old_run)

    with pytest.raises(error):
        produce_project(project_dir, tts, runner)

    assert (project_dir / "project.yaml").read_bytes() == original_manifest
    assert _run_artifacts(old_run) == original_artifacts
    assert list((project_dir / "renders").glob(".*.produce-*")) == []
    assert list((project_dir / "renders").iterdir()) == [old_run], label
    assert not (project_dir / "audio" / "narration.wav").exists(), label
    assert not (project_dir / "render-input.json").exists(), label

    def successful_runner(argv: list[str]) -> int:
        _write_synthetic_output(argv)
        return 0

    output = produce_project(project_dir, SilentTTS(), successful_runner)
    assert output.is_file(), label
    assert read_yaml(project_dir / "project.yaml")["state"] == "awaiting_video_review"


def test_promotion_failure_preserves_active_run_and_allows_retry(
    tmp_path, monkeypatch
) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")
    old_run = _write_existing_production_run(project_dir)
    original_manifest = (project_dir / "project.yaml").read_bytes()
    original_run = _run_artifacts(old_run)

    def successful_runner(argv: list[str]) -> int:
        _write_synthetic_output(argv)
        return 0

    def fail_promotion(staging_dir: Path, run_dir: Path) -> None:
        raise OSError("synthetic promotion failure")

    monkeypatch.setattr(produce_workflow, "_promote_run", fail_promotion, raising=False)
    with pytest.raises(OSError, match="promotion"):
        produce_project(project_dir, SilentTTS(), successful_runner)

    assert (project_dir / "project.yaml").read_bytes() == original_manifest
    assert _run_artifacts(old_run) == original_run
    assert list((project_dir / "renders").glob(".*.produce-*")) == []
    monkeypatch.undo()

    output = produce_project(project_dir, SilentTTS(), successful_runner)
    assert output.is_file()
    assert _run_artifacts(old_run) == original_run


def test_manifest_write_failure_leaves_recoverable_run_for_retry(
    tmp_path, monkeypatch
) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")
    old_run = _write_existing_production_run(project_dir)
    original_manifest = (project_dir / "project.yaml").read_bytes()
    original_run = _run_artifacts(old_run)
    calls: list[list[str]] = []

    def successful_runner(argv: list[str]) -> int:
        calls.append(argv)
        _write_synthetic_output(argv)
        return 0

    def fail_manifest_write(path: Path, data: object) -> None:
        raise OSError("synthetic manifest write failure")

    monkeypatch.setattr(produce_workflow, "write_yaml_atomic", fail_manifest_write)
    with pytest.raises(OSError, match="manifest write"):
        produce_project(project_dir, SilentTTS(), successful_runner)

    assert (project_dir / "project.yaml").read_bytes() == original_manifest
    assert _run_artifacts(old_run) == original_run
    assert (
        len([path for path in (project_dir / "renders").iterdir() if path.is_dir()])
        == 2
    )
    monkeypatch.undo()

    output = produce_project(project_dir, SilentTTS(), successful_runner)
    assert output.is_file()
    assert len(calls) == 1
    assert read_yaml(project_dir / "project.yaml")["state"] == "awaiting_video_review"


@pytest.mark.parametrize("state", ["idea", "awaiting_medical_review"])
def test_produce_dry_run_rejects_invalid_state_without_calling_renderer(
    tmp_path, state
) -> None:
    project_dir = create_project_fixture(tmp_path, state=state)
    calls: list[list[str]] = []

    with pytest.raises(ValueError, match="script_approved"):
        produce_project(project_dir, SilentTTS(), calls.append, dry_run=True)

    assert calls == []


def test_produce_dry_run_rejects_reviewed_project_with_cache_miss(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="awaiting_video_review")
    calls: list[list[str]] = []

    with pytest.raises(ValueError, match="script_approved"):
        produce_project(project_dir, SilentTTS(), calls.append, dry_run=True)

    assert calls == []


RUN_ARTIFACT_NAMES = frozenset(
    {"audio/narration.wav", "render-input.json", "video.mp4", "manifest.json"}
)


def test_produce_publishes_a_populated_run_in_one_rename(tmp_path, monkeypatch) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")
    real_promote = produce_workflow._promote_run
    observed: list[tuple[frozenset[str], bool]] = []

    def observing_promote(staging_dir: Path, run_dir: Path) -> None:
        observed.append((frozenset(_run_artifacts(staging_dir)), run_dir.exists()))
        real_promote(staging_dir, run_dir)

    def successful_runner(argv: list[str]) -> int:
        _write_synthetic_output(argv)
        return 0

    monkeypatch.setattr(produce_workflow, "_promote_run", observing_promote)
    output = produce_project(project_dir, SilentTTS(), successful_runner)

    assert len(observed) == 1
    staged_names, destination_existed = observed[0]
    assert not destination_existed
    assert RUN_ARTIFACT_NAMES <= staged_names
    assert RUN_ARTIFACT_NAMES <= frozenset(_run_artifacts(output.parent))
    assert not (project_dir / "audio" / "narration.wav").exists()
    assert not (project_dir / "render-input.json").exists()
    assert not (project_dir / "renders" / "video.mp4").exists()
    assert not (project_dir / "renders" / "manifest.json").exists()


def test_produce_republishes_over_a_damaged_published_run(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")
    calls: list[list[str]] = []

    def successful_runner(argv: list[str]) -> int:
        calls.append(argv)
        _write_synthetic_output(argv)
        return 0

    output = produce_project(project_dir, SilentTTS(), successful_runner)
    output.unlink()
    project = read_yaml(project_dir / "project.yaml")
    project["state"] = "script_approved"
    write_yaml_atomic(project_dir / "project.yaml", project)

    republished = produce_project(project_dir, SilentTTS(), successful_runner)

    assert republished == output
    assert len(calls) == 2
    assert RUN_ARTIFACT_NAMES <= frozenset(_run_artifacts(republished.parent))
    assert list((project_dir / "renders").iterdir()) == [republished.parent]
    assert read_yaml(project_dir / "project.yaml")["state"] == "awaiting_video_review"


def test_input_hash_changes_for_every_declared_input(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")
    script_data = read_yaml(project_dir / "script" / "script.yaml")
    storyboard_data = read_yaml(project_dir / "storyboard" / "storyboard.yaml")

    script = Script.model_validate(script_data)
    storyboard = Storyboard.model_validate(storyboard_data)
    profile = {"language": "vi", "directness": "clear_and_calm"}
    baseline = _input_hash(script, storyboard, profile, "silent")

    changed_script = script.model_copy(
        update={"title": "Ăn mặn và tăng huyết áp — cập nhật"}
    )
    changed_storyboard = storyboard.model_copy(
        update={"title": "Ăn mặn và tăng huyết áp — cập nhật"}
    )

    assert _input_hash(changed_script, storyboard, profile, "silent") != baseline
    assert _input_hash(script, changed_storyboard, profile, "silent") != baseline
    assert (
        _input_hash(
            script, storyboard, {"language": "vi", "directness": "direct"}, "silent"
        )
        != baseline
    )
    assert _input_hash(script, storyboard, profile, "other") != baseline


def _run_artifacts(run_dir: Path) -> dict[str, bytes]:
    paths = tuple(path for path in run_dir.rglob("*") if path.is_file())
    return {
        path.relative_to(run_dir).as_posix(): path.read_bytes()
        for path in paths
        if path.is_file()
    }


def _write_synthetic_output(argv: list[str]) -> None:
    output = Path(argv[argv.index("--output") + 1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"synthetic-mp4")


def _active_run(project_dir: Path) -> Path:
    input_hash = read_yaml(project_dir / "project.yaml")["artifact_hashes"][
        "production"
    ]
    return project_dir / "renders" / input_hash


def _write_existing_production_run(project_dir: Path) -> Path:
    old_hash = "previous-run"
    project = read_yaml(project_dir / "project.yaml")
    project["artifact_hashes"]["production"] = old_hash
    write_yaml_atomic(project_dir / "project.yaml", project)
    run_dir = project_dir / "renders" / old_hash
    artifacts = {
        run_dir / "audio" / "narration.wav": b"old-audio",
        run_dir / "render-input.json": b'{"old":"input"}',
        run_dir / "manifest.json": b'{"old":"manifest"}',
        run_dir / "video.mp4": b"old-video",
    }
    for path, contents in artifacts.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
    return run_dir
