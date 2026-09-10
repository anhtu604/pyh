from pathlib import Path

from healthvideo.storage.project_layout import resolve_project_layout

GOLDEN_PROJECTS = [
    Path("tests/fixtures/golden-project"),
    Path("tests/fixtures/golden-project-v2"),
]


def test_v1_and_v2_golden_are_available_from_first_m1_task() -> None:
    layouts = [resolve_project_layout(path) for path in GOLDEN_PROJECTS]

    assert [layout.schema_version for layout in layouts] == ["1.0", "2.0"]
    for layout in layouts:
        assert (layout.artifact_root / "evidence" / "ledger.yaml").is_file()
        assert (layout.artifact_root / "script" / "script.yaml").is_file()
        assert (layout.artifact_root / "storyboard" / "storyboard.yaml").is_file()
