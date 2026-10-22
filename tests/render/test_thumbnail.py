import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.render import thumbnail
from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.gate_review import approve_gate
from healthvideo.workflows.package import package_project
from healthvideo.workflows.produce import produce_project
from healthvideo.workflows.review_html import render_video_packet
from tests.helpers import advance_v2_project_to_video_review, create_v2_project_fixture

NOW = datetime(2026, 10, 23, tzinfo=UTC)


def add_thumbnail(root, headline="5 điều cần biết [claim:C01]"):
    path = root / "posts/posts.yaml"
    data = read_yaml(path)
    data["thumbnail"] = {"headline": headline, "background_prompt": "A quiet heart illustration", "seed": 7}
    write_yaml_atomic(path, data)


def runner(argv):
    Image.new("RGB", (1280, 720), "navy").save(Path(argv[argv.index("--output") + 1]))
    return 0


def test_thumbnail_claim_marker_not_rendered(tmp_path):
    project = create_v2_project_fixture(tmp_path)
    root = project / "revisions/001"
    add_thumbnail(root)

    def inspect(argv):
        props = json.loads(Path(argv[argv.index("--props") + 1]).read_text(encoding="utf-8"))
        assert props["headline"] == "5 điều cần biết"
        assert "still" in argv and "Thumbnail" in argv
        return runner(argv)

    thumbnail.render_thumbnail(root, runner=inspect)
    ledger = read_yaml(root / "posts/license-ledger.yaml")
    assert ledger["entries"][0]["sha256"] == sha256_file(root / "posts/thumbnail-background.png")


def test_render_thumbnail_cached_by_hash(tmp_path, monkeypatch):
    project = create_v2_project_fixture(tmp_path)
    root = project / "revisions/001"
    add_thumbnail(root)
    calls = []

    def track(argv):
        calls.append(argv)
        return runner(argv)

    output = thumbnail.render_thumbnail(root, runner=track)
    thumbnail.render_thumbnail(root, runner=track)
    assert len(calls) == 1
    add_thumbnail(root, "Vì sao cần theo dõi huyết áp?")
    thumbnail.render_thumbnail(root, runner=track)
    assert len(calls) == 2
    output.write_bytes(b"corrupt")
    thumbnail.render_thumbnail(root, runner=track)
    assert len(calls) == 3
    monkeypatch.setattr(thumbnail, "renderer_identity", lambda: {"version": "changed"})
    thumbnail.render_thumbnail(root, runner=track)
    assert len(calls) == 4
    for field, value in (("seed", 8), ("background_prompt", "Another decorative background")):
        path = root / "posts/posts.yaml"
        data = read_yaml(path)
        data["thumbnail"][field] = value
        write_yaml_atomic(path, data)
        thumbnail.render_thumbnail(root, runner=track)
    assert len(calls) == 6
    data = read_yaml(thumbnail.BRAND_PROFILE_PATH)
    data["colors"]["teal"] = "#18A6A7"
    brand_path = tmp_path / "brand.yaml"
    write_yaml_atomic(brand_path, data)
    monkeypatch.setattr(thumbnail, "BRAND_PROFILE_PATH", brand_path)
    thumbnail.render_thumbnail(root, runner=track)
    assert len(calls) == 7


@pytest.mark.parametrize("code,valid", [(1, True), (0, False)])
def test_thumbnail_failure_does_not_replace_previous_output(tmp_path, code, valid):
    project = create_v2_project_fixture(tmp_path)
    root = project / "revisions/001"
    add_thumbnail(root)
    output = thumbnail.render_thumbnail(root, runner=runner)
    before = output.read_bytes()
    add_thumbnail(root, "Headline changed")

    def fail(argv):
        if valid:
            runner(argv)
        else:
            Path(argv[argv.index("--output") + 1]).write_bytes(b"invalid png")
        return code

    with pytest.raises((RuntimeError, OSError, ValueError)):
        thumbnail.render_thumbnail(root, runner=fail)
    assert output.read_bytes() == before


def test_video_gate_binds_thumbnail(tmp_path):
    project = create_v2_project_fixture(tmp_path)
    advance_v2_project_to_video_review(project, now=NOW)
    root = project / "revisions/001"
    add_thumbnail(root)
    with pytest.raises(FileNotFoundError, match="thumbnail"):
        approve_gate(project, GateKind.VIDEO, reviewer="Doctor", now=NOW)
    thumbnail.render_thumbnail(root, runner=runner)
    approval = approve_gate(project, GateKind.VIDEO, reviewer="Doctor", now=NOW)
    assert approval.artifact_hashes["posts/thumbnail.png"] == sha256_file(root / "posts/thumbnail.png")
    assert '../posts/thumbnail.png' in render_video_packet(root)
    (root / "posts/thumbnail.png").write_bytes(b"changed")
    with pytest.raises(ValueError, match="current video approval"):
        package_project(project)


def test_package_copies_approved_thumbnail(tmp_path):
    project = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    root = project / "revisions/001"
    add_thumbnail(root)
    approve_gate(project, GateKind.MEDICAL, reviewer="Doctor", now=NOW)
    still_calls = []

    def video_runner(argv):
        if "still" in argv:
            still_calls.append(argv)
            return runner(argv)
        Path(argv[argv.index("--output") + 1]).write_bytes(b"synthetic-video")
        return 0

    produce_project(project, SilentTTS(), video_runner)
    produce_project(project, SilentTTS(), video_runner)
    assert len(still_calls) == 1
    add_thumbnail(root, "Vì sao cần theo dõi huyết áp?")
    produce_project(project, SilentTTS(), video_runner)
    assert len(still_calls) == 2
    approve_gate(project, GateKind.VIDEO, reviewer="Doctor", now=NOW)
    publish = package_project(project)
    assert (publish / "thumbnail.png").read_bytes() == (root / "posts/thumbnail.png").read_bytes()
    manifest = json.loads((publish / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["payload_sha256"]["thumbnail.png"] == sha256_file(publish / "thumbnail.png")
