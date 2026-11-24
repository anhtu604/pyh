"""Typer primitives for the shared /pyh operator workflow."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.storyboard import Storyboard
from healthvideo.domain.topic import TopicCard
from healthvideo.storage.files import read_yaml
from healthvideo.workflows.create_project_v2 import create_project_v2
from healthvideo.workflows.draft import (
    submit_draft,
    submit_medical_review,
    submit_script_draft,
)
from healthvideo.workflows.gate_review import snapshot_r5_assets
from healthvideo.workflows.operator import get_next_action, render_status
from healthvideo.workflows.shorts_plan import save_shorts_plan
from healthvideo.workflows.storyboard_design import submit_storyboard_design
from healthvideo.workflows.topic import select_topic
from healthvideo.workflows.voice_prep import save_voice_prep

app = typer.Typer(no_args_is_help=True)


@app.command("new")
def new(
    root: Annotated[Path, typer.Argument(help="Thư mục chứa project")],
    slug: Annotated[str, typer.Option("--slug")],
    title: Annotated[str, typer.Option("--title")],
) -> None:
    """Create a revisioned v2 project."""
    try:
        project = create_project_v2(root, slug, title, now=datetime.now().astimezone())
    except (OSError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(str(project))


@app.command("status")
def status(
    project_dir: Annotated[Path, typer.Argument(help="Thư mục project")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show the next action without changing project files."""
    try:
        if json_output:
            action = get_next_action(project_dir)
            payload = asdict(action)
            typer.echo(json.dumps(payload, ensure_ascii=False, default=str))
        else:
            typer.echo(render_status(project_dir))
    except (OSError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error


@app.command("select")
def select(
    project_dir: Annotated[Path, typer.Argument(help="Thư mục project")],
    file: Annotated[Path, typer.Option("--file", help="Topic card YAML")],
) -> None:
    """Select a validated topic card for the active revision."""
    try:
        card = TopicCard.model_validate(read_yaml(file))
        changed = select_topic(project_dir, card)
    except (OSError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(changed.state.value)


@app.command("draft")
def draft(
    project_dir: Annotated[Path, typer.Argument(help="Thư mục project")],
    script: Annotated[Path, typer.Option("--script", help="Script YAML đã soạn")],
    storyboard: Annotated[Path, typer.Option("--storyboard", help="Storyboard YAML đã soạn")],
    assets: Annotated[Path, typer.Option("--assets", help="Asset manifest YAML")],
) -> None:
    """Validate and submit authored draft artifacts for a v2 project."""
    try:
        changed = submit_draft(project_dir, script, storyboard, assets)
    except (OSError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    style_path = (
        project_dir / "revisions" / changed.active_revision / "reviews/style-lint.json"
    )
    if style_path.is_file():
        style_data = read_yaml(style_path)
        issues = style_data.get("issues", []) if isinstance(style_data, dict) else []
        for item in issues:
            if isinstance(item, dict) and item.get("severity") == "warn":
                typer.echo(
                    f"warn [{item.get('line_id')}] ({item.get('rule')}): "
                    f"{item.get('excerpt')}"
                )
    typer.echo(changed.state.value)


@app.command("submit-medical")
def submit_medical(
    project_dir: Annotated[Path, typer.Argument(help="Thư mục project")],
) -> None:
    """Submit a validated draft to the doctor's medical review gate."""
    try:
        manifest_path = project_dir / "project.yaml"
        if manifest_path.is_file():
            manifest = ProjectManifestV2.model_validate(read_yaml(manifest_path))
            if manifest.state is WorkflowState.DRAFT_READY:
                revision_root = project_dir / "revisions" / manifest.active_revision
                board_path = revision_root / "storyboard/storyboard.yaml"
                if board_path.is_file():
                    board = Storyboard.model_validate(read_yaml(board_path))
                    if board.quality_profile == "r5_v1":
                        snapshot_r5_assets(revision_root, board)
        changed = submit_medical_review(project_dir)
    except (OSError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(changed.state.value)


@app.command("draft-script")
def draft_script(
    project_dir: Annotated[Path, typer.Argument(help="Thư mục project")],
    script: Annotated[Path, typer.Option("--script", help="Script YAML đã soạn")],
    outline: Annotated[Path | None, typer.Option("--outline", help="Outline YAML (nếu youtube_long)")] = None,
) -> None:
    """Validate and submit only script.yaml (+ optional outline.yaml) before visual/voice fan-out."""
    try:
        changed = submit_script_draft(project_dir, script, outline_file=outline)
    except (OSError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(changed.state.value)


@app.command("storyboard")
def storyboard(
    project_dir: Annotated[Path, typer.Argument(help="Thư mục project")],
    storyboard_file: Annotated[Path, typer.Option("--storyboard", help="Storyboard YAML")],
    assets: Annotated[Path, typer.Option("--assets", help="Asset manifest YAML")],
    clip_plan: Annotated[Path | None, typer.Option("--clip-plan", help="Clip plan YAML")] = None,
    outline: Annotated[Path | None, typer.Option("--outline", help="Outline YAML")] = None,
) -> None:
    """Validate and save storyboard/asset-manifest/(clip-plan) for active revision."""
    try:
        changed = submit_storyboard_design(
            project_dir,
            storyboard_file,
            assets,
            clip_plan_file=clip_plan,
            outline_file=outline,
        )
    except (OSError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(changed.state.value)


@app.command("voice-prep")
def voice_prep(
    project_dir: Annotated[Path, typer.Argument(help="Thư mục project")],
    file: Annotated[Path, typer.Option("--file", help="VoicePrepSheet YAML")],
) -> None:
    """Validate and save pre-TTS pronunciation sheet (script/voice-prep.yaml)."""
    try:
        saved = save_voice_prep(project_dir, file)
    except (OSError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(str(saved))


@app.command("shorts-plan")
def shorts_plan(
    project_dir: Annotated[Path, typer.Argument(help="Thư mục project")],
    file: Annotated[Path, typer.Option("--file", help="ShortsPlan YAML")],
) -> None:
    """Validate and save vertical 9:16 Shorts plan (posts/shorts-plan.yaml)."""
    try:
        saved = save_shorts_plan(project_dir, file)
    except (OSError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(str(saved))
