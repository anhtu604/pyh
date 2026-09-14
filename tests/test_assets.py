from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest

from healthvideo.assets import referenced_storyboard_assets
from healthvideo.domain.ai_clip import AIClipProvenance
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


def ai_record(
    path: str, data: bytes, revision: Path, *, semantic: bool
) -> AssetRecord:
    target = revision / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    digest = sha256(data).hexdigest()
    return AssetRecord(
        path=path,
        kind=AssetKind.AI_CLIP,
        semantic=semantic,
        classification_reason=None if semantic else "Decorative transition only.",
        sha256=digest,
        source="operator supplied provider record",
        license="operator supplied terms record",
        creator="operator supplied creator",
        revision="001",
        rights_required=True,
        storyboard_role="ai_clip",
        ai_provenance=AIClipProvenance(
            provider="google_vertex_ai",
            model="veo-3.1-fast-generate-001",
            prompt="Minh họa món ăn ít muối.",
            generated_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
            request_sha256="a" * 64,
            output_sha256=digest,
            mime_type="video/mp4",
            container="mp4",
            width=1080,
            height=1920,
            source_fps=24,
            duration_ms=4000,
            source_frame_count=96,
        ),
    )


def ai_board(
    ref: VisualAssetRef | None,
    *,
    semantic: bool,
    second_scene: bool = False,
) -> Storyboard:
    assets = () if ref is None else (ref,)
    first = Scene(
        id="S01",
        start_frame=0,
        duration_frames=120,
        narration="Minh họa.",
        claim_id="C01" if semantic else None,
        source_marker="[1]" if semantic else None,
        visual="ai_clip",
        visual_assets=assets,
    )
    scenes = (first,)
    if second_scene:
        scenes += (first.model_copy(update={"id": "S02", "start_frame": 120}),)
    return Storyboard(
        title="AI clip",
        visual_budget_profile="m6_5_v1",
        visual_budget_override={
            "rationale": "Resolver-only AI fixture.",
            "whiteboard_svg": {"min_percent": 0, "max_percent": 0},
            "chart_crop": {"min_percent": 0, "max_percent": 0},
            "ai_clip": {"min_percent": 100, "max_percent": 100},
        },
        scenes=scenes,
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


@pytest.mark.parametrize("semantic", [True, False])
def test_ai_clip_role_resolves_exact_owned_bytes(
    tmp_path: Path, semantic: bool
) -> None:
    data = b"synthetic-ai-clip"
    record = ai_record("assets/ai-clips/S01.mp4", data, tmp_path, semantic=semantic)
    ref = VisualAssetRef(path=record.path, role="ai_clip")

    assert referenced_storyboard_assets(
        tmp_path, ai_board(ref, semantic=semantic), AssetManifest(assets=(record,))
    ) == {record.path: tmp_path / record.path}

    (tmp_path / record.path).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="sha256"):
        referenced_storyboard_assets(
            tmp_path, ai_board(ref, semantic=semantic), AssetManifest(assets=(record,))
        )


def test_enabled_ai_scene_requires_exactly_one_ai_ref(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        referenced_storyboard_assets(
            tmp_path, ai_board(None, semantic=False), AssetManifest()
        )

    records = tuple(
        ai_record(
            f"assets/ai-clips/S0{index}.mp4",
            f"clip-{index}".encode(),
            tmp_path,
            semantic=False,
        )
        for index in (1, 2)
    )
    refs = tuple(VisualAssetRef(path=item.path, role="ai_clip") for item in records)
    duplicate = ai_board(refs[0], semantic=False).model_copy(
        update={
            "scenes": (
                ai_board(refs[0], semantic=False).scenes[0].model_copy(
                    update={"visual_assets": refs}
                ),
            )
        }
    )
    with pytest.raises(ValueError, match="exactly one"):
        referenced_storyboard_assets(
            tmp_path, duplicate, AssetManifest(assets=records)
        )


def test_ai_clip_role_requires_ai_scene_and_one_scene_owner(tmp_path: Path) -> None:
    record = ai_record(
        "assets/ai-clips/S01.mp4", b"synthetic-ai-clip", tmp_path, semantic=False
    )
    ref = VisualAssetRef(path=record.path, role="ai_clip")
    wrong_scene = ai_board(ref, semantic=False).model_copy(
        update={
            "scenes": (
                ai_board(ref, semantic=False).scenes[0].model_copy(
                    update={"visual": "whiteboard"}
                ),
            )
        }
    )
    with pytest.raises(ValueError, match="ai_clip"):
        referenced_storyboard_assets(
            tmp_path, wrong_scene, AssetManifest(assets=(record,))
        )

    with pytest.raises(ValueError, match="exactly one scene"):
        referenced_storyboard_assets(
            tmp_path,
            ai_board(ref, semantic=False, second_scene=True),
            AssetManifest(assets=(record,)),
        )


def test_ai_clip_semantic_shape_matches_asset_classification(tmp_path: Path) -> None:
    semantic = ai_record(
        "assets/ai-clips/semantic.mp4", b"semantic", tmp_path, semantic=True
    )
    decorative = ai_record(
        "assets/ai-clips/decorative.mp4", b"decorative", tmp_path, semantic=False
    )
    semantic_ref = VisualAssetRef(path=semantic.path, role="ai_clip")
    decorative_ref = VisualAssetRef(path=decorative.path, role="ai_clip")

    for missing in ({"claim_id": None}, {"source_marker": None}):
        base = ai_board(semantic_ref, semantic=True)
        invalid = base.model_copy(
            update={
                "scenes": (base.scenes[0].model_copy(update=missing),),
            }
        )
        with pytest.raises(ValueError, match="claim_id|source_marker"):
            referenced_storyboard_assets(
                tmp_path, invalid, AssetManifest(assets=(semantic,))
            )

    base = ai_board(decorative_ref, semantic=False)
    for binding in ({"claim_id": "C01"}, {"source_marker": "[1]"}):
        invalid = base.model_copy(
            update={
                "scenes": (base.scenes[0].model_copy(update=binding),),
            }
        )
        with pytest.raises(ValueError, match="decorative"):
            referenced_storyboard_assets(
                tmp_path, invalid, AssetManifest(assets=(decorative,))
            )
