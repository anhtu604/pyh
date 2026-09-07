from typer.testing import CliRunner

from healthvideo import __version__
from healthvideo.cli import app


def test_version_command() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__
