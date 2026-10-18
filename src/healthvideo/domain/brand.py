"""Validated visual identity tokens for deterministic PYH assets."""

import struct
from enum import StrEnum
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from healthvideo.storage.files import read_yaml

REPO_ROOT = Path(__file__).resolve().parents[3]


class MascotPose(StrEnum):
    WELCOME = "welcome"
    EXPLAIN = "explain"
    CAUTION = "caution"


class LogoVariant(StrEnum):
    HORIZONTAL = "horizontal"
    MONOGRAM = "monogram"
    ONE_COLOR = "one_color"
    REVERSE = "reverse"


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
    night: str = Field(pattern=r"^#[0-9A-F]{6}$")


class BrandAssets(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    creator: str = Field(pattern=r"\S")
    license: str = Field(pattern=r"\S")


class MascotArtwork(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    def resolved_path(self) -> Path:
        path = PurePosixPath(self.path)
        if (not self.path or "\\" in self.path or ":" in self.path
                or path.is_absolute() or ".." in path.parts
                or self.path != path.as_posix() or path.suffix != ".png"):
            raise ValueError("mascot artwork must use a relative POSIX .png path")
        target = (REPO_ROOT / self.path).resolve()
        if not target.is_relative_to(REPO_ROOT.resolve()):
            raise ValueError("mascot artwork must use a relative POSIX path inside repo")
        return target

    def png_dimensions(self) -> tuple[int, int]:
        target = self.resolved_path()
        if not target.is_file():
            raise ValueError(f"mascot artwork file does not exist: {self.path}")
        data = target.read_bytes()
        if sha256(data).hexdigest() != self.sha256:
            raise ValueError(f"mascot artwork SHA-256 mismatch: {self.path}")
        if (len(data) < 33 or data[:8] != b"\x89PNG\r\n\x1a\n"
                or data[8:16] != b"\0\0\0\rIHDR"):
            raise ValueError(f"mascot artwork must be PNG with IHDR: {self.path}")
        width, height, depth, color, compression, filtering, interlace = struct.unpack(
            ">IIBBBBB", data[16:29]
        )
        if color != 6 or depth not in (8, 16) or compression or filtering or interlace > 1:
            raise ValueError(f"mascot artwork must be PNG RGBA: {self.path}")
        if min(width, height) < 768:
            raise ValueError("mascot artwork shortest edge must be at least 768 pixels")
        return width, height


class MascotIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    poses: tuple[MascotPose, ...]
    artwork: dict[MascotPose, MascotArtwork] | None = None

    @model_validator(mode="after")
    def _exact_pose_set(self) -> "MascotIdentity":
        expected = (
            MascotPose.WELCOME,
            MascotPose.EXPLAIN,
            MascotPose.CAUTION,
        )
        if self.poses != expected:
            raise ValueError("mascot poses must be welcome, explain, caution")
        if self.artwork is not None:
            if set(self.artwork) != set(expected):
                raise ValueError("mascot artwork requires all three poses")
            dimensions = {item.png_dimensions() for item in self.artwork.values()}
            if len(dimensions) != 1:
                raise ValueError("mascot artwork must have the same dimensions")
        return self


class BrandCTA(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    youtube_full_video: str = Field(
        default="Xem bản đầy đủ trên YouTube", pattern=r"\S"
    )


class BrandProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    canvas: BrandCanvas
    colors: BrandColors
    assets: BrandAssets
    mascot: MascotIdentity
    cta: BrandCTA = Field(default_factory=BrandCTA)


def load_brand_profile(path: Path) -> BrandProfile:
    """Load the checked, immutable PYH brand profile."""
    return BrandProfile.model_validate(read_yaml(path))
