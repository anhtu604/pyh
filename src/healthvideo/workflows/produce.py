import hashlib
import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
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
AUTHOR_PROFILE_PATH = Path(__file__).resolve().parents[3] / "profiles" / "author-voice.vi.yaml"


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
    storyboard = Storyboard.model_validate(read_yaml(project_dir / "storyboard" / "storyboard.yaml"))
    author_profile = read_yaml(AUTHOR_PROFILE_PATH)
    provider_name = _provider_name(tts)
    input_hash = _input_hash(script, storyboard, author_profile, provider_name)
    output = project_dir / "renders" / OUTPUT_NAME
    render_manifest = project_dir / "renders" / MANIFEST_NAME

    if project.state is ProjectState.AWAITING_VIDEO_REVIEW:
        if _cache_matches(render_manifest, input_hash, output):
            return output
        raise ValueError("Production requires project state script_approved")
    if project.state is not ProjectState.SCRIPT_APPROVED:
        raise ValueError("Production requires project state script_approved")
    if _cache_matches(render_manifest, input_hash, output):
        return output

    render_input_path = project_dir / "render-input.json"
    audio_path = project_dir / "audio" / "narration.wav"
    render_input = build_render_input(storyboard, audio_file="audio/narration.wav")
    argv = build_render_argv(render_input_path, output, project_dir)
    if dry_run:
        runner(argv)
        return output

    _write_project_state(manifest_path, project, ProjectState.PRODUCING)
    narration = " ".join(line.text for line in script.lines)
    tts.synthesize(
        TTSRequest(
            text=narration,
            language=script.language,
            delivery_beats=tuple(line.delivery.model_dump(mode="json") for line in script.lines),
        ),
        audio_path,
    )
    _write_json_atomic(render_input_path, render_input.model_dump(mode="json"))
    exit_code = runner(argv)
    if exit_code != 0:
        raise RuntimeError(f"Remotion render failed with exit code {exit_code}")
    if not output.is_file():
        raise FileNotFoundError(f"Remotion render did not create output: {output}")

    _write_json_atomic(
        render_manifest,
        {"input_hash": input_hash, "output": OUTPUT_NAME, "provider": provider_name},
    )
    rendered = ProjectManifest.model_validate(read_yaml(manifest_path))
    _write_project_state(manifest_path, rendered, ProjectState.RENDERED)
    awaiting_review = ProjectManifest.model_validate(read_yaml(manifest_path))
    _write_project_state(manifest_path, awaiting_review, ProjectState.AWAITING_VIDEO_REVIEW)
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
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _cache_matches(manifest_path: Path, input_hash: str, output: Path) -> bool:
    if not manifest_path.is_file() or not output.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return manifest.get("input_hash") == input_hash and manifest.get("output") == output.name


def _write_project_state(
    manifest_path: Path, project: ProjectManifest, target: ProjectState
) -> None:
    write_yaml_atomic(manifest_path, transition(project, target).model_dump(mode="json"))


def _write_json_atomic(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
