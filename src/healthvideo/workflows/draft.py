"""Validate an agent-authored v2 draft and submit it to the medical gate."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from tempfile import mkdtemp

from healthvideo.assets import referenced_storyboard_assets
from healthvideo.domain.asset_manifest import (
    AssetManifest,
    validate_asset_manifest,
)
from healthvideo.domain.clip_plan import (
    ClipPlan,
    validate_clip_plan,
    validate_clip_script,
)
from healthvideo.domain.evidence import EvidenceClaim
from healthvideo.domain.hook_outro import validate_hook_outro
from healthvideo.domain.long_form import long_form_scenes
from healthvideo.domain.mascot_usage import lint_mascot_usage
from healthvideo.domain.outline import Outline
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.script import Script
from healthvideo.domain.script_style import StyleIssue, lint_script_style
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.domain.storyboard import Storyboard, validate_anatomy_subjects
from healthvideo.domain.visual_budget import validate_visual_budget
from healthvideo.qa.script import review_script
from healthvideo.storage.explainer import read_explainer
from healthvideo.storage.files import (
    canonical_json_hash,
    read_agent_yaml,
    read_yaml,
    replace_directory_atomic,
    write_text_atomic,
    write_yaml_atomic,
)
from healthvideo.workflows.citations import resolve_citations


def validate_estimated_layout(
    project_dir: Path, script: Script, storyboard: Storyboard,
    assets: AssetManifest | None = None, *, clip_plan: ClipPlan | None = None,
    claims: dict[str, EvidenceClaim] | None = None,
) -> Storyboard:
    """Pre-gate timing check; source artifacts stay immutable, draft audio may be cached."""
    from healthvideo.render.beats import resolve_scene_beats, visual_rhythm_qa
    from healthvideo.render.timing import (
        calibrated_rate,
        estimate_line_ms,
        retime_storyboard,
    )
    from healthvideo.render.word_timing import entrance_timing_qa

    measured = None
    # The draft voice is another speaker; once the published voice has receipts its rate wins.
    if storyboard.quality_profile == 'r5_v1' and calibrated_rate(project_dir, script.language) is None:
        from healthvideo.workflows.voice_preview import draft_line_ms

        measured = draft_line_ms(project_dir, script)
    line_ms = measured if measured is not None else estimate_line_ms(script, project_dir)
    timed, _ = retime_storyboard(storyboard, line_ms)
    errors: list[str] = []
    if storyboard.quality_profile == 'r5_v1':
        from healthvideo.domain.quality_standards import validate_r5_contract
        from healthvideo.render.quality import (
            R5RuntimeStoryboard,
            measure_r5_quality,
            resolve_r5_shots,
            validate_r5_quality,
        )

        timed = R5RuntimeStoryboard.model_validate({**timed.model_dump(), 'estimated': True})
        try:
            validate_r5_contract(timed, script)
        except ValueError as error:
            errors.append(f'{error}; owner=storyboard_director')
        report = measure_r5_quality(timed)
        try:
            validate_r5_quality(report, estimated=True)
        except ValueError as error:
            errors.append(str(error))
        # Estimates miss the real voice by up to ~10% per line: per-shot rhythm must hold at
        # both speeds. Whole-video medians average that error out, so they stay nominal.
        seen = set(report.issues)
        for factor in (0.9, 1.1):
            scaled, _ = retime_storyboard(storyboard, {k: round(v * factor) for k, v in line_ms.items()})
            scaled = R5RuntimeStoryboard.model_validate({**scaled.model_dump(), 'estimated': True})
            extra = [i for i in measure_r5_quality(scaled).issues if i not in seen]
            seen.update(extra)
            if extra:
                errors.append('R5 rhythm fails if the real voice is 10% faster/slower '
                              '(giọng thật nhanh/chậm 10%): keep each step 3.3-5.4s:\n' + '\n'.join(extra))
        if not report.issues:
            try:
                timed = resolve_r5_shots(timed)
            except ValueError as error:
                errors.append(str(error))
    try:
        validate_visual_budget(timed, assets, margin_percent=1)
    except ValueError as error:
        errors.append(str(error) + '; scenes: ' + ', '.join(
            f'{s.id}={s.duration_frames} frames ({s.visual})' for s in timed.scenes))
    for scene in timed.scenes:
        if storyboard.quality_profile == 'r5_v1':
            continue  # Same frame measurement above is reused after TTS.
        try:
            resolved = resolve_scene_beats(scene)
            entrance_timing_qa(resolved)
            visual_rhythm_qa(resolved)
        except ValueError as error:
            errors.append(f'{error}; scene duration={scene.duration_frames} frames; '
                          f'entrances={[e.start_frame for e in scene.entrances]}')
    revision = project_dir / 'revisions' / _project(project_dir).active_revision if (
        project_dir / 'project.yaml').is_file() else None
    used_assets = {path for scene in timed.scenes for shot in scene.shots for path in shot.asset_paths}
    if storyboard.quality_profile == 'r5_v1' and used_assets and revision is not None:
        # submit_medical snapshots only catalogued assets; fail here with a fix the agent can apply.
        from healthvideo.visuals.medanim_assets import load_asset_catalog

        catalog = revision / 'assets/r5/catalog.yaml'
        known = {record.file for record in load_asset_catalog(catalog)} if catalog.is_file() else set()
        # Name every scene: storyboard parts reopen only scenes the error mentions.
        for scene in timed.scenes:
            for shot in scene.shots:
                for path in shot.asset_paths:
                    if path not in known:
                        errors.append(f'Scene {scene.id} shot {shot.id}: R5 asset_path {path} is not registered '
                                      'in assets/r5/catalog.yaml (stage licensed assets with `healthvideo step '
                                      'stage-r5-assets`, or drop asset_paths and use the scene mascot for '
                                      'StoryShot); owner=storyboard_director')
    if timed.format_profile == 'youtube_long':
        if clip_plan is None:
            if revision is None or not (revision / 'script/clip-plan.yaml').is_file():
                # The storyboard director writes it in storyboard_design; say so instead of crashing.
                raise ValueError('Estimated layout precheck failed:\n' + '\n'.join([*errors,
                    ('youtube_long requires script/clip-plan.yaml written in storyboard_design; '
                     'owner=storyboard_director')]))
            clip_plan = ClipPlan.model_validate(read_yaml(revision / 'script/clip-plan.yaml'))
        if claims is None:
            ledger = read_yaml(revision / 'evidence/ledger.yaml') if revision else {}
            claims = {item.id: item for item in (
                EvidenceClaim.model_validate(data) for data in ledger.get('claims', []))}
        for clip in clip_plan.clips:
            try:
                validate_clip_plan(ClipPlan(clips=(clip,)), timed, claims,
                                   min_frames=1980, max_frames=4860, script=script)
            except ValueError as error:
                errors.append(str(error))
    if errors:
        raise ValueError('Estimated layout precheck failed:\n' + '\n'.join(errors))
    return timed


def _project(project_dir: Path) -> ProjectManifestV2:
    data = read_yaml(project_dir / "project.yaml")
    if data.get("schema_version") != "2.0":
        raise ValueError("draft submission requires project schema 2.0")
    return ProjectManifestV2.model_validate(data)


def _validate(
    revision: Path,
    script: Script,
    storyboard: Storyboard,
    assets: AssetManifest,
    *,
    project: ProjectManifestV2,
) -> list[StyleIssue]:
    _ = project
    ledger = read_yaml(revision / "evidence/ledger.yaml")
    if not script.lines or not storyboard.scenes:
        raise ValueError("draft requires nonempty script lines and storyboard scenes")
    validate_clip_script(script, storyboard)
    claims = [EvidenceClaim.model_validate(item) for item in ledger.get("claims", [])]
    if script.format_profile != "explain_first_v1":
        raise ValueError(
            "explain_first_v1 project requires script format_profile explain_first_v1"
        )
    if not (revision / "explainer/explainer.yaml").is_file():
        raise ValueError("explain_first_v1 requires explainer/explainer.yaml")
    explainer = read_explainer(revision)
    layers = {layer.id: layer for layer in explainer.layers}
    for scene in storyboard.scenes:
        if scene.explainer_layer_id is None:
            continue
        layer = layers.get(scene.explainer_layer_id)
        if layer is None:
            raise ValueError(
                f"Scene {scene.id}: unknown explainer layer {scene.explainer_layer_id}"
            )
        if scene.visual != layer.visual.kind:
            raise ValueError(
                f"Scene {scene.id}: visual must match explainer layer "
                f"{layer.id}: {layer.visual.kind}"
            )
    issues = review_script(script, claims, [], explainer=explainer)
    blocking = [issue for issue in issues if issue.code == "unknown_claim"]
    if blocking:
        raise ValueError("script references unknown claim: " + blocking[0].message)
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        raise ValueError(f"script review error ({errors[0].code}): {errors[0].message}")
    style_issues = lint_script_style(script)
    style_blocks = [issue for issue in style_issues if issue.severity == "block"]
    if style_blocks:
        details = "; ".join(
            f"{issue.line_id} ({issue.rule}): {issue.excerpt}"
            for issue in style_blocks
        )
        raise ValueError(f"script style block: {details}")
    validate_visual_budget(storyboard, assets)
    validate_anatomy_subjects(storyboard)
    from healthvideo.render.beats import draft_visual_rhythm_qa

    if storyboard.quality_profile == 'r5_v1':
        validate_estimated_layout(revision.parents[1], script, storyboard, assets)
    else:
        draft_visual_rhythm_qa(long_form_scenes(storyboard))
    validate_hook_outro(script, storyboard, require_brand=True, allow_line_references=True)
    resolve_citations(
        script,
        ledger,
        storyboard.scenes,
        strict_line_ids=script.format_profile == "hook_outro_v1",
    )
    validate_asset_manifest(revision, assets)
    referenced_storyboard_assets(revision, storyboard, assets)
    style_issues.extend(lint_mascot_usage(storyboard))
    return style_issues


def submit_script_draft(
    project_dir: Path,
    script_file: Path,
    *,
    outline_file: Path | None = None,
) -> ProjectManifestV2:
    """Validate and submit only script.yaml (+ optional outline.yaml) so visual/voice prep can fan out."""
    project = _project(project_dir)
    if project.state not in {
        WorkflowState.EVIDENCE_READY,
        WorkflowState.DRAFT_READY,
        WorkflowState.NEEDS_MEDICAL_REVISION,
    }:
        raise ValueError(
            "script draft submission requires evidence_ready, draft_ready, or needs_medical_revision"
        )
    script = Script.model_validate(read_agent_yaml(script_file))
    if not script.lines:
        raise ValueError("draft requires nonempty script lines")
    if script.format_profile != "explain_first_v1":
        raise ValueError(
            "explain_first_v1 project requires script format_profile explain_first_v1"
        )
    revision = project_dir / "revisions" / project.active_revision
    if not (revision / "explainer/explainer.yaml").is_file():
        raise ValueError("explain_first_v1 requires explainer/explainer.yaml")
    outline = Outline.model_validate(read_agent_yaml(outline_file)) if outline_file else None
    staging = Path(mkdtemp(prefix=f".{revision.name}.script-", dir=revision.parent))
    promoted = False
    try:
        shutil.copytree(revision, staging, dirs_exist_ok=True)
        write_yaml_atomic(staging / "script/script.yaml", script.model_dump(mode="json"))
        if outline is not None:
            write_yaml_atomic(
                staging / "script/outline.yaml", outline.model_dump(mode="json")
            )
        ledger = read_yaml(staging / "evidence/ledger.yaml")
        claims = [EvidenceClaim.model_validate(item) for item in ledger.get("claims", [])]
        claim_ids = {claim.id for claim in claims}
        if outline is not None:
            for chapter in outline.chapters:
                unknown = [cid for cid in chapter.claim_ids if cid not in claim_ids]
                if unknown:
                    raise ValueError(
                        f"outline chapter {chapter.id} references unknown claim: {unknown[0]}"
                    )
        explainer = read_explainer(staging)
        issues = review_script(script, claims, [], explainer=explainer)
        blocking = [issue for issue in issues if issue.code == "unknown_claim"]
        if blocking:
            raise ValueError("script references unknown claim: " + blocking[0].message)
        errors = [issue for issue in issues if issue.severity == "error"]
        if errors:
            raise ValueError(f"script review error ({errors[0].code}): {errors[0].message}")
        style_issues = lint_script_style(script)
        style_blocks = [issue for issue in style_issues if issue.severity == "block"]
        if style_blocks:
            details = "; ".join(
                f"{issue.line_id} ({issue.rule}): {issue.excerpt}"
                for issue in style_blocks
            )
            raise ValueError(f"script style block: {details}")
        write_text_atomic(
            staging / "reviews/style-lint.json",
            json.dumps(
                {"issues": [issue.to_dict() for issue in style_issues]},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
        script_data = read_yaml(staging / "script/script.yaml")
        context = TransitionContext(
            active_revision=project.active_revision,
            current_input_hash=canonical_json_hash(script_data),
            validated_artifacts=frozenset({"script/script.yaml"}),
        )
        changed = (
            transition_v2(project, WorkflowState.DRAFT_READY, context)
            if project.state is WorkflowState.EVIDENCE_READY
            else project
        )
        replace_directory_atomic(staging, revision)
        promoted = True
        if changed != project:
            write_yaml_atomic(project_dir / "project.yaml", changed.model_dump(mode="json"))
        return changed
    finally:
        if not promoted and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def submit_draft(
    project_dir: Path,
    script_file: Path,
    storyboard_file: Path,
    assets_file: Path,
) -> ProjectManifestV2:
    """Promote a complete validated draft without leaving partial revision files."""
    project = _project(project_dir)
    if project.state not in {WorkflowState.EVIDENCE_READY, WorkflowState.DRAFT_READY}:
        raise ValueError("draft submission requires evidence_ready or draft_ready")
    script = Script.model_validate(read_agent_yaml(script_file))
    storyboard = Storyboard.model_validate(read_agent_yaml(storyboard_file))
    assets = AssetManifest.model_validate(read_agent_yaml(assets_file))
    revision = project_dir / "revisions" / project.active_revision
    staging = Path(mkdtemp(prefix=f".{revision.name}.draft-", dir=revision.parent))
    promoted = False
    try:
        shutil.copytree(revision, staging, dirs_exist_ok=True)
        write_yaml_atomic(staging / "script/script.yaml", script.model_dump(mode="json"))
        write_yaml_atomic(
            staging / "storyboard/storyboard.yaml", storyboard.model_dump(mode="json")
        )
        write_yaml_atomic(
            staging / "assets/asset-manifest.yaml", assets.model_dump(mode="json")
        )
        style_issues = _validate(staging, script, storyboard, assets, project=project)
        write_text_atomic(
            staging / "reviews/style-lint.json",
            json.dumps(
                {"issues": [issue.to_dict() for issue in style_issues]},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
        script_data = read_yaml(staging / "script/script.yaml")
        context = TransitionContext(
            active_revision=project.active_revision,
            current_input_hash=canonical_json_hash(script_data),
            validated_artifacts=frozenset({"script/script.yaml"}),
        )
        changed = (
            transition_v2(project, WorkflowState.DRAFT_READY, context)
            if project.state is WorkflowState.EVIDENCE_READY
            else project
        )
        replace_directory_atomic(staging, revision)
        promoted = True
        write_yaml_atomic(project_dir / "project.yaml", changed.model_dump(mode="json"))
        return changed
    finally:
        if not promoted and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def submit_medical_review(project_dir: Path) -> ProjectManifestV2:
    """Enter medical review after revalidating the active draft, without approval."""
    project = _project(project_dir)
    if project.state is not WorkflowState.DRAFT_READY:
        raise ValueError("medical submission requires draft_ready")
    from healthvideo.workflows.script_review import require_passed_review

    require_passed_review(project_dir)
    revision = project_dir / "revisions" / project.active_revision
    script_data = read_yaml(revision / "script/script.yaml")
    script = Script.model_validate(script_data)
    storyboard = Storyboard.model_validate(read_yaml(revision / "storyboard/storyboard.yaml"))
    assets = AssetManifest.model_validate(read_yaml(revision / "assets/asset-manifest.yaml"))
    validate_estimated_layout(project_dir, script, storyboard, assets)
    _validate(revision, script, storyboard, assets, project=project)
    if storyboard.quality_profile == "r5_v1":
        # Every submit path (CLI or factory) pins the R5 used-asset snapshot the gate reviews.
        from healthvideo.workflows.gate_review import snapshot_r5_assets

        snapshot_r5_assets(revision, storyboard)
    context = TransitionContext(
        active_revision=project.active_revision,
        current_input_hash=canonical_json_hash(script_data),
        validated_artifacts=frozenset(
            {"script/script.yaml", "storyboard/storyboard.yaml", "assets/asset-manifest.yaml"}
        ),
    )
    changed = transition_v2(project, WorkflowState.AWAITING_MEDICAL_REVIEW, context)
    write_yaml_atomic(project_dir / "project.yaml", changed.model_dump(mode="json"))
    from healthvideo.workflows.script_review import mark_submitted

    mark_submitted(revision)
    return changed
