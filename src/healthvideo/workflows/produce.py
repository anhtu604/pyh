import hashlib
import json
import os
import shutil
from collections.abc import Callable, Mapping
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

from healthvideo.domain.project import ProjectManifest, ProjectState, transition
from healthvideo.domain.script import Script
from healthvideo.domain.storyboard import Storyboard
from healthvideo.render.input import build_render_input
from healthvideo.render.remotion import build_render_argv
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.tts.base import TTSProvider, TTSRequest

Runner = Callable[[list[str]], int]
OUTPUT_NAME = "video.mp4"
MANIFEST_NAME = "manifest.json"
AUTHOR_PROFILE_PATH = (
    Path(__file__).resolve().parents[3] / "profiles" / "author-voice.vi.yaml"
)


def produce_project(
    project_dir: Path,
    tts: TTSProvider,
    runner: Runner,
    *,
    dry_run: bool = False,
) -> Path:
    """Render an approved project, reusing an output with a matching input hash."""
    manifest_path = project_dir / "project.yaml"
    project = ProjectManifest.model_validate(read_yaml(manifest_path))
    script = Script.model_validate(read_yaml(project_dir / "script" / "script.yaml"))
    storyboard = Storyboard.model_validate(
        read_yaml(project_dir / "storyboard" / "storyboard.yaml")
    )
    author_profile = read_yaml(AUTHOR_PROFILE_PATH)
    provider_name = _provider_name(tts)
    input_hash = _input_hash(script, storyboard, author_profile, provider_name)
    output = project_dir / "renders" / OUTPUT_NAME
    render_manifest = project_dir / "renders" / MANIFEST_NAME
    render_input = build_render_input(storyboard, audio_file="audio/narration.wav")

    if dry_run:
        build_render_argv(project_dir / "render-input.json", output, project_dir)
        return output

    if project.state is ProjectState.AWAITING_VIDEO_REVIEW:
        if _cache_matches(render_manifest, input_hash, output):
            return output
        raise ValueError("Production requires project state script_approved")
    if project.state is not ProjectState.SCRIPT_APPROVED:
        raise ValueError("Production requires project state script_approved")
    if _cache_matches(render_manifest, input_hash, output):
        return output

    staging_dir = _create_staging_directory(project_dir, project.slug)
    try:
        _copy_project_assets(project_dir, staging_dir)
        staged_audio = staging_dir / "audio" / "narration.wav"
        tts.synthesize(
            TTSRequest(
                text=" ".join(line.text for line in script.lines),
                language=script.language,
                delivery_beats=tuple(
                    line.delivery.model_dump(mode="json") for line in script.lines
                ),
            ),
            staged_audio,
        )
        staged_render_input = staging_dir / "render-input.json"
        _write_json_atomic(staged_render_input, render_input.model_dump(mode="json"))
        staged_output = staging_dir / "renders" / OUTPUT_NAME
        argv = build_render_argv(staged_render_input, staged_output, staging_dir)
        exit_code = runner(argv)
        if exit_code != 0:
            raise RuntimeError(f"Remotion render failed with exit code {exit_code}")
        if not staged_output.is_file():
            raise FileNotFoundError(
                f"Remotion render did not create output: {staged_output}"
            )
        _write_json_atomic(
            staging_dir / "renders" / MANIFEST_NAME,
            {
                "input_hash": input_hash,
                "output": OUTPUT_NAME,
                "provider": provider_name,
            },
        )
        _publish_staged_artifacts(staging_dir, project_dir)
        write_yaml_atomic(
            manifest_path,
            _completed_project(project).model_dump(mode="json"),
        )
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    else:
        shutil.rmtree(staging_dir, ignore_errors=True)
    return output


def _provider_name(tts: TTSProvider) -> str:
    provider_name = getattr(tts, "provider_name", None)
    if not isinstance(provider_name, str) or not provider_name:
        raise ValueError("TTS provider must define a non-empty provider_name")
    return provider_name


def _input_hash(
    script: Script,
    storyboard: Storyboard,
    author_profile: Mapping[str, Any],
    provider_name: str,
) -> str:
    payload = {
        "author_profile": dict(author_profile),
        "provider": provider_name,
        "script": script.model_dump(mode="json"),
        "storyboard": storyboard.model_dump(mode="json"),
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _cache_matches(manifest_path: Path, input_hash: str, output: Path) -> bool:
    if not manifest_path.is_file() or not output.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return (
        manifest.get("input_hash") == input_hash
        and manifest.get("output") == output.name
    )


def _completed_project(project: ProjectManifest) -> ProjectManifest:
    producing = transition(project, ProjectState.PRODUCING)
    rendered = transition(producing, ProjectState.RENDERED)
    return transition(rendered, ProjectState.AWAITING_VIDEO_REVIEW)


def _create_staging_directory(project_dir: Path, slug: str) -> Path:
    return Path(mkdtemp(prefix=f".{slug}.produce-", dir=project_dir.parent))


def _copy_project_assets(project_dir: Path, staging_dir: Path) -> None:
    assets = project_dir / "assets"
    if assets.is_dir():
        shutil.copytree(assets, staging_dir / "assets")


def _publish_staged_artifacts(staging_dir: Path, project_dir: Path) -> None:
    destinations = (
        (
            staging_dir / "audio" / "narration.wav",
            project_dir / "audio" / "narration.wav",
        ),
        (staging_dir / "render-input.json", project_dir / "render-input.json"),
        (staging_dir / "renders" / OUTPUT_NAME, project_dir / "renders" / OUTPUT_NAME),
        (
            staging_dir / "renders" / MANIFEST_NAME,
            project_dir / "renders" / MANIFEST_NAME,
        ),
    )
    for source, destination in destinations:
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, destination)


def _write_json_atomic(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(
                data, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
