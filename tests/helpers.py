import json
from datetime import datetime
from pathlib import Path
from typing import Any

from healthvideo.domain.explainer import Explainer
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.storage.explainer import write_explainer
from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic
from healthvideo.tts.base import TTSRequest
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.gate_review import approve_gate

FIXTURE_PRODUCTION_HASH = "synthetic-production-run"
FIXTURE_REVIEWER = "BS Nguyễn Văn An"


def _write_json(path: Path, data: dict[str, Any]) -> None:
    serialized = json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    path.write_text(f"{serialized}\n", encoding="utf-8")


def synthesize_fixture_audio(project_dir: Path) -> Path:
    """Create a local silent WAV for a copied fixture without tracking generated audio."""
    script = read_yaml(project_dir / "script" / "script.yaml")
    narration = " ".join(line["text"] for line in script["lines"])
    output = project_dir / "audio" / "narration.wav"
    return (
        SilentTTS()
        .synthesize(TTSRequest(text=narration, language=script["language"]), output)
        .audio_file
    )


def create_v2_project_fixture(
    root: Path, *, state: WorkflowState = WorkflowState.DRAFT_READY
) -> Path:
    """Build a synthetic schema-2.0 project at `revisions/001`, ready for gate tests."""
    state = WorkflowState(state)
    project_dir = root / "muoi-va-huyet-ap-v2"
    revision_root = project_dir / "revisions" / "001"
    for name in ("topic", "evidence", "script", "storyboard", "assets"):
        (revision_root / name).mkdir(parents=True, exist_ok=True)

    asset_bytes = b"<svg xmlns='http://www.w3.org/2000/svg'><text>synthetic</text></svg>"
    (revision_root / "assets" / "evidence-r01.svg").write_bytes(asset_bytes)
    asset_sha256 = sha256_file(revision_root / "assets" / "evidence-r01.svg")

    write_yaml_atomic(
        revision_root / "topic" / "card.yaml",
        {
            "schema_version": "2.0",
            "synthetic_test_record": True,
            "slug": "muoi-va-huyet-ap",
            "title": "Ăn mặn và tăng huyết áp",
            "origin": "test_fixture",
        },
    )
    write_yaml_atomic(
        revision_root / "evidence" / "ledger.yaml",
        {
            "schema_version": "1.0",
            "records": [
                {
                    "id": "R01",
                    "title": "Bản ghi tổng hợp cho test: giảm muối và huyết áp",
                    "authors": ["Nguyen A", "Tran B"],
                    "year": 2020,
                    "study_design": "tổng quan hệ thống",
                    "doi": "10.0000/synthetic-salt-bp",
                    "synthetic_test_record": True,
                }
            ],
            "claims": [
                {
                    "id": "C01",
                    "text_public": "Giảm muối giúp hạ huyết áp ở nhiều người.",
                    "text_technical": "Giảm natri ăn vào liên quan tới hạ huyết áp.",
                    "type": "evidence",
                    "sources": ["R01"],
                    "synthetic_test_record": True,
                }
            ],
        },
    )
    write_yaml_atomic(
        revision_root / "script" / "script.yaml",
        {
            "schema_version": "1.0",
            "title": "Ăn mặn và tăng huyết áp",
            "language": "vi",
            "lines": [
                {
                    "id": "L01",
                    "text": "Ăn mặn có thể làm huyết áp tăng.",
                    "claim_id": "C01",
                    "source_marker": "[1]",
                    "delivery": {"intent": "explain"},
                }
            ],
        },
    )
    write_yaml_atomic(
        revision_root / "storyboard" / "storyboard.yaml",
        {
            "schema_version": "1.0",
            "title": "Ăn mặn và tăng huyết áp",
            "scenes": [
                {
                    "id": "S01",
                    "start_frame": 0,
                    "duration_frames": 225,
                    "script_line_id": "L01",
                    "narration": "Ăn mặn có thể làm huyết áp tăng.",
                    "claim_id": "C01",
                    "source_marker": "[1]",
                    "visual": "evidence_highlight",
                    "evidence_highlight": {
                        "image": "assets/evidence-r01.svg",
                        "quote": "Synthetic evidence fixture for tests only.",
                        "x": 0.1,
                        "y": 0.2,
                        "width": 0.8,
                        "height": 0.2,
                    },
                }
            ],
        },
    )
    write_yaml_atomic(
        revision_root / "assets" / "asset-manifest.yaml",
        {
            "schema_version": "2.0",
            "assets": [
                {
                    "path": "assets/evidence-r01.svg",
                    "kind": "evidence_highlight",
                    "semantic": True,
                    "classification_reason": "Evidence highlight changes the medical meaning.",
                    "sha256": asset_sha256,
                    "source": "synthetic_test_fixture",
                    "license": "synthetic_test_only",
                    "creator": "repository_fixture",
                    "revision": "001",
                }
            ],
        },
    )
    write_yaml_atomic(
        project_dir / "project.yaml",
        {
            "schema_version": "2.0",
            "slug": "muoi-va-huyet-ap",
            "language": "vi",
            "state": WorkflowState.DRAFT_READY.value,
            "active_revision": "001",
            "artifact_hashes": {},
        },
    )
    complete_explain_first_fixture(revision_root)
    if state is not WorkflowState.DRAFT_READY:
        _advance_v2_state(project_dir, state)
    return project_dir


def create_long_form_project_fixture(root: Path) -> Path:
    """youtube_long v2 project awaiting medical review: 6 scenes, 5 chapters, 3 clips.

    Claim C01 (scene S01) carries caveat C02 (scene S02): a clip showing S01 must show S02.
    """
    project_dir = create_v2_project_fixture(root, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    revision_root = project_dir / "revisions" / "001"

    ledger_path = revision_root / "evidence" / "ledger.yaml"
    ledger = read_yaml(ledger_path)
    ledger["claims"][0]["caveat_claim_ids"] = ["C02"]
    ledger["claims"].append(
        {
            "id": "C02",
            "text_public": "Mức giảm khác nhau giữa từng người.",
            "text_technical": "Đáp ứng huyết áp với giảm natri không đồng nhất.",
            "type": "evidence",
            "sources": ["R01"],
            "synthetic_test_record": True,
        }
    )
    write_yaml_atomic(ledger_path, ledger)

    texts = (
        "Ăn mặn có thể làm huyết áp tăng.",
        "Mức giảm khác nhau giữa từng người.",
        "Muối ẩn trong nhiều món chế biến sẵn.",
        "Đọc nhãn giúp biết lượng muối.",
        "Nêm nhạt dần để vị giác quen.",
        "Tóm tắt các ý chính của video.",
    )
    # Real measured SilentTTS audio must sustain each one-minute, two-scene clip.
    texts = tuple(
        " ".join((text.split() * count)[:count])
        for text, count in zip(texts, (100, 80, 80, 80, 130, 30), strict=True)
    )
    claims = {0: "C01", 1: "C02"}
    lines = []
    for index, text in enumerate(texts):
        line = {"id": f"L{index + 1:02d}", "text": text, "delivery": {"intent": "explain"}}
        if index in claims:
            line.update({"claim_id": claims[index], "source_marker": "[1]"})
        lines.append(line)
    script_path = revision_root / "script" / "script.yaml"
    script = read_yaml(script_path)
    script["lines"] = lines
    write_yaml_atomic(script_path, script)

    board_path = revision_root / "storyboard" / "storyboard.yaml"
    board = read_yaml(board_path)
    first = board["scenes"][0]
    first.update({"duration_frames": 1000, "chapter_id": "CH01", "narration": texts[0]})
    scenes = [first]
    chapters = ("CH01", "CH02", "CH03", "CH04", "CH05", "CH05")
    frames = (1000, 900, 900, 900, 1500, 300)
    start = 1000
    for index in range(1, 6):
        scene = {
            "id": f"S{index + 1:02d}",
            "start_frame": start,
            "duration_frames": frames[index],
            "narration": texts[index],
            "script_line_id": f"L{index + 1:02d}",
            "visual": "whiteboard",
            "chapter_id": chapters[index],
        }
        if index < 5:
            scene.update({
                "visual": "process_animation",
                "anatomy": {"subject": "artery_cross_section", "state": "normal",
                            "severity": 0, "motion": "Illustrative test motion"},
            })
        if index in claims:
            scene.update({"claim_id": claims[index], "source_marker": "[1]"})
        scenes.append(scene)
        start += frames[index]
    from healthvideo.domain.hook_outro import OUTRO_TEXT

    lines.append({"id": "OUTRO", "text": OUTRO_TEXT, "purpose": "outro",
                  "delivery": {"intent": "thank"}})
    write_yaml_atomic(script_path, script | {"lines": lines})
    scenes.append({
        "id": "OUTRO", "start_frame": start, "duration_frames": 600,
        "narration": OUTRO_TEXT, "script_line_id": "OUTRO",
        "visual": "brand_outro", "chapter_id": "CH05",
        "visual_assets": [{"path": "assets/test-logo.svg", "role": "brand"}],
    })
    board.update({"format_profile": "youtube_long", "scenes": scenes})
    write_yaml_atomic(board_path, board)

    write_yaml_atomic(
        revision_root / "script" / "outline.yaml",
        {
            "schema_version": "1.0",
            "title": "Ăn mặn và tăng huyết áp",
            "chapters": [
                {
                    "id": f"CH{number:02d}",
                    "title": f"Chương {number}",
                    "goal": "Giải thích một ý chính",
                    "claim_ids": {1: ["C01"], 2: ["C02"]}.get(number, []),
                    "target_seconds": 240,
                }
                for number in range(1, 6)
            ],
        },
    )
    write_yaml_atomic(
        revision_root / "script" / "clip-plan.yaml",
        {
            "schema_version": "1.0",
            "clips": [
                {"id": "CL01", "title": "Muối và huyết áp", "first_scene_id": "S01", "last_scene_id": "S02"},
                {"id": "CL02", "title": "Muối ẩn", "first_scene_id": "S03", "last_scene_id": "S04"},
                {"id": "CL03", "title": "Nêm nhạt dần", "first_scene_id": "S05", "last_scene_id": "S06"},
            ],
        },
    )
    return project_dir


_V2_MAIN_SEQUENCE = [
    WorkflowState.IDEA,
    WorkflowState.TOPIC_SELECTED,
    WorkflowState.RESEARCH_IN_PROGRESS,
    WorkflowState.EVIDENCE_READY,
    WorkflowState.DRAFT_READY,
    WorkflowState.AWAITING_MEDICAL_REVIEW,
]


def _advance_v2_state(project_dir: Path, state: WorkflowState) -> None:
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    context = TransitionContext(
        active_revision="001",
        current_input_hash="0" * 64,
        validated_artifacts=frozenset(
            {
                "topic/card.yaml",
                "evidence/ledger.yaml",
                "explainer/explainer.yaml",
                "script/script.yaml",
                "storyboard/storyboard.yaml",
                "assets/asset-manifest.yaml",
            }
        ),
    )
    if manifest.state in _V2_MAIN_SEQUENCE and state in _V2_MAIN_SEQUENCE:
        start_idx = _V2_MAIN_SEQUENCE.index(manifest.state)
        end_idx = _V2_MAIN_SEQUENCE.index(state)
        for i in range(start_idx, end_idx):
            manifest = transition_v2(manifest, _V2_MAIN_SEQUENCE[i + 1], context)
    else:
        manifest = transition_v2(manifest, state, context)
    write_yaml_atomic(project_dir / "project.yaml", manifest.model_dump(mode="json"))


def advance_v2_project_to_video_review(project_dir: Path, *, now: datetime) -> None:
    """Push a draft_ready v2 fixture through to awaiting_video_review with synthetic renders."""
    revision_root = project_dir / "revisions" / "001"
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    context = TransitionContext(
        active_revision="001",
        current_input_hash="0" * 64,
        validated_artifacts=frozenset(
            {
                "script/script.yaml",
                "storyboard/storyboard.yaml",
                "assets/asset-manifest.yaml",
            }
        ),
    )
    manifest = transition_v2(manifest, WorkflowState.AWAITING_MEDICAL_REVIEW, context)
    write_yaml_atomic(project_dir / "project.yaml", manifest.model_dump(mode="json"))
    approve_gate(project_dir, GateKind.MEDICAL, reviewer="BS Nguyễn Văn An", now=now)

    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    (revision_root / "renders").mkdir(parents=True, exist_ok=True)
    _write_json(
        revision_root / "renders" / "render-manifest.json",
        {"provider": "silent", "frames": 225},
    )
    (revision_root / "renders" / "video.mp4").write_bytes(b"synthetic-mp4")
    (revision_root / "reviews").mkdir(parents=True, exist_ok=True)
    _write_json(
        revision_root / "reviews" / "video-qa.json",
        {"codec": "h264", "issues": []},
    )
    context = TransitionContext(
        active_revision="001",
        current_input_hash="0" * 64,
        validated_artifacts=frozenset(
            {
                "reviews/medical-approval.yaml",
                "renders/render-manifest.json",
                "reviews/video-qa.json",
            }
        ),
    )
    manifest = transition_v2(manifest, WorkflowState.PRODUCTION_IN_PROGRESS, context)
    manifest = transition_v2(manifest, WorkflowState.AWAITING_VIDEO_REVIEW, context)
    write_yaml_atomic(project_dir / "project.yaml", manifest.model_dump(mode="json"))


def write_explainer_fixture(revision: Path, claim_id: str) -> None:
    """Add a synthetic mechanism map bound to an existing fixture claim."""
    from tests.domain.test_explainer import explainer_data

    data = explainer_data()
    for layer in data["layers"]:
        layer["claim_ids"] = [claim_id]
    write_explainer(revision, Explainer.model_validate(data))


def complete_explain_first_fixture(revision: Path) -> None:
    """Complete synthetic fixture content with mechanism scenes and a pinned outro."""
    from healthvideo.domain.hook_outro import OUTRO_TEXT

    script_path = revision / "script/script.yaml"
    board_path = revision / "storyboard/storyboard.yaml"
    script = read_yaml(script_path)
    board = read_yaml(board_path)
    script["format_profile"] = "explain_first_v1"
    board["visual_budget_profile"] = "explain_first_v1"
    for line, scene in zip(script["lines"], board["scenes"], strict=True):
        scene["script_line_id"] = line["id"]
    # Keep the evidence fixture first; subsequent synthetic scenes explain its mechanism.
    if len(script["lines"]) == 1:
        for index in range(2, 6):
            line = {"id": f"L{index:02}", "text": "Illustrative test mechanism.",
                    "delivery": {"intent": "explain"}}
            script["lines"].append(line)
            board["scenes"].append({"id": f"S{index:02}", "start_frame": 0,
                "duration_frames": 225, "script_line_id": line["id"],
                "narration": line["text"], "visual": "whiteboard"})
    highlight = next(scene["evidence_highlight"] for scene in board["scenes"]
                     if scene.get("evidence_highlight"))
    board["scenes"][0].update(visual="evidence_highlight", evidence_highlight=highlight)
    for index, scene in enumerate(board["scenes"]):
        scene["duration_frames"] = 225
        if 0 < index < len(board["scenes"]) - 1:
            scene["visual"] = "comparison"
            scene.pop("evidence_highlight", None)
            scene["anatomy"] = {"subject": "artery_cross_section", "state": "normal",
                                "motion": "Illustrative test motion"}
    script["lines"].append({"id": "OUTRO", "text": OUTRO_TEXT,
        "purpose": "outro", "delivery": {"intent": "thank"}})
    board["scenes"].append({"id": "OUTRO", "start_frame": 0,
        "duration_frames": 90, "script_line_id": "OUTRO", "narration": OUTRO_TEXT,
        "visual": "brand_outro", "visual_assets": [{"path": "assets/test-logo.svg", "role": "brand"}]})
    # 60% mechanism, 20% evidence, 12% ordinary whiteboard, 8% outro.
    weights = {"comparison": 780 // (len(board["scenes"]) - 3),
               "evidence_highlight": 240, "chart": 240,
               "whiteboard": 90, "brand_outro": 90}
    frame = 0
    for scene in board["scenes"]:
        scene["start_frame"] = frame
        scene["duration_frames"] = weights.get(scene["visual"], 150) or 150
        frame += scene["duration_frames"]
    for line, scene in zip(script["lines"], board["scenes"], strict=True):
        if scene["visual"] == "comparison":
            words = 98 // (len(board["scenes"]) - 3)
            line["text"] = " ".join(["Synthetic mechanism."] * words)
        elif scene["visual"] == "evidence_highlight":
            line["text"] = " ".join(["Synthetic evidence."] * 30)
        elif scene["visual"] == "whiteboard":
            line["text"] = "Synthetic illustration."
        scene["narration"] = line["text"]
    write_yaml_atomic(script_path, script)
    write_yaml_atomic(board_path, board)
    logo = revision / "assets/test-logo.svg"
    logo.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
    assets_path = revision / "assets/asset-manifest.yaml"
    assets = read_yaml(assets_path)
    assets["assets"].append({"path": "assets/test-logo.svg", "kind": "flourish",
        "semantic": False, "classification_reason": "Decorative synthetic logo",
        "sha256": sha256_file(logo), "source": "synthetic_test_fixture",
        "license": "synthetic_test_only", "creator": "test", "revision": "001",
        "storyboard_role": "brand"})
    write_yaml_atomic(assets_path, assets)
    write_explainer_fixture(revision, "C01")


def align_fixture_script(revision: Path, board: dict[str, Any]) -> None:
    """Bind custom scenario scenes to their script, retaining the pinned branded outro."""
    script_path = revision / "script/script.yaml"
    script = read_yaml(script_path)
    existing = {line["id"]: line for line in script["lines"]}
    original = read_yaml(revision / "storyboard/storyboard.yaml")
    if board["scenes"][-1]["visual"] != "brand_outro":
        outro = original["scenes"][-1].copy()
        first = board["scenes"][0]
        first["duration_frames"] -= outro["duration_frames"]
        board["scenes"].append(outro)
    frame = 0
    lines = []
    used_ids = set()
    for index, scene in enumerate(board["scenes"]):
        scene["start_frame"] = frame
        frame += scene["duration_frames"]
        line_id = scene.get("script_line_id") or f"CUSTOM{index}"
        line = existing.get(line_id, {"id": line_id, "delivery": {"intent": "explain"}}).copy()
        if line_id in used_ids:
            line_id = f"CUSTOM{index}"
        line["id"] = line_id
        used_ids.add(line_id)
        line.update(text=scene["narration"], claim_id=scene.get("claim_id"),
                    source_marker=scene.get("source_marker"))
        scene["script_line_id"] = line_id
        lines.append(line)
    script["lines"] = lines
    write_yaml_atomic(script_path, script)
