import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

import healthvideo.workflows.package as package_workflow
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.gate_review import approve_gate
from healthvideo.workflows.package import package_project
from healthvideo.workflows.produce import produce_project
from tests.helpers import (
    create_long_form_project_fixture,
    create_v2_project_fixture,
    submit_video_fixture,
)

NOW = datetime(2026, 9, 12, 8, 0, tzinfo=UTC)


def test_v2_package_refuses_before_video_approval(tmp_path: Path) -> None:
    project_dir = _v2_awaiting_video_review_project(tmp_path)

    with pytest.raises(ValueError, match="video_approved|video approval"):
        package_project(project_dir)

    assert not (_revision_root(project_dir) / "publish").exists()


def test_v2_package_refuses_video_bytes_that_no_longer_match_approval(
    tmp_path: Path,
) -> None:
    project_dir = _v2_video_approved_project(tmp_path)
    (_revision_root(project_dir) / "renders" / "video.mp4").write_bytes(
        b"changed-after-approval"
    )

    with pytest.raises(ValueError, match="video approval"):
        package_project(project_dir)

    assert not (_revision_root(project_dir) / "publish").exists()


def test_v2_package_promotes_payload_then_transitions_to_packaged(
    tmp_path: Path, monkeypatch
) -> None:
    project_dir = _v2_video_approved_project(tmp_path)
    resolutions = 0
    real_resolve = package_workflow.resolve_project_layout

    def counting_resolve(path: Path):
        nonlocal resolutions
        resolutions += 1
        return real_resolve(path)

    monkeypatch.setattr(package_workflow, "resolve_project_layout", counting_resolve)

    output = package_project(project_dir)

    assert output == _revision_root(project_dir) / "publish"
    assert {"video.mp4", "caption.txt", "sources.md", "posts.yaml", "posts.md", "manifest.json"} <= {
        path.name for path in output.iterdir()
    }
    assert read_yaml(project_dir / "project.yaml")["state"] == (
        WorkflowState.PACKAGED.value
    )
    assert resolutions == 1


def test_v2_package_promotion_failure_keeps_state_and_leaves_no_partial_package(
    tmp_path: Path, monkeypatch
) -> None:
    project_dir = _v2_video_approved_project(tmp_path)

    def fail_promotion(source_dir: Path, destination_dir: Path) -> None:
        raise OSError("synthetic package promotion failure")

    monkeypatch.setattr(
        package_workflow, "replace_directory_atomic", fail_promotion
    )

    with pytest.raises(OSError, match="promotion failure"):
        package_project(project_dir)

    revision_root = _revision_root(project_dir)
    assert read_yaml(project_dir / "project.yaml")["state"] == (
        WorkflowState.VIDEO_APPROVED.value
    )
    assert not (revision_root / "publish").exists()
    assert list(revision_root.glob(".*.package-*")) == []


def test_v2_package_rejects_render_input_changed_during_copy(
    tmp_path: Path, monkeypatch
) -> None:
    project_dir = _v2_video_approved_project(tmp_path)
    real_copy = shutil.copy2

    def tampering_copy(source: Path, destination: Path) -> Path:
        copied = real_copy(source, destination)
        if source.name == "render-input.json":
            payload = json.loads(destination.read_text(encoding="utf-8"))
            payload["title"] = "Unapproved staged render input"
            destination.write_text(json.dumps(payload), encoding="utf-8")
        return copied

    monkeypatch.setattr(package_workflow.shutil, "copy2", tampering_copy)

    with pytest.raises(ValueError, match="staged render_input"):
        package_project(project_dir)

    revision_root = _revision_root(project_dir)
    assert read_yaml(project_dir / "project.yaml")["state"] == "video_approved"
    assert not (revision_root / "publish").exists()
    assert list(revision_root.glob(".*.package-*")) == []


ZERO_AI_PAYLOAD = {
    "video.mp4",
    "caption.txt",
    "sources.md",
    "posts.yaml",
    "posts.md",
    "manifest.json",
    "render-input.json",
}


def test_v2_zero_ai_package_keeps_exact_payload_without_disclosure(tmp_path: Path) -> None:
    output = package_project(_v2_video_approved_project(tmp_path))

    assert {path.name for path in output.iterdir()} == ZERO_AI_PAYLOAD
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["payload_sha256"]) == ZERO_AI_PAYLOAD - {"manifest.json"}


def _v2_awaiting_video_review_project(tmp_path: Path) -> Path:
    project_dir = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    storyboard_path = _revision_root(project_dir) / "storyboard" / "storyboard.yaml"
    storyboard = read_yaml(storyboard_path)
    write_yaml_atomic(storyboard_path, storyboard)
    approve_gate(
        project_dir,
        GateKind.MEDICAL,
        reviewer="BS Nguyễn Văn An",
        now=NOW,
    )
    produce_project(project_dir, SilentTTS(), _fake_renderer)
    submit_video_fixture(project_dir)
    return project_dir


def _v2_video_approved_project(tmp_path: Path) -> Path:
    project_dir = _v2_awaiting_video_review_project(tmp_path)
    approve_gate(
        project_dir,
        GateKind.VIDEO,
        reviewer="BS Nguyễn Văn An",
        now=NOW,
    )
    return project_dir


def _revision_root(project_dir: Path) -> Path:
    return project_dir / "revisions" / "001"


def _fake_renderer(argv: list[str]) -> int:
    output = Path(argv[argv.index("--output") + 1] if '--output' in argv else argv[-1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"synthetic-v2-mp4")
    return 0


@pytest.fixture
def long_approved_project(tmp_path):
    project = create_long_form_project_fixture(tmp_path)
    approve_gate(project, GateKind.MEDICAL, reviewer='BS thử', now=NOW)
    produce_project(project, SilentTTS(), _fake_renderer)
    submit_video_fixture(project)
    approve_gate(project, GateKind.VIDEO, reviewer='BS thử', now=NOW)
    return project


def test_long_package_includes_hashed_srt_with_outro_and_no_short_sidecars(long_approved_project):
    output = package_project(long_approved_project)
    srt = output / 'subtitles.vi.srt'
    manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['payload_sha256']['subtitles.vi.srt'] == sha256_file(srt)
    assert list(output.rglob('*.srt')) == [srt]
    script = read_yaml(_revision_root(long_approved_project) / 'script/script.yaml')
    blocks = srt.read_text(encoding='utf-8').strip().split('\n\n')
    words = []
    for index, block in enumerate(blocks, 1):
        number, timestamps, *caption = block.splitlines()
        assert number == str(index)
        assert re.fullmatch(r'\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}', timestamps)
        words.extend(' '.join(caption).split())
    assert words == ' '.join(line['text'] for line in script['lines']).split()


@pytest.mark.parametrize('relative', ['renders/video.mp4', 'script/script.yaml',
                                    'renders/render-manifest.json', 'renders/scene-timing.json'])
def test_long_package_refuses_stale_approval_or_unbound_timing(long_approved_project, relative):
    revision = _revision_root(long_approved_project)
    path = revision / relative
    path.write_bytes(path.read_bytes() + b' ')
    if relative == 'script/script.yaml':
        data = read_yaml(path)
        data['lines'][0]['text'] += ' thay đổi'
        write_yaml_atomic(path, data)
    elif relative == 'renders/render-manifest.json':
        data = json.loads(path.read_text(encoding='utf-8'))
        data['scene_timing_sha256'] = 'changed'
        path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='approval|approved render manifest'):
        package_project(long_approved_project)
    assert not (revision / 'publish').exists()
    assert read_yaml(long_approved_project / 'project.yaml')['state'] == 'video_approved'
