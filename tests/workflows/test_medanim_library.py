from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.approver_pin import set_pin
from healthvideo.domain.medanim_library import MedAnimEntry
from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic
from healthvideo.workflows.medanim_library import (
    approve_medanim_entry,
    approved_medanim_catalog,
    list_medanim_library,
    reject_medanim_entry,
    resolve_medanim_preview,
)

NOW = datetime(2026, 11, 19, 12, 30, tzinfo=UTC)
SVG_BYTES = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4"/></svg>\n'
PNG_BYTES = b"\x89PNG\r\n\x1a\nfakepng"


def _build_entry_payload(
    *,
    anim_id: str = "alveolar-gas-exchange",
    asset_sha: str,
    license_name: str = "Public Domain",
    passed: bool = True,
    checked_claims: bool = True,
    checked_anatomy: bool = True,
    quote: str = "Oxygen diffuses across the alveolar capillary membrane into pulmonary capillary blood.",
    open_issues: list[dict] | None = None,
) -> dict:
    return {
        "schema_version": "1.0",
        "id": anim_id,
        "title": "Trao đổi khí tại phế nang",
        "category": "physiology",
        "summary": "Khuếch tán O2 và CO2 qua màng phế nang - mao mạch.",
        "target_duration_seconds": 45,
        "compositions": {
            "landscape": "MedAnimAlveolarGasExchange",
            "portrait": "MedAnimAlveolarGasExchangeVertical",
        },
        "sources": [
            {
                "id": "wagner2015",
                "pmid": "25595605",
                "pmcid": "PMC4318661",
                "doi": "10.1183/09031936.00039214",
                "citation": "Wagner PD. The physiological basis of pulmonary gas exchange. Eur Respir J. 2015.",
                "checked_in": "full_text",
                "url": "https://europepmc.org/article/PMC/PMC4318661",
            }
        ],
        "steps": [
            {
                "id": "B1",
                "t_start": 0.0,
                "t_end": 10.0,
                "narration": "Oxy đi từ lòng phế nang qua màng mỏng vào mao mạch phổi.",
                "visual": "Phế nang và mao mạch phổi vector SVG.",
                "claim": "Khí khuếch tán thụ động qua hàng rào phế nang - mao mạch.",
                "quotes": [
                    {
                        "source_id": "wagner2015",
                        "quote": quote,
                        "locator": "Introduction",
                    }
                ],
            }
        ],
        "assets": [
            {
                "file": "alveolus.svg",
                "source_page": "https://bioart.niaid.nih.gov/bioart/1",
                "original_url": "https://bioart.niaid.nih.gov/api/bioarts/1/files/1",
                "author": "NIAID BioArt",
                "license": license_name,
                "sha256": asset_sha,
            }
        ],
        "medical_audit": {
            "checked_claims": checked_claims,
            "checked_anatomy": checked_anatomy,
            "auditor_role": "medical_expert",
            "audited_at": NOW.isoformat(),
            "passed": passed,
        },
        "open_issues": open_issues or [],
        "preview_frames": ["previews/b1.png"],
    }


def _create_medanim_fixture(
    root: Path,
    *,
    anim_id: str = "alveolar-gas-exchange",
    in_public: bool = False,
    passed: bool = True,
    open_issues: list[dict] | None = None,
) -> tuple[Path, Path]:
    entry_dir = root / "library" / "medanim" / anim_id
    (entry_dir / "assets").mkdir(parents=True, exist_ok=True)
    (entry_dir / "previews").mkdir(parents=True, exist_ok=True)
    asset_file = entry_dir / "assets" / "alveolus.svg"
    asset_file.write_bytes(SVG_BYTES)
    if in_public:
        pub_file = root / "video" / "public" / "medanim" / anim_id / "alveolus.svg"
        pub_file.parent.mkdir(parents=True, exist_ok=True)
        pub_file.write_bytes(SVG_BYTES)
    (entry_dir / "previews" / "b1.png").write_bytes(PNG_BYTES)
    digest = sha256_file(asset_file)
    write_yaml_atomic(
        entry_dir / "animation.yaml",
        _build_entry_payload(anim_id=anim_id, asset_sha=digest, passed=passed, open_issues=open_issues),
    )
    pin_path = root / "config" / "approver-pin.json"
    set_pin("918273", path=pin_path)
    return entry_dir, pin_path


@pytest.mark.parametrize("bad_license", ["CC BY-SA 4.0", "CC BY-SA 3.0", "CC BY-NC 4.0", "CC BY-ND 4.0", "All Rights Reserved"])
def test_schema_rejects_forbidden_licenses(bad_license):
    payload = _build_entry_payload(asset_sha="a" * 64, license_name=bad_license)
    with pytest.raises(ValueError, match="license"):
        MedAnimEntry.model_validate(payload)


@pytest.mark.parametrize("ok_license", ["Public Domain", "CC0", "CC0 1.0", "CC BY 3.0", "CC BY 4.0"])
def test_schema_accepts_open_allowlist_licenses(ok_license):
    payload = _build_entry_payload(asset_sha="a" * 64, license_name=ok_license)
    entry = MedAnimEntry.model_validate(payload)
    assert entry.assets[0].license in {"Public Domain", "CC0", "CC BY 3.0", "CC BY 4.0"}


def test_schema_enforces_quote_word_limit_and_audit_flags():
    too_long = " ".join(["word"] * 26)
    with pytest.raises(ValueError, match="25 words"):
        MedAnimEntry.model_validate(_build_entry_payload(asset_sha="a" * 64, quote=too_long))

    with pytest.raises(ValueError, match="checked_claims"):
        MedAnimEntry.model_validate(_build_entry_payload(asset_sha="a" * 64, passed=True, checked_anatomy=False))


def test_approve_requires_pin_audit_and_matching_sha256_then_invalidates_on_edit(tmp_path):
    entry_dir, pin_path = _create_medanim_fixture(tmp_path, in_public=True)

    # Wrong PIN rejected
    with pytest.raises(PermissionError):
        approve_medanim_entry(
            tmp_path,
            "alveolar-gas-exchange",
            reviewer="BS An",
            pin="000000",
            pin_file=pin_path,
            now=NOW,
        )
    assert not (entry_dir / "doctor-approval.yaml").exists()
    assert approved_medanim_catalog(tmp_path) == []

    # Approve with valid PIN
    record = approve_medanim_entry(
        tmp_path,
        "alveolar-gas-exchange",
        reviewer="BS An",
        pin="918273",
        note="Đạt chuẩn sinh lý.",
        pin_file=pin_path,
        now=NOW,
    )
    assert record.anim_id == "alveolar-gas-exchange"
    assert (entry_dir / "doctor-approval.yaml").is_file()
    assert len(approved_medanim_catalog(tmp_path)) == 1

    # Duplicate approval on unchanged files refused
    with pytest.raises(FileExistsError):
        approve_medanim_entry(
            tmp_path,
            "alveolar-gas-exchange",
            reviewer="BS An",
            pin="918273",
            pin_file=pin_path,
            now=NOW,
        )

    # Modifying animation.yaml automatically switches status to needs_reapproval
    anim_data = read_yaml(entry_dir / "animation.yaml")
    anim_data["summary"] = "Bản đã chỉnh sửa câu mô tả."
    write_yaml_atomic(entry_dir / "animation.yaml", anim_data)

    listed = list_medanim_library(tmp_path)
    assert listed[0]["status"] == "needs_reapproval"
    assert approved_medanim_catalog(tmp_path) == []

    # Re-approval succeeds by archiving superseded approval without overwriting history
    reapproved = approve_medanim_entry(
        tmp_path,
        "alveolar-gas-exchange",
        reviewer="BS An",
        pin="918273",
        pin_file=pin_path,
        now=NOW,
    )
    assert reapproved.content_sha256 == sha256_file(entry_dir / "animation.yaml")
    assert list((entry_dir / "reviews").glob("*-superseded-approval*.yaml"))
    assert len(approved_medanim_catalog(tmp_path)) == 1

    # Modifying real asset file also flips to needs_reapproval
    (entry_dir / "assets" / "alveolus.svg").write_bytes(SVG_BYTES + b"<!-- changed -->\n")
    assert list_medanim_library(tmp_path)[0]["status"] == "needs_reapproval"
    assert approved_medanim_catalog(tmp_path) == []


def test_approve_refuses_failed_medical_audit_or_public_drift(tmp_path):
    entry_dir, pin_path = _create_medanim_fixture(tmp_path, in_public=True, passed=False)
    with pytest.raises(ValueError, match="medical_audit.passed"):
        approve_medanim_entry(
            tmp_path,
            "alveolar-gas-exchange",
            reviewer="BS An",
            pin="918273",
            pin_file=pin_path,
            now=NOW,
        )

    # Fix audit, break public copy hash
    anim_data = read_yaml(entry_dir / "animation.yaml")
    anim_data["medical_audit"]["passed"] = True
    write_yaml_atomic(entry_dir / "animation.yaml", anim_data)
    (tmp_path / "video" / "public" / "medanim" / "alveolar-gas-exchange" / "alveolus.svg").write_bytes(b"<svg/>")
    with pytest.raises(ValueError, match="không khớp"):
        approve_medanim_entry(
            tmp_path,
            "alveolar-gas-exchange",
            reviewer="BS An",
            pin="918273",
            pin_file=pin_path,
            now=NOW,
        )


def test_reject_writes_immutable_record_and_revokes_prior_approval(tmp_path):
    entry_dir, pin_path = _create_medanim_fixture(tmp_path)
    approve_medanim_entry(
        tmp_path,
        "alveolar-gas-exchange",
        reviewer="BS An",
        pin="918273",
        pin_file=pin_path,
        now=NOW,
    )
    assert len(approved_medanim_catalog(tmp_path)) == 1

    rej = reject_medanim_entry(
        tmp_path,
        "alveolar-gas-exchange",
        reviewer="BS An",
        reason="Cần bổ sung nhãn màng đáy.",
        pin="918273",
        pin_file=pin_path,
        now=NOW,
    )
    assert rej.decision == "rejected"
    assert not (entry_dir / "doctor-approval.yaml").exists()
    assert list((entry_dir / "reviews").glob("*-rejected*.yaml"))
    assert list_medanim_library(tmp_path)[0]["status"] == "rejected"
    assert approved_medanim_catalog(tmp_path) == []


def test_resolve_preview_blocks_traversal_and_non_raster(tmp_path):
    entry_dir, _ = _create_medanim_fixture(tmp_path)
    resolved = resolve_medanim_preview(tmp_path, "alveolar-gas-exchange", "b1.png")
    assert resolved == (entry_dir / "previews" / "b1.png").resolve()
    assert resolve_medanim_preview(tmp_path, "alveolar-gas-exchange", "previews/b1.png") == resolved

    with pytest.raises(LookupError):
        resolve_medanim_preview(tmp_path, "alveolar-gas-exchange", "../assets/alveolus.svg")
    with pytest.raises(LookupError):
        resolve_medanim_preview(tmp_path, "alveolar-gas-exchange", "alveolus.svg")
