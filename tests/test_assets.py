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
            AssetKind.DATA_CHART,
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


def test_chart_role_requires_semantic_owned_data_chart_and_chart_scene(
    tmp_path: Path,
) -> None:
    data = b"<svg id='declared-chart'/>"
    chart = record("assets/chart.svg", data, tmp_path, AssetKind.DATA_CHART).model_copy(
        update={"semantic": True, "storyboard_role": "chart"}
    )
    ref = VisualAssetRef(path=chart.path, role="chart")
    chart_board = Storyboard(
        title="PHY",
        visual_budget_profile="m6_5_v1",
        visual_budget_override={
            "rationale": "Resolver-only chart fixture.",
            "whiteboard_svg": {"min_percent": 0, "max_percent": 0},
            "chart_crop": {"min_percent": 100, "max_percent": 100},
            "ai_clip": {"min_percent": 0, "max_percent": 0},
        },
        scenes=(
            Scene(
                id="S01",
                start_frame=0,
                duration_frames=90,
                narration="Chart",
                visual="chart",
                visual_assets=(ref,),
            ),
        ),
    )
    assert referenced_storyboard_assets(
        tmp_path, chart_board, AssetManifest(assets=(chart,))
    ) == {chart.path: tmp_path / chart.path}

    for changed in (
        chart.model_copy(update={"storyboard_role": None}),
        chart.model_copy(update={"semantic": False, "kind": AssetKind.BACKGROUND}),
    ):
        with pytest.raises(ValueError, match="chart|role|kind|classification"):
            referenced_storyboard_assets(
                tmp_path, chart_board, AssetManifest(assets=(changed,))
            )
    wrong_scene = chart_board.model_copy(
        update={
            "scenes": (chart_board.scenes[0].model_copy(update={"visual": "whiteboard"}),)
        }
    )
    with pytest.raises(ValueError, match="chart"):
        referenced_storyboard_assets(
            tmp_path, wrong_scene, AssetManifest(assets=(chart,))
        )
    reused = chart_board.model_copy(
        update={
            "scenes": (
                chart_board.scenes[0],
                chart_board.scenes[0].model_copy(update={"id": "S02", "start_frame": 90}),
            )
        }
    )
    with pytest.raises(ValueError, match="exactly one scene"):
        referenced_storyboard_assets(
            tmp_path, reused, AssetManifest(assets=(chart,))
        )


def test_enabled_chart_scene_requires_exactly_one_chart_ref(tmp_path: Path) -> None:
    base = Storyboard(
        title="PHY",
        visual_budget_profile="m6_5_v1",
        scenes=(
            Scene(
                id="S01",
                start_frame=0,
                duration_frames=90,
                narration="Chart",
                visual="chart",
            ),
        ),
    )
    with pytest.raises(ValueError, match="exactly one"):
        referenced_storyboard_assets(tmp_path, base, AssetManifest())

    records = []
    refs = []
    for index in (1, 2):
        path = f"assets/chart-{index}.svg"
        records.append(
            record(path, f"<svg>{index}</svg>".encode(), tmp_path, AssetKind.DATA_CHART).model_copy(
                update={"semantic": True, "storyboard_role": "chart"}
            )
        )
        refs.append(VisualAssetRef(path=path, role="chart"))
    duplicate = base.model_copy(
        update={"scenes": (base.scenes[0].model_copy(update={"visual_assets": tuple(refs)}),)}
    )
    with pytest.raises(ValueError, match="exactly one"):
        referenced_storyboard_assets(
            tmp_path, duplicate, AssetManifest(assets=tuple(records))
        )


def test_chart_owned_manifest_record_cannot_be_orphaned(tmp_path: Path) -> None:
    chart = record(
        "assets/chart.svg", b"<svg/>", tmp_path, AssetKind.DATA_CHART
    ).model_copy(update={"semantic": True, "storyboard_role": "chart"})
    with pytest.raises(ValueError, match="not referenced"):
        referenced_storyboard_assets(
            tmp_path,
            Storyboard(title="Legacy", scenes=()),
            AssetManifest(assets=(chart,)),
        )
