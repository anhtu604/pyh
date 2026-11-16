"""Mascot editorial warnings and the registered artwork to render-props path."""

import json
from pathlib import Path

import pytest

from healthvideo.domain.storyboard import Scene, Storyboard, VisualAssetRef
from healthvideo.storage.files import read_yaml


def _board(*, mascot=False, visual="whiteboard", format_profile="youtube_long"):
    data = {"id": "S01", "start_frame": 0, "duration_frames": 150, "narration": "Synthetic hook.",
            "visual": visual, "on_screen_text": "Synthetic hook", "chapter_id": "CH01"}
    if mascot:
        data["visual_assets"] = [{"path": "assets/welcome.png", "role": "mascot", "pose": "welcome"}]
    return Storyboard(title="Synthetic", format_profile=format_profile,
                      scenes=(Scene.model_validate(data),))


def test_missing_mascot_warning_is_long_video_only():
    from healthvideo.domain.mascot_usage import lint_mascot_usage

    issues = lint_mascot_usage(_board())
    assert [issue.rule for issue in issues] == ["mascot_missing"]
    assert all(issue.severity == "warn" for issue in issues)
    assert not lint_mascot_usage(_board(format_profile="vertical_clip"))
    assert not lint_mascot_usage(_board(mascot=True))


@pytest.mark.parametrize("visual", ["anatomy_animation", "chart"])
def test_dense_scene_warns_without_blocking(visual):
    from healthvideo.domain.mascot_usage import lint_mascot_usage

    base = read_yaml(Path("tests/fixtures/golden-project-v2/revisions/001/storyboard/storyboard.yaml"))
    scene = next(Scene.model_validate(s) for s in base["scenes"] if s.get("anatomy"))
    # Keep a genuine anatomy scene; other dense visuals need no semantic payload for this lint.
    if visual != "anatomy_animation":
        scene = _board(mascot=True).scenes[0].model_copy(update={"visual": visual})
    scene = scene.model_copy(update={"visual_assets": (
        VisualAssetRef(path="assets/welcome.png", role="mascot", pose="welcome"),)})
    issues = lint_mascot_usage(Storyboard(title="Synthetic", scenes=(scene,)))
    assert [issue.rule for issue in issues] == ["mascot_dense_scene"]
    assert issues[0].severity == "warn"
    assert scene.id in issues[0].excerpt


def test_submission_records_mascot_warning_and_remains_draft_ready(tmp_path):
    from healthvideo.domain.brand import MascotPose
    from healthvideo.workflows.draft import submit_draft
    from healthvideo.workflows.storyboard_design import submit_storyboard_design
    from healthvideo.workflows.visual_assets import create_mascot_reaction_asset
    from tests.workflows.test_draft import SOURCE, _evidence_ready

    project = _evidence_ready(tmp_path)
    submit_draft(project, SOURCE / "script/script.yaml", SOURCE / "storyboard/storyboard.yaml",
                 SOURCE / "assets/asset-manifest.yaml")
    rev = project / "revisions/001"
    board = read_yaml(rev / "storyboard/storyboard.yaml")
    scene = next(s for s in board["scenes"] if s.get("anatomy"))
    create_mascot_reaction_asset(project, scene_id=scene["id"], asset_name="caution",
                                 pose=MascotPose.CAUTION)
    result = submit_storyboard_design(project, rev / "storyboard/storyboard.yaml",
                                      rev / "assets/asset-manifest.yaml")
    issues = json.loads((rev / "reviews/style-lint.json").read_text(encoding="utf-8"))["issues"]
    assert any(i["rule"] == "mascot_dense_scene" and i["severity"] == "warn" for i in issues)
    assert result.state.value == "draft_ready"
    assert not (rev / "reviews/medical-approval.yaml").exists()


def test_four_registered_brand_poses_validate_and_reach_both_render_formats(tmp_path, monkeypatch):
    from healthvideo.assets import referenced_storyboard_assets
    from healthvideo.domain.asset_manifest import AssetManifest, validate_asset_manifest
    from healthvideo.domain.brand import MascotPose, load_brand_profile
    from healthvideo.domain.license_ledger import LicenseLedger, validate_license_ledger
    from healthvideo.render.input import build_render_input
    from healthvideo.storage.files import sha256_file, write_yaml_atomic
    from healthvideo.workflows import visual_assets
    from healthvideo.workflows.draft import submit_draft
    from healthvideo.workflows.long_form import clip_render_input
    from healthvideo.workflows.produce import _copy_v2_assets
    from healthvideo.workflows.visual_assets import create_mascot_reaction_asset
    from tests.workflows.test_draft import SOURCE, _evidence_ready

    project = _evidence_ready(tmp_path)
    submit_draft(project, SOURCE / "script/script.yaml", SOURCE / "storyboard/storyboard.yaml",
                 SOURCE / "assets/asset-manifest.yaml")
    rev = project / "revisions/001"
    poses = {0: "welcome", 4: "myth_bust", 8: "caution", 119: "thumbs_up"}
    logo_refs = Storyboard.model_validate(read_yaml(
        rev / "storyboard/storyboard.yaml")).scenes[-1].visual_assets
    scenes = tuple(Scene(
        id=f"S{i:03}", start_frame=i * 150, duration_frames=150,
        narration={0: "Synthetic opening.", 4: "Synthetic myth correction.",
                   8: "Synthetic warning.", 119: "Synthetic CTA."}.get(i, "Synthetic summary."),
        visual="brand_outro" if i == 119 else "whiteboard",
        on_screen_text="Synthetic", chapter_id="CH01",
        visual_assets=logo_refs if i == 119 else (),
    ) for i in range(120))
    board = Storyboard(title="Synthetic mascot journey", format_profile="youtube_long", scenes=scenes)
    write_yaml_atomic(rev / "storyboard/storyboard.yaml", board.model_dump(mode="json"))
    brand_path = Path("profiles/brand.vi.yaml")
    monkeypatch.setattr(visual_assets, "BRAND_PROFILE_PATH", brand_path)
    brand = load_brand_profile(brand_path)
    for index, pose in poses.items():
        create_mascot_reaction_asset(project, scene_id=scenes[index].id,
                                     asset_name=pose, pose=MascotPose(pose))
    board = Storyboard.model_validate(read_yaml(rev / "storyboard/storyboard.yaml"))
    manifest = AssetManifest.model_validate(read_yaml(rev / "assets/asset-manifest.yaml"))
    validate_asset_manifest(rev, manifest)
    validate_license_ledger(manifest, LicenseLedger.model_validate(
        read_yaml(rev / "assets/license-ledger.yaml")), "001")
    resolved = referenced_storyboard_assets(rev, board, manifest)
    staging = tmp_path / "render-staging"
    _copy_v2_assets(rev, staging, board, {path: sha256_file(file) for path, file in resolved.items()})
    for pose in poses.values():
        record = next(a for a in manifest.assets if a.path == f"assets/{pose}.png")
        assert record.sha256 == brand.mascot.artwork[MascotPose(pose)].sha256
        assert record.sha256 == sha256_file(resolved[record.path])
        assert record.license == brand.assets.license
        assert record.creator == brand.assets.creator
        assert record.source == "built_in:pyh-mascot"
        assert record.storyboard_role == "mascot" and not record.semantic
        assert sha256_file(staging / record.path) == record.sha256
    long = build_render_input(board, "audio/long.wav")
    assert (long.width, long.height) == (1920, 1080)
    assert [a.pose.value for s in long.scenes for a in s.visual_assets
            if a.role == "mascot"] == list(poses.values())
    # One registered mascot per extracted clip; the default branded CTA is separate.
    for index, pose in poses.items():
        selected = (board.scenes[index], *board.scenes[20:31])
        clip = clip_render_input(board, selected, "audio/clip.wav", brand=brand)
        assert (clip.width, clip.height) == (1080, 1920)
        ref = next(a for a in clip.scenes[0].visual_assets if a.role == "mascot")
        assert ref.pose.value == pose
        assert ref.path == f"assets/{pose}.png"
        assert clip.youtube_cta.mascot_path == "clips/cta/welcome.png"
