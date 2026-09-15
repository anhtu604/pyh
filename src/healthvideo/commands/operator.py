"""Typer primitives for the shared /pyh operator workflow."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from healthvideo.domain.author import AuthorBrief
from healthvideo.domain.topic import TopicCard
from healthvideo.storage.files import read_yaml
from healthvideo.storage.lease import read_write_lease
from healthvideo.workflows.author import save_author_brief
from healthvideo.workflows.create_project_v2 import create_project_v2
from healthvideo.workflows.operations import project_mutation
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
            lease = read_write_lease(project_dir)
            payload["busy"] = lease is not None
            payload["writer"] = (
                {"host_id": lease.host_id, "pid": lease.pid, "operation": lease.operation}
                if lease is not None
                else None
            )
            typer.echo(json.dumps(payload, ensure_ascii=False, default=str))
        else:
            typer.echo(render_status(project_dir))
    except (OSError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error


@app.command("select")
@project_mutation("operator_select")
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


@app.command("brief")
@project_mutation("operator_brief")
def brief(
    project_dir: Annotated[Path, typer.Argument(help="Thư mục project")],
    title: Annotated[str, typer.Option("--title")],
    why_speak: Annotated[str, typer.Option("--why-speak")] = "",
    personal_position: Annotated[str, typer.Option("--personal-position")] = "",
    desired_audience_action: Annotated[str, typer.Option("--desired-audience-action")] = "",
    confirm: Annotated[bool, typer.Option("--confirm")] = False,
) -> None:
    """Save the doctor's brief; only --confirm advances its state."""
    try:
        changed = save_author_brief(
            project_dir,
            AuthorBrief(
                title=title,
                why_speak=why_speak,
                personal_position=personal_position,
                desired_audience_action=desired_audience_action,
            ),
            confirm=confirm,
            now=datetime.now().astimezone(),
        )
    except (OSError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(changed.state.value)
