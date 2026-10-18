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
            "night": "#0A1C2E",
        },
        "assets": {"creator": "Protect Your Health", "license": "PYH internal"},
        "mascot": {"poses": ["welcome", "explain", "caution"]},
    }


def test_brand_profile_has_approved_pyh_tokens(brand_profile_path) -> None:
    brand = load_brand_profile(brand_profile_path)
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



def test_night_is_required() -> None:
    data = valid_brand_data()
    del data["colors"]["night"]
    with pytest.raises(ValidationError, match="night"):
        BrandProfile.model_validate(data)


def test_palette_matches_profile(brand_profile_path) -> None:
    import re

    palette = (ROOT / "video/src/anatomy/palette.ts").read_text(encoding="utf-8")
    tokens = dict(re.findall(r"(\w+): '(#[0-9A-F]{6})'", palette.split("} as const;")[0]))
    assert tokens == load_brand_profile(brand_profile_path).colors.model_dump()


@pytest.mark.parametrize("problem, message", [
    ("missing_pose", "three poses"),
    ("hash", "SHA-256"),
    ("signature", "PNG"),
    ("rgb", "RGBA"),
    ("dimensions", "same dimensions"),
    ("small", "768"),
    ("missing_file", "exist"),
    ("traversal", "relative POSIX"),
    ("backslash", "relative POSIX"),
    ("absolute", "relative POSIX"),
])
def test_artwork_rejects_invalid_files(artwork_brand, problem, message) -> None:
    from hashlib import sha256

    from tests.brand_artwork import png_bytes

    data, root = artwork_brand
    artwork = data["mascot"]["artwork"]
    entry = artwork["welcome"]
    target = root / entry["path"]
    if problem == "missing_pose":
        del artwork["caution"]
    elif problem == "hash":
        entry["sha256"] = "0" * 64
    elif problem in {"signature", "rgb", "dimensions", "small"}:
        content = {"signature": b"not a PNG", "rgb": png_bytes(color_type=2),
                   "dimensions": png_bytes(width=800), "small": png_bytes(width=767)}[problem]
        target.write_bytes(content)
        entry["sha256"] = sha256(content).hexdigest()
    elif problem == "missing_file":
        target.unlink()
    else:
        entry["path"] = {"traversal": "../welcome.png", "backslash": r"assets\welcome.png",
                         "absolute": "C:/welcome.png"}[problem]
    with pytest.raises(ValidationError, match=message):
        BrandProfile.model_validate(data)


def test_artwork_accepts_complete_rgba_set(artwork_brand) -> None:
    data, _ = artwork_brand
    brand = BrandProfile.model_validate(data)
    assert set(brand.mascot.artwork) == set(MascotPose)


def test_checked_in_artwork_loads_and_validates() -> None:
    brand = load_brand_profile(ROOT / "profiles/brand.vi.yaml")
    assert brand.mascot.artwork is not None
    assert set(brand.mascot.artwork) == set(MascotPose)
    dimensions = {asset.png_dimensions() for asset in brand.mascot.artwork.values()}
    assert len(dimensions) == 1
    width, height = dimensions.pop()
    assert width == height and width >= 768
