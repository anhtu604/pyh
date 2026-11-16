import json
import runpy
from pathlib import Path

import pytest

from healthvideo.domain.storyboard import (
    SUPPORTED_ANATOMY_SUBJECTS,
    Scene,
    Storyboard,
    validate_anatomy_subjects,
)
from healthvideo.storage.files import sha256_file
from healthvideo.visuals.anatomy_library import (
    APPROVED_PATH,
    LIBRARY_PATH,
    cue_actions,
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


def _anatomy_board(subject: str) -> Storyboard:
    return Storyboard(
        title="Live anatomy library",
        scenes=(Scene(
            id="S01", start_frame=0, duration_frames=90,
            narration="Anatomy", visual="anatomy_animation",
            anatomy={"subject": subject, "state": "normal", "motion": "pulse"},
        ),),
    )


def _use_fake_repo(tmp_path: Path, monkeypatch) -> Path:
    repo = _setup_fake_repo(tmp_path)
    monkeypatch.setattr(
        "healthvideo.domain.storyboard.__file__",
        str(repo / "src/healthvideo/domain/storyboard.py"),
    )
    return repo


def test_validation_reads_library_changes_without_reload(tmp_path: Path, monkeypatch) -> None:
    repo = _use_fake_repo(tmp_path, monkeypatch)
    board = _anatomy_board("new_subject")
    with pytest.raises(ValueError, match="unsupported anatomy subject 'new_subject'"):
        validate_anatomy_subjects(board)

    path = repo / LIBRARY_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["components"]["new_subject"] = {"file": "New.tsx"}
    path.write_text(json.dumps(payload), encoding="utf-8")
    validate_anatomy_subjects(board)

    del payload["components"]["new_subject"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported anatomy subject 'new_subject'"):
        validate_anatomy_subjects(board)


def test_variety_error_lists_current_subjects(tmp_path: Path, monkeypatch) -> None:
    repo = _use_fake_repo(tmp_path, monkeypatch)
    board = _anatomy_board("heart")
    path = repo / LIBRARY_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["components"]["new_subject"] = {"file": "New.tsx"}
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="choose from library.json: .*new_subject"):
        Storyboard(title=board.title, scenes=board.scenes * 2)


def test_validation_reports_corrupt_library_after_success(tmp_path: Path, monkeypatch) -> None:
    repo = _use_fake_repo(tmp_path, monkeypatch)
    board = _anatomy_board("heart")
    validate_anatomy_subjects(board)
    (repo / LIBRARY_PATH).write_text('{"components":', encoding="utf-8")
    with pytest.raises(ValueError, match=r"Invalid anatomy library JSON.*library\.json"):
        validate_anatomy_subjects(board)


def test_validation_reports_missing_library(tmp_path: Path, monkeypatch) -> None:
    repo = _use_fake_repo(tmp_path, monkeypatch)
    (repo / LIBRARY_PATH).unlink()
    with pytest.raises((OSError, RuntimeError), match=r"library\.json"):
        validate_anatomy_subjects(_anatomy_board("heart"))


def test_cue_actions_reads_library_and_component_changes(tmp_path: Path) -> None:
    repo = _setup_fake_repo(tmp_path)
    component = repo / LIBRARY_PATH.parent / "Heart.tsx"
    component.write_text("export const CUE_ACTIONS = ['pulse'];", encoding="utf-8")
    assert cue_actions(repo, "heart") == ("pulse",)
    component.write_text("export const CUE_ACTIONS = ['relax'];", encoding="utf-8")
    assert cue_actions(repo, "heart") == ("relax",)

    other = component.with_name("New.tsx")
    other.write_text("export const CUE_ACTIONS = ['highlight'];", encoding="utf-8")
    path = repo / LIBRARY_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["components"]["heart"]["file"] = "New.tsx"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert cue_actions(repo, "heart") == ("highlight",)
    path.write_text('{"components":', encoding="utf-8")
    with pytest.raises(ValueError, match=r"Invalid anatomy library JSON.*library\.json"):
        cue_actions(repo, "heart")
