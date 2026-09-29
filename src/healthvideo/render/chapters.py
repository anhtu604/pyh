"""Chapter spans and content-addressed cache keys for long-form render."""

from collections.abc import Mapping
from dataclasses import dataclass

from healthvideo.render.input import RenderInput
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
    return canonical_json_hash(
        {
            "format_profile": render_input.format_profile,
            "fps": render_input.fps,
            "scenes": scenes,
            "assets": {path: asset_hashes.get(path, "") for path in sorted(paths)},
            "renderer": dict(renderer_identity),
        }
    )
