"""Exercise reviewed FLUX recipes through production's actual renderer boundary."""

import json
from datetime import UTC, datetime
from functools import partial
from io import BytesIO
from pathlib import Path
from subprocess import CompletedProcess

import pytest
from PIL import Image

from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic
from healthvideo.tts.silent import SilentTTS
from healthvideo.visuals.flux import generate_illustration
from healthvideo.workflows import produce
from healthvideo.workflows.gate_review import approve_gate
from tests.helpers import create_v2_project_fixture
from tests.test_flux import illustration_record


@pytest.fixture
def fake_flux(tmp_path, monkeypatch):
    """Replace only the model subprocess, keeping PNG validation/cache/copy real."""
    buffer = BytesIO()
    image = Image.new("RGB", (1080, 1920), "#e0f0de")
    image.putpixel((19, 31), (17, 88, 201))
    image.save(buffer, format="PNG")
    png = buffer.getvalue()

    def model_runner(argv, **kwargs):
        Path(argv[argv.index("--out") + 1]).write_bytes(png)
        return CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(produce, "generate_illustration", partial(
        generate_illustration, runner=model_runner, cache_dir=tmp_path / "flux-cache",
    ))
    from tests.workflows.test_produce_illustrations import fake_contact_sheet
    fake_contact_sheet.__wrapped__(monkeypatch)
    return png


def test_flux_recipe_reaches_scene_renderer_with_identical_bytes_and_provenance(
    tmp_path, fake_flux,
):
    # Dropping whiteboard refs during retiming or copying a substituted image
    # must fail at the renderer boundary, before the synthetic output is written.
    project = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW,
    )
    revision = project / "revisions/001"
    manifest_path = revision / "assets/asset-manifest.yaml"
    manifest = read_yaml(manifest_path)
    recipe = illustration_record()
    manifest["assets"].append(recipe)
    write_yaml_atomic(manifest_path, manifest)
    board_path = revision / "storyboard/storyboard.yaml"
    board = read_yaml(board_path)
    reference = {"path": recipe["path"], "role": "whiteboard"}
    illustrated_scene = next(scene for scene in board["scenes"] if scene["visual"] == "whiteboard")
    illustrated_scene["visual_assets"] = [reference]
    write_yaml_atomic(board_path, board)
    approve_gate(project, GateKind.MEDICAL, reviewer="synthetic test doctor",
                 now=datetime(2026, 10, 23, tzinfo=UTC))
    reviewed_manifest_bytes = manifest_path.read_bytes()
    reviewed_board_bytes = board_path.read_bytes()
    assert not (revision / recipe["path"]).exists()
    rendered_scenes = []

    def renderer(argv):
        render_input = json.loads(Path(argv[argv.index("--props") + 1]).read_text(encoding="utf-8"))
        public_dir = Path(argv[argv.index("--public-dir") + 1])
        scene = next(scene for scene in render_input["scenes"]
                     if scene["id"] == illustrated_scene["id"])
        assert scene["visual"] == "whiteboard"
        assert scene["visual_assets"] == [{**reference, "pose": None}]
        assert (public_dir / scene["visual_assets"][0]["path"]).read_bytes() == fake_flux
        assert (revision / recipe["path"]).read_bytes() == fake_flux
        rendered_scenes.append(scene)
        Path(argv[argv.index("--output") + 1]).write_bytes(b"synthetic video")
        return 0

    class CheckedTTS(SilentTTS):
        def synthesize(self, request, output):
            # The synchronous FLUX subprocess must finish before another GPU stage.
            assert (revision / recipe["path"]).read_bytes() == fake_flux
            return super().synthesize(request, output)

    output = produce.produce_project(project, CheckedTTS(), renderer, music=False)

    assert len(rendered_scenes) == 1
    assert output.is_file()
    assert (revision / "renders" / recipe["path"]).read_bytes() == fake_flux
    promoted_input = json.loads((revision / "renders/render-input.json").read_text(encoding="utf-8"))
    assert next(scene for scene in promoted_input["scenes"]
                if scene["id"] == illustrated_scene["id"]) == rendered_scenes[0]
    assert manifest_path.read_bytes() == reviewed_manifest_bytes
    assert board_path.read_bytes() == reviewed_board_bytes
    entry, = read_yaml(revision / "renders/license-ledger.yaml")["entries"]
    assert {key: entry[key] for key in ("path", "source", "license", "creator", "revision")} == {
        key: recipe[key] for key in ("path", "source", "license", "creator", "revision")
    }
    digest = sha256_file(revision / recipe["path"])
    assert entry["sha256"] == digest
    render_manifest = json.loads((revision / "renders/render-manifest.json").read_text(encoding="utf-8"))
    assert render_manifest["asset_sha256"][recipe["path"]] == digest
    assert render_manifest["generated_visual_sha256"][recipe["path"]] == digest
    assert read_yaml(project / "project.yaml")["state"] == "production_in_progress"
