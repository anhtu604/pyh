import subprocess
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from healthvideo import __version__
from healthvideo.render.remotion import build_render_argv
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.create_project import create_project
from healthvideo.workflows.produce import produce_project

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


@app.command()
def produce(
    project_dir: Annotated[
        Path, typer.Argument(help="Thư mục dự án đã duyệt kịch bản")
    ],
    tts: Annotated[str, typer.Option("--tts", help="Nhà cung cấp TTS")] = "silent",
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", help="In lệnh render, không ghi artifact hoặc đổi state"
        ),
    ] = False,
) -> None:
    """Tạo video từ script/storyboard đã duyệt y khoa."""
    if tts != "silent":
        typer.echo(f"Unsupported TTS provider: {tts}")
        raise typer.Exit(code=1)

    def run_remotion(argv: list[str]) -> int:
        return subprocess.run(argv, check=False).returncode

    try:
        output = produce_project(
            project_dir, SilentTTS(), run_remotion, dry_run=dry_run
        )
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    if dry_run:
        typer.echo(
            " ".join(
                build_render_argv(
                    output.parent / "render-input.json", output, output.parent
                )
            )
        )
        return
    typer.echo(f"Rendered video: {output}")


@project_app.command("new")
def new_project(
    slug: Annotated[str, typer.Argument(help="Slug dự án, ví dụ: muoi-va-huyet-ap")],
    title: Annotated[str, typer.Option("--title", help="Tiêu đề làm việc của video")],
    root: Annotated[
        Path | None, typer.Option("--root", help="Thư mục chứa dự án")
    ] = None,
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
