from hashlib import sha256
from pathlib import Path

import pytest

from healthvideo.assets import referenced_storyboard_assets
from healthvideo.domain.asset_manifest import AssetKind, AssetManifest, AssetRecord
from healthvideo.domain.storyboard import Scene, Storyboard, VisualAssetRef


def record(path: str, data: bytes, revision: Path, kind: AssetKind) -> AssetRecord:
    target = revision / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return AssetRecord(
        path=path,
        kind=kind,
        semantic=kind
        in {
            AssetKind.MASCOT_MEDICAL_ANNOTATION,
            AssetKind.MEDICAL_TEXT,
            AssetKind.MEDICAL_DIAGRAM,
        },
        sha256=sha256(data).hexdigest(),
        source="built_in:phy",
        license="PHY internal",
        creator="Protect Your Health",
        revision="001",
    )


def board(ref: VisualAssetRef) -> Storyboard:
    return Storyboard(
        title="PHY",
        scenes=(
            Scene(
                id="S01",
                start_frame=0,
                duration_frames=1350,
                narration="Visual",
                visual="whiteboard",
                visual_assets=(ref,),
            ),
        ),
    )


def test_storyboard_asset_resolver_rejects_undeclared_path(tmp_path: Path) -> None:
    storyboard = board(
        VisualAssetRef(path="assets/missing.svg", role="mascot", pose="welcome")
    )
    with pytest.raises(ValueError, match="not declared"):
        referenced_storyboard_assets(tmp_path, storyboard, AssetManifest())


def test_storyboard_asset_resolver_validates_role_and_all_bytes(tmp_path: Path) -> None:
    ref = VisualAssetRef(path="assets/guide.svg", role="mascot", pose="welcome")
    wrong = record(ref.path, b"<svg/>", tmp_path, AssetKind.MEDICAL_TEXT)
    with pytest.raises(ValueError, match="role.*kind"):
        referenced_storyboard_assets(tmp_path, board(ref), AssetManifest(assets=(wrong,)))

    right = record(ref.path, b"<svg id='guide'/>", tmp_path, AssetKind.MASCOT_REACTION)
    resolved = referenced_storyboard_assets(tmp_path, board(ref), AssetManifest(assets=(right,)))
    assert resolved == {ref.path: tmp_path / ref.path}
    (tmp_path / ref.path).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="sha256"):
        referenced_storyboard_assets(tmp_path, board(ref), AssetManifest(assets=(right,)))


def test_storyboard_asset_resolver_rejects_orphan_scene_asset(tmp_path: Path) -> None:
    orphan = record(
        "assets/orphan.svg", b"<svg/>", tmp_path, AssetKind.MASCOT_REACTION
    ).model_copy(update={"storyboard_role": "mascot"})
    empty = Storyboard(
        title="PHY",
        scenes=(
            Scene(
                id="S01",
                start_frame=0,
                duration_frames=1350,
                narration="Legacy",
                visual="whiteboard",
            ),
        ),
    )
    with pytest.raises(ValueError, match="not referenced"):
        referenced_storyboard_assets(tmp_path, empty, AssetManifest(assets=(orphan,)))


def test_storyboard_asset_resolver_keeps_legacy_unowned_records_compatible(
    tmp_path: Path,
) -> None:
    legacy = record(
        "assets/legacy.svg", b"<svg/>", tmp_path, AssetKind.MASCOT_REACTION
    )
    assert referenced_storyboard_assets(
        tmp_path, Storyboard(title="PHY"), AssetManifest(assets=(legacy,))
    ) == {}
