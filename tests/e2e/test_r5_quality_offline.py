"""Offline R5.3.10 acceptance tests: full mocked workflow, gate/PIN/hash guards, pinning & rollback.

All records, claims, assets, and audio/render outputs here are explicitly synthetic fixtures.
Offline checks pass without real TTS, FLUX, Remotion rendering, or live factory runs, and do
NOT certify real video quality or replace doctor gates.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.approver_pin import set_pin
from healthvideo.domain.evidence import EvidenceClaim, SourceRecord
from healthvideo.domain.explainer import Explainer
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.hook_outro import OUTRO_TEXT
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.quality_standards import (
    D4_PRODUCT_REVIEW_ROUNDS,
    D4_SCRIPT_REVIEW_ROUNDS,
    D4_VISUAL_REVIEW_ROUNDS,
    R5_STANDARD_NAME,
    r5_standard_snapshot,
)
from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.explainer import write_explainer
from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic
from healthvideo.tts.base import TTSRequest, TTSResult, word_timestamps
from healthvideo.tts.silent import CHANNELS, SAMPLE_RATE, SAMPLE_WIDTH_BYTES, SilentTTS
from healthvideo.workflows import factory_standards, review_budget
from healthvideo.workflows.create_project_v2 import create_project_v2
from healthvideo.workflows.draft import submit_draft, submit_medical_review
from healthvideo.workflows.evidence import build_evidence_ledger
from healthvideo.workflows.gate_review import (
    R5_CATALOG,
    R5_LICENSE_LEDGER,
    R5_USED_ASSETS,
    approve_gate,
    snapshot_r5_assets,
    validate_r5_render_report,
)
from healthvideo.workflows.package import package_project
from healthvideo.workflows.produce import produce_project
from tests.domain.test_explainer import explainer_data
from tests.helpers import (
    create_v2_project_fixture,
    submit_video_fixture,
    write_critic_review_fixture,
    write_posts_fixture,
)
from tests.workflows.test_produce import _r5_alignment

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 24, 10, 0, tzinfo=UTC)
REVIEWER = "BS Fixture Acceptance"


def _mock_render(argv: list[str]) -> int:
    out = Path(argv[argv.index("--output") + 1]) if "--output" in argv else Path(argv[-1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"synthetic-mp4")
    return 0


class _R5MockTTS(SilentTTS):
    """Offline mock TTS calibrated to Vietnamese char/s pacing (no network/Vibi calls)."""

    def synthesize(self, request: TTSRequest, output: Path) -> TTSResult:
        import os
        import wave

        words = request.text.split()
        duration_ms = max(1000, round(len(request.text) / 16.39 * 1000))
        frame_count = round(duration_ms * SAMPLE_RATE / 1000)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(f"{output.suffix}.tmp")
        try:
            with wave.open(str(temporary), "wb") as wav:
                wav.setnchannels(CHANNELS)
                wav.setsampwidth(SAMPLE_WIDTH_BYTES)
                wav.setframerate(SAMPLE_RATE)
                wav.writeframes(b"\x00" * frame_count * CHANNELS * SAMPLE_WIDTH_BYTES)
            os.replace(temporary, output)
        finally:
            if temporary.exists():
                temporary.unlink()
        return TTSResult(
            provider=self.provider_name,
            audio_file=output,
            duration_ms=duration_ms,
            word_timestamps=word_timestamps(words, duration_ms),
        )


def _synthetic_r5_project(root: Path, *, slug: str = "r5-offline-fixture") -> Path:
    """Create a synthetic R5 long-form project at research_in_progress with fixture assets."""
    project = create_project_v2(root / "projects", slug, "Fixture R5 tổng hợp", now=NOW)
    revision = project / "revisions" / "001"

    # Pin R5 quality standard explicitly on this new revision.
    (revision / "workflow" / "standards.yaml").unlink(missing_ok=True)
    factory_standards.pin_standards(root, project, quality_profile="r5_v1")

    # Advance project to research_in_progress so build_evidence_ledger moves it to evidence_ready.
    proj_data = read_yaml(project / "project.yaml")
    proj_data["state"] = WorkflowState.RESEARCH_IN_PROGRESS.value
    write_yaml_atomic(project / "project.yaml", proj_data)

    # Seed explainer bound to synthetic fixture claims C01 and C02.
    exp_data = explainer_data()
    for idx, layer in enumerate(exp_data["layers"]):
        layer["claim_ids"] = ["C01" if idx % 2 == 0 else "C02"]
    write_explainer(revision, Explainer.model_validate(exp_data))

    # Build evidence ledger with explicitly marked synthetic test records (never real library).
    records = [
        SourceRecord(
            id="R-FIX-01",
            title="Synthetic fixture source: physiology overview (test only)",
            authors=["Fixture Author A"],
            year=2024,
            study_design="synthetic_fixture",
            doi="10.0000/synthetic-r5-01",
            synthetic_test_record=True,
        ),
        SourceRecord(
            id="R-FIX-02",
            title="Synthetic fixture source: latest professional update (test only)",
            authors=["Fixture Author B"],
            year=2026,
            study_design="synthetic_fixture",
            doi="10.0000/synthetic-r5-02",
            synthetic_test_record=True,
        ),
    ]
    claims = [
        EvidenceClaim(
            id="C01",
            type="evidence",
            text_public="Fixture: cơ quan và tế bào có tầng cấu trúc rõ ràng.",
            text_technical="Synthetic fixture claim C01 for offline R5 tests.",
            sources=["R-FIX-01"],
            caveat_claim_ids=["C02"],
            synthetic_test_record=True,
        ),
        EvidenceClaim(
            id="C02",
            type="evidence",
            text_public="Fixture: ngưỡng tham chiếu cần đối chiếu bối cảnh lâm sàng.",
            text_technical="Synthetic fixture claim C02 for offline R5 tests.",
            sources=["R-FIX-02"],
            synthetic_test_record=True,
        ),
    ]
    build_evidence_ledger(project, claims, records)

    # Create synthetic licensed R5 assets + brand logo inside revision.
    (revision / "assets" / "r5").mkdir(parents=True, exist_ok=True)
    organ_svg = revision / "assets" / "r5" / "organ-zoom.svg"
    cell_svg = revision / "assets" / "r5" / "cell-leak.svg"
    logo_svg = revision / "assets" / "test-logo.svg"
    organ_svg.write_text("<svg xmlns='http://www.w3.org/2000/svg'><g id='organ'/></svg>", encoding="utf-8")
    cell_svg.write_text("<svg xmlns='http://www.w3.org/2000/svg'><g id='cell'/></svg>", encoding="utf-8")
    logo_svg.write_text("<svg xmlns='http://www.w3.org/2000/svg'><g id='brand'/></svg>", encoding="utf-8")

    catalog_records = [
        {
            "id": "fixture-organ-zoom",
            "file": "assets/r5/organ-zoom.svg",
            "source_page": "https://smart.servier.com/smart_image/fixture-organ/",
            "original_url": "https://smart.servier.com/fixture-organ.svg",
            "author": "Servier Fixture",
            "license": "CC BY 4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "license_evidence": "Synthetic CC BY 4.0 fixture record.",
            "sha256": sha256_file(organ_svg),
        },
        {
            "id": "fixture-cell-leak",
            "file": "assets/r5/cell-leak.svg",
            "source_page": "https://smart.servier.com/smart_image/fixture-cell/",
            "original_url": "https://smart.servier.com/fixture-cell.svg",
            "author": "Servier Fixture",
            "license": "CC BY 4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "license_evidence": "Synthetic CC BY 4.0 fixture record.",
            "sha256": sha256_file(cell_svg),
        },
    ]
    write_yaml_atomic(revision / R5_CATALOG, {"assets": catalog_records})

    manifest_assets = [
        {
            "path": rec["file"],
            "kind": "medical_diagram",
            "semantic": True,
            "classification_reason": "Synthetic R5 licensed mechanism illustration.",
            "sha256": rec["sha256"],
            "source": rec["source_page"],
            "license": rec["license"],
            "creator": rec["author"],
            "revision": "001",
            "rights_required": True,
        }
        for rec in catalog_records
    ]
    manifest_assets.append({
        "path": "assets/test-logo.svg",
        "kind": "flourish",
        "semantic": False,
        "classification_reason": "Decorative synthetic brand logo.",
        "sha256": sha256_file(logo_svg),
        "source": "synthetic_test_fixture",
        "license": "synthetic_test_only",
        "creator": "test",
        "revision": "001",
        "storyboard_role": "brand",
    })
    write_yaml_atomic(
        revision / "assets" / "asset-manifest.yaml",
        {"schema_version": "2.0", "assets": manifest_assets},
    )
    write_yaml_atomic(
        revision / "assets" / "license-ledger.yaml",
        {
            "schema_version": "2.0",
            "entries": [
                {
                    "path": rec["file"],
                    "source": rec["source_page"],
                    "creator": rec["author"],
                    "license": rec["license"],
                    "rights_basis": rec["license_evidence"],
                    "revision": "001",
                    "sha256": rec["sha256"],
                }
                for rec in catalog_records
            ],
        },
    )

    # Script lines with unique anchor tokens so both estimated & aligned timing resolve cleanly.
    lines = [
        {
            "id": "L01",
            "text": (
                "Đi khám định kỳ nhiều bạn thắc mắc men gan là gì? "
                "Tờ phiếu ghi đậm chữ đỏ vì sao chỉ số tăng? "
                "Và khi nào cần mang kết quả đi khám bác sĩ?"
            ),
            "delivery": {"intent": "hook"},
        },
        {
            "id": "L02",
            "text": (
                "Ta đi từ toàn thân tới vùng gan ở hạ sườn phải. "
                "Phóng sâu vào đơn vị tiểu thùy để thấy hàng tế bào xếp đều. "
                "Mỗi tế bào giữ enzym bên trong để xử lý chuyển hóa."
            ),
            "claim_id": "C01",
            "source_marker": "[1]",
            "delivery": {"intent": "explain"},
        },
        {
            "id": "L03",
            "text": (
                "Bình thường enzym nằm gọn trong tế bào gan khỏe mạnh. "
                "Khi màng tế bào bị tổn thương thì hàng rào lỏng dần. "
                "Enzym tràn ra dòng máu rồi hiện trên mẫu xét nghiệm."
            ),
            "claim_id": "C02",
            "source_marker": "[2]",
            "delivery": {"intent": "explain"},
        },
        {
            "id": "L04",
            "text": (
                "Đường cong minh họa giúp bạn thấy khoảng tham chiếu phổ biến. "
                "Một mức cao nhẹ không tự nói lên toàn bộ nguyên nhân. "
                "Bác sĩ luôn đặt con số vào bối cảnh triệu chứng riêng."
            ),
            "claim_id": "C02",
            "source_marker": "[2]",
            "delivery": {"intent": "explain"},
        },
        {
            "id": "L05",
            "text": (
                "Về cập nhật chuyên môn tìm ngày hai bốn tháng mười một. "
                "Nguồn mới nhất tìm được năm hai nghìn hai sáu vẫn giữ nguyên tắc. "
                "Chưa có cập nhật mới thay đổi bước đánh giá ban đầu."
            ),
            "claim_id": "C02",
            "source_marker": "[2]",
            "delivery": {"intent": "explain"},
        },
        {
            "id": "L06",
            "text": (
                "Ở lớp mô sâu hơn dòng máu giàu dưỡng chất đi qua từng xoang mạch nhỏ. "
                "Tế bào hấp thu chất từ đường ruột rồi chuyển hóa theo nhiều bước nhịp nhàng. "
                "Nhờ vậy cơ quan gan lọc gọn các sản phẩm dư thừa sinh ra mỗi ngày. "
                "Khi áp lực chuyển hóa kéo dài thì màng tế bào phải chịu sức ép lớn hơn. "
                "Tín hiệu viêm khởi phát làm thay đổi tính thấm ở lớp màng bảo vệ tế bào. "
                "Theo dõi lặp lại đúng lịch hẹn giúp bác sĩ nhận diện xu hướng thật sự."
            ),
            "claim_id": "C01",
            "source_marker": "[1]",
            "delivery": {"intent": "explain"},
        },
        {
            "id": "L07",
            "text": (
                "Nhớ ngắn gọn men gan phản ánh tình trạng tế bào gan hiện tại. "
                "Mức tăng đi kèm nhiều nguyên nhân nên hãy mang phiếu đi khám. "
                "Cảm ơn bạn đã xem phần giải thích."
            ),
            "delivery": {"intent": "explain"},
        },
        {
            "id": "OUTRO",
            "text": OUTRO_TEXT,
            "purpose": "outro",
            "delivery": {"intent": "thank"},
        },
        {
            "id": "CL01_HOOK",
            "text": "Vì sao phiếu xét nghiệm ghi men gan tăng cao bất ngờ?",
            "purpose": "clip_hook",
            "clip_id": "CL01",
            "delivery": {"intent": "hook"},
        },
        {
            "id": "CL01_OUTRO",
            "text": "Mang phiếu đi khám bác sĩ để đánh giá đầy đủ. Xem video đầy đủ trên kênh nhé.",
            "purpose": "clip_outro",
            "clip_id": "CL01",
            "delivery": {"intent": "thank"},
        },
    ]
    script_data = {
        "schema_version": "1.0",
        "title": "Fixture R5: men gan và cơ chế tế bào",
        "language": "vi",
        "format_profile": "explain_first_v1",
        "lines": lines,
    }
    write_yaml_atomic(revision / "script" / "script.yaml", script_data)

    r5_contract = {
        "questions": [
            {
                "id": "Q1",
                "text": "men gan là gì?",
                "hook_line_id": "L01",
                "answer_line_ids": ["L07"],
            },
            {
                "id": "Q2",
                "text": "sao chỉ số tăng?",
                "hook_line_id": "L01",
                "answer_line_ids": ["L07"],
            },
            {
                "id": "Q3",
                "text": "khi nào cần mang kết quả đi khám",
                "hook_line_id": "L01",
                "answer_line_ids": ["L07"],
            },
        ],
        "blocks": [
            {
                "id": "B1",
                "line_ids": ["L02", "L06"],
                "question_ids": ["Q1"],
                "takeaway_line_id": "L02",
                "professional_update": False,
            },
            {
                "id": "B2",
                "line_ids": ["L03", "L04"],
                "question_ids": ["Q2"],
                "takeaway_line_id": "L03",
                "professional_update": False,
            },
            {
                "id": "B3",
                "line_ids": ["L05", "L07"],
                "question_ids": ["Q3"],
                "takeaway_line_id": "L07",
                "professional_update": True,
            },
        ],
    }

    def _p(line_id: str, phrase: str) -> dict:
        return {"kind": "phrase", "line_id": line_id, "phrase": phrase}

    start_anc = {"kind": "scene_start"}
    end_anc = {"kind": "scene_end"}

    scenes = [
        {
            "id": "S01",
            "start_frame": 0,
            "duration_frames": 270,
            "script_line_id": "L01",
            "narration": lines[0]["text"],
            "visual": "whiteboard",
            "on_screen_text": "Ba câu hỏi về men gan",
            "chapter_id": "CH01",
            "shots": [
                {
                    "id": "SH01",
                    "kind": "story",
                    "tier": "body",
                    "component": "ScaleChain",
                    "asset_paths": ["assets/r5/organ-zoom.svg"],
                    "question_ids": ["Q1"],
                    "start": start_anc,
                    "end": _p("L01", "Tờ phiếu"),
                    "actions": [],
                    "text_windows": [
                        {
                            "kind": "scale_bar",
                            "text": "Cơ thể → Cơ quan → Tế bào",
                            "start": start_anc,
                            "end": _p("L01", "Tờ phiếu"),
                        }
                    ],
                },
                {
                    "id": "SH02",
                    "kind": "story",
                    "tier": None,
                    "component": "VnLabSheet",
                    "asset_paths": [],
                    "question_ids": ["Q2"],
                    "start": _p("L01", "Tờ phiếu"),
                    "end": _p("L01", "Và khi"),
                    "actions": [],
                    "text_windows": [
                        {
                            "kind": "lab_sheet",
                            "text": "ALT | 120 | U/L | < 40 | H",
                            "claim_ids": ["C02"],
                            "start": _p("L01", "Tờ phiếu"),
                            "end": _p("L01", "Và khi"),
                        }
                    ],
                },
                {
                    "id": "SH03",
                    "kind": "story",
                    "tier": None,
                    "component": "TakeawayCard",
                    "asset_paths": [],
                    "question_ids": ["Q3"],
                    "start": _p("L01", "Và khi"),
                    "end": end_anc,
                    "actions": [],
                    "text_windows": [],
                },
            ],
        },
        {
            "id": "S02",
            "start_frame": 270,
            "duration_frames": 360,
            "script_line_id": "L02",
            "narration": lines[1]["text"],
            "claim_id": "C01",
            "source_marker": "[1]",
            "visual": "process_animation",
            "anatomy": {
                "subject": "liver_organ",
                "state": "normal",
                "severity": 0,
                "motion": "Zoom from body to liver lobule",
            },
            "chapter_id": "CH02",
            "shots": [
                {
                    "id": "SH04",
                    "kind": "mechanism",
                    "tier": "organ",
                    "component": "ZoomChain",
                    "asset_paths": ["assets/r5/organ-zoom.svg"],
                    "question_ids": ["Q1"],
                    "start": start_anc,
                    "end": end_anc,
                    "actions": [
                        {
                            "actor": "camera",
                            "compartment": "body",
                            "change": "locate liver",
                            "outcome": "organ framed",
                            "start": start_anc,
                            "end": _p("L02", "Phóng sâu"),
                        },
                        {
                            "actor": "camera",
                            "compartment": "lobule",
                            "change": "zoom into lobule",
                            "outcome": "hepatocyte cord visible",
                            "start": _p("L02", "Phóng sâu"),
                            "end": _p("L02", "Mỗi tế bào"),
                        },
                        {
                            "actor": "enzyme",
                            "compartment": "hepatocyte",
                            "change": "retain intracellularly",
                            "outcome": "normal metabolism",
                            "start": _p("L02", "Mỗi tế bào"),
                            "end": end_anc,
                        },
                    ],
                    "text_windows": [
                        {
                            "kind": "label",
                            "text": "Vùng gan",
                            "claim_ids": ["C01"],
                            "start": start_anc,
                            "end": _p("L02", "Phóng sâu"),
                        }
                    ],
                }
            ],
        },
        {
            "id": "S03",
            "start_frame": 630,
            "duration_frames": 360,
            "script_line_id": "L03",
            "narration": lines[2]["text"],
            "claim_id": "C02",
            "source_marker": "[2]",
            "visual": "process_animation",
            "anatomy": {
                "subject": "liver_lobule",
                "state": "diseased",
                "severity": 1,
                "motion": "Hepatocyte membrane permeability shift",
            },
            "chapter_id": "CH03",
            "shots": [
                {
                    "id": "SH05",
                    "kind": "mechanism",
                    "tier": "cell",
                    "component": "R5LiverLeakSignature",
                    "asset_paths": ["assets/r5/cell-leak.svg"],
                    "question_ids": ["Q2"],
                    "start": start_anc,
                    "end": end_anc,
                    "actions": [
                        {
                            "actor": "enzyme",
                            "compartment": "intracellular",
                            "change": "normal retention",
                            "outcome": "stays inside cell",
                            "start": start_anc,
                            "end": _p("L03", "Khi màng"),
                        },
                        {
                            "actor": "membrane",
                            "compartment": "membrane",
                            "change": "permeability increase",
                            "outcome": "barrier loosens",
                            "start": _p("L03", "Khi màng"),
                            "end": _p("L03", "Enzym tràn"),
                        },
                        {
                            "actor": "enzyme",
                            "compartment": "bloodstream",
                            "change": "release into blood",
                            "outcome": "detected on test",
                            "start": _p("L03", "Enzym tràn"),
                            "end": end_anc,
                        },
                    ],
                    "text_windows": [],
                }
            ],
        },
        {
            "id": "S04",
            "start_frame": 990,
            "duration_frames": 360,
            "script_line_id": "L04",
            "narration": lines[3]["text"],
            "claim_id": "C02",
            "source_marker": "[2]",
            "visual": "process_animation",
            "anatomy": {
                "subject": "liver_lobule",
                "state": "normal",
                "severity": 0,
                "motion": "Reference distribution illustration",
            },
            "chapter_id": "CH03",
            "shots": [
                {
                    "id": "SH06",
                    "kind": "mechanism",
                    "tier": "clinical",
                    "component": "ReferenceDistribution",
                    "asset_paths": ["assets/r5/organ-zoom.svg"],
                    "question_ids": ["Q2"],
                    "start": start_anc,
                    "end": end_anc,
                    "actions": [
                        {
                            "actor": "curve",
                            "compartment": "reference_band",
                            "change": "highlight central band",
                            "outcome": "range shown",
                            "start": start_anc,
                            "end": _p("L04", "Một mức"),
                        },
                        {
                            "actor": "marker",
                            "compartment": "upper_tail",
                            "change": "place marker",
                            "outcome": "mild elevation shown",
                            "start": _p("L04", "Một mức"),
                            "end": _p("L04", "Bác sĩ"),
                        },
                        {
                            "actor": "context",
                            "compartment": "clinical_frame",
                            "change": "overlay symptoms",
                            "outcome": "individual context",
                            "start": _p("L04", "Bác sĩ"),
                            "end": end_anc,
                        },
                    ],
                    "text_windows": [
                        {
                            "kind": "label",
                            "text": "Minh họa",
                            "claim_ids": ["C02"],
                            "start": start_anc,
                            "end": _p("L04", "Một mức"),
                        }
                    ],
                }
            ],
        },
        {
            "id": "S05",
            "start_frame": 1350,
            "duration_frames": 360,
            "script_line_id": "L05",
            "narration": lines[4]["text"],
            "claim_id": "C02",
            "source_marker": "[2]",
            "visual": "process_animation",
            "anatomy": {
                "subject": "liver_organ",
                "state": "normal",
                "severity": 0,
                "motion": "Professional update timeline",
            },
            "chapter_id": "CH04",
            "shots": [
                {
                    "id": "SH07",
                    "kind": "mechanism",
                    "tier": "update",
                    "component": "ZoomChain",
                    "asset_paths": ["assets/r5/cell-leak.svg"],
                    "question_ids": ["Q3"],
                    "start": start_anc,
                    "end": end_anc,
                    "actions": [
                        {
                            "actor": "timeline",
                            "compartment": "evidence_panel",
                            "change": "mark search date",
                            "outcome": "2026-11-24 noted",
                            "start": start_anc,
                            "end": _p("L05", "Nguồn mới"),
                        },
                        {
                            "actor": "guideline",
                            "compartment": "evidence_panel",
                            "change": "show latest source",
                            "outcome": "2026 source pinned",
                            "start": _p("L05", "Nguồn mới"),
                            "end": _p("L05", "Chưa có"),
                        },
                        {
                            "actor": "workflow",
                            "compartment": "clinical_step",
                            "change": "confirm baseline triage",
                            "outcome": "no invented update",
                            "start": _p("L05", "Chưa có"),
                            "end": end_anc,
                        },
                    ],
                    "text_windows": [],
                }
            ],
        },
        {
            "id": "S06",
            "start_frame": 1710,
            "duration_frames": 900,
            "script_line_id": "L06",
            "narration": lines[5]["text"],
            "claim_id": "C01",
            "source_marker": "[1]",
            "visual": "process_animation",
            "anatomy": {
                "subject": "liver_lobule",
                "state": "diseased",
                "severity": 1,
                "motion": "Sinusoid flow and membrane stress",
            },
            "chapter_id": "CH04",
            "shots": [
                {
                    "id": "SH08",
                    "kind": "mechanism",
                    "tier": "tissue",
                    "component": "ZoomChain",
                    "asset_paths": ["assets/r5/organ-zoom.svg"],
                    "question_ids": ["Q1"],
                    "start": start_anc,
                    "end": _p("L06", "Khi áp lực"),
                    "actions": [
                        {
                            "actor": "blood",
                            "compartment": "sinusoid",
                            "change": "flow across lobule",
                            "outcome": "delivery to cells",
                            "start": start_anc,
                            "end": _p("L06", "Tế bào hấp"),
                        },
                        {
                            "actor": "hepatocyte",
                            "compartment": "cytoplasm",
                            "change": "absorb nutrients",
                            "outcome": "stepwise processing",
                            "start": _p("L06", "Tế bào hấp"),
                            "end": _p("L06", "Nhờ vậy"),
                        },
                        {
                            "actor": "liver",
                            "compartment": "clearance",
                            "change": "filter byproducts",
                            "outcome": "homeostasis maintained",
                            "start": _p("L06", "Nhờ vậy"),
                            "end": _p("L06", "Khi áp lực"),
                        },
                    ],
                    "text_windows": [],
                },
                {
                    "id": "SH09",
                    "kind": "mechanism",
                    "tier": "cell",
                    "component": "R5LiverLeakSignature",
                    "asset_paths": ["assets/r5/cell-leak.svg"],
                    "question_ids": ["Q1"],
                    "start": _p("L06", "Khi áp lực"),
                    "end": end_anc,
                    "actions": [
                        {
                            "actor": "stress",
                            "compartment": "membrane",
                            "change": "prolonged load",
                            "outcome": "membrane strain",
                            "start": _p("L06", "Khi áp lực"),
                            "end": _p("L06", "Tín hiệu viêm"),
                        },
                        {
                            "actor": "inflammation",
                            "compartment": "membrane",
                            "change": "alter permeability",
                            "outcome": "leakage risk rises",
                            "start": _p("L06", "Tín hiệu viêm"),
                            "end": _p("L06", "Theo dõi"),
                        },
                        {
                            "actor": "trend",
                            "compartment": "followup",
                            "change": "compare repeat tests",
                            "outcome": "true trajectory identified",
                            "start": _p("L06", "Theo dõi"),
                            "end": end_anc,
                        },
                    ],
                    "text_windows": [],
                },
            ],
        },
        {
            "id": "S07",
            "start_frame": 2610,
            "duration_frames": 270,
            "script_line_id": "L07",
            "narration": lines[6]["text"],
            "visual": "whiteboard",
            "on_screen_text": "Tóm tắt ba câu hỏi và nguồn hình",
            "chapter_id": "CH05",
            "shots": [
                {
                    "id": "SH10",
                    "kind": "recap",
                    "tier": None,
                    "component": "TakeawayCard",
                    "asset_paths": [],
                    "question_ids": ["Q1", "Q2", "Q3"],
                    "start": start_anc,
                    "end": _p("L07", "Cảm ơn"),
                    "actions": [],
                    "text_windows": [
                        {
                            "kind": "takeaway",
                            "text": "Men gan phản ánh tế bào gan",
                            "claim_ids": ["C01"],
                            "start": start_anc,
                            "end": _p("L07", "Mức tăng"),
                        }
                    ],
                },
                {
                    "id": "SH11",
                    "kind": "credit",
                    "tier": None,
                    "component": "CreditCard",
                    "asset_paths": [
                        "assets/r5/organ-zoom.svg",
                        "assets/r5/cell-leak.svg",
                    ],
                    "question_ids": ["Q1"],
                    "start": _p("L07", "Cảm ơn"),
                    "end": end_anc,
                    "actions": [],
                    "text_windows": [
                        {
                            "kind": "credit",
                            "text": "Servier Fixture · CC BY 4.0",
                            "start": _p("L07", "Cảm ơn"),
                            "end": end_anc,
                        }
                    ],
                },
            ],
        },
        {
            "id": "OUTRO",
            "start_frame": 2880,
            "duration_frames": 180,
            "script_line_id": "OUTRO",
            "narration": OUTRO_TEXT,
            "visual": "brand_outro",
            "chapter_id": "CH05",
            "visual_assets": [{"path": "assets/test-logo.svg", "role": "brand"}],
            "shots": [
                {
                    "id": "SH12",
                    "kind": "recap",
                    "tier": None,
                    "component": "TakeawayCard",
                    "asset_paths": [],
                    "question_ids": ["Q3"],
                    "start": start_anc,
                    "end": end_anc,
                    "actions": [],
                    "text_windows": [],
                }
            ],
        },
        {
            "id": "CL01_H",
            "start_frame": 0,
            "duration_frames": 120,
            "script_line_id": "CL01_HOOK",
            "narration": "Vì sao phiếu xét nghiệm ghi men gan tăng cao bất ngờ?",
            "visual": "whiteboard",
            "on_screen_text": "Men gan tăng là gì?",
            "clip_only": "CL01",
            "shots": [
                {
                    "id": "SH13",
                    "kind": "story",
                    "tier": None,
                    "component": "TakeawayCard",
                    "asset_paths": [],
                    "question_ids": ["Q1"],
                    "start": start_anc,
                    "end": end_anc,
                    "actions": [],
                    "text_windows": [],
                }
            ],
        },
        {
            "id": "CL01_O",
            "start_frame": 0,
            "duration_frames": 150,
            "script_line_id": "CL01_OUTRO",
            "narration": "Mang phiếu đi khám bác sĩ để đánh giá đầy đủ. Xem video đầy đủ trên kênh nhé.",
            "visual": "whiteboard",
            "on_screen_text": "Xem video đầy đủ trên kênh",
            "clip_only": "CL01",
            "shots": [
                {
                    "id": "SH14",
                    "kind": "recap",
                    "tier": None,
                    "component": "TakeawayCard",
                    "asset_paths": [],
                    "question_ids": ["Q3"],
                    "start": start_anc,
                    "end": end_anc,
                    "actions": [],
                    "text_windows": [],
                }
            ],
        },
    ]

    board_data = {
        "schema_version": "1.0",
        "title": "Fixture R5: men gan và cơ chế tế bào",
        "format_profile": "youtube_long",
        "quality_profile": "r5_v1",
        "r5_contract": r5_contract,
        "scenes": scenes,
    }
    write_yaml_atomic(revision / "storyboard" / "storyboard.yaml", board_data)

    write_yaml_atomic(
        revision / "script" / "outline.yaml",
        {
            "schema_version": "1.0",
            "title": "Fixture R5: men gan và cơ chế tế bào",
            "chapters": [
                {
                    "id": "CH01",
                    "title": "Mở đầu và 3 câu hỏi",
                    "goal": "Nêu câu hỏi cốt lõi",
                    "claim_ids": [],
                    "target_seconds": 180,
                },
                {
                    "id": "CH02",
                    "title": "Zoom tầng cơ quan tới tế bào",
                    "goal": "Giải thích vị trí men gan",
                    "claim_ids": ["C01"],
                    "target_seconds": 180,
                },
                {
                    "id": "CH03",
                    "title": "Cơ chế tràn men và khoảng tham chiếu",
                    "goal": "Giải thích cơ chế tăng men",
                    "claim_ids": ["C02"],
                    "target_seconds": 180,
                },
                {
                    "id": "CH04",
                    "title": "Cập nhật chuyên môn và dòng mô",
                    "goal": "Cập nhật nguồn và tiến triển",
                    "claim_ids": ["C01", "C02"],
                    "target_seconds": 180,
                },
                {
                    "id": "CH05",
                    "title": "Tổng kết và credit",
                    "goal": "Trả đủ 3 câu hỏi và nguồn ảnh",
                    "claim_ids": [],
                    "target_seconds": 180,
                },
            ],
        },
    )
    write_yaml_atomic(
        revision / "script" / "clip-plan.yaml",
        {
            "schema_version": "1.0",
            "clips": [
                {
                    "id": "CL01",
                    "title": "Zoom gan và cơ chế men gan",
                    "first_scene_id": "S02",
                    "last_scene_id": "S06",
                    "hook_scene_id": "CL01_H",
                    "outro_scene_id": "CL01_O",
                }
            ],
        },
    )
    write_posts_fixture(revision)
    return project


def test_factory_standards_yaml_records_pyh_r5_quality_v1_and_keeps_legacy_history() -> None:
    """profiles/factory-standards.yaml adds pyh_r5_quality_v1 matching r5_standard_snapshot()."""
    accepted = factory_standards.accepted_standards(REPO_ROOT)
    assert 1 in accepted
    assert accepted[1]["id"] == "d74962cb823a4f60a4285d69e53f2e81"

    raw = read_yaml(REPO_ROOT / factory_standards.STANDARDS_FILE)
    entries = raw.get("quality_standards")
    assert isinstance(entries, list) and entries
    r5 = next(item for item in entries if item.get("name") == R5_STANDARD_NAME)
    snapshot = r5_standard_snapshot()
    assert r5["profile"] == snapshot["profile"] == "r5_v1"
    assert r5["accepted_at"] == "2026-11-24"
    assert r5["source"] == "bác sĩ chốt 2026-11-24"
    for key in ("D1", "D2", "D3", "D4"):
        assert r5[key] == snapshot[key]


def test_r5_full_offline_pipeline_and_two_layout_shapes(tmp_path: Path, monkeypatch) -> None:
    """End-to-end offline R5 flow: draft -> pre-gate QA -> snapshot -> gates -> mocked produce -> package."""
    project = _synthetic_r5_project(tmp_path)
    from tests.helpers import reviewed_r5_lexicon_fixture
    reviewed_r5_lexicon_fixture(project, monkeypatch)
    revision = project / "revisions" / "001"

    # 1. Draft submission runs pre-gate estimated R5 QA (contract + D1 + D2 + clip plan).
    manifest = submit_draft(
        project,
        revision / "script" / "script.yaml",
        revision / "storyboard" / "storyboard.yaml",
        revision / "assets" / "asset-manifest.yaml",
    )
    assert manifest.state == WorkflowState.DRAFT_READY

    # 2. Snapshot R5 licensed assets before medical gate, record script review in D4 ledger, submit.
    board = Storyboard.model_validate(read_yaml(revision / "storyboard" / "storyboard.yaml"))
    snapshot_r5_assets(revision, board)
    assert (revision / R5_USED_ASSETS).is_file()
    assert (revision / R5_LICENSE_LEDGER).is_file()

    write_critic_review_fixture(project, product=False)
    assert review_budget.review_budget_status(revision, "script")["used"] == 1
    manifest = submit_medical_review(project)
    assert manifest.state == WorkflowState.AWAITING_MEDICAL_REVIEW

    # 3. Attempting production before Gate 1 approval must be blocked.
    with pytest.raises(ValueError, match="medically_approved|medical approval"):
        produce_project(project, SilentTTS(), lambda _: 0, music=False)

    # 4. Gate 1 approval via test helper (no hand-written approval file in live projects).
    med_approval = approve_gate(project, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)
    assert f"r5-byte:{R5_USED_ASSETS}" in med_approval.artifact_hashes
    assert f"r5-byte:{R5_LICENSE_LEDGER}" in med_approval.artifact_hashes
    assert "workflow/standards.yaml" in med_approval.artifact_hashes

    # 5. Produce with mock Vietnamese-paced TTS + deterministic mock alignment + mock Remotion runner.
    _r5_alignment(monkeypatch)
    produce_project(
        project,
        _R5MockTTS(),
        _mock_render,
        music=False,
    )
    validate_r5_render_report(revision)

    quality_report = json.loads((revision / "renders" / "quality-report.json").read_text(encoding="utf-8"))
    assert quality_report["quality"]["estimated"] is False
    assert quality_report["quality"]["manual_review"] == "pending"
    assert quality_report["quality"]["story"]["count"] == 3
    assert quality_report["quality"]["mechanism"]["count"] == 6
    assert (
        quality_report["quality"]["numerator_frames"] * 100
        <= quality_report["quality"]["denominator_frames"] * 15
    )

    # Verify 16:9 main render input vs 9:16 vertical clip render input shapes.
    main_input = json.loads((revision / "renders" / "render-input.json").read_text(encoding="utf-8"))
    clip_input = json.loads(
        (revision / "renders" / "clips" / "CL01.render-input.json").read_text(encoding="utf-8")
    )
    assert (main_input["format_profile"], main_input["width"], main_input["height"]) == (
        "youtube_long",
        1920,
        1080,
    )
    assert (clip_input["format_profile"], clip_input["width"], clip_input["height"]) == (
        "vertical_clip",
        1080,
        1920,
    )
    assert main_input["quality_profile"] == "r5_v1"
    assert clip_input["quality_profile"] == "r5_v1"
    assert all(scene["words"] for scene in main_input["scenes"])
    assert all(scene["words"] for scene in clip_input["scenes"])
    assert any(
        shot["component"] == "CreditCard"
        for scene in main_input["scenes"]
        for shot in scene["resolved_shots"]
    )
    assert any(
        shot["component"] == "VnLabSheet"
        for scene in main_input["scenes"]
        for shot in scene["resolved_shots"]
    )

    # 6. Product review uses D4 review-budget ledger; packaging before Gate 2 is blocked.
    submit_video_fixture(project)
    assert review_budget.review_budget_status(revision, "product")["used"] == 1
    assert (revision / review_budget.LEDGER).is_file()

    with pytest.raises(ValueError, match="video_approved|video approval"):
        package_project(project)

    # 7. Gate 2 approval + packaging.
    video_approval = approve_gate(project, GateKind.VIDEO, reviewer=REVIEWER, now=NOW)
    assert "renders/clips/CL01.mp4" in video_approval.artifact_hashes
    assert "reviews/quality-report.json" in video_approval.artifact_hashes

    published = package_project(project)
    assert read_yaml(project / "project.yaml")["state"] == WorkflowState.PACKAGED.value
    assert (published / "workflow" / "standards.yaml").is_file()
    pinned = read_yaml(published / "workflow" / "standards.yaml")
    assert pinned["quality_standard"] == r5_standard_snapshot()


def test_r5_blocks_missing_pin_stale_hash_missing_license_and_exhausted_budget(
    tmp_path: Path, monkeypatch
) -> None:
    """Missing PIN, missing license, stale hashes, and exhausted D4 budgets all fail closed."""
    project = _synthetic_r5_project(tmp_path)
    from tests.helpers import reviewed_r5_lexicon_fixture
    reviewed_r5_lexicon_fixture(project, monkeypatch)
    revision = project / "revisions" / "001"
    submit_draft(
        project,
        revision / "script" / "script.yaml",
        revision / "storyboard" / "storyboard.yaml",
        revision / "assets" / "asset-manifest.yaml",
    )
    board = Storyboard.model_validate(read_yaml(revision / "storyboard" / "storyboard.yaml"))
    snapshot_r5_assets(revision, board)
    write_critic_review_fixture(project, product=False)
    submit_medical_review(project)

    # Missing license ledger blocks Gate 1.
    ledger_path = revision / R5_LICENSE_LEDGER
    saved_ledger = ledger_path.read_bytes()
    ledger_path.unlink()
    with pytest.raises((FileNotFoundError, ValueError)):
        approve_gate(project, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)
    ledger_path.write_bytes(saved_ledger)

    # Approve Gate 1, then tamper evidence -> stale hash blocks production.
    approve_gate(project, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)
    ledger_ev = revision / "evidence" / "ledger.yaml"
    saved_ev = ledger_ev.read_bytes()
    ledger_ev.write_bytes(saved_ev + b"\n# tampered\n")
    with pytest.raises(ValueError, match="current medical approval|stale"):
        produce_project(project, SilentTTS(), lambda _: 0, music=False)
    ledger_ev.write_bytes(saved_ev)

    # Produce validly, then check missing PIN blocks pronunciation override at Gate 2.
    _r5_alignment(monkeypatch)
    produce_project(
        project,
        _R5MockTTS(),
        _mock_render,
        music=False,
    )
    submit_video_fixture(project)
    pin_file = tmp_path / "pin.json"
    set_pin("654321", path=pin_file)
    qa_path = revision / "reviews" / "video-qa.json"
    qa = json.loads(qa_path.read_text(encoding="utf-8"))
    qa["status"] = "failed"
    qa["pronunciation"] = {
        "passed": False,
        "blocking_count": 1,
        "report_sha256": sha256_file(revision / "renders" / "pronunciation-qa.json"),
    }
    qa_path.write_text(json.dumps(qa), encoding="utf-8")
    with pytest.raises(ValueError, match="PIN"):
        approve_gate(
            project,
            GateKind.VIDEO,
            reviewer=REVIEWER,
            now=NOW,
            accept_pronunciation=True,
            pronunciation_pin=None,
            pin_file=pin_file,
        )

    # D4 budget ceilings: script 2, visual 3, product 3 -> stop_and_present_to_doctor.
    for stage, limit in (
        ("script", D4_SCRIPT_REVIEW_ROUNDS),
        ("visual", D4_VISUAL_REVIEW_ROUNDS),
        ("product", D4_PRODUCT_REVIEW_ROUNDS),
    ):
        status = review_budget.review_budget_status(revision, stage)
        for idx in range(status["used"], limit):
            review_budget.consume_review_budget(revision, stage, f"fill:{stage}:{idx + 1}")
        with pytest.raises(review_budget.ReviewBudgetExhausted) as exc_info:
            review_budget.consume_review_budget(revision, stage, f"over:{stage}")
        assert exc_info.value.brief["policy"] == "stop_and_present_to_doctor"
        assert exc_info.value.brief["passed"] is False


def test_r5_pinning_legacy_immutability_and_rollback_path(tmp_path: Path) -> None:
    """Opt-in R5 pins pyh_r5_quality_v1; legacy snapshot is immutable; omitting R5 rolls back cleanly."""
    # Mirror profiles/factory-standards.yaml into an isolated root (without Style A spec).
    standards_root = tmp_path / "standards-root"
    (standards_root / "profiles").mkdir(parents=True)
    (standards_root / factory_standards.STANDARDS_FILE).write_bytes(
        (REPO_ROOT / factory_standards.STANDARDS_FILE).read_bytes()
    )

    # Legacy project without R5 opt-in.
    legacy_project = create_v2_project_fixture(tmp_path / "legacy", state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    legacy_snapshot = factory_standards.pin_standards(standards_root, legacy_project)
    legacy_bytes = legacy_snapshot.read_bytes()
    assert "quality_standard" not in read_yaml(legacy_snapshot)

    # Re-pinning with quality_profile="r5_v1" must NEVER retroactively mutate an existing legacy snapshot.
    factory_standards.pin_standards(standards_root, legacy_project, quality_profile="r5_v1")
    assert legacy_snapshot.read_bytes() == legacy_bytes

    # Rollback path: producing a non-R5 project stays on the legacy path (no quality-report.json, no r5 keys).
    approve_gate(legacy_project, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)
    produce_project(
        legacy_project,
        SilentTTS(),
        _mock_render,
        music=False,
    )
    legacy_rev = legacy_project / "revisions" / "001"
    assert not (legacy_rev / "renders" / "quality-report.json").exists()
    legacy_input = json.loads((legacy_rev / "renders" / "render-input.json").read_text(encoding="utf-8"))
    assert "quality_profile" not in legacy_input
    assert "r5_contract" not in legacy_input

    # New revision opting into R5 pins the exact locked D1-D4 snapshot.
    r5_project = create_project_v2(tmp_path / "r5", "r5-opt-in", "R5 opt-in fixture", now=NOW)
    r5_rev = r5_project / "revisions" / "001"
    (r5_rev / "workflow" / "standards.yaml").unlink(missing_ok=True)
    r5_snapshot = factory_standards.pin_standards(standards_root, r5_project, quality_profile="r5_v1")
    assert read_yaml(r5_snapshot)["quality_standard"] == r5_standard_snapshot()
