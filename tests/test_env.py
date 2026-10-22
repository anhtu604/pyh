"""Tests for `.env` loading and CLI startup integration."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from healthvideo.cli import app
from healthvideo.env import load_dotenv


def test_load_dotenv_sets_missing_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXISTING_API_KEY", "already-set")
    monkeypatch.delenv("NEW_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "EXISTING_API_KEY=from-dotenv\nNEW_API_KEY=fresh-value\n",
        encoding="utf-8",
    )

    loaded = load_dotenv(env_file)

    assert loaded == {"NEW_API_KEY": "fresh-value"}
    assert os.environ["EXISTING_API_KEY"] == "already-set"
    assert os.environ["NEW_API_KEY"] == "fresh-value"


def test_load_dotenv_skips_pin_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APPROVER_PIN", raising=False)
    monkeypatch.delenv("pin_secret", raising=False)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APPROVER_PIN=123456\npin_secret=abcdef\nYOUTUBE_API_KEY=yt-123\n",
        encoding="utf-8",
    )

    loaded = load_dotenv(env_file)

    assert loaded == {"YOUTUBE_API_KEY": "yt-123"}
    assert "APPROVER_PIN" not in os.environ
    assert "pin_secret" not in os.environ
    assert os.environ["YOUTUBE_API_KEY"] == "yt-123"


def test_load_dotenv_strips_quotes_and_comments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in ("DOUBLE_QUOTED", "SINGLE_QUOTED", "UNQUOTED_COMMENT", "UTF8_NOTE"):
        monkeypatch.delenv(key, raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "# Comment đầu file\n"
        "\n"
        'DOUBLE_QUOTED="value with spaces"\n'
        "SINGLE_QUOTED='single-quoted-value'\n"
        "UNQUOTED_COMMENT=plain-token # inline comment\n"
        'UTF8_NOTE="Bác sĩ kiểm duyệt"\n',
        encoding="utf-8",
    )

    loaded = load_dotenv(env_file)

    assert loaded == {
        "DOUBLE_QUOTED": "value with spaces",
        "SINGLE_QUOTED": "single-quoted-value",
        "UNQUOTED_COMMENT": "plain-token",
        "UTF8_NOTE": "Bác sĩ kiểm duyệt",
    }


def test_cli_callback_loads_dotenv_without_printing_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.delenv("HEALTHVIDEO_PIN", raising=False)
    secret_value = "super-secret-youtube-token-999"
    (tmp_path / ".env").write_text(
        f'YOUTUBE_API_KEY="{secret_value}"\nHEALTHVIDEO_PIN=123456\n',
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["step", "version"])

    assert result.exit_code == 0
    assert os.environ.get("YOUTUBE_API_KEY") == secret_value
    assert "HEALTHVIDEO_PIN" not in os.environ
    assert secret_value not in result.output
