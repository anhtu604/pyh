"""Contact sheets are disposable QA aids; never write workflow or approval artifacts."""

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw, ImageFont, ImageOps

from healthvideo.domain.storyboard import MECHANISM_VISUALS
from healthvideo.render.input import RenderInput
from healthvideo.render.remotion import (
    RemotionRunner,
    build_render_argv,
    renderer_identity,
)
from healthvideo.storage.files import sha256_file
from healthvideo.storage.project_layout import resolve_project_layout


@dataclass(frozen=True)
class FrameSample:
    scene_id: str
    frame: int


def sample_frames(
    data: RenderInput,
    *,
    start: float | None = None,
    end: float | None = None,
    every: float | None = None,
) -> list[FrameSample]:
    """Default: scene +9, clamped within that scene. Dense bounds are inclusive seconds."""
    for value in (start, end, every):
        if value is not None and (not math.isfinite(value) or value < 0):
            raise ValueError("Sampling seconds must be finite and nonnegative")
    if every is not None and every < 1 / data.fps:
        raise ValueError("--every must be at least one frame (1/30 second)")
    if not data.scenes:
        raise ValueError("Render input has no scenes")
    last = max(s.start_frame + s.duration_frames for s in data.scenes) - 1
    first_frame = math.ceil((start or 0) * data.fps)
    last_frame = min(last, math.floor(end * data.fps) if end is not None else last)
    if first_frame > last_frame:
        raise ValueError("Sampling range is empty or outside the scene timeline")
    if every is None:
        return [
            FrameSample(s.id, frame)
            for s in data.scenes
            if first_frame
            <= (frame := min(s.start_frame + 9, s.start_frame + s.duration_frames - 1))
            <= last_frame
        ]
    count = math.floor((last_frame - first_frame) / (every * data.fps)) + 1
    samples = []
    for i in range(count):
        frame = round(first_frame + i * every * data.fps)
        for scene in data.scenes:
            if scene.start_frame <= frame < scene.start_frame + scene.duration_frames:
                samples.append(FrameSample(scene.id, frame))
                break
    return samples


def timestamp(frame: int, fps: int) -> str:
    tenths = frame * 10 // fps
    return f"{tenths // 600:02}:{tenths // 10 % 60:02}.{tenths % 10}"


def tile_frames(
    samples: list[FrameSample],
    images: list[Path],
    output: Path,
    data: RenderInput,
) -> list[dict]:
    """4 by 2 sheets, 360px wide cells with the target's original aspect ratio."""
    output.mkdir(parents=True, exist_ok=True)
    for old_sheet in output.glob("sheet-*.png"):
        if re.fullmatch(r"sheet-\d{2,}\.png", old_sheet.name):
            old_sheet.unlink()
    width, height = 360, round(360 * data.height / data.width)
    font = ImageFont.load_default(size=18)
    entries = []
    for offset in range(0, len(samples), 8):
        name = f"sheet-{offset // 8 + 1:02}.png"
        sheet = Image.new("RGB", (width * 4, height * 2), "#151b25")
        for cell, (sample, path) in enumerate(
            zip(samples[offset : offset + 8], images[offset : offset + 8], strict=True)
        ):
            with Image.open(path) as image:
                tile = ImageOps.pad(
                    image.convert("RGB"), (width, height), color="black"
                )
            draw = ImageDraw.Draw(tile)
            draw.rectangle((0, height - 30, width, height), fill="black")
            draw.text(
                (8, height - 26),
                f"{sample.scene_id}  {timestamp(sample.frame, data.fps)}",
                font=font,
                fill="white",
            )
            sheet.paste(tile, (cell % 4 * width, cell // 4 * height))
            entries.append(
                {
                    "scene_id": sample.scene_id,
                    "frame": sample.frame,
                    "time": sample.frame / data.fps,
                    "sheet": name,
                    "cell": cell,
                }
            )
        sheet.save(output / name)
    return entries


def target_paths(renders: Path, clip: str | None) -> tuple[Path, Path, Path]:
    if clip is not None and not re.fullmatch(r"CL\d{2}", clip):
        raise ValueError("--clip must be CLxx, for example CL01")
    input_path = renders / (
        f"clips/{clip}.render-input.json" if clip else "render-input.json"
    )
    video = renders / (f"clips/{clip}.mp4" if clip else "video.mp4")
    output = renders / "review-frames" / (clip or "long")
    return input_path, video, output


def _draft_source(data: RenderInput, input_path: Path, renders: Path) -> dict:
    media = {data.audio_file}
    for scene in data.scenes:
        media.update(asset.path for asset in scene.visual_assets)
        if scene.evidence_highlight is not None:
            media.add(scene.evidence_highlight.image)
    if data.youtube_cta is not None:
        media.add(data.youtube_cta.mascot_path)
    hashes = {}
    for relative in sorted(media):
        path = renders / relative
        if not path.resolve().is_relative_to(renders.resolve()):
            raise ValueError(
                "Render media must stay within the render public directory"
            )
        hashes[relative] = sha256_file(path) if path.is_file() else None
    return {
        "input": sha256_file(input_path),
        "media": hashes,
        "renderer": renderer_identity(),
    }


def review_frames(
    project_dir: Path,
    *,
    runner: RemotionRunner,
    clip: str | None = None,
    start: float | None = None,
    end: float | None = None,
    every: float | None = None,
) -> Path:
    layout = resolve_project_layout(project_dir)
    if layout.schema_version != "2.0":
        raise ValueError("review frames requires a schema 2.0 active revision")
    renders = layout.artifact_root / "renders"
    input_path, video, output = target_paths(renders, clip)
    data = RenderInput.model_validate_json(input_path.read_text(encoding="utf-8"))
    samples = sample_frames(data, start=start, end=end, every=every)
    if not samples:
        raise ValueError("No scene samples in the requested range; use --every")
    output.mkdir(parents=True, exist_ok=True)
    # Invalidate the old QA index before doing work, including on failed retries.
    (output / "index.json").unlink(missing_ok=True)
    (output / "mechanism/index.json").unlink(missing_ok=True)
    input_hash = sha256_file(input_path)
    if not video.is_file():
        video = output / "draft.mp4"
        source = _draft_source(data, input_path, renders)
        source_path = output / "draft-source.json"
        try:
            previous = json.loads(source_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous = None
        if not video.is_file() or previous != source:
            source_path.unlink(missing_ok=True)
            video.unlink(missing_ok=True)
            argv = build_render_argv(input_path, video, renders)
            argv.append("--scale=0.5")
            if runner(argv) != 0 or not video.is_file():
                raise RuntimeError("Remotion draft render failed")
            if source != _draft_source(data, input_path, renders):
                raise RuntimeError("Render source changed during draft render; retry")
            source_path.write_text(json.dumps(source), encoding="utf-8")
    video_hash = sha256_file(video)
    with TemporaryDirectory(prefix=".frames-", dir=output) as temp:
        images = []
        for index, sample in enumerate(samples):
            image = Path(temp) / f"frame-{index:05}.png"
            argv = [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                str(video.resolve()),
                "-vf",
                f"select=eq(n\\,{sample.frame})",
                "-frames:v",
                "1",
                str(image.resolve()),
            ]
            if runner(argv) != 0 or not image.is_file():
                raise RuntimeError(f"FFmpeg extraction failed at frame {sample.frame}")
            images.append(image)
        entries = tile_frames(samples, images, output, data)
        mechanism_ids = {s.id for s in data.scenes if s.visual in MECHANISM_VISUALS}
        selected = [
            (s, p)
            for s, p in zip(samples, images, strict=True)
            if s.scene_id in mechanism_ids
        ]
        mechanism_entries = tile_frames(
            [s for s, _ in selected],
            [p for _, p in selected],
            output / "mechanism",
            data,
        )
    if input_hash != sha256_file(input_path) or video_hash != sha256_file(video):
        raise RuntimeError("Render input or video changed during frame review; retry")
    metadata = {
        "render_input_sha256": input_hash,
        "video_sha256": video_hash,
        "video": video.relative_to(renders).as_posix(),
    }
    for directory, items in (
        (output, entries),
        (output / "mechanism", mechanism_entries),
    ):
        (directory / "index.json").write_text(
            json.dumps({**metadata, "frames": items}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
    return output


def mechanism_sheets(revision_root: Path) -> list[Path]:
    """Only current, local QA sheets may be attached; missing/stale QA never blocks a gate."""
    renders = revision_root / "renders"
    sheets = []
    for index in sorted((renders / "review-frames").glob("*/mechanism/index.json")):
        target = index.parent.parent.name
        try:
            input_path, video, output = target_paths(
                renders, None if target == "long" else target
            )
            metadata = json.loads(index.read_text(encoding="utf-8"))
            if not video.is_file():
                video = output / "draft.mp4"
            if metadata["render_input_sha256"] != sha256_file(input_path) or metadata[
                "video_sha256"
            ] != sha256_file(video):
                continue
            for name in dict.fromkeys(item["sheet"] for item in metadata["frames"]):
                if re.fullmatch(r"sheet-\d{2,}\.png", name):
                    path = index.parent / name
                    if path.is_file():
                        sheets.append(path)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return sheets
