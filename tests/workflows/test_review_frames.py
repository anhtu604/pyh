import json
from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner

from healthvideo.cli import app
from healthvideo.domain.storyboard import Scene
from healthvideo.render.input import RenderInput
from healthvideo.storage.files import write_yaml_atomic
from healthvideo.workflows import review_frames as frames


def scene(number, start, duration=90, visual="anatomy_animation"):
    return Scene(
        id=f"S-TEST-{number:02}",
        start_frame=start,
        duration_frames=duration,
        narration="Synthetic illustration only.",
        visual=visual,
        anatomy=(
            {
                "subject": "artery_cross_section",
                "state": "normal",
                "severity": 0,
                "motion": "Synthetic motion",
            }
            if visual != "whiteboard"
            else None
        ),
    )


def setup_project(tmp_path, *, clip=False, video=False):
    project = tmp_path / "synthetic"
    write_yaml_atomic(
        project / "project.yaml",
        {
            "schema_version": "2.0",
            "slug": "synthetic",
            "active_revision": "001",
        },
    )
    renders = project / "revisions/001/renders"
    input_path = renders / (
        "clips/CL01.render-input.json" if clip else "render-input.json"
    )
    input_path.parent.mkdir(parents=True, exist_ok=True)
    data = RenderInput(
        title="Synthetic QA",
        audio_file="audio/narration.wav",
        scenes=(scene(1, 0), scene(2, 90, visual="whiteboard")),
    )
    input_path.write_text(data.model_dump_json(), encoding="utf-8")
    if video:
        (input_path.parent / ("CL01.mp4" if clip else "video.mp4")).write_bytes(b"fake")
    return project, renders, data


def fake_runner(calls):
    def run(argv):
        calls.append(argv)
        if argv[0] == "pnpm":
            Path(argv[argv.index("--output") + 1]).write_bytes(b"draft")
        else:
            Image.new("RGB", (54, 96), "red").save(argv[-1])
        return 0

    return run


def test_scene_samples_clamp_offset_and_dense_range():
    data = RenderInput(
        title="Synthetic",
        audio_file="audio/test.wav",
        scenes=(scene(1, 0, 3), scene(2, 3, 90)),
    )
    assert [(s.scene_id, s.frame) for s in frames.sample_frames(data)] == [
        ("S-TEST-01", 2),
        ("S-TEST-02", 12),
    ]
    assert [
        s.frame for s in frames.sample_frames(data, start=0, end=0.2, every=0.1)
    ] == [0, 3, 6]
    with pytest.raises(ValueError):
        frames.sample_frames(data, every=0)
    with pytest.raises(ValueError):
        frames.sample_frames(data, start=float("nan"))


def test_tiles_paginate_keep_portrait_aspect_and_record_cells(tmp_path):
    data = RenderInput(
        title="Synthetic",
        audio_file="audio/test.wav",
        scenes=tuple(scene(i, i * 90) for i in range(9)),
    )
    samples = frames.sample_frames(data)
    images = []
    for i in range(9):
        path = tmp_path / f"frame-{i}.png"
        Image.new("RGB", (54, 96), "red").save(path)
        images.append(path)
    entries = frames.tile_frames(samples, images, tmp_path / "sheets", data)
    assert len(entries) == 9
    assert entries[8]["sheet"] == "sheet-02.png"
    assert entries[8]["cell"] == 0
    assert entries[0]["time"] == 0.3
    with Image.open(tmp_path / "sheets/sheet-01.png") as sheet:
        assert sheet.size == (360 * 4, 640 * 2)
        assert sheet.getpixel((180, 100)) == (255, 0, 0)
        assert sheet.getpixel((180, 630)) == (0, 0, 0)  # label background
    frames.tile_frames(samples[:1], images[:1], tmp_path / "sheets", data)
    assert not (tmp_path / "sheets/sheet-02.png").exists()


@pytest.mark.parametrize("clip", [False, True])
@pytest.mark.parametrize("existing", [False, True])
def test_workflow_uses_active_input_fake_runner_and_preserves_state(
    tmp_path, clip, existing
):
    project, renders, _ = setup_project(tmp_path, clip=clip, video=existing)
    before = (project / "project.yaml").read_bytes()
    calls = []
    output = frames.review_frames(
        project, clip="CL01" if clip else None, runner=fake_runner(calls)
    )
    assert (project / "project.yaml").read_bytes() == before
    assert output.is_relative_to(renders / "review-frames")
    index = json.loads((output / "index.json").read_text())
    assert [e["frame"] for e in index["frames"]] == [9, 99]
    mechanism = json.loads((output / "mechanism/index.json").read_text())
    assert [e["scene_id"] for e in mechanism["frames"]] == ["S-TEST-01"]
    render_calls = [c for c in calls if c[0] == "pnpm"]
    assert len(render_calls) == (0 if existing else 1)
    if render_calls:
        assert "--scale=0.5" in render_calls[0]
        assert render_calls[0][render_calls[0].index("--public-dir") + 1] == str(
            renders.resolve()
        )
    assert "select=eq(n\\,9)" in calls[-2]


def test_cli_dense_sampling_and_invalid_clip(tmp_path, monkeypatch):
    project, _, _ = setup_project(tmp_path)
    calls = []
    monkeypatch.setattr("healthvideo.cli.run_render_argv", fake_runner(calls))
    result = CliRunner().invoke(
        app,
        [
            "review",
            "frames",
            str(project),
            "--from",
            "1",
            "--to",
            "2",
            "--every",
            "0.5",
        ],
    )
    assert result.exit_code == 0, result.output
    output = Path(result.output.strip())
    assert [
        e["frame"] for e in json.loads((output / "index.json").read_text())["frames"]
    ] == [30, 45, 60]
    bad = CliRunner().invoke(
        app, ["review", "frames", str(project), "--clip", "../bad"]
    )
    assert bad.exit_code == 1


def test_failed_extraction_does_not_publish_index(tmp_path):
    project, renders, _ = setup_project(tmp_path, video=True)
    with pytest.raises(RuntimeError, match="FFmpeg"):
        frames.review_frames(project, runner=lambda argv: 1)
    assert not list((renders / "review-frames").rglob("index.json"))


def test_reuses_current_draft_but_rerenders_when_public_media_changes(tmp_path):
    project, renders, _ = setup_project(tmp_path)
    calls = []
    frames.review_frames(project, runner=fake_runner(calls))
    calls.clear()
    frames.review_frames(project, runner=fake_runner(calls))
    assert not any(c[0] == "pnpm" for c in calls)
    media = renders / "audio/narration.wav"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"new synthetic audio")
    calls.clear()
    frames.review_frames(project, runner=fake_runner(calls))
    assert sum(c[0] == "pnpm" for c in calls) == 1


@pytest.mark.parametrize(
    "kind", ["anatomy_animation", "process_animation", "comparison", "timelapse"]
)
def test_all_four_mechanism_kinds_are_included(tmp_path, kind):
    project, renders, data = setup_project(tmp_path, clip=True, video=True)
    data = data.model_copy(update={"scenes": (scene(1, 0, visual=kind),)})
    (renders / "clips/CL01.render-input.json").write_text(data.model_dump_json())
    frames.review_frames(project, clip="CL01", runner=fake_runner([]))
    assert [p.name for p in frames.mechanism_sheets(renders.parent)] == ["sheet-01.png"]


def test_packet_attaches_only_mechanism_sheets_without_changing_gate_hashes(tmp_path):
    from healthvideo.workflows.gate_review import (
        hash_reviewed_artifacts,
        video_reviewed_paths,
    )
    from healthvideo.workflows.review_html import render_video_packet

    project, renders, data = setup_project(tmp_path, video=True)
    revision = renders.parent
    write_yaml_atomic(
        revision / "storyboard/storyboard.yaml",
        {
            "title": data.title,
            "scenes": [s.model_dump(mode="json") for s in data.scenes],
        },
    )
    (renders / "render-manifest.json").write_text("{}")
    before = hash_reviewed_artifacts(video_reviewed_paths(revision))
    assert "sheet-01.png" not in render_video_packet(revision)
    frames.review_frames(project, runner=fake_runner([]))
    html = render_video_packet(revision)
    assert "review-frames/long/mechanism/sheet-01.png" in html
    assert "review-frames/long/sheet-01.png" not in html
    assert hash_reviewed_artifacts(video_reviewed_paths(revision)) == before
    (renders / "video.mp4").write_bytes(b"new video")
    assert "sheet-01.png" not in render_video_packet(revision)
