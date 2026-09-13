from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from healthvideo.domain.brand import (
    BrandCanvas,
    BrandProfile,
    MascotPose,
    load_brand_profile,
)

ROOT = Path(__file__).resolve().parents[2]


def valid_brand_data() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "canvas": {"width": 1080, "height": 1920, "fps": 30},
        "colors": {
            "navy": "#12304A",
            "teal": "#18A6A6",
            "yellow": "#F4B942",
            "off_white": "#F7F4EC",
            "charcoal": "#263238",
        },
        "assets": {"creator": "Protect Your Health", "license": "PHY internal"},
        "mascot": {"poses": ["welcome", "explain", "caution"]},
    }


def test_checked_in_brand_profile_has_approved_phy_tokens() -> None:
    brand = load_brand_profile(ROOT / "profiles/brand.vi.yaml")
    assert brand.canvas == BrandCanvas(width=1080, height=1920, fps=30)
    assert brand.colors.model_dump() == valid_brand_data()["colors"]
    assert brand.mascot.poses == (
        MascotPose.WELCOME,
        MascotPose.EXPLAIN,
        MascotPose.CAUTION,
    )


@pytest.mark.parametrize("color", ["12304A", "#xyzxyz", "#12304AFF"])
def test_brand_profile_rejects_non_rgb_hex(color: str) -> None:
    data = deepcopy(valid_brand_data())
    assert isinstance(data["colors"], dict)
    data["colors"]["navy"] = color
    with pytest.raises(ValidationError):
        BrandProfile.model_validate(data)


def test_brand_profile_rejects_missing_token_unknown_pose_and_extra_field() -> None:
    missing = deepcopy(valid_brand_data())
    assert isinstance(missing["colors"], dict)
    del missing["colors"]["teal"]
    with pytest.raises(ValidationError):
        BrandProfile.model_validate(missing)

    pose = deepcopy(valid_brand_data())
    pose["mascot"] = {"poses": ["welcome", "dance", "caution"]}
    with pytest.raises(ValidationError):
        BrandProfile.model_validate(pose)

    extra = deepcopy(valid_brand_data())
    extra["slogan"] = "invented"
    with pytest.raises(ValidationError):
        BrandProfile.model_validate(extra)
