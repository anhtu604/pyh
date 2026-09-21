from collections.abc import Mapping
from pathlib import Path

from healthvideo.jev.config import resolve_jev_config


def test_resolve_config_from_process_env_precedence(tmp_path: Path) -> None:
    appdata = tmp_path / "appdata"
    secret_dir = appdata / "ProtectYourHealth"
    secret_dir.mkdir(parents=True)
    (secret_dir / "typesafe.env").write_text("TYPESAFE_API_KEY=file-secret-key\n", encoding="utf-8")

    env: Mapping[str, str] = {
        "TYPESAFE_API_KEY": "env-secret-key",
        "TYPESAFE_MODEL": "jev-custom-model",
    }

    config = resolve_jev_config(env=env, appdata_dir=appdata)

    assert config.api_key == "env-secret-key"
    assert config.model == "jev-custom-model"
    assert config.is_configured is True
    assert config.masked_key == "***"
    assert "env-secret-key" not in repr(config)
    assert "env-secret-key" not in str(config)


def test_resolve_config_from_local_appdata_fallback(tmp_path: Path) -> None:
    appdata = tmp_path / "appdata"
    secret_dir = appdata / "ProtectYourHealth"
    secret_dir.mkdir(parents=True)
    (secret_dir / "typesafe.env").write_text("TYPESAFE_API_KEY=file-fallback-key\n", encoding="utf-8")

    config = resolve_jev_config(env={}, appdata_dir=appdata)

    assert config.api_key == "file-fallback-key"
    assert config.is_configured is True
    assert "file-fallback-key" not in repr(config)


def test_resolve_config_missing_fails_closed(tmp_path: Path) -> None:
    appdata = tmp_path / "appdata"
    config = resolve_jev_config(env={}, appdata_dir=appdata)

    assert config.api_key is None
    assert config.is_configured is False
    assert config.masked_key == "not configured"
    assert config.confidence_threshold == 0.90
    assert config.max_input_bytes == 16384


def test_resolve_config_ignores_malformed_file(tmp_path: Path) -> None:
    appdata = tmp_path / "appdata"
    secret_dir = appdata / "ProtectYourHealth"
    secret_dir.mkdir(parents=True)
    (secret_dir / "typesafe.env").write_text("MALFORMED_LINE_WITHOUT_EQUALS\n", encoding="utf-8")

    config = resolve_jev_config(env={}, appdata_dir=appdata)

    assert config.api_key is None
    assert config.is_configured is False
