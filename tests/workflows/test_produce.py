import json

import pytest

from healthvideo.storage.files import read_yaml
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.produce import produce_project
from tests.helpers import create_project_fixture


def test_produce_reuses_matching_artifact_hash(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")
    calls: list[list[str]] = []

    def fake_runner(argv: list[str]) -> int:
        calls.append(argv)
        output = project_dir / "renders" / "video.mp4"
        output.write_bytes(b"synthetic-mp4")
        return 0

    first = produce_project(project_dir, SilentTTS(), fake_runner)
    second = produce_project(project_dir, SilentTTS(), fake_runner)

    assert first == project_dir / "renders" / "video.mp4"
    assert second == first
    assert len(calls) == 1
    assert read_yaml(project_dir / "project.yaml")["state"] == "awaiting_video_review"


def test_produce_rejects_reviewed_project_when_cached_output_is_missing(
    tmp_path,
) -> None:
    project_dir = create_project_fixture(tmp_path, state="awaiting_video_review")

    with pytest.raises(ValueError, match="script_approved"):
        produce_project(project_dir, SilentTTS(), lambda argv: 0)


def test_produce_dry_run_does_not_mutate_project_or_run_renderer(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")
    original_manifest = (project_dir / "project.yaml").read_bytes()
    calls: list[list[str]] = []

    output = produce_project(project_dir, SilentTTS(), calls.append, dry_run=True)

    assert output == project_dir / "renders" / "video.mp4"
    assert len(calls) == 1
    assert calls[0][0:2] == ["pnpm", "--dir"]
    assert calls[0][3] == "render"
    assert calls[0][-2:] == ["--public-dir", str(project_dir)]
    assert not output.exists()
    assert not (project_dir / "audio" / "narration.wav").exists()
    assert not (project_dir / "render-input.json").exists()
    assert (project_dir / "project.yaml").read_bytes() == original_manifest


def test_produce_writes_render_input_and_manifest_with_canonical_hash(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")

    def fake_runner(argv: list[str]) -> int:
        (project_dir / "renders" / "video.mp4").write_bytes(b"synthetic-mp4")
        return 0

    produce_project(project_dir, SilentTTS(), fake_runner)

    render_input = json.loads(
        (project_dir / "render-input.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (project_dir / "renders" / "manifest.json").read_text(encoding="utf-8")
    )
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
        (project_dir / "renders" / "video.mp4").write_bytes(b"synthetic-mp4")
        return 0

    produce_project(project_dir, SilentTTS(), fake_runner)
    profile.write_text("language: vi\ndirectness: direct\n", encoding="utf-8")

    with pytest.raises(ValueError, match="script_approved"):
        produce_project(project_dir, SilentTTS(), fake_runner)
