"""Explicit asset rights/provenance declarations; no license inference."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from healthvideo.domain.asset_manifest import AssetManifest, _posix_relative_path


class LicenseEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    source: str
    creator: str
    license: str
    rights_basis: str
    revision: str = Field(pattern=r"^[0-9]{3}$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def _safe_path(cls, value: str) -> str:
        _posix_relative_path(value)
        return value

    @field_validator("source", "creator", "license", "rights_basis")
    @classmethod
    def _explicit_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source and usage rights must be explicit")
        return value


class LicenseLedger(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["2.0"] = "2.0"
    entries: tuple[LicenseEntry, ...] = ()

    @model_validator(mode="after")
    def _unique_paths(self) -> LicenseLedger:
        paths = [entry.path for entry in self.entries]
        if len(paths) != len(set(paths)):
            raise ValueError("duplicate license-ledger asset path")
        return self


def validate_license_ledger(
    manifest: AssetManifest, ledger: LicenseLedger, revision: str
) -> None:
    """Keep declared rights metadata bound to the exact registered asset bytes."""
    assets = {asset.path: asset for asset in manifest.assets}
    for entry in ledger.entries:
        asset = assets.get(entry.path)
        if asset is None or (
            entry.sha256 != asset.sha256
            or entry.revision != asset.revision
            or entry.revision != revision
            or entry.source != asset.source
            or entry.creator != asset.creator
            or entry.license != asset.license
        ):
            raise ValueError(
                f"license ledger does not match asset manifest: {entry.path}"
            )
    covered = {entry.path for entry in ledger.entries}
    if any(
        asset.kind.value == "data_chart" and asset.path not in covered
        for asset in manifest.assets
    ):
        raise ValueError("license ledger must cover every data chart")
