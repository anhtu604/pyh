"""Chapter spans and content-addressed cache keys for long-form render."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from healthvideo.render.input import RenderInput
from healthvideo.render.remotion import build_concat_argv, build_render_argv
from healthvideo.storage.files import canonical_json_hash


@dataclass(frozen=True)
class ChapterSpan:
    chapter_id: str
    start_frame: int
    end_frame: int  # exclusive


def chapter_spans(render_input: RenderInput) -> tuple[ChapterSpan, ...]:
    spans: list[ChapterSpan] = []
    for scene in render_input.scenes:
        if scene.chapter_id is None:
            raise ValueError(f"Scene {scene.id}: youtube_long scene requires chapter_id")
        end = scene.start_frame + scene.duration_frames
        if spans and spans[-1].chapter_id == scene.chapter_id:
            spans[-1] = ChapterSpan(scene.chapter_id, spans[-1].start_frame, end)
        else:
            spans.append(ChapterSpan(scene.chapter_id, scene.start_frame, end))
    return tuple(spans)


def chapter_cache_key(
    render_input: RenderInput,
    span: ChapterSpan,
    asset_hashes: Mapping[str, str],
    renderer_identity: Mapping[str, str],
) -> str:
    scenes = []
    paths: set[str] = set()
    for scene in render_input.scenes:
        if scene.chapter_id != span.chapter_id:
            continue
        data = scene.model_dump(mode="json")
        data["start_frame"] = scene.start_frame - span.start_frame
        scenes.append(data)
        paths.update(asset.path for asset in scene.visual_assets)
        if scene.evidence_highlight is not None:
            paths.add(scene.evidence_highlight.image)
    missing = sorted(paths - asset_hashes.keys())
    if missing:
        raise ValueError(f"Chapter {span.chapter_id}: no content hash for asset {missing[0]}")
    return canonical_json_hash(
        {
            "format_profile": render_input.format_profile,
            "fps": render_input.fps,
            "scenes": scenes,
            "assets": {path: asset_hashes[path] for path in sorted(paths)},
            "renderer": dict(renderer_identity),
        }
    )


def render_long_form(
    *,
    render_input_path: Path,
    render_input: RenderInput,
    public_dir: Path,
    audio: Path,
    output: Path,
    cache_dir: Path,
    asset_hashes: Mapping[str, str],
    renderer_identity: Mapping[str, str],
    runner: Callable[[list[str]], int],
) -> tuple[str, ...]:
    # ponytail: parts are never garbage-collected; delete renders-cache/ by hand
    # if disk matters.
    cache_dir.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    for span in chapter_spans(render_input):
        key = chapter_cache_key(render_input, span, asset_hashes, renderer_identity)
        part = cache_dir / f"{span.chapter_id}-{key[:16]}.mp4"
        if not part.is_file():
            staged = cache_dir / f".{part.stem}.partial.mp4"
            argv = build_render_argv(
                render_input_path, staged, public_dir,
                frames=(span.start_frame, span.end_frame - 1), muted=True,
            )
            if runner(argv) != 0 or not staged.is_file():
                staged.unlink(missing_ok=True)
                raise RuntimeError(f"Chapter {span.chapter_id} render failed")
            staged.replace(part)
        parts.append(part)
    output.parent.mkdir(parents=True, exist_ok=True)
    concat_list = cache_dir / "chapters.txt"
    concat_list.write_text(
        "".join(f"file '{part.resolve().as_posix()}'" + "\n" for part in parts),
        encoding="utf-8",
    )
    if runner(build_concat_argv(concat_list, audio, output)) != 0 or not output.is_file():
        raise RuntimeError("FFmpeg chapter concat failed")
    return tuple(part.name for part in parts)
