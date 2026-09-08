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
PRODUCTION_ARTIFACT = "production"
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
    renders_dir = project_dir / "renders"
    run_dir = renders_dir / input_hash
    output = run_dir / OUTPUT_NAME
    render_input = build_render_input(storyboard, audio_file="audio/narration.wav")
    cache_valid = _run_is_valid(run_dir, input_hash, provider_name)

    if project.state is ProjectState.AWAITING_VIDEO_REVIEW:
        if not _is_active_cache(project, input_hash, cache_valid):
            raise ValueError("Production requires project state script_approved")
        return output
    if project.state is not ProjectState.SCRIPT_APPROVED:
        raise ValueError("Production requires project state script_approved")
    if dry_run:
        return output
    if cache_valid:
        write_yaml_atomic(
            manifest_path,
            _completed_project(project, input_hash).model_dump(mode="json"),
        )
        return output

    staging_dir = _create_staging_directory(renders_dir, project.slug)
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
        staged_output = staging_dir / OUTPUT_NAME
        argv = build_render_argv(staged_render_input, staged_output, staging_dir)
        exit_code = runner(argv)
        if exit_code != 0:
            raise RuntimeError(f"Remotion render failed with exit code {exit_code}")
        if not staged_output.is_file():
            raise FileNotFoundError(
                f"Remotion render did not create output: {staged_output}"
            )
        _write_json_atomic(
            staging_dir / MANIFEST_NAME,
            {
                "input_hash": input_hash,
                "output": OUTPUT_NAME,
                "provider": provider_name,
            },
        )
        _validate_staged_run(staging_dir, input_hash, provider_name)
        _promote_run(staging_dir, run_dir)
        write_yaml_atomic(
            manifest_path,
            _completed_project(project, input_hash).model_dump(mode="json"),
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


def _run_is_valid(run_dir: Path, input_hash: str, provider_name: str) -> bool:
    required_paths = (
        run_dir / "audio" / "narration.wav",
        run_dir / "render-input.json",
        run_dir / OUTPUT_NAME,
        run_dir / MANIFEST_NAME,
    )
    if not all(path.is_file() for path in required_paths):
        return False
    try:
        manifest = json.loads((run_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return (
        manifest.get("input_hash") == input_hash
        and manifest.get("output") == OUTPUT_NAME
        and manifest.get("provider") == provider_name
    )


def _is_active_cache(
    project: ProjectManifest, input_hash: str, cache_valid: bool
) -> bool:
    return (
        project.artifact_hashes.get(PRODUCTION_ARTIFACT) == input_hash and cache_valid
    )


def _completed_project(project: ProjectManifest, input_hash: str) -> ProjectManifest:
    producing = transition(project, ProjectState.PRODUCING)
    rendered = transition(producing, ProjectState.RENDERED)
    complete = transition(rendered, ProjectState.AWAITING_VIDEO_REVIEW)
    hashes = dict(complete.artifact_hashes)
    hashes[PRODUCTION_ARTIFACT] = input_hash
    return complete.model_copy(update={"artifact_hashes": hashes})


def _create_staging_directory(renders_dir: Path, slug: str) -> Path:
    renders_dir.mkdir(parents=True, exist_ok=True)
    return Path(mkdtemp(prefix=f".{slug}.produce-", dir=renders_dir))


def _copy_project_assets(project_dir: Path, staging_dir: Path) -> None:
    assets = project_dir / "assets"
    if assets.is_dir():
        shutil.copytree(assets, staging_dir / "assets")


def _validate_staged_run(
    staging_dir: Path, input_hash: str, provider_name: str
) -> None:
    if not _run_is_valid(staging_dir, input_hash, provider_name):
        raise ValueError("Staged production run is incomplete")


def _promote_run(staging_dir: Path, run_dir: Path) -> None:
    os.replace(staging_dir, run_dir)


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
