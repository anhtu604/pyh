import json
import shutil
import wave
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from healthvideo import cli
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.storage.files import read_yaml, sha256_file
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows import produce
from healthvideo.workflows.gate_review import approve_gate, medical_reviewed_paths
from tests.helpers import create_v2_project_fixture


@pytest.fixture
def approved_project(tmp_path):
    project = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    approve_gate(project, GateKind.MEDICAL, reviewer="doctor",
                 now=datetime(2026, 9, 12, 8, 0, tzinfo=UTC))
    return project


def renderer(argv):
    Path(argv[argv.index("--output") + 1]).write_bytes(b"video")
    return 0


def fake_generate(mood, *, seconds, out, seed, **kwargs):
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as audio:
        audio.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\x01\x00" * 2 * 480)
    return out


@pytest.fixture
def fake_music(monkeypatch):
    monkeypatch.setattr(produce, "generate_music", fake_generate, raising=False)
    monkeypatch.setattr(produce, "mix_with_ducking",
                        lambda narration, music, *, out, **kw: shutil.copyfile(narration, out),
                        raising=False)


def test_music_disabled_flag(approved_project, monkeypatch):
    monkeypatch.setattr(produce, "generate_music", lambda *a, **k: pytest.fail("music disabled"), raising=False)
    monkeypatch.setattr(cli, "run_render_argv", renderer)
    result = CliRunner().invoke(cli.app, ["produce", str(approved_project), "--no-music"])
    assert result.exit_code == 0, result.output
    renders = approved_project / "revisions/001/renders"
    assert not (renders / "audio/music.wav").exists()
    assert json.loads((renders / "render-manifest.json").read_text())["music"] is None


def test_music_license_recorded(approved_project, fake_music):
    revision = approved_project / "revisions/001"
    before = {name: sha256_file(path) for name, path in medical_reviewed_paths(revision).items()
              if path.is_file()}
    produce.produce_project(approved_project, SilentTTS(), renderer)
    renders = revision / "renders"
    manifest = json.loads((renders / "render-manifest.json").read_text())
    entry = read_yaml(renders / "license-ledger.yaml")["entries"][0]
    assert entry["license"] == "MIT"
    assert entry["source"] == "generated:ace-step-1.5"
    assert entry["sha256"] == sha256_file(renders / "audio/music.wav")
    assert manifest["music"]["sha256"] == entry["sha256"]
    assert manifest["music"]["music_db"] == -20.0
    assert manifest["music"]["duck_db"] == -12.0
    assert (renders / "audio/narration-voice.wav").is_file()
    assert before == {name: sha256_file(path) for name, path in medical_reviewed_paths(revision).items()
                      if path.is_file()}
    # Hash all generated audio and provenance on reuse, including the original voice.
    assert produce.produce_project(approved_project, SilentTTS(),
                                   lambda _: pytest.fail("cache missed")) == renders / "video.mp4"
    (renders / "audio/music.wav").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="medically_approved"):
        produce.produce_project(approved_project, SilentTTS(), renderer)


def test_music_failure_blocks_production_with_clear_error(approved_project, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("ACE-Step music generation failed: CUDA out of memory")

    monkeypatch.setattr(produce, "generate_music", fail, raising=False)
    with pytest.raises(RuntimeError, match="ACE-Step.*CUDA out of memory"):
        produce.produce_project(approved_project, SilentTTS(), renderer)
    assert read_yaml(approved_project / "project.yaml")["state"] == "medically_approved"
    assert not (approved_project / "revisions/001/renders/video.mp4").exists()


def test_music_setting_invalidates_render(approved_project, fake_music):
    produce.produce_project(approved_project, SilentTTS(), renderer)
    with pytest.raises(ValueError, match="medically_approved"):
        produce.produce_project(approved_project, SilentTTS(), renderer, music=False)


def test_music_mood_from_outline(tmp_path):
    from healthvideo.domain.outline import Outline
    from healthvideo.storage.files import write_yaml_atomic

    outline = Outline.model_validate({
        "title": "Test", "mood": "calm",
        "chapters": [{"id": f"CH{i:02}", "title": "Test", "goal": "Test",
                      "target_seconds": 150, "mood": "gentle piano"} for i in range(1, 5)],
    })
    write_yaml_atomic(tmp_path / "script/outline.yaml", outline.model_dump(mode="json"))
    assert produce._music_mood(tmp_path) == "calm; gentle piano"


def test_music_manifest_parameters_verified_on_reuse(approved_project, fake_music):
    produce.produce_project(approved_project, SilentTTS(), renderer)
    manifest_path = approved_project / "revisions/001/renders/render-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["music"]["duck_db"] = -1.0
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="medically_approved"):
        produce.produce_project(approved_project, SilentTTS(), renderer)
