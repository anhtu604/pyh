import json
import runpy
from pathlib import Path

import pytest

from healthvideo.domain.storyboard import SUPPORTED_ANATOMY_SUBJECTS
from healthvideo.storage.files import sha256_file
from healthvideo.visuals.anatomy_library import (
    APPROVED_PATH,
    LIBRARY_PATH,
    library_status,
    load_library,
    record_approval,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _setup_fake_repo(tmp_path: Path) -> Path:
    anatomy_dir = tmp_path / LIBRARY_PATH.parent
    anatomy_dir.mkdir(parents=True, exist_ok=True)
    (anatomy_dir / "ArterySection.tsx").write_text(
        "export const ArterySection = () => <svg data-layer='lumen' />;\n",
        encoding="utf-8",
    )
    (anatomy_dir / "Heart.tsx").write_text(
        "export const Heart = () => <svg data-chamber='ventricles' />;\n",
        encoding="utf-8",
    )
    (tmp_path / LIBRARY_PATH).write_text(
        json.dumps(
            {
                "version": 1,
                "components": {
                    "artery_cross_section": {
                        "file": "ArterySection.tsx",
                        "layers": ["lumen"],
                    },
                    "heart": {
                        "file": "Heart.tsx",
                        "layers": ["ventricles"],
                    },
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return tmp_path


def test_new_component_flagged(tmp_path: Path) -> None:
    repo = _setup_fake_repo(tmp_path)
    assert library_status(repo) == {
        "artery_cross_section": "new",
        "heart": "new",
    }
    (repo / APPROVED_PATH).write_text(
        json.dumps({"version": 1, "components": {}}),
        encoding="utf-8",
    )
    assert library_status(repo) == {
        "artery_cross_section": "new",
        "heart": "new",
    }


def test_modified_component_flagged(tmp_path: Path) -> None:
    repo = _setup_fake_repo(tmp_path)
    record_approval(
        repo,
        ["artery_cross_section"],
        project="tang-huyet-ap",
        revision="001",
    )
    (repo / LIBRARY_PATH.parent / "ArterySection.tsx").write_text(
        "export const ArterySection = () => <svg data-layer='intima' />;\n",
        encoding="utf-8",
    )
    assert library_status(repo) == {
        "artery_cross_section": "modified",
        "heart": "new",
    }


def test_approved_component_status(tmp_path: Path) -> None:
    repo = _setup_fake_repo(tmp_path)
    record_approval(
        repo,
        ["artery_cross_section"],
        project="tang-huyet-ap",
        revision="001",
    )
    assert library_status(repo) == {
        "artery_cross_section": "approved",
        "heart": "new",
    }


def test_record_approval_roundtrip(tmp_path: Path) -> None:
    repo = _setup_fake_repo(tmp_path)
    record_approval(
        repo,
        ["artery_cross_section", "heart"],
        project="tang-huyet-ap",
        revision="002",
    )
    approved_file = repo / APPROVED_PATH
    assert approved_file.is_file()
    assert not list(approved_file.parent.glob("*.tmp"))
    payload = json.loads(approved_file.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert set(payload["components"]) == {"artery_cross_section", "heart"}
    artery_sha = sha256_file(repo / LIBRARY_PATH.parent / "ArterySection.tsx")
    heart_sha = sha256_file(repo / LIBRARY_PATH.parent / "Heart.tsx")
    assert payload["components"]["artery_cross_section"] == {
        "sha256": artery_sha,
        "project": "tang-huyet-ap",
        "revision": "002",
    }
    assert payload["components"]["heart"] == {
        "sha256": heart_sha,
        "project": "tang-huyet-ap",
        "revision": "002",
    }
    assert library_status(repo) == {
        "artery_cross_section": "approved",
        "heart": "approved",
    }


def test_supported_subjects_match_library() -> None:
    components = load_library(REPOSITORY_ROOT)
    assert isinstance(SUPPORTED_ANATOMY_SUBJECTS, tuple)
    assert tuple(components) == SUPPORTED_ANATOMY_SUBJECTS
    for info in components.values():
        assert (REPOSITORY_ROOT / LIBRARY_PATH.parent / info["file"]).is_file()
        assert isinstance(info.get("layers"), list) and info["layers"]


def test_supported_subjects_loaded_at_import(monkeypatch) -> None:
    monkeypatch.setattr(
        "healthvideo.visuals.anatomy_library.load_library",
        lambda repo: {"new_subject": {"file": "New.tsx"}},
    )
    module = runpy.run_path(str(REPOSITORY_ROOT / "src/healthvideo/domain/storyboard.py"))
    assert module["SUPPORTED_ANATOMY_SUBJECTS"] == ("new_subject",)


def test_supported_subjects_unreadable_library_fails(monkeypatch) -> None:
    def unreadable(repo):
        raise FileNotFoundError(str(repo / LIBRARY_PATH))

    monkeypatch.setattr("healthvideo.visuals.anatomy_library.load_library", unreadable)
    with pytest.raises((FileNotFoundError, RuntimeError), match="library.json"):
        runpy.run_path(str(REPOSITORY_ROOT / "src/healthvideo/domain/storyboard.py"))
