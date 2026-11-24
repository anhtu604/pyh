"""Offline chunk cache and real FFmpeg assembly checks; no Remotion renders."""

import json
import subprocess
import wave
from array import array
from itertools import pairwise
from pathlib import Path

import pytest

from healthvideo.render import chunked
from healthvideo.render.input import build_render_input
from healthvideo.render.quality import resolve_r5_shots
from tests.render.test_quality import board, shot


def render_input():
    source = board([shot(0, 60)], frames=60)
    first = source.scenes[0].model_copy(update={"chapter_id": "CH01"})
    second = first.model_copy(update={"id": "S2", "start_frame": 60, "chapter_id": "CH02",
        "shots": (first.shots[0].model_copy(update={"id": "SH2"}),)})
    source = source.model_copy(update={"scenes": (first, second)})
    return build_render_input(resolve_r5_shots(source), "audio.wav").model_copy(
        update={"format_profile": "youtube_long", "width": 1920, "height": 1080})


def audio(path, changed=False):
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        stream.writeframes((b"\x01\x00" if changed else b"\x00\x00") * 96000
                           + b"\x00\x00" * 96000)


def setup(tmp_path):
    value = render_input()
    audio(tmp_path / "audio.wav")
    (tmp_path / "input.json").write_text(value.model_dump_json(), encoding="utf-8")
    return {"render_input_path": tmp_path / "input.json", "render_input": value,
            "public_dir": tmp_path, "audio": tmp_path / "audio.wav",
            "output": tmp_path / "video.mp4", "cache_dir": tmp_path / "render-chunks",
            "asset_hashes": {}, "renderer_identity": {"source": "test"}, "audio_identity": {}}


def fake_runner(calls):
    def run(argv):
        calls.append(argv)
        out = Path(argv[argv.index("--output") + 1] if "--output" in argv else argv[-1])
        out.write_bytes(b"test mp4")
        return 0
    return run


def test_keys_and_cache_are_local_and_corruption_is_repaired(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(chunked, "validate_media", lambda *a, **kw: None)
    opts = setup(tmp_path)
    calls = []
    caplog.set_level("INFO")
    first = chunked.render_chunked(**opts, runner=fake_runner(calls))
    assert len(calls) == 3
    assert all("--muted" in c for c in calls[:2])
    assert "--frames=0-59" in calls[0] and "--frames=60-119" in calls[1]
    second = chunked.render_chunked(**opts, runner=fake_runner(calls))
    assert second == first and len(calls) == 4
    audio(tmp_path / "audio.wav", changed=True)
    third = chunked.render_chunked(**opts, runner=fake_runner(calls))
    assert first[0] != third[0] and first[1] == third[1]
    assert len(calls) == 6
    (opts["cache_dir"] / third[1]).write_bytes(b"damaged")
    chunked.render_chunked(**opts, runner=fake_runner(calls))
    assert len(calls) == 8
    manifest = json.loads((opts["cache_dir"] / "chunks.json").read_text())
    assert [(c["start_frame"], c["end_frame"]) for c in manifest["chunks"]] == [(0, 59), (60, 119)]
    assert "reused=1 rendered=1" in caplog.text
    assert "reused=1 rendered=1" in (opts["cache_dir"] / "chunks.log").read_text()


def test_input_assets_bundle_and_parameters_invalidate(tmp_path, monkeypatch):
    monkeypatch.setattr(chunked, "validate_media", lambda *a, **kw: None)
    opts = setup(tmp_path)
    value = opts["render_input"]
    asset = tmp_path / "asset.png"
    asset.write_bytes(b"image1")
    # Use JSON data for key tests so future unknown fields are covered too.
    data = value.model_dump(mode="json")
    data["scenes"][0]["visual_assets"] = [{"path": "asset.png", "role": "whiteboard"}]
    spans = chunked.chunk_spans(value)
    def keys():
        return [chunked.chunk_key(data, s, tmp_path, tmp_path / "audio.wav",
                                  {"bundle": "a"}, {"gl": "angle"}) for s in spans]
    initial = keys()
    asset.write_bytes(b"image2")
    changed = keys()
    assert changed[0] != initial[0] and changed[1] == initial[1]
    data["scenes"][0]["on_screen_text"] = "new text"
    assert keys()[0] != changed[0] and keys()[1] == changed[1]
    assert chunked.chunk_key(data, spans[1], tmp_path, tmp_path / "audio.wav",
                             {"bundle": "b"}, {"gl": "angle"}) != keys()[1]
    for name in ("fps", "width", "height", "codec", "crf", "pixel_format", "gl"):
        assert chunked.chunk_key(data, spans[1], tmp_path, tmp_path / "audio.wav",
                                 {"bundle": "a"}, {"gl": "angle", name: "changed"}) != keys()[1]


@pytest.mark.parametrize("failure", ["return", "raise", "probe"])
def test_failure_cleans_staging_and_preserves_final(tmp_path, monkeypatch, failure):
    opts = setup(tmp_path)
    opts["output"].write_bytes(b"previous video")
    def runner(argv):
        fake_runner([])(argv)
        if failure == "raise":
            raise OSError("interrupted")
        return 1 if failure == "return" else 0
    monkeypatch.setattr(chunked, "validate_media", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("probe")))
    with pytest.raises((RuntimeError, OSError)):
        chunked.render_chunked(**opts, runner=runner)
    assert not list(opts["cache_dir"].glob("*.mp4"))
    assert not list(opts["cache_dir"].glob(".*partial*"))
    assert opts["output"].read_bytes() == b"previous video"


def test_scene_fallback_and_repeated_chapter_ids():
    value = render_input()
    value = value.model_copy(update={"scenes": tuple(s.model_copy(update={"chapter_id": None}) for s in value.scenes)})
    assert len(chunked.chunk_spans(value)) == 2
    bad = value.model_copy(update={"scenes": (value.scenes[0], value.scenes[1].model_copy(update={"start_frame": 61}))})
    with pytest.raises(ValueError, match="contiguous"):
        chunked.chunk_spans(bad)
    third = value.scenes[1].model_copy(update={"id": "S3", "start_frame": 120})
    value = value.model_copy(update={"scenes": tuple(s.model_copy(update={"chapter_id": chapter})
        for s, chapter in zip((*value.scenes, third), ("A", "B", "A"), strict=True))})
    assert [(s.chapter_id, s.start_frame, s.end_frame) for s in chunked.chunk_spans(value)] == [
        ("A", 0, 60), ("B", 60, 120), ("A", 120, 180)]


def test_ffmpeg_copy_and_single_audio_mux(tmp_path):
    opts = setup(tmp_path)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=440:sample_rate=48000:duration=4", str(opts["audio"])], check=True)
    calls = []
    def runner(argv):
        calls.append(argv)
        if "--output" in argv:
            out = argv[argv.index("--output") + 1]
            color = "red" if "--frames=0-59" in argv else "blue"
            argv = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"color=c={color}:s=1920x1080:r=30:d=2", "-an", "-c:v", "libx264",
                    "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p", out]
        return subprocess.run(argv, capture_output=True, check=False).returncode
    chunked.render_chunked(**opts, runner=runner)
    chunked.validate_media(opts["output"], 120, 30, require_audio=True)
    assert calls[-1][calls[-1].index("-c:v") + 1] == "copy"
    # One continuous AAC encode: no per-chapter encoder delay or joins.
    assert calls[-1].count("-c:a") == 1
    decoded = subprocess.run(["ffmpeg", "-v", "error", "-i", str(opts["output"]),
        "-vn", "-f", "s16le", "-ac", "1", "-ar", "48000", "pipe:1"],
        capture_output=True, check=True)
    samples = array("h", decoded.stdout)
    seam = samples[96000 - 100:96000 + 100]
    assert max(abs(a - b) for a, b in pairwise(seam)) < 1000
    opts["audio"].unlink()
    with pytest.raises((OSError, wave.Error)):
        chunked.render_chunked(**opts, runner=runner)


def test_concat_failure_keeps_completed_cache_and_old_output(tmp_path, monkeypatch):
    opts = setup(tmp_path)
    monkeypatch.setattr(chunked, "validate_media", lambda *a, **kw: None)
    opts["output"].write_bytes(b"previous")
    calls = []
    def fail_concat(argv):
        fake_runner(calls)(argv)
        return 1 if argv[0] == "ffmpeg" else 0
    with pytest.raises(RuntimeError, match="concat"):
        chunked.render_chunked(**opts, runner=fail_concat)
    assert opts["output"].read_bytes() == b"previous"
    assert len(list(opts["cache_dir"].glob("*.mp4"))) == 2
    assert not list(tmp_path.rglob("*.partial*"))
    calls.clear()
    chunked.render_chunked(**opts, runner=fake_runner(calls))
    assert len(calls) == 1 and calls[0][0] == "ffmpeg"


def test_new_revision_imports_verified_unchanged_parts(tmp_path, monkeypatch):
    monkeypatch.setattr(chunked, "validate_media", lambda *a, **kw: None)
    opts = setup(tmp_path)
    opts["cache_dir"] = tmp_path / "revisions/001/render-chunks"
    first = chunked.render_chunked(**opts, runner=fake_runner([]))
    # Only chapter one changes in revision two.
    audio(opts["audio"], changed=True)
    opts["cache_dir"] = tmp_path / "revisions/002/render-chunks"
    calls = []
    second = chunked.render_chunked(**opts, runner=fake_runner(calls))
    assert len(calls) == 2 and first[1] == second[1]
    # Copies are independent, not hardlinks into the approved revision.
    previous = tmp_path / "revisions/001/render-chunks" / first[1]
    (opts["cache_dir"] / second[1]).write_bytes(b"damaged")
    assert previous.read_bytes() == b"test mp4"
    previous.write_bytes(b"also damaged")
    calls.clear()
    chunked.render_chunked(**opts, runner=fake_runner(calls))
    assert len(calls) == 2  # A corrupt previous revision is never imported.


def test_chapter_key_binds_absolute_start_and_total_frames(tmp_path):
    opts = setup(tmp_path)
    value = opts["render_input"]
    def keys(value):
        return [chunked.chunk_key(value.model_dump(mode="json"), span, tmp_path,
            opts["audio"], {}, {}) for span in chunked.chunk_spans(value)]
    initial = keys(value)
    with wave.open(str(opts["audio"]), "rb") as stream:
        params, pcm = stream.getparams(), stream.readframes(stream.getnframes())
    with wave.open(str(opts["audio"]), "wb") as stream:
        stream.setparams(params)
        stream.writeframes(pcm + bytes(48000 * 2))
    shifted = value.model_copy(update={"scenes": (
        value.scenes[0].model_copy(update={"duration_frames": 90}),
        value.scenes[1].model_copy(update={"start_frame": 90}),
    )})
    changed = keys(shifted)
    assert all(a != b for a, b in zip(changed, initial, strict=True))
    # A total-duration change alone also invalidates an earlier, unmoved part.
    extended = value.model_copy(update={"scenes": (value.scenes[0],
        value.scenes[1].model_copy(update={"duration_frames": 90}))})
    assert keys(extended)[0] != initial[0]
    # Moving the boundary with unchanged total duration still changes part two.
    boundary = value.model_copy(update={"scenes": (
        value.scenes[0].model_copy(update={"duration_frames": 30}),
        value.scenes[1].model_copy(update={"start_frame": 30, "duration_frames": 90}))})
    assert keys(boundary)[1] != initial[1]


def test_produce_chunk_retries_gpu_failure_through_cpu_fallback(tmp_path, monkeypatch):
    from healthvideo.domain.gate_review import GateKind
    from healthvideo.domain.storyboard import Storyboard
    from healthvideo.render.remotion import FALLBACK_GL
    from healthvideo.storage.files import read_yaml
    from healthvideo.workflows.draft import submit_draft, submit_medical_review
    from healthvideo.workflows.gate_review import approve_gate, snapshot_r5_assets
    from healthvideo.workflows.produce import produce_project
    from tests.e2e.test_r5_quality_offline import (
        NOW,
        REVIEWER,
        _mock_render,
        _R5MockTTS,
        _synthetic_r5_project,
    )
    from tests.helpers import write_critic_review_fixture
    from tests.workflows.test_produce import _r5_alignment

    project = _synthetic_r5_project(tmp_path)
    from tests.helpers import reviewed_r5_lexicon_fixture
    reviewed_r5_lexicon_fixture(project, monkeypatch)
    revision = project / "revisions/001"
    submit_draft(project, revision / "script/script.yaml", revision / "storyboard/storyboard.yaml",
                 revision / "assets/asset-manifest.yaml")
    snapshot_r5_assets(revision, Storyboard.model_validate(read_yaml(revision / "storyboard/storyboard.yaml")))
    write_critic_review_fixture(project, product=False)
    submit_medical_review(project)
    approve_gate(project, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)
    _r5_alignment(monkeypatch)
    monkeypatch.setenv("PYH_REMOTION_GL", "angle")
    calls = []
    failed = False
    def runner(argv):
        nonlocal failed
        calls.append(argv)
        _mock_render(argv)
        if not failed and any(arg.startswith("--frames=") for arg in argv):
            assert "--gl=angle" in argv
            failed = True
            return 1
        return 0

    output = produce_project(project, _R5MockTTS(), runner, music=False)
    parts = [call for call in calls if any(arg.startswith("--frames=") for arg in call)]
    assert output.is_file() and failed
    assert "--gl=angle" in parts[0] and f"--gl={FALLBACK_GL}" in parts[1]
    assert "--hardware-acceleration=disable" in parts[1]
    assert [arg for arg in parts[0] if arg.startswith("--frames=")] == [
        arg for arg in parts[1] if arg.startswith("--frames=")]
    assert parts[0][parts[0].index("--output") + 1] == parts[1][parts[1].index("--output") + 1]
    assert "--muted" in parts[0] and "--muted" in parts[1]


def test_disable_uses_original_single_render(tmp_path, monkeypatch):
    opts = setup(tmp_path)
    monkeypatch.setenv("PYH_RENDER_CHUNKS", "0")
    calls = []
    assert chunked.render_chunked(**opts, runner=fake_runner(calls)) == ()
    assert len(calls) == 1 and "--muted" not in calls[0]
    assert not any(arg.startswith("--frames") for arg in calls[0])
    assert not opts["cache_dir"].exists()


def test_cache_staging_fits_windows_path_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(chunked, "validate_media", lambda *a, **kw: None)
    opts = setup(tmp_path)
    padding = max(1, 170 - len(str(tmp_path)) - len("/render-chunks/"))
    opts["cache_dir"] = tmp_path / ("x" * padding) / "render-chunks"
    calls = []
    parts = chunked.render_chunked(**opts, runner=fake_runner(calls))
    assert len(parts) == 2
    assert all(len(call[call.index("--output") + 1]) < 260 for call in calls if "--output" in call)
    assert not list(opts["cache_dir"].glob("*.partial*"))


def test_bundle_identity_and_same_size_asset_refresh(tmp_path, monkeypatch):
    import os

    from healthvideo.render import remotion

    bundle = tmp_path / "bundle"
    bundle.mkdir()
    html = bundle / "index.html"
    html.write_text('<script>window.remotion_staticFiles = [{"name":"a","lastModified":1}]</script>', encoding="utf-8")
    script = bundle / "main.js"
    script.write_text("code1", encoding="utf-8")
    public = tmp_path / "public"
    public.mkdir()
    asset = public / "asset.png"
    asset.write_bytes(b"first")
    with remotion.active_bundle(bundle):
        initial = remotion.chunk_renderer_identity()
        html.write_text('<script>window.remotion_staticFiles = [{"name":"a","lastModified":2}]</script>', encoding="utf-8")
        assert remotion.chunk_renderer_identity() == initial
        remotion.build_render_argv(tmp_path / "i.json", tmp_path / "o.mp4", public,
                                   stage_fonts=False, verify_public=True)
        target = bundle / "public/asset.png"
        asset.write_bytes(b"other")
        os.utime(asset, ns=(target.stat().st_atime_ns, target.stat().st_mtime_ns))
        remotion.build_render_argv(tmp_path / "i.json", tmp_path / "o.mp4", public,
                                   stage_fonts=False, verify_public=True)
        assert target.read_bytes() == b"other"
        assert remotion.chunk_renderer_identity() == initial  # Assets are per chunk.
        script.write_text("code2", encoding="utf-8")
        assert remotion.chunk_renderer_identity() != initial


@pytest.mark.parametrize("wrong", ["frames", "audio", "probe"])
def test_probe_rejects_bad_assembly(tmp_path, monkeypatch, wrong):
    result = {"streams": [{"codec_type": "video", "nb_read_frames": "120",
        "duration": "4", "r_frame_rate": "30/1"}, {"codec_type": "audio", "duration": "4"}]}
    if wrong == "frames":
        result["streams"][0]["nb_read_frames"] = "119"
    if wrong == "audio":
        result["streams"][1]["duration"] = "3.9"
    monkeypatch.setattr(chunked.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(
        [], 1 if wrong == "probe" else 0, json.dumps(result), "bad" if wrong == "probe" else ""))
    with pytest.raises(RuntimeError):
        chunked.validate_media(tmp_path / "bad.mp4", 120, 30, require_audio=True)
