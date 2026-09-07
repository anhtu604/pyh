from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from healthvideo import __version__
from healthvideo.workflows.create_project import create_project

app = typer.Typer(no_args_is_help=True)
project_app = typer.Typer(no_args_is_help=True)
app.add_typer(project_app, name="project")


@app.callback()
def main() -> None:
    """Các lệnh healthvideo."""


@app.command()
def version() -> None:
    """In phiên bản healthvideo."""
    typer.echo(__version__)


@project_app.command("new")
def new_project(
    slug: Annotated[str, typer.Argument(help="Slug dự án, ví dụ: muoi-va-huyet-ap")],
    title: Annotated[str, typer.Option("--title", help="Tiêu đề làm việc của video")],
    root: Annotated[Path | None, typer.Option("--root", help="Thư mục chứa dự án")] = None,
) -> None:
    """Tạo scaffold dự án và author brief ban đầu."""
    project_root = root or default_project_root()
    try:
        project_dir = create_project(project_root, slug, title)
    except FileExistsError as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(f"Created project: {project_dir}")


def default_project_root() -> Path:
    local_now = datetime.now().astimezone()
    return Path("projects") / local_now.strftime("%Y") / local_now.strftime("%m")
