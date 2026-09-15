import json
import os
import shutil
from collections.abc import Callable, Mapping
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

from healthvideo.assets import (
    evidence_asset_hashes,
    referenced_evidence_assets,
    referenced_storyboard_assets,
)
from healthvideo.domain.asset_manifest import load_asset_manifest
from healthvideo.domain.gate_review import GateApprovalRecord, GateKind
from healthvideo.domain.hook_outro import validate_hook_outro
from healthvideo.domain.project import ProjectManifest, ProjectState, transition
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.review import ReviewKind
from healthvideo.domain.script import Script
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.domain.storyboard import Storyboard
from healthvideo.domain.visual_budget import validate_visual_budget
from healthvideo.render.input import audio_timing_qa, build_render_input
from healthvideo.render.remotion import build_render_argv
from healthvideo.render.run import (
    MANIFEST_NAME,
    OUTPUT_NAME,
    PRODUCTION_ARTIFACT,
    RENDER_INPUT_NAME,
    renders_directory,
)
from healthvideo.storage.files import (
    canonical_json_hash,
    read_yaml,
    replace_directory_atomic,
    sha256_file,
    write_yaml_atomic,
)
from healthvideo.storage.project_layout import ProjectLayout, resolve_project_layout
from healthvideo.tts import pronunciation as pronunciation_module
from healthvideo.tts.audio_checks import inspect_wav
from healthvideo.tts.base import TTSProvider, TTSRequest, provider_identity
from healthvideo.tts.pronunciation import (
    apply_pronunciation,
    load_pronunciation_lexicon,
    pronunciation_hash,
)
from healthvideo.workflows.ai_clips import recover_ai_clip_generation
from healthvideo.workflows.gate_review import (
    MEDICAL_APPROVAL_ARTIFACT,
    hash_reviewed_artifacts,
    medical_reviewed_paths,
)
from healthvideo.workflows.review import ensure_approval_current
from healthvideo.workflows.visual_assets import recover_chart_asset_binding

Runner = Callable[[list[str]], int]
AUTHOR_PROFILE_PATH = (
    Path(__file__).resolve().parents[3] / "profiles" / "author-voice.vi.yaml"
)
V2_RENDER_MANIFEST_NAME = "render-manifest.json"
V2_VIDEO_QA_ARTIFACT = "reviews/video-qa.json"


def produce_project(
    project_dir: Path,
    tts: TTSProvider,
    runner: Runner,
    *,
    dry_run: bool = False,
) -> Path:
    """Render an approved project, reusing an output with a matching input hash."""
    layout = resolve_project_layout(project_dir)
    if layout.schema_version == "2.0":
        return _produce_v2(layout, tts, runner, dry_run=dry_run)
    return _produce_v1(layout, tts, runner, dry_run=dry_run)


def _produce_v1(
    layout: ProjectLayout,
    tts: TTSProvider,
    runner: Runner,
    *,
    dry_run: bool,
) -> Path:
    project_dir = layout.project_dir
    manifest_path = project_dir / "project.yaml"
    project = layout.manifest
    assert isinstance(project, ProjectManifest)
    if project.state not in {
        ProjectState.SCRIPT_APPROVED,
        ProjectState.AWAITING_VIDEO_REVIEW,
    }:
        raise ValueError("Production requires project state script_approved")
    ensure_approval_current(project_dir, project, ReviewKind.MEDICAL)
    script = Script.model_validate(read_yaml(project_dir / "script" / "script.yaml"))
    storyboard = Storyboard.model_validate(
        read_yaml(project_dir / "storyboard" / "storyboard.yaml")
    )
    author_profile = read_yaml(AUTHOR_PROFILE_PATH)
    provider_name = _provider_name(tts)
    asset_hashes = evidence_asset_hashes(project_dir, storyboard)
    input_hash = _input_hash(
        script, storyboard, author_profile, provider_name, asset_hashes
    )
    renders_dir = renders_directory(project_dir)
    run_dir = renders_dir / input_hash
    output = run_dir / OUTPUT_NAME
    render_input = build_render_input(storyboard, audio_file="audio/narration.wav")
    cache_valid = _run_is_valid(run_dir, input_hash, provider_name, asset_hashes)

    if project.state is ProjectState.AWAITING_VIDEO_REVIEW:
        if not _is_active_cache(project, input_hash, cache_valid):
            raise ValueError("Production requires project state script_approved")
        return output
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
        _copy_project_assets(project_dir, staging_dir, storyboard, asset_hashes)
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
        staged_render_input = staging_dir / RENDER_INPUT_NAME
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
                "asset_sha256": dict(asset_hashes),
            },
        )
        _validate_staged_run(staging_dir, input_hash, provider_name, asset_hashes)
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


def _produce_v2(
    layout: ProjectLayout,
    tts: TTSProvider,
    runner: Runner,
    *,
    dry_run: bool,
) -> Path:
    project = layout.manifest
    assert isinstance(project, ProjectManifestV2)
    if project.state not in {
        WorkflowState.MEDICALLY_APPROVED,
        WorkflowState.PRODUCTION_IN_PROGRESS,
        WorkflowState.AWAITING_VIDEO_REVIEW,
    }:
        raise ValueError(
            "Production requires v2 project state medically_approved"
        )

    recover_chart_asset_binding(layout.project_dir)
    recover_ai_clip_generation(layout.project_dir)
    _ensure_v2_medical_approval_current(layout.artifact_root)
    script = Script.model_validate(
        read_yaml(layout.artifact_root / "script" / "script.yaml")
    )
    storyboard = Storyboard.model_validate(
        read_yaml(layout.artifact_root / "storyboard" / "storyboard.yaml")
    )
    visual_budget_report = validate_visual_budget(storyboard)
    visual_budget_qa = (
        visual_budget_report.model_dump(mode="json")
        if storyboard.visual_budget_profile == "m6_5_v1"
        else None
    )
    validate_hook_outro(script, storyboard, require_brand=script.format_profile == "hook_outro_v1")
    author_profile = read_yaml(AUTHOR_PROFILE_PATH)
    pronunciation = load_pronunciation_lexicon(
        pronunciation_module.PRONUNCIATION_PROFILE_PATH
    )
    pronunciation_sha256 = pronunciation_hash(pronunciation)
    narration = " ".join(line.text for line in script.lines)
    provider_name = _provider_name(tts)
    provider_identity_data = provider_identity(tts)
    asset_hashes = evidence_asset_hashes(layout.artifact_root, storyboard)
    visual_paths = referenced_storyboard_assets(
        layout.artifact_root,
        storyboard,
        load_asset_manifest(layout.artifact_root / "assets/asset-manifest.yaml"),
    )
    asset_hashes.update(
        {relative: sha256_file(path) for relative, path in visual_paths.items()}
    )
    input_hash = canonical_json_hash(
        {
            "production": _input_hash(
                script, storyboard, author_profile, provider_name, asset_hashes
            ),
            "pronunciation_sha256": pronunciation_sha256,
            "provider_identity": provider_identity_data,
        }
    )
    render_input = build_render_input(
        storyboard, audio_file="audio/narration.wav", duration_policy="v2"
    )
    final_scene = storyboard.scenes[-1]
    final_frame = final_scene.start_frame + final_scene.duration_frames
    require_timing = script.format_profile == "hook_outro_v1"
    renders_dir = layout.artifact_root / "renders"
    output = renders_dir / OUTPUT_NAME
    cache_valid = _v2_run_is_valid(
        renders_dir, input_hash, provider_name, asset_hashes,
        pronunciation_sha256=pronunciation_sha256,
        provider_identity=provider_identity_data,
        require_timing=False,
    )
    if cache_valid and (require_timing or visual_budget_qa is not None):
        cache_valid = _v2_video_qa_is_valid(
            layout.artifact_root,
            input_hash,
            require_timing=require_timing,
            final_frame=final_frame,
            expected_visual_budget=visual_budget_qa,
        ) or _production_qa_is_valid(
            renders_dir / "video-qa.json",
            renders_dir,
            final_frame,
            require_timing=require_timing,
            expected_visual_budget=visual_budget_qa,
        )

    if project.state is WorkflowState.AWAITING_VIDEO_REVIEW:
        if not (
            _is_active_v2_cache(project, input_hash, cache_valid)
            and _v2_video_qa_is_valid(
                layout.artifact_root,
                input_hash,
                require_timing=require_timing,
                final_frame=final_frame,
                expected_visual_budget=visual_budget_qa,
            )
        ):
            raise ValueError(
                "Production requires v2 project state medically_approved"
            )
        return output
    if dry_run:
        return output
    if cache_valid:
        _promote_v2_video_qa_if_needed(
            layout.artifact_root,
            input_hash,
            require_timing=require_timing,
            final_frame=final_frame,
            expected_visual_budget=visual_budget_qa,
        )
        write_yaml_atomic(
            layout.project_dir / "project.yaml",
            _completed_v2_project(project, input_hash).model_dump(mode="json"),
        )
        return output

    staging_dir = Path(
        mkdtemp(
            prefix=f".{project.slug}.produce-", dir=layout.artifact_root
        )
    )
    try:
        _copy_v2_assets(layout.artifact_root, staging_dir, storyboard, asset_hashes)
        staged_audio = staging_dir / "audio" / "narration.wav"
        tts.synthesize(
            TTSRequest(
                text=apply_pronunciation(narration, pronunciation),
                language=script.language,
                delivery_beats=tuple(
                    line.delivery.model_dump(mode="json") for line in script.lines
                ),
            ),
            staged_audio,
        )
        audio_report = inspect_wav(
            staged_audio, require_signal=getattr(tts, "require_signal", False)
        )
        timing_qa = audio_timing_qa(audio_report.duration_ms, final_frame)
        render_input_data = render_input.model_dump(mode="json")
        staged_render_input = staging_dir / RENDER_INPUT_NAME
        _write_json_atomic(staged_render_input, render_input_data)
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
            staging_dir / V2_RENDER_MANIFEST_NAME,
            {
                "input_hash": input_hash,
                "output": OUTPUT_NAME,
                "provider": provider_name,
                "asset_sha256": dict(asset_hashes),
                "render_input_sha256": canonical_json_hash(render_input_data),
                "pronunciation_version": pronunciation.version,
                "pronunciation_sha256": pronunciation_sha256,
                "provider_identity": provider_identity_data,
            },
        )
        _write_json_atomic(
            staging_dir / "video-qa.json",
            {
                "schema_version": "2.0",
                "status": "render_complete",
                "input_hash": input_hash,
                "checks": {"output_exists": True},
                **timing_qa,
                **(
                    {"visual_budget": visual_budget_qa}
                    if visual_budget_qa is not None
                    else {}
                ),
            },
        )
        _validate_v2_staged_run(
            staging_dir, input_hash, provider_name, asset_hashes,
            pronunciation_sha256=pronunciation_sha256,
            provider_identity=provider_identity_data,
            require_timing=require_timing,
            final_frame=final_frame,
            expected_visual_budget=visual_budget_qa,
        )
        _promote_run(staging_dir, renders_dir)
        _promote_v2_video_qa_if_needed(
            layout.artifact_root,
            input_hash,
            require_timing=require_timing,
            final_frame=final_frame,
            expected_visual_budget=visual_budget_qa,
        )
        write_yaml_atomic(
            layout.project_dir / "project.yaml",
            _completed_v2_project(project, input_hash).model_dump(mode="json"),
        )
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    else:
        shutil.rmtree(staging_dir, ignore_errors=True)
    return output


def _ensure_v2_medical_approval_current(revision_root: Path) -> GateApprovalRecord:
    approval_path = revision_root / MEDICAL_APPROVAL_ARTIFACT
    if not approval_path.is_file():
        raise FileNotFoundError(
            "Production requires a medical approval record for the active revision"
        )
    approval = GateApprovalRecord.model_validate(read_yaml(approval_path))
    if approval.kind is not GateKind.MEDICAL:
        raise ValueError("Production requires a medical approval record")
    current_hashes = hash_reviewed_artifacts(
        medical_reviewed_paths(revision_root)
    )
    if current_hashes != approval.artifact_hashes:
        raise ValueError("Production requires a current medical approval")
    return approval


def _v2_run_is_valid(
    run_dir: Path,
    input_hash: str,
    provider_name: str,
    asset_hashes: Mapping[str, str],
    *,
    pronunciation_sha256: str,
    provider_identity: Mapping[str, str],
    require_timing: bool = False,
    final_frame: int | None = None,
    expected_visual_budget: Mapping[str, Any] | None = None,
) -> bool:
    required_paths = (
        run_dir / "audio" / "narration.wav",
        run_dir / RENDER_INPUT_NAME,
        run_dir / OUTPUT_NAME,
        run_dir / V2_RENDER_MANIFEST_NAME,
    )
    if not all(path.is_file() for path in required_paths):
        return False
    if require_timing and not _timing_qa_is_valid(
        run_dir / "video-qa.json", run_dir, final_frame
    ):
        return False
    if expected_visual_budget is not None and not _visual_budget_qa_is_valid(
        run_dir / "video-qa.json", expected_visual_budget
    ):
        return False
    try:
        manifest = json.loads(
            (run_dir / V2_RENDER_MANIFEST_NAME).read_text(encoding="utf-8")
        )
        render_input = json.loads(
            (run_dir / RENDER_INPUT_NAME).read_text(encoding="utf-8")
        )
    except json.JSONDecodeError:
        return False
    if not (
        manifest.get("input_hash") == input_hash
        and manifest.get("output") == OUTPUT_NAME
        and manifest.get("provider") == provider_name
        and manifest.get("asset_sha256") == dict(asset_hashes)
        and manifest.get("pronunciation_sha256") == pronunciation_sha256
        and manifest.get("provider_identity") == dict(provider_identity)
        and manifest.get("render_input_sha256")
        == canonical_json_hash(render_input)
    ):
        return False
    return all(
        (run_dir / relative).is_file()
        and sha256_file(run_dir / relative) == expected
        for relative, expected in asset_hashes.items()
    )


def _validate_v2_staged_run(
    staging_dir: Path,
    input_hash: str,
    provider_name: str,
    asset_hashes: Mapping[str, str],
    *,
    pronunciation_sha256: str,
    provider_identity: Mapping[str, str],
    require_timing: bool = False,
    final_frame: int | None = None,
    expected_visual_budget: Mapping[str, Any] | None = None,
) -> None:
    if not _v2_run_is_valid(
        staging_dir, input_hash, provider_name, asset_hashes,
        pronunciation_sha256=pronunciation_sha256,
        provider_identity=provider_identity,
        require_timing=require_timing,
        final_frame=final_frame,
        expected_visual_budget=expected_visual_budget,
    ):
        raise ValueError("Staged v2 production run is incomplete")


def _is_active_v2_cache(
    project: ProjectManifestV2, input_hash: str, cache_valid: bool
) -> bool:
    return (
        project.artifact_hashes.get(PRODUCTION_ARTIFACT) == input_hash
        and cache_valid
    )


def _promote_v2_video_qa_if_needed(
    revision_root: Path,
    input_hash: str,
    *,
    require_timing: bool = False,
    final_frame: int | None = None,
    expected_visual_budget: Mapping[str, Any] | None = None,
) -> None:
    if _v2_video_qa_is_valid(
        revision_root, input_hash, require_timing=require_timing,
        final_frame=final_frame,
        expected_visual_budget=expected_visual_budget,
    ):
        return
    source = revision_root / "renders" / "video-qa.json"
    if not source.is_file():
        raise FileNotFoundError(f"Production video QA is missing: {source}")
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("Production video QA is invalid") from error
    if data.get("input_hash") != input_hash:
        raise ValueError("Production video QA does not match the active render")
    if require_timing and not _timing_qa_is_valid(
        source, revision_root / "renders", final_frame
    ):
        raise ValueError("Production video QA timing is invalid")
    if expected_visual_budget is not None and not _visual_budget_qa_is_valid(
        source, expected_visual_budget
    ):
        raise ValueError("Production visual-budget QA is invalid")
    target = revision_root / V2_VIDEO_QA_ARTIFACT
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, target)


def _v2_video_qa_is_valid(
    revision_root: Path,
    input_hash: str,
    *,
    require_timing: bool = False,
    final_frame: int | None = None,
    expected_visual_budget: Mapping[str, Any] | None = None,
) -> bool:
    path = revision_root / V2_VIDEO_QA_ARTIFACT
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return (
        data.get("input_hash") == input_hash
        and (
            not require_timing
            or _timing_qa_is_valid(path, revision_root / "renders", final_frame)
        )
        and (
            expected_visual_budget is None
            or _visual_budget_qa_is_valid(path, expected_visual_budget)
        )
    )


def _production_qa_is_valid(
    path: Path,
    run_dir: Path,
    final_frame: int | None,
    *,
    require_timing: bool,
    expected_visual_budget: Mapping[str, Any] | None,
) -> bool:
    return (
        not require_timing or _timing_qa_is_valid(path, run_dir, final_frame)
    ) and (
        expected_visual_budget is None
        or _visual_budget_qa_is_valid(path, expected_visual_budget)
    )


def _visual_budget_qa_is_valid(
    path: Path, expected_visual_budget: Mapping[str, Any]
) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    # Canonical JSON keeps 0/False and 1000/1000.0 distinct, unlike dict equality.
    return isinstance(data, dict) and canonical_json_hash(
        data.get("visual_budget")
    ) == canonical_json_hash(dict(expected_visual_budget))


def _timing_qa_is_valid(path: Path, run_dir: Path, final_frame: int | None) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        audio_ms = data["audio_duration_ms"]
        composition_ms = data["composition_duration_ms"]
        trailing_ms = data["trailing_visual_ms"]
        measured_ms = inspect_wav(run_dir / "audio" / "narration.wav").duration_ms
        expected = audio_timing_qa(measured_ms, final_frame)
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return (
        all(
            type(value) is int and value >= 0
            for value in (audio_ms, composition_ms, trailing_ms)
        )
        and {key: data[key] for key in expected} == expected
    )


def _completed_v2_project(
    project: ProjectManifestV2, input_hash: str
) -> ProjectManifestV2:
    context = TransitionContext(
        active_revision=project.active_revision,
        current_input_hash=input_hash,
        validated_artifacts=frozenset(
            {
                MEDICAL_APPROVAL_ARTIFACT,
                "renders/render-manifest.json",
                V2_VIDEO_QA_ARTIFACT,
            }
        ),
    )
    producing = project
    if project.state is WorkflowState.MEDICALLY_APPROVED:
        producing = transition_v2(
            project, WorkflowState.PRODUCTION_IN_PROGRESS, context
        )
    complete = transition_v2(
        producing, WorkflowState.AWAITING_VIDEO_REVIEW, context
    )
    hashes = dict(complete.artifact_hashes)
    hashes[PRODUCTION_ARTIFACT] = input_hash
    return complete.model_copy(update={"artifact_hashes": hashes})


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
    asset_hashes: Mapping[str, str],
) -> str:
    payload = {
        "author_profile": dict(author_profile),
        "provider": provider_name,
        "script": script.model_dump(mode="json"),
        "storyboard": storyboard.model_dump(mode="json"),
        "evidence_assets": dict(asset_hashes),
    }
    return canonical_json_hash(payload)


def _run_is_valid(
    run_dir: Path,
    input_hash: str,
    provider_name: str,
    asset_hashes: Mapping[str, str],
) -> bool:
    required_paths = (
        run_dir / "audio" / "narration.wav",
        run_dir / RENDER_INPUT_NAME,
        run_dir / OUTPUT_NAME,
        run_dir / MANIFEST_NAME,
    )
    if not all(path.is_file() for path in required_paths):
        return False
    try:
        manifest = json.loads((run_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    if not (
        manifest.get("input_hash") == input_hash
        and manifest.get("output") == OUTPUT_NAME
        and manifest.get("provider") == provider_name
        and manifest.get("asset_sha256") == dict(asset_hashes)
    ):
        return False
    return all(
        (run_dir / relative).is_file()
        and sha256_file(run_dir / relative) == expected
        for relative, expected in asset_hashes.items()
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


def _copy_project_assets(
    project_dir: Path,
    staging_dir: Path,
    storyboard: Storyboard,
    expected_hashes: Mapping[str, str],
) -> None:
    for relative, source in referenced_evidence_assets(
        project_dir, storyboard
    ).items():
        destination = staging_dir.joinpath(*Path(relative).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if sha256_file(destination) != expected_hashes[relative]:
            raise ValueError(
                f"Evidence asset changed while staging production: {relative}"
            )


def _copy_v2_assets(
    revision_root: Path,
    staging_dir: Path,
    storyboard: Storyboard,
    expected_hashes: Mapping[str, str],
) -> None:
    paths = referenced_evidence_assets(revision_root, storyboard)
    paths.update(
        referenced_storyboard_assets(
            revision_root,
            storyboard,
            load_asset_manifest(revision_root / "assets/asset-manifest.yaml"),
        )
    )
    for relative, source in paths.items():
        destination = staging_dir.joinpath(*Path(relative).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if sha256_file(destination) != expected_hashes[relative]:
            raise ValueError(f"Visual asset changed while staging: {relative}")


def _validate_staged_run(
    staging_dir: Path,
    input_hash: str,
    provider_name: str,
    asset_hashes: Mapping[str, str],
) -> None:
    if not _run_is_valid(staging_dir, input_hash, provider_name, asset_hashes):
        raise ValueError("Staged production run is incomplete")


def _promote_run(staging_dir: Path, run_dir: Path) -> None:
    """Publish a staged run with one rename, replacing an unusable run if present."""
    replace_directory_atomic(staging_dir, run_dir)


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
