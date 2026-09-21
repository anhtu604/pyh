from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class JevConfig:
    api_key: str | None = None
    base_url: str | None = None
    model: str = "jev-v1"
    confidence_threshold: float = 0.90
    timeout_seconds: float = 10.0
    max_input_bytes: int = 16384

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    @property
    def masked_key(self) -> str:
        return "***" if self.is_configured else "not configured"

    def __repr__(self) -> str:
        return (
            f"JevConfig(api_key={self.masked_key!r}, model={self.model!r}, "
            f"confidence_threshold={self.confidence_threshold}, "
            f"timeout_seconds={self.timeout_seconds}, max_input_bytes={self.max_input_bytes})"
        )

    def __str__(self) -> str:
        return self.__repr__()


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    try:
        content = path.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            values[key.strip()] = val.strip().strip("'\"")
    except OSError:
        return {}
    return values


def resolve_jev_config(
    env: Mapping[str, str] | None = None,
    appdata_dir: Path | None = None,
) -> JevConfig:
    active_env = os.environ if env is None else env
    api_key = active_env.get("TYPESAFE_API_KEY")
    base_url = active_env.get("TYPESAFE_BASE_URL")
    model = active_env.get("TYPESAFE_MODEL", "jev-v1")

    if not api_key:
        local_appdata = (
            appdata_dir
            if appdata_dir is not None
            else (
                Path(active_env["LOCALAPPDATA"])
                if "LOCALAPPDATA" in active_env
                else Path.home() / "AppData" / "Local"
            )
        )
        secret_file = local_appdata / "ProtectYourHealth" / "typesafe.env"
        file_vars = _read_env_file(secret_file)
        api_key = file_vars.get("TYPESAFE_API_KEY")
        if not base_url:
            base_url = file_vars.get("TYPESAFE_BASE_URL")
        if model == "jev-v1" and "TYPESAFE_MODEL" in file_vars:
            model = file_vars["TYPESAFE_MODEL"]

    return JevConfig(
        api_key=api_key.strip() if api_key else None,
        base_url=base_url.strip() if base_url else None,
        model=model.strip() if model else "jev-v1",
        confidence_threshold=0.90,
        timeout_seconds=10.0,
        max_input_bytes=16384,
    )
