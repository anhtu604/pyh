import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from healthvideo import __version__
from healthvideo.domain.project import ProjectManifest
from healthvideo.domain.review import ReviewKind, ReviewRecord
from healthvideo.render.remotion import build_render_argv
from healthvideo.storage.files import read_yaml
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.create_project import create_project
from healthvideo.workflows.produce import produce_project
from healthvideo.workflows.review import (
    approval_is_stale,
    approve_medical,
    approve_video,
    latest_approval,
)

CONFIRMATION = "APPROVE"
app = typer.Typer(no_args_is_help=True)
project_app = typer.Typer(no_args_is_help=True)
review_app = typer.Typer(no_args_is_help=True)
app.add_typer(project_app, name="project")
app.add_typer(review_app, name="review")

ProjectDir = Annotated[Path, typer.Argument(help="Thư mục dự án")]
Reviewer = Annotated[str, typer.Option("--reviewer", help="Tên bác sĩ duyệt")]
Note = Annotated[str, typer.Option("--note", help="Ghi chú của người duyệt")]
SkipConfirmation = Annotated[
    bool, typer.Option("--yes", help=f"Bỏ qua xác nhận gõ {CONFIRMATION}")
]


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


@review_app.command("medical")
def review_medical(
    project_dir: ProjectDir,
    reviewer: Reviewer,
    note: Note = "",
    yes: SkipConfirmation = False,
) -> None:
    """Duyệt bằng chứng và kịch bản trước khi sản xuất."""
    _record_approval(approve_medical, "y khoa", project_dir, reviewer, note, yes=yes)


@review_app.command("video")
def review_video(
    project_dir: ProjectDir,
    reviewer: Reviewer,
    note: Note = "",
    yes: SkipConfirmation = False,
) -> None:
    """Duyệt video đã render trước khi đóng gói."""
    _record_approval(approve_video, "video", project_dir, reviewer, note, yes=yes)


@app.command()
def status(project_dir: ProjectDir) -> None:
    """In trạng thái dự án và hiệu lực của hai cổng duyệt."""
    try:
        project = ProjectManifest.model_validate(
            read_yaml(project_dir / "project.yaml")
        )
    except (FileNotFoundError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error

    stale = False
    typer.echo(f"state={project.state.value}")
    for kind in ReviewKind:
        record = latest_approval(project_dir, kind)
        if record is None:
            typer.echo(f"{kind.value}_approval=none")
            continue
        stale = stale or approval_is_stale(project_dir, project, kind)
        typer.echo(
            f"{kind.value}_approval={record.reviewer} "
            f"({record.reviewed_at.isoformat()})"
        )
    typer.echo(f"approval_stale={'true' if stale else 'false'}")


def _record_approval(
    approve: Callable[..., ReviewRecord],
    label: str,
    project_dir: Path,
    reviewer: str,
    note: str,
    *,
    yes: bool,
) -> None:
    if not yes:
        typed = typer.prompt(f"Gõ {CONFIRMATION} để duyệt {label}")
        if typed.strip() != CONFIRMATION:
            typer.echo(f"Đã hủy: cần gõ {CONFIRMATION} để xác nhận.")
            raise typer.Exit(code=1)
    try:
        record = approve(project_dir, reviewer=reviewer, note=note)
    except (FileNotFoundError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(f"Đã duyệt {label}: {record.id}")
