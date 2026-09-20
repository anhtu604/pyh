import tomllib
from pathlib import Path


def test_click_is_declared_as_a_direct_runtime_dependency() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert "click==8.5.0" in project["project"]["dependencies"]
