import json
from pathlib import Path
from typing import Any

from healthvideo.domain.project import ORDER, ProjectState
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.domain.storyboard import Storyboard
from healthvideo.render.input import build_render_input
from healthvideo.render.run import (
    MANIFEST_NAME,
    OUTPUT_NAME,
    PRODUCTION_ARTIFACT,
    RENDER_INPUT_NAME,
    production_run_dir,
)
from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic
from healthvideo.tts.base import TTSRequest
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.review import approve_medical, approve_video

FIXTURE_PRODUCTION_HASH = "synthetic-production-run"
FIXTURE_REVIEWER = "BS Nguyễn Văn An"


def create_project_fixture(root: Path, state: str) -> Path:
    """Create a complete synthetic project that is safe for offline tests."""
    project_dir = root / "muoi-va-huyet-ap"
    for directory in ("audio", "assets", "evidence", "renders", "script", "storyboard"):
        (project_dir / directory).mkdir(parents=True, exist_ok=True)
    (project_dir / "assets" / "evidence-r01.svg").write_text(
        "<svg xmlns='http://www.w3.org/2000/svg'><text>synthetic</text></svg>",
        encoding="utf-8",
    )

    project: dict[str, Any] = {
        "schema_version": "1.0",
        "slug": "muoi-va-huyet-ap",
        "language": "vi",
        "state": state,
        "artifact_hashes": {},
    }
    brief = {
        "schema_version": "1.0",
        "title": "Ăn mặn và tăng huyết áp",
        "personal_position": "Giảm muối là một bước thực tế.",
        "reasoning": "Huyết áp thường đáp ứng với lượng muối.",
        "emotion": "bình tĩnh",
        "audience_concern": "Người trưởng thành quan tâm huyết áp.",
        "phrases_to_keep": [],
    }
    lines = [
        {
            "id": f"L{index:02}",
            "text": text,
            "claim_id": "C01",
            "source_marker": "[1]",
            "delivery": {"intent": "explain"},
        }
        for index, text in enumerate(
            (
                "Ăn mặn có thể làm huyết áp tăng.",
                "Điều này không có nghĩa là bạn phải bỏ hết gia vị.",
                "Bằng chứng cho thấy giảm muối giúp hạ huyết áp.",
                "Hiệu quả khác nhau giữa mỗi người.",
                "Quan điểm của tôi là giảm dần sẽ dễ duy trì hơn.",
                "Hãy trao đổi với bác sĩ nếu bạn đang điều trị huyết áp.",
            ),
            start=1,
        )
    ]
    script = {
        "schema_version": "1.0",
        "title": brief["title"],
        "language": "vi",
        "lines": lines,
    }
    scenes = []
    for index, line in enumerate(lines):
        scene: dict[str, Any] = {
            "id": f"S{index + 1:02}",
            "start_frame": index * 225,
            "duration_frames": 225,
            "narration": line["text"],
            "claim_id": "C01",
            "source_marker": "[1]",
            "visual": "whiteboard",
        }
        if index == 0:
            scene["visual"] = "evidence_highlight"
            scene["evidence_highlight"] = {
                "image": "assets/evidence-r01.svg",
                "quote": "Synthetic evidence fixture for tests only.",
                "x": 0.1,
                "y": 0.2,
                "width": 0.8,
                "height": 0.2,
            }
        scenes.append(scene)
    storyboard = {"schema_version": "1.0", "title": brief["title"], "scenes": scenes}
    ledger = {
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
    }

    if _has_published_render(state):
        _write_published_run(project_dir, storyboard)
        project["artifact_hashes"][PRODUCTION_ARTIFACT] = FIXTURE_PRODUCTION_HASH

    approve_the_video = _needs_video_approval(state)
    approve_the_medical_review = _needs_medical_approval(state)
    if approve_the_medical_review:
        project["state"] = ProjectState.AWAITING_MEDICAL_REVIEW.value

    write_yaml_atomic(project_dir / "project.yaml", project)
    write_yaml_atomic(project_dir / "author-brief.yaml", brief)
    write_yaml_atomic(project_dir / "evidence" / "ledger.yaml", ledger)
    write_yaml_atomic(project_dir / "script" / "script.yaml", script)
    write_yaml_atomic(project_dir / "storyboard" / "storyboard.yaml", storyboard)
    if approve_the_medical_review:
        approve_medical(project_dir, reviewer=FIXTURE_REVIEWER, note="Đã đối chiếu.")
    if approve_the_video:
        _set_state(project_dir, ProjectState.AWAITING_VIDEO_REVIEW.value)
        approve_video(project_dir, reviewer=FIXTURE_REVIEWER, note="Đã xem toàn bộ.")
    if approve_the_medical_review:
        _set_state(project_dir, state)
    return project_dir


def _set_state(project_dir: Path, state: str) -> None:
    """Restore the requested state after the gate walked the project forward."""
    manifest_path = project_dir / "project.yaml"
    manifest = read_yaml(manifest_path)
    manifest["state"] = state
    write_yaml_atomic(manifest_path, manifest)


def _has_published_render(state: str) -> bool:
    return ORDER.index(ProjectState(state)) >= ORDER.index(ProjectState.RENDERED)


def _needs_video_approval(state: str) -> bool:
    """States at or past the video gate carry a real approval record."""
    return ORDER.index(ProjectState(state)) >= ORDER.index(
        ProjectState.APPROVED_TO_PUBLISH
    )


def _needs_medical_approval(state: str) -> bool:
    """Every fixture at or beyond production carries a real medical approval."""
    return ORDER.index(ProjectState(state)) >= ORDER.index(
        ProjectState.SCRIPT_APPROVED
    )


def _write_published_run(project_dir: Path, storyboard: dict[str, Any]) -> None:
    """Publish a synthetic render run so review and packaging have artifacts."""
    run_dir = production_run_dir(project_dir, FIXTURE_PRODUCTION_HASH)
    (run_dir / "audio").mkdir(parents=True, exist_ok=True)
    (run_dir / "audio" / "narration.wav").write_bytes(b"synthetic-wav")
    (run_dir / OUTPUT_NAME).write_bytes(b"synthetic-mp4")
    asset = project_dir / "assets" / "evidence-r01.svg"
    staged_asset = run_dir / "assets" / "evidence-r01.svg"
    staged_asset.parent.mkdir(parents=True, exist_ok=True)
    staged_asset.write_bytes(asset.read_bytes())
    render_input = build_render_input(
        Storyboard.model_validate(storyboard), audio_file="audio/narration.wav"
    )
    _write_json(run_dir / RENDER_INPUT_NAME, render_input.model_dump(mode="json"))
    _write_json(
        run_dir / MANIFEST_NAME,
        {
            "input_hash": FIXTURE_PRODUCTION_HASH,
            "output": OUTPUT_NAME,
            "provider": "silent",
            "asset_sha256": {"assets/evidence-r01.svg": sha256_file(asset)},
        },
    )


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
    project_dir = root / "muoi-va-huyet-ap-v2"
    revision_root = project_dir / "revisions" / "001"
    for name in ("topic", "author", "evidence", "script", "storyboard", "assets"):
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
        revision_root / "author" / "brief.yaml",
        {
            "schema_version": "1.0",
            "title": "Ăn mặn và tăng huyết áp",
            "personal_position": "Giảm muối là một bước thực tế.",
            "reasoning": "Huyết áp thường đáp ứng với lượng muối.",
            "emotion": "bình tĩnh",
            "audience_concern": "Người trưởng thành quan tâm huyết áp.",
            "phrases_to_keep": [],
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
    if state is not WorkflowState.DRAFT_READY:
        _advance_v2_state(project_dir, state)
    return project_dir


_V2_MAIN_SEQUENCE = [
    WorkflowState.IDEA,
    WorkflowState.TOPIC_SELECTED,
    WorkflowState.AUTHOR_BRIEF_READY,
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
                "author/brief.yaml",
                "evidence/ledger.yaml",
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
