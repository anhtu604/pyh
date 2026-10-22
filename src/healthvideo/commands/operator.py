"""Typer primitives for the shared /pyh operator workflow."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from healthvideo.domain.topic import TopicCard
from healthvideo.storage.files import read_yaml
from healthvideo.workflows.create_project_v2 import create_project_v2
from healthvideo.workflows.draft import submit_draft, submit_medical_review
from healthvideo.workflows.operator import get_next_action, render_status
from healthvideo.workflows.topic import select_topic

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
    typer.echo(changed.state.value)


@app.command("submit-medical")
def submit_medical(
    project_dir: Annotated[Path, typer.Argument(help="Thư mục project")],
) -> None:
    """Submit a validated draft to the doctor's medical review gate."""
    try:
        changed = submit_medical_review(project_dir)
    except (OSError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(changed.state.value)
