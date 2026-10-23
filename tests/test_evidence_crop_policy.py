from pathlib import Path

import pytest

from healthvideo.assets import validate_evidence_highlights
from healthvideo.domain.asset_manifest import AssetManifest
from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.files import read_yaml, write_yaml_atomic

FIXTURE = Path("tests/fixtures/golden-project-v2/revisions/001")


def test_registered_synthetic_raster_crop_passes_policy():
    validate_evidence_highlights(
        FIXTURE, Storyboard.model_validate(read_yaml(FIXTURE / "storyboard/storyboard.yaml")),
        AssetManifest.model_validate(read_yaml(FIXTURE / "assets/asset-manifest.yaml")),
    )


@pytest.mark.parametrize("change", ["svg", "no_source", "no_crop", "no_rights", "wrong_source", "wrong_size", "wrong_hash"])
def test_fake_or_unbound_source_image_is_refused(tmp_path, change):
    import shutil

    root = tmp_path / "001"
    shutil.copytree(FIXTURE, root)
    data = read_yaml(root / "storyboard/storyboard.yaml")
    manifest = read_yaml(root / "assets/asset-manifest.yaml")
    highlight = next(s["evidence_highlight"] for s in data["scenes"] if s.get("evidence_highlight"))
    asset = next(a for a in manifest["assets"] if a["path"] == highlight["image"])
    if change == "svg":
        highlight["image"] = "assets/evidence-r01.svg"
    elif change == "no_source":
        highlight["source_id"] = highlight["page"] = None
        for key in list(highlight):
            if key.startswith("crop_"):
                highlight[key] = None
    elif change == "no_crop":
        for key in list(highlight):
            if key.startswith("crop_"):
                highlight[key] = None
    elif change == "no_rights":
        asset["rights_required"] = False
    elif change == "wrong_source":
        highlight["source_id"] = "invented-source"
    elif change == "wrong_size":
        highlight["crop_pixel_width"] += 1
    elif change == "wrong_hash":
        (root / highlight["image"]).write_bytes(b"fake bytes")
    with pytest.raises(ValueError):
        validate_evidence_highlights(root, Storyboard.model_validate(data), AssetManifest.model_validate(manifest))


def test_missing_license_ledger_refuses_source_image(tmp_path):
    import shutil

    root = tmp_path / "001"
    shutil.copytree(FIXTURE, root)
    (root / "assets/license-ledger.yaml").unlink()
    with pytest.raises(ValueError, match="license ledger"):
        validate_evidence_highlights(
            root, Storyboard.model_validate(read_yaml(root / "storyboard/storyboard.yaml")),
            AssetManifest.model_validate(read_yaml(root / "assets/asset-manifest.yaml")),
        )


def test_license_metadata_must_match_exact_source_bytes(tmp_path):
    import shutil

    root = tmp_path / "001"
    shutil.copytree(FIXTURE, root)
    rights = read_yaml(root / "assets/license-ledger.yaml")
    rights["entries"][0]["sha256"] = "0" * 64
    write_yaml_atomic(root / "assets/license-ledger.yaml", rights)
    with pytest.raises(ValueError, match="license ledger does not match"):
        validate_evidence_highlights(
            root, Storyboard.model_validate(read_yaml(root / "storyboard/storyboard.yaml")),
            AssetManifest.model_validate(read_yaml(root / "assets/asset-manifest.yaml")),
        )
