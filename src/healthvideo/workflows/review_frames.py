"""Contact sheets are disposable QA aids; never write workflow or approval artifacts."""

import json
import math
import re
from collections.abc import Mapping
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
from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.visuals.anatomy_library import (
    LIBRARY_PATH,
    ComponentStatus,
    library_status,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
UNAPPROVED_COMPONENTS_HEADING = "Component giải phẫu mới hoặc vừa sửa cần soát kỹ"


def imported_reviewed_paths(revision_root: Path) -> dict[str, Path]:
    """Bound imported rasters and their inert contact sheet enter video review hashes."""
    manifest_path = revision_root / 'assets/asset-manifest.yaml'
    if not manifest_path.is_file():
        return {}
    result = {}
    for asset in read_yaml(manifest_path).get('assets', []):
        relative = asset.get('path', '')
        if not relative.startswith('assets/imported/') or not asset.get('storyboard_role'):
            continue
        path = revision_root / relative
        if not path.resolve().is_relative_to(revision_root.resolve()) or path.suffix != '.png':
            raise ValueError('Imported review asset escapes revision')
        if not path.is_file() or sha256_file(path) != asset.get('sha256'):
            raise ValueError('Imported review asset hash changed')
        result[relative] = path
    if result:
        for relative in ('reviews/imported-contact-sheet.png', 'reviews/imported-contact-sheet.yaml'):
            path = revision_root / relative
            if not path.resolve().is_relative_to(revision_root.resolve()) or not path.is_file():
                raise ValueError('Imported contact sheet is missing or outside revision')
            result[relative] = path
        metadata = read_yaml(result['reviews/imported-contact-sheet.yaml'])
        expected = {name: sha256_file(path) for name, path in result.items() if name.startswith('assets/')}
        if metadata.get('assets') != expected or metadata.get('sheet_sha256') != sha256_file(result['reviews/imported-contact-sheet.png']):
            raise ValueError('Imported contact sheet is stale')
    return result


def imported_contact_sheet(revision_root: Path) -> Path | None:
    """Tile imported assets actually bound to scenes; no render or workflow calls."""
    from healthvideo.workflows.asset_library import _index, _local

    manifest = read_yaml(revision_root / 'assets/asset-manifest.yaml')
    records = [a for a in manifest.get('assets', []) if a.get('path', '').startswith('assets/imported/') and a.get('storyboard_role')]
    if not records:
        return None
    metadata = {i['path']: i for i in _index(revision_root)}
    sheet = Image.new('RGB', (720, 260 * math.ceil(len(records) / 2)), '#121b30')
    hashes = {}
    provenance = []
    for index, record in enumerate(records):
        path = _local(revision_root, record['path'])
        if not path.is_file() or sha256_file(path) != record['sha256']:
            raise ValueError('Imported image changed before contact sheet')
        with Image.open(path) as image:
            tile = ImageOps.pad(image.convert('RGB'), (360, 220), color='#121b30')
        x, y = index % 2 * 360, index // 2 * 260
        sheet.paste(tile, (x, y))
        row = metadata[record['path']]
        label = f"{row['origin'][:24]} · {', '.join(row.get('used_in', []))}"
        ImageDraw.Draw(sheet).text((x + 8, y + 228), label, fill='white')
        hashes[record['path']] = record['sha256']
        provenance.append(row)
    output = revision_root / 'reviews/imported-contact-sheet.png'
    if not output.resolve().is_relative_to(revision_root.resolve()):
        raise ValueError('Imported contact sheet escapes revision')
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)
    sidecar = revision_root / 'reviews/imported-contact-sheet.yaml'
    if not sidecar.resolve().is_relative_to(revision_root.resolve()):
        raise ValueError('Imported contact sheet metadata escapes revision')
    write_yaml_atomic(sidecar, {'assets': hashes, 'sheet_sha256': sha256_file(output), 'provenance': provenance})
    return output


def _resolve_repo_root(project_dir: Path, repo: Path | None = None) -> Path:
    if repo is not None:
        return repo
    resolved = project_dir.resolve()
    for candidate in (resolved, *resolved.parents):
        if (candidate / LIBRARY_PATH).is_file():
            return candidate
    return REPOSITORY_ROOT


def unapproved_anatomy_components(
    data: RenderInput,
    *,
    repo: Path = REPOSITORY_ROOT,
) -> dict[str, ComponentStatus]:
    """Return used anatomy subjects whose library status is 'new' or 'modified'."""
    used_subjects = list(
        dict.fromkeys(
            scene.anatomy.subject
            for scene in data.scenes
            if scene.anatomy is not None
        )
    )
    if not used_subjects or not (repo / LIBRARY_PATH).is_file():
        return {}
    statuses = library_status(repo)
    return {
        subject: status
        for subject in used_subjects
        if (status := statuses.get(subject)) in ("new", "modified")
    }


def render_unapproved_components_section(
    components: Mapping[str, ComponentStatus],
) -> str:
    if not components:
        return ""
    lines = [f"## {UNAPPROVED_COMPONENTS_HEADING}"]
    for subject, status in components.items():
        lines.append(f"- {subject}: {status}")
    return "\n".join(lines)


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
    repo: Path | None = None,
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
    (output / "unapproved-components.md").unlink(missing_ok=True)
    (output / "mechanism/unapproved-components.md").unlink(missing_ok=True)
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
    resolved_repo = _resolve_repo_root(project_dir, repo)
    unapproved = unapproved_anatomy_components(data, repo=resolved_repo)
    unapproved_section = render_unapproved_components_section(unapproved)
    metadata = {
        "render_input_sha256": input_hash,
        "video_sha256": video_hash,
        "video": video.relative_to(renders).as_posix(),
        "unapproved_components_heading": (
            UNAPPROVED_COMPONENTS_HEADING if unapproved else None
        ),
        "unapproved_components": unapproved,
        "unapproved_components_section": unapproved_section,
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
        if unapproved_section:
            (directory / "unapproved-components.md").write_text(
                unapproved_section + "\n",
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
