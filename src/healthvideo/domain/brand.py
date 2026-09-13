"""Validated visual identity tokens for deterministic PHY assets."""

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from healthvideo.storage.files import read_yaml


class MascotPose(StrEnum):
    WELCOME = "welcome"
    EXPLAIN = "explain"
    CAUTION = "caution"


class LogoVariant(StrEnum):
    HORIZONTAL = "horizontal"
    MONOGRAM = "monogram"
    ONE_COLOR = "one_color"


class BrandCanvas(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    width: Literal[1080] = 1080
    height: Literal[1920] = 1920
    fps: Literal[30] = 30


class BrandColors(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    navy: str = Field(pattern=r"^#[0-9A-F]{6}$")
    teal: str = Field(pattern=r"^#[0-9A-F]{6}$")
    yellow: str = Field(pattern=r"^#[0-9A-F]{6}$")
    off_white: str = Field(pattern=r"^#[0-9A-F]{6}$")
    charcoal: str = Field(pattern=r"^#[0-9A-F]{6}$")


class BrandAssets(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    creator: str = Field(pattern=r"\S")
    license: str = Field(pattern=r"\S")


class MascotIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    poses: tuple[MascotPose, ...]

    @model_validator(mode="after")
    def _exact_pose_set(self) -> "MascotIdentity":
        expected = (
            MascotPose.WELCOME,
            MascotPose.EXPLAIN,
            MascotPose.CAUTION,
        )
        if self.poses != expected:
            raise ValueError("mascot poses must be welcome, explain, caution")
        return self


class BrandProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    canvas: BrandCanvas
    colors: BrandColors
    assets: BrandAssets
    mascot: MascotIdentity


def load_brand_profile(path: Path) -> BrandProfile:
    """Load the checked, immutable PHY brand profile."""
    return BrandProfile.model_validate(read_yaml(path))
