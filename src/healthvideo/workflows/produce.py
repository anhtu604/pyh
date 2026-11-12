import json
import os
import re
import shutil
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from tempfile import mkdtemp
from typing import Any

from healthvideo.assets import (
    evidence_asset_hashes,
    referenced_evidence_assets,
    referenced_storyboard_assets,
)
from healthvideo.audio.align import align_lines, alignment_identity, pronunciation_qa
from healthvideo.audio.music import (
    DEFAULT_MOOD,
    DUCK_DB,
    MIX_VERSION,
    MODEL_ID,
    MUSIC_DB,
    MUSIC_SECONDS,
    MUSIC_SEED,
    generate_music,
    mix_with_ducking,
)
from healthvideo.audio.sfx import (
    SFX_ROOT,
    mix_sfx,
    resolve_sfx,
    sfx_identity,
    sfx_rights,
)
from healthvideo.domain.asset_manifest import (
    AssetKind,
    AssetManifest,
    load_asset_manifest,
)
from healthvideo.domain.brand import load_brand_profile
from healthvideo.domain.format_profile import FORMAT_SPECS
from healthvideo.domain.gate_review import GateApprovalRecord, GateKind
from healthvideo.domain.hook_outro import validate_hook_outro
from healthvideo.domain.license_ledger import LicenseEntry, LicenseLedger
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.script import Script
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.domain.storyboard import (
    SUPPORTED_ANATOMY_SUBJECTS,  # noqa: F401 - compatibility export
    Storyboard,
    validate_anatomy_subjects,
)
from healthvideo.domain.visual_budget import validate_visual_budget
from healthvideo.render.beats import resolve_scene_beats
from healthvideo.render.chapters import render_long_form
from healthvideo.render.input import audio_timing_qa, build_render_input
from healthvideo.render.remotion import build_render_argv, renderer_identity
from healthvideo.render.run import (
    OUTPUT_NAME,
    PRODUCTION_ARTIFACT,
    RENDER_INPUT_NAME,
)
from healthvideo.render.thumbnail import render_optional_thumbnail
from healthvideo.render.timing import (
    PAD_FRAMES,
    TIMING_POLICY_VERSION,
    concat_scene_audio,
    restore_timed_storyboard,
    retime_storyboard,
)
from healthvideo.render.word_timing import apply_alignment
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
from healthvideo.visuals.flux import (
    generate_illustration,
    illustration_recipe_hash,
    validate_illustration_png,
)
from healthvideo.workflows.gate_review import (
    MEDICAL_APPROVAL_ARTIFACT,
    hash_reviewed_artifacts,
    medical_reviewed_paths,
)
from healthvideo.workflows.long_form import (
    CLIP_PLAN_ARTIFACT,
    load_clip_scenes,
    render_clips,
)
from healthvideo.workflows.visual_assets import (
    BRAND_PROFILE_PATH,
    recover_chart_asset_binding,
)
from healthvideo.workflows.visual_review import (
    CANDIDATES,
    apply_visual_fallbacks,
    ensure_candidates,
    prepare_contact_sheet,
    review_complete,
    visual_identity,
)
from healthvideo.workflows.visual_review import (
    REPORT as VISUAL_REVIEW_REPORT,
)

Runner = Callable[[list[str]], int]
AUTHOR_PROFILE_PATH = (
    Path(__file__).resolve().parents[3] / "profiles" / "author-voice.vi.yaml"
)
V2_RENDER_MANIFEST_NAME = "render-manifest.json"
V2_VIDEO_QA_ARTIFACT = "reviews/video-qa.json"
CHAPTER_CACHE_DIRECTORY = "renders-cache"


def _synthesize_cached_line(
    tts: TTSProvider, request: TTSRequest, output: Path, *, cache_dir: Path,
) -> None:
    """Retain paid line requests even when a later render fails."""
    if provider_identity(tts)["provider"] not in {"elevenlabs", "vibi_minimax"}:
        tts.synthesize(request, output)
        return
    key = canonical_json_hash({"request": request.model_dump(mode="json"),
                               "provider": provider_identity(tts)})
    cached = cache_dir / f"{key}.wav"
    receipt = cached.with_suffix(".json")
    try:
        if read_yaml(receipt).get("sha256") == sha256_file(cached):
            inspect_wav(cached, require_signal=getattr(tts, "require_signal", False))
            shutil.copyfile(cached, output)
            return
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    tts.synthesize(request, output)
    try:
        inspect_wav(output, require_signal=getattr(tts, "require_signal", False))
    except ValueError as error:
        output.unlink(missing_ok=True)
        raise RuntimeError(f"TTS provider returned invalid audio: {error}") from None
    cache_dir.mkdir(parents=True, exist_ok=True)
    temporary = cached.with_suffix(".tmp")
    shutil.copyfile(output, temporary)
    os.replace(temporary, cached)
    _write_json_atomic(receipt, {"sha256": sha256_file(cached),
                                 "request": request.model_dump(mode="json"),
                                 "provider": provider_identity(tts)})


def _music_mood(root: Path) -> str:
    path = root / "script/outline.yaml"
    if path.is_file():
        outline = read_yaml(path)
        moods = [outline.get("mood"), *(
            chapter.get("mood") for chapter in outline.get("chapters", [])
        )]
        specified = list(dict.fromkeys(mood.strip() for mood in moods
                                      if isinstance(mood, str) and mood.strip()))
        if specified:
            return "; ".join(specified)
    return DEFAULT_MOOD


def _prepare_illustrations(
    root: Path, storyboard: Storyboard, manifest: AssetManifest, *, generate: bool,
) -> list[LicenseEntry]:
    """Materialize reviewed decorative recipes without changing any medical artifact."""
    spec = FORMAT_SPECS[storyboard.format_profile]
    references = {PurePosixPath(ref.path).as_posix() for scene in storyboard.scenes for ref in scene.visual_assets}
    rights = []
    candidates = ensure_candidates(root, storyboard, manifest, generate=generate_illustration) if generate else {}
    for asset in manifest.assets:
        if asset.kind is not AssetKind.ILLUSTRATION or asset.path not in references:
            continue
        path = root.joinpath(*Path(asset.path).parts)
        assert asset.prompt is not None and asset.seed is not None
        recipe_hash = illustration_recipe_hash(asset.prompt, spec.width, spec.height, asset.seed)
        receipt = path.with_suffix(".flux.json")
        needs_generation = not path.is_file()
        if asset.sha256 is None and path.is_file():
            try:
                needs_generation = json.loads(receipt.read_text(encoding="utf-8")) != {
                    "recipe_sha256": recipe_hash, "sha256": sha256_file(path),
                }
            except (OSError, ValueError):
                needs_generation = True
        if candidates:
            # Selection is a derived production choice, never a change to the reviewed recipe.
            needs_generation = False
        # The shared resolver has already checked path/symlink safety and label policy.
        if needs_generation:
            if not generate:
                if not path.is_file():
                    continue
                raise ValueError(f"Production requires current illustration recipe provenance: {asset.path}")
            generate_illustration(asset.prompt, out=path, width=spec.width, height=spec.height, seed=asset.seed)
        validate_illustration_png(path, spec.width, spec.height)
        digest = sha256_file(path)
        if asset.sha256 is not None and asset.sha256 != digest:
            raise ValueError(f"Generated illustration sha256 mismatch: {asset.path}")
        if (needs_generation or candidates) and asset.sha256 is None:
            _write_json_atomic(receipt, {"recipe_sha256": recipe_hash, "sha256": digest})
        rights.append(LicenseEntry(
            path=asset.path, source="generated:flux2-klein-4b", creator=asset.creator,
            license="Apache-2.0", rights_basis="Generated unlabeled illustration using Apache-2.0 FLUX.2 klein 4B weights",
            revision=asset.revision, sha256=digest,
        ))
    return rights


def produce_project(
    project_dir: Path,
    tts: TTSProvider,
    runner: Runner,
    *,
    dry_run: bool = False,
    music: bool = True,
    hold_for_product_review: bool = False,
) -> Path:
    """Render an approved project, reusing an output with a matching input hash.

    With ``hold_for_product_review`` the final render waits for the product critic
    instead of entering the doctor's video gate; ``submit_video`` submits it later.
    """
    layout = resolve_project_layout(project_dir)
    return _produce_v2(layout, tts, runner, dry_run=dry_run, music=music,
                       hold=hold_for_product_review)


def _produce_v2(
    layout: ProjectLayout,
    tts: TTSProvider,
    runner: Runner,
    *,
    dry_run: bool,
    music: bool,
    hold: bool = False,
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
    _ensure_v2_medical_approval_current(layout.artifact_root)
    # Repeated direct `produce` calls cannot skip or implicitly accept visual review.
    visual_index = layout.artifact_root / CANDIDATES
    visual_report = layout.artifact_root / VISUAL_REVIEW_REPORT
    if visual_index.is_file() and not review_complete(layout.artifact_root):
        pending = read_yaml(visual_index)
        unprocessed = visual_report.is_file() and pending.get('review_sha256') != sha256_file(visual_report)
        if pending.get('contact_sheet') and not unprocessed and (layout.artifact_root / 'renders' / OUTPUT_NAME).is_file():
            visual_identity(layout.artifact_root)
            return layout.artifact_root / 'renders' / OUTPUT_NAME
    script = Script.model_validate(
        read_yaml(layout.artifact_root / "script" / "script.yaml")
    )
    storyboard = Storyboard.model_validate(
        read_yaml(layout.artifact_root / "storyboard" / "storyboard.yaml")
    )
    validate_anatomy_subjects(storyboard)
    asset_manifest = load_asset_manifest(layout.artifact_root / "assets/asset-manifest.yaml")
    visual_budget_report = validate_visual_budget(storyboard, asset_manifest)
    visual_budget_qa = visual_budget_report.model_dump(mode="json")
    validate_hook_outro(
        script, storyboard, require_brand=script.format_profile == "hook_outro_v1",
        allow_line_references=True,
    )
    author_profile = read_yaml(AUTHOR_PROFILE_PATH)
    pronunciation = load_pronunciation_lexicon(
        pronunciation_module.PRONUNCIATION_PROFILE_PATH
    )
    pronunciation_sha256 = pronunciation_hash(pronunciation)
    provider_name = _provider_name(tts)
    provider_identity_data = provider_identity(tts)
    renderer_identity_data = renderer_identity()
    # Validate pending declarations before any model invocation. All GPU subprocesses
    # finish synchronously: FLUX first, then VieNeu, then ACE-Step.
    referenced_storyboard_assets(layout.artifact_root, storyboard, asset_manifest)
    illustration_rights = _prepare_illustrations(
        layout.artifact_root, storyboard, asset_manifest,
        generate=not dry_run and project.state is not WorkflowState.AWAITING_VIDEO_REVIEW,
    )
    asset_hashes = evidence_asset_hashes(layout.artifact_root, storyboard)
    visual_paths = referenced_storyboard_assets(
        layout.artifact_root,
        storyboard,
        asset_manifest,
    )
    asset_hashes.update(
        {relative: sha256_file(path) for relative, path in visual_paths.items()}
    )
    clip_brand = (
        load_brand_profile(BRAND_PROFILE_PATH)
        if storyboard.format_profile == "youtube_long" else None
    )
    music_settings = {
        "model_id": MODEL_ID, "mood": _music_mood(layout.artifact_root),
        "seconds": MUSIC_SECONDS, "seed": MUSIC_SEED,
        "music_db": MUSIC_DB, "duck_db": DUCK_DB, "mix_version": MIX_VERSION,
    } if music else None
    input_hash = canonical_json_hash(
        {
            "production": _input_hash(
                script,
                storyboard,
                author_profile,
                provider_name,
                asset_hashes,
                renderer_identity_data,
            ),
            "timing_policy": TIMING_POLICY_VERSION,
            "pronunciation_sha256": pronunciation_sha256,
            "provider_identity": provider_identity_data,
            "renderer_identity": renderer_identity_data,
            "music": music_settings,
            "alignment": alignment_identity(),
            "sfx": sfx_identity(storyboard, layout.artifact_root),
            "visual_review": visual_identity(layout.artifact_root),
            **(
                {"clip_plan": read_yaml(layout.artifact_root / CLIP_PLAN_ARTIFACT),
                 "clip_brand": clip_brand.model_dump(mode="json")}
                if storyboard.format_profile == "youtube_long"
                else {}
            ),
        }
    )
    approved_storyboard = storyboard
    final_scene = storyboard.scenes[-1]
    final_frame = final_scene.start_frame + final_scene.duration_frames
    require_timing = True
    renders_dir = layout.artifact_root / "renders"
    output = renders_dir / OUTPUT_NAME
    cache_valid = _v2_run_is_valid(
        renders_dir, input_hash, provider_name, asset_hashes,
        pronunciation_sha256=pronunciation_sha256,
        provider_identity=provider_identity_data,
        renderer_identity=renderer_identity_data,
        music_settings=music_settings,
        require_timing=False,
    )
    if cache_valid:
        try:
            timing_record = json.loads((renders_dir / "scene-timing.json").read_text(encoding="utf-8"))
            if timing_record["fps"] != 30 or timing_record["pad_frames"] != PAD_FRAMES:
                raise ValueError("Cached scene timing uses another timing policy")
            storyboard = restore_timed_storyboard(approved_storyboard, timing_record)
            visual_budget_report = validate_visual_budget(storyboard, asset_manifest)
            visual_budget_qa = visual_budget_report.model_dump(mode="json")
            final_frame = storyboard.scenes[-1].start_frame + storyboard.scenes[-1].duration_frames
            storyboard = apply_alignment(storyboard, _read_alignment(renders_dir, script))
            storyboard = storyboard.model_copy(update={"scenes": tuple(
                resolve_scene_beats(scene, clamp_outside=True) for scene in storyboard.scenes
            )})
            storyboard = apply_visual_fallbacks(layout.artifact_root, storyboard)
            expected_input = build_render_input(
                storyboard, audio_file="audio/narration.wav"
            ).model_dump(mode="json")
            cached_input = json.loads((renders_dir / RENDER_INPUT_NAME).read_text(encoding="utf-8"))
            cache_valid = canonical_json_hash(expected_input) == canonical_json_hash(cached_input)
        except (OSError, ValueError, KeyError, TypeError):
            cache_valid = False
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
        if not dry_run:
            _promote_pronunciation_qa(layout.artifact_root, input_hash)
            render_optional_thumbnail(layout.artifact_root, runner=runner)
        return output
    if dry_run:
        return output
    if cache_valid:
        if not review_complete(layout.artifact_root):
            prepare_contact_sheet(layout.artifact_root)
        elif (layout.artifact_root / CANDIDATES).is_file():
            prepare_contact_sheet(layout.artifact_root, final=True)
        render_optional_thumbnail(layout.artifact_root, runner=runner)
        _promote_v2_video_qa_if_needed(
            layout.artifact_root,
            input_hash,
            require_timing=require_timing,
            final_frame=final_frame,
            expected_visual_budget=visual_budget_qa,
        )
        write_yaml_atomic(
            layout.project_dir / "project.yaml",
            _production_project(layout, project, input_hash, hold=hold).model_dump(mode="json"),
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
        line_wavs: dict[str, Path] = {}
        line_ms: dict[str, int] = {}
        spoken_scripts: dict[str, str] = {}
        usage_provider = getattr(tts, "inner", tts)
        usage_setter = getattr(usage_provider, "set_usage_path", None)
        if callable(usage_setter):
            usage_setter(layout.artifact_root / "audio/tts-usage.json")
        elif hasattr(usage_provider, "usage_path"):
            usage_provider.usage_path = layout.artifact_root / "audio/tts-usage.json"
        if len({line.id for line in script.lines}) != len(script.lines):
            raise ValueError("Script line IDs must be unique for production timing")
        for line in script.lines:
            # IDs are reviewed identifiers, but must also be safe filenames.
            if Path(line.id).name != line.id or any(c in line.id for c in "/\\:") or line.id in {".", ".."}:
                raise ValueError(f"Unsafe script line id: {line.id}")
            line_audio = staging_dir / "audio" / "lines" / f"{line.id}.wav"
            line_audio.parent.mkdir(parents=True, exist_ok=True)
            sent_text = apply_pronunciation(
                line.tts_text(expressive=provider_name == "elevenlabs"), pronunciation,
            )
            # Lexicon hyphens mark syllables, whereas Whisper returns separate
            # words (u-rát -> u / rát). They are not omitted or extra speech.
            spoken_scripts[line.id] = " ".join(
                re.sub(r"\[[^\]]*\]", "", sent_text).replace("-", " ").split()
            )
            _synthesize_cached_line(
                tts, TTSRequest(text=sent_text, language=script.language,
                                delivery_beats=line.delivery_beats()),
                line_audio, cache_dir=layout.project_dir / "cache/tts",
            )
            line_wavs[line.id] = line_audio
            line_ms[line.id] = inspect_wav(
                line_audio, require_signal=getattr(tts, "require_signal", False)
            ).duration_ms
        usage_path = layout.artifact_root / "audio/tts-usage.json"
        if provider_name in {"elevenlabs", "vibi_minimax"} and usage_path.is_file():
            shutil.copyfile(usage_path, staging_dir / "audio/tts-usage.json")
        alignment = align_lines(
            line_wavs, {line.id: line.text for line in script.lines},
            out_dir=staging_dir / "audio/alignment",
        )
        # Caption anchors remain canonical. QA compares the actual spoken forms;
        # align_lines reuses raw Whisper transcripts for the same WAV bytes.
        qa_alignment = alignment
        if spoken_scripts != {line.id: line.text for line in script.lines}:
            qa_alignment = align_lines(
                line_wavs, spoken_scripts,
                out_dir=staging_dir / "audio/pronunciation-alignment",
            )
        pronunciation_report = pronunciation_qa(
            qa_alignment, terms=[term for entry in pronunciation.entries
                                 for term in (entry.written, entry.spoken.replace("-", " "))],
        )
        pronunciation_report["input_hash"] = input_hash
        _write_json_atomic(staging_dir / "pronunciation-qa.json", pronunciation_report)
        storyboard, timing_record = retime_storyboard(approved_storyboard, line_ms)
        storyboard = apply_alignment(storyboard, alignment)
        storyboard = storyboard.model_copy(update={"scenes": tuple(
            resolve_scene_beats(scene, clamp_outside=True) for scene in storyboard.scenes
        )})
        timing_record["audio_alignment"] = concat_scene_audio(storyboard, line_wavs, staged_audio)
        # Keyword-timed SFX read the alignment just written to staging, not the previous run's.
        sfx_events = resolve_sfx(storyboard, staging_dir)
        music_record = None
        generated_rights = list(illustration_rights)
        generated_visual_hashes: dict[str, str] = {}
        generated_audio_hashes: dict[str, str] = {}
        if music_settings is not None:
            # Keep the precisely timed voice for ASR and speech-only QA.
            voice_audio = staged_audio.with_name("narration-voice.wav")
            shutil.copyfile(staged_audio, voice_audio)
            music_audio = staged_audio.with_name("music.wav")
            generate_music(
                music_settings["mood"], seconds=MUSIC_SECONDS, seed=MUSIC_SEED, out=music_audio,
            )
            if sfx_events:
                mix_sfx(voice_audio, sfx_events, out=staged_audio, music=music_audio)
            else:
                mix_with_ducking(voice_audio, music_audio, out=staged_audio,
                                 music_db=MUSIC_DB, duck_db=DUCK_DB)
            music_record = {**music_settings, "sha256": sha256_file(music_audio)}
            generated_rights.append(LicenseEntry(
                path="audio/music.wav", source="generated:ace-step-1.5", creator="ACE-Step 1.5",
                license="MIT", rights_basis="Generated instrumental using MIT-licensed ACE-Step 1.5 weights",
                revision=project.active_revision, sha256=music_record["sha256"],
            ))
            generated_audio_hashes = {
                path.relative_to(staging_dir).as_posix(): sha256_file(path)
                for path in (voice_audio, music_audio, staged_audio)
            }
        elif sfx_events:
            voice_audio = staged_audio.with_name("narration-voice.wav")
            shutil.copyfile(staged_audio, voice_audio)
            mix_sfx(voice_audio, sfx_events, out=staged_audio)
            generated_audio_hashes = {
                path.relative_to(staging_dir).as_posix(): sha256_file(path)
                for path in (voice_audio, staged_audio)
            }
        if provider_name == "elevenlabs":
            generated_rights.append(LicenseEntry(
                path="audio/narration.wav", source="generated:elevenlabs",
                creator=f"ElevenLabs voice {provider_identity_data.get('voice_id', 'unknown')}",
                license="ElevenLabs subscription commercial rights (operator responsibility)",
                rights_basis=(f"Model {provider_identity_data.get('model_id', 'eleven_v3')}; "
                              "the operator must ensure their subscription and voice rights permit commercial use."),
                revision=project.active_revision, sha256=sha256_file(staged_audio),
            ))
        if sfx_events:
            for entry in sfx_rights(sfx_events, project.active_revision):
                target = staging_dir / entry.path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(SFX_ROOT / Path(entry.path).name, target)
                generated_audio_hashes[entry.path] = entry.sha256
                generated_rights.append(entry)
            _write_json_atomic(staging_dir / "sfx.json", sfx_events)
            generated_audio_hashes["sfx.json"] = sha256_file(staging_dir / "sfx.json")
        if generated_rights:
            rights = LicenseLedger(entries=tuple(generated_rights))
            ledger_path = staging_dir / "license-ledger.yaml"
            write_yaml_atomic(ledger_path, rights.model_dump(mode="json"))
            ledger_hash = sha256_file(ledger_path)
            if music_settings is not None or sfx_events:
                generated_audio_hashes["license-ledger.yaml"] = ledger_hash
            if provider_name == "elevenlabs":
                generated_audio_hashes["audio/narration.wav"] = sha256_file(staged_audio)
                generated_audio_hashes["license-ledger.yaml"] = ledger_hash
            if illustration_rights:
                generated_visual_hashes = {entry.path: entry.sha256 for entry in illustration_rights}
                generated_visual_hashes["license-ledger.yaml"] = ledger_hash
        _write_json_atomic(staging_dir / "scene-timing.json", timing_record)
        visual_budget_report = validate_visual_budget(storyboard, asset_manifest)
        visual_budget_qa = visual_budget_report.model_dump(mode="json")
        storyboard = apply_visual_fallbacks(layout.artifact_root, storyboard)
        render_input = build_render_input(
            storyboard, audio_file="audio/narration.wav"
        )
        final_frame = storyboard.scenes[-1].start_frame + storyboard.scenes[-1].duration_frames
        audio_report = inspect_wav(staged_audio)
        timing_qa = audio_timing_qa(
            audio_report.duration_ms, final_frame, timing_record=timing_record
        )
        render_input_data = render_input.model_dump(mode="json")
        staged_render_input = staging_dir / RENDER_INPUT_NAME
        _write_json_atomic(staged_render_input, render_input_data)
        staged_output = staging_dir / OUTPUT_NAME
        chapter_parts: tuple[str, ...] = ()
        clip_outputs: dict[str, str] = {}
        if render_input.format_profile == "youtube_long":
            clip_outputs = render_clips(
                load_clip_scenes(layout.artifact_root, storyboard),
                storyboard,
                staging_dir,
                line_wavs=line_wavs,
                runner=runner,
                brand=clip_brand,
                revision=project.active_revision,
                sfx_events=sfx_events,
            )
            chapter_parts = render_long_form(
                render_input_path=staged_render_input,
                render_input=render_input,
                public_dir=staging_dir,
                audio=staged_audio,
                output=staged_output,
                cache_dir=layout.project_dir / CHAPTER_CACHE_DIRECTORY,
                asset_hashes=asset_hashes,
                renderer_identity=renderer_identity_data,
                runner=runner,
            )
        else:
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
                "visual_review": visual_identity(layout.artifact_root),
                "output": OUTPUT_NAME,
                "provider": provider_name,
                "asset_sha256": dict(asset_hashes),
                "render_input_sha256": canonical_json_hash(render_input_data),
                "scene_timing_sha256": sha256_file(staging_dir / "scene-timing.json"),
                "alignment_sha256": {
                    path.relative_to(staging_dir).as_posix(): sha256_file(path)
                    for path in [staging_dir / "pronunciation-qa.json",
                                 *(staging_dir / "audio/alignment").glob("*.json"),
                                 *(staging_dir / "audio/pronunciation-alignment").glob("*.json")]
                },
                "line_audio_sha256": {
                    path.relative_to(staging_dir).as_posix(): sha256_file(path)
                    for path in line_wavs.values()
                },
                "pronunciation_version": pronunciation.version,
                "pronunciation_sha256": pronunciation_sha256,
                "provider_identity": provider_identity_data,
                "renderer_identity": renderer_identity_data,
                "music": music_record,
                "sfx": sfx_events,
                "generated_audio_sha256": generated_audio_hashes,
                "generated_visual_sha256": generated_visual_hashes,
                **({"chapter_parts": list(chapter_parts)} if chapter_parts else {}),
                **({"clips": clip_outputs} if clip_outputs else {}),
                **({"clip_artifact_sha256": {
                    path.relative_to(staging_dir).as_posix(): sha256_file(path)
                    for clip_id in clip_outputs
                    for path in (
                        staging_dir / f"audio/clips/{clip_id}.wav",
                        staging_dir / f"clips/{clip_id}.render-input.json",
                        staging_dir / f"clips/{clip_id}.scene-timing.json",
                        staging_dir / f"clips/{clip_id}.video-qa.json",
                    )
                }} if clip_outputs else {}),
            },
        )
        _write_json_atomic(
            staging_dir / "video-qa.json",
            {
                "schema_version": "2.0",
                "status": "failed" if pronunciation_report.get("blocked") else "render_complete",
                "input_hash": input_hash,
                "checks": {"output_exists": True},
                "pronunciation": {
                    "passed": not pronunciation_report.get("blocked", False),
                    "blocking_count": sum(flag.get("severity") == "block"
                                          for flag in pronunciation_report["flags"]),
                    "report_sha256": sha256_file(staging_dir / "pronunciation-qa.json"),
                },
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
            renderer_identity=renderer_identity_data,
            music_settings=music_settings,
            require_timing=require_timing,
            final_frame=final_frame,
            expected_visual_budget=visual_budget_qa,
        )
        _promote_run(staging_dir, renders_dir)
        if not review_complete(layout.artifact_root):
            prepare_contact_sheet(layout.artifact_root)
        elif (layout.artifact_root / CANDIDATES).is_file():
            prepare_contact_sheet(layout.artifact_root, final=True)
        render_optional_thumbnail(layout.artifact_root, runner=runner)
        _promote_v2_video_qa_if_needed(
            layout.artifact_root,
            input_hash,
            require_timing=require_timing,
            final_frame=final_frame,
            expected_visual_budget=visual_budget_qa,
        )
        write_yaml_atomic(
            layout.project_dir / "project.yaml",
            _production_project(layout, project, input_hash, hold=hold).model_dump(mode="json"),
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
    renderer_identity: Mapping[str, str],
    music_settings: Mapping[str, Any] | None = None,
    require_timing: bool = True,
    final_frame: int | None = None,
    expected_visual_budget: Mapping[str, Any] | None = None,
) -> bool:
    required_paths = (
        run_dir / "audio" / "narration.wav",
        run_dir / RENDER_INPUT_NAME,
        run_dir / OUTPUT_NAME,
        run_dir / V2_RENDER_MANIFEST_NAME,
        run_dir / "scene-timing.json",
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
        and manifest.get("renderer_identity") == dict(renderer_identity)
        and manifest.get("scene_timing_sha256") == sha256_file(run_dir / "scene-timing.json")
        and manifest.get("render_input_sha256")
        == canonical_json_hash(render_input)
    ):
        return False
    alignment_hashes = manifest.get("alignment_sha256", {})
    if not isinstance(alignment_hashes, dict) or not all(
        (run_dir / relative).is_file() and sha256_file(run_dir / relative) == digest
        for relative, digest in alignment_hashes.items()
    ):
        return False
    line_hashes = manifest.get("line_audio_sha256")
    music_record = manifest.get("music")
    if music_settings is None:
        if music_record is not None:
            return False
    elif not isinstance(music_record, dict) or {
        key: value for key, value in music_record.items() if key != "sha256"
    } != dict(music_settings):
        return False
    generated_hashes = manifest.get("generated_audio_sha256", {})
    if provider_name == "elevenlabs" and (
        not isinstance(generated_hashes, dict)
        or not {"audio/narration.wav", "license-ledger.yaml"}.issubset(generated_hashes)
        or not all((run_dir / relative).is_file()
                   and sha256_file(run_dir / relative) == digest
                   for relative, digest in generated_hashes.items())
    ):
        return False
    generated_visual_hashes = manifest.get("generated_visual_sha256", {})
    if not isinstance(generated_visual_hashes, dict) or not all(
        (run_dir / relative).is_file() and sha256_file(run_dir / relative) == digest
        for relative, digest in generated_visual_hashes.items()
    ):
        return False
    illustration_paths = {
        relative for relative in asset_hashes if relative.startswith("assets/illustrations/")
    }
    if illustration_paths and (
        set(generated_visual_hashes) != illustration_paths | {"license-ledger.yaml"}
        or any(generated_visual_hashes[path] != asset_hashes[path] for path in illustration_paths)
    ):
        return False
    if manifest.get("music") is not None or manifest.get("sfx"):
        required_audio = {"audio/narration-voice.wav", "audio/narration.wav", "license-ledger.yaml"}
        if manifest.get("music") is not None:
            required_audio.add("audio/music.wav")
        if manifest.get("sfx"):
            required_audio.add("sfx.json")
        if not isinstance(generated_hashes, dict) or not required_audio.issubset(generated_hashes):
            return False
        if not all(
            (run_dir / relative).is_file() and sha256_file(run_dir / relative) == digest
            for relative, digest in generated_hashes.items()
        ):
            return False
        if manifest.get("music") and manifest["music"].get("sha256") != generated_hashes["audio/music.wav"]:
            return False
    if not isinstance(line_hashes, dict) or not line_hashes or not all(
        (run_dir / relative).is_file() and sha256_file(run_dir / relative) == expected
        for relative, expected in line_hashes.items()
    ):
        return False
    if not all(
        (run_dir / relative).is_file() for relative in manifest.get("clips", {}).values()
    ):
        return False
    if manifest.get("clips"):
        clip_hashes = manifest.get("clip_artifact_sha256", {})
        if not clip_hashes or not all(
            (run_dir / relative).is_file() and sha256_file(run_dir / relative) == expected
            for relative, expected in clip_hashes.items()
        ):
            return False
        if not all(_clip_qa_is_valid(run_dir, clip_id) for clip_id in manifest["clips"]):
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
    renderer_identity: Mapping[str, str],
    music_settings: Mapping[str, Any] | None = None,
    require_timing: bool = True,
    final_frame: int | None = None,
    expected_visual_budget: Mapping[str, Any] | None = None,
) -> None:
    if not _v2_run_is_valid(
        staging_dir, input_hash, provider_name, asset_hashes,
        pronunciation_sha256=pronunciation_sha256,
        provider_identity=provider_identity,
        renderer_identity=renderer_identity,
        music_settings=music_settings,
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
    require_timing: bool = True,
    final_frame: int | None = None,
    expected_visual_budget: Mapping[str, Any] | None = None,
) -> None:
    _promote_pronunciation_qa(revision_root, input_hash)
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
    require_timing: bool = True,
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
        timing_record = json.loads((run_dir / "scene-timing.json").read_text(encoding="utf-8"))
        if timing_record.get("intentional_tail_frames", 0) != 0:
            return False
        expected = audio_timing_qa(measured_ms, final_frame, timing_record=timing_record)
        drift_ms = data["max_scene_drift_ms"]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return (
        all(
            type(value) is int and value >= 0
            for value in (audio_ms, composition_ms, trailing_ms, drift_ms)
        )
        and {key: data[key] for key in expected} == expected
    )


def _clip_qa_is_valid(run_dir: Path, clip_id: str) -> bool:
    try:
        render_input = json.loads(
            (run_dir / f"clips/{clip_id}.render-input.json").read_text(encoding="utf-8")
        )
        timing = json.loads(
            (run_dir / f"clips/{clip_id}.scene-timing.json").read_text(encoding="utf-8")
        )
        scenes = render_input["scenes"]
        end = scenes[-1]["start_frame"] + scenes[-1]["duration_frames"]
        frames = end + render_input["youtube_cta"]["duration_frames"]
        if not 1800 <= frames <= 5400 or timing.get("intentional_tail_frames") != 90:
            return False
        expected_alignment = [
            (scene["id"], round(scene["start_frame"] * 1000 / 30)) for scene in scenes
        ] + [(f"{clip_id}-CTA", round(end * 1000 / 30))]
        if [(row["scene_id"], row["video_start_ms"]) for row in timing["audio_alignment"]] != expected_alignment:
            return False
        measured = inspect_wav(run_dir / f"audio/clips/{clip_id}.wav").duration_ms
        expected = audio_timing_qa(measured, frames, timing_record=timing)
        recorded = json.loads(
            (run_dir / f"clips/{clip_id}.video-qa.json").read_text(encoding="utf-8")
        )
        return canonical_json_hash(recorded) == canonical_json_hash(expected)
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return False


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


def submit_video(project_dir: Path) -> None:
    """Submit a held final render to the doctor's video gate after product review."""
    from healthvideo.workflows.product_review import mark_submitted

    layout = resolve_project_layout(project_dir)
    project = layout.manifest
    assert isinstance(project, ProjectManifestV2)
    if project.state is not WorkflowState.PRODUCTION_IN_PROGRESS:
        raise ValueError(f"submit_video cần production_in_progress, đang là {project.state.value}")
    input_hash = project.artifact_hashes.get(PRODUCTION_ARTIFACT)
    if not input_hash:
        raise ValueError("Chưa có bản dựng cuối để nộp bác sĩ.")
    _ensure_v2_medical_approval_current(layout.artifact_root)
    write_yaml_atomic(
        layout.project_dir / "project.yaml",
        _completed_v2_project(project, input_hash).model_dump(mode="json"),
    )
    mark_submitted(layout.artifact_root)


def _production_project(layout: ProjectLayout, project: ProjectManifestV2, input_hash: str,
                        *, hold: bool = False) -> ProjectManifestV2:
    if review_complete(layout.artifact_root) and not hold:
        return _completed_v2_project(project, input_hash)
    if review_complete(layout.artifact_root):
        from healthvideo.workflows.product_review import hold as hold_for_review

        hold_for_review(layout.artifact_root, input_hash)
    # No approval transition: Python rendered candidates or the final cut and now awaits
    # agent judgement.
    producing = project
    if project.state is WorkflowState.MEDICALLY_APPROVED:
        producing = transition_v2(project, WorkflowState.PRODUCTION_IN_PROGRESS,
                                  TransitionContext(active_revision=project.active_revision,
                                                    current_input_hash=input_hash,
                                                    validated_artifacts=frozenset({MEDICAL_APPROVAL_ARTIFACT})))
    return producing.model_copy(update={'artifact_hashes': {
        **producing.artifact_hashes, PRODUCTION_ARTIFACT: input_hash,
    }})


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
    renderer: Mapping[str, str],
) -> str:
    payload = {
        "author_profile": dict(author_profile),
        "provider": provider_name,
        "script": script.model_dump(mode="json"),
        "storyboard": storyboard.model_dump(mode="json"),
        "evidence_assets": dict(asset_hashes),
        "renderer_identity": dict(renderer),
    }
    return canonical_json_hash(payload)


def _create_staging_directory(renders_dir: Path, slug: str) -> Path:
    renders_dir.mkdir(parents=True, exist_ok=True)
    return Path(mkdtemp(prefix=f".{slug}.produce-", dir=renders_dir))


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


def _read_alignment(run_dir: Path, script: Script) -> dict[str, list[dict]]:
    result = {}
    for line in script.lines:
        path = run_dir / "audio/alignment" / f"{line.id}.json"
        if path.is_file():
            words = json.loads(path.read_text(encoding="utf-8"))
            if [word["word"] for word in words] != line.text.split():
                raise ValueError("Cached alignment differs from script")
            result[line.id] = words
    return result


def _promote_pronunciation_qa(revision_root: Path, input_hash: str) -> None:
    pronunciation_source = revision_root / "renders/pronunciation-qa.json"
    if pronunciation_source.is_file():
        pronunciation_data = json.loads(pronunciation_source.read_text(encoding="utf-8"))
        if pronunciation_data.get("input_hash") != input_hash:
            raise ValueError("Pronunciation QA does not match active render")
        _write_json_atomic(revision_root / "reviews/pronunciation-qa.json", pronunciation_data)
