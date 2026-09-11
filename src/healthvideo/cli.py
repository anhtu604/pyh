import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer

from healthvideo import __version__
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project import ProjectManifest
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.review import ReviewKind, ReviewRecord
from healthvideo.process import resolve_pnpm_argv
from healthvideo.render.remotion import build_render_argv
from healthvideo.storage.files import read_yaml, write_text_atomic
from healthvideo.storage.revisions import create_revision
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.create_project import create_project
from healthvideo.workflows.doctor import (
    check_environment,
    has_mandatory_failure,
    run_command,
)
from healthvideo.workflows.gate_review import approve_gate, reject_gate, resume_gate
from healthvideo.workflows.migrate import (
    MigrationPlan,
    migrate_project,
    plan_migration,
)
from healthvideo.workflows.package import package_project
from healthvideo.workflows.produce import produce_project
from healthvideo.workflows.review import (
    approval_is_stale,
    approve_medical,
    approve_video,
    latest_approval,
)
from healthvideo.workflows.review_html import render_medical_packet, render_video_packet

CONFIRMATION = "APPROVE"
app = typer.Typer(no_args_is_help=True)
project_app = typer.Typer(no_args_is_help=True)
review_app = typer.Typer(no_args_is_help=True)
revision_app = typer.Typer(no_args_is_help=True)
app.add_typer(project_app, name="project")
app.add_typer(review_app, name="review")
app.add_typer(revision_app, name="revision")

ProjectDir = Annotated[Path, typer.Argument(help="Thư mục dự án")]
Reviewer = Annotated[str, typer.Option("--reviewer", help="Tên bác sĩ duyệt")]
Note = Annotated[str, typer.Option("--note", help="Ghi chú của người duyệt")]
SkipConfirmation = Annotated[
    bool, typer.Option("--yes", help=f"Bỏ qua xác nhận gõ {CONFIRMATION}")
]
REJECT_CONFIRMATION = "REJECT"
Gate = Annotated[GateKind, typer.Option("--gate", help="medical hoặc video")]
Reason = Annotated[str, typer.Option("--reason", help="Lý do từ chối")]
ResumeTo = Annotated[str, typer.Option("--resume-to", help="Trạng thái nối lại sau khi sửa")]
ResumeTarget = Annotated[str, typer.Option("--to", help="Trạng thái muốn quay lại")]
ReasonClass = Annotated[
    str | None,
    typer.Option("--reason-class", help='Bắt buộc là "semantic_issue" khi resume video về draft_ready'),
]

_RENDER_PACKET = {GateKind.MEDICAL: render_medical_packet, GateKind.VIDEO: render_video_packet}
_PACKET_NAME = {GateKind.MEDICAL: "medical-packet.html", GateKind.VIDEO: "video-packet.html"}


@app.callback()
def main() -> None:
    """Các lệnh healthvideo."""
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            reconfigure = getattr(stream, "reconfigure", None)
            if reconfigure is not None:
                reconfigure(encoding="utf-8")


@app.command()
def version() -> None:
    """In phiên bản healthvideo."""
    typer.echo(__version__)


@app.command()
def doctor() -> None:
    """Kiểm tra các dependency cục bộ cần để tạo video."""
    results = check_environment(run_command)
    for result in results:
        status = "OK" if result.ok else "WARN" if result.required == "optional" else "FAIL"
        typer.echo(
            f"{status} {result.name}: {result.detected} "
            f"(requires {result.required})"
        )
        if not result.ok:
            typer.echo(f"  Remedy: {result.remedy}")
    if has_mandatory_failure(results):
        raise typer.Exit(code=1)


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
        resolved = resolve_pnpm_argv(argv[1:])
        return subprocess.run(resolved, check=False, shell=False).returncode

    try:
        output = produce_project(
            project_dir, SilentTTS(), run_remotion, dry_run=dry_run
        )
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    if dry_run:
        logical = build_render_argv(
            output.parent / "render-input.json", output, output.parent
        )
        typer.echo(subprocess.list2cmdline(resolve_pnpm_argv(logical[1:])))
        return
    typer.echo(f"Rendered video: {output}")


@app.command()
def package(
    project_dir: Annotated[Path, typer.Argument(help="Thư mục dự án đã duyệt video")],
) -> None:
    """Đóng gói video đã duyệt thành thư mục publish để đăng thủ công."""
    try:
        output = package_project(project_dir)
    except (FileNotFoundError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(f"Packaged: {output}")


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


@project_app.command("migrate")
def migrate_project_command(
    project_dir: ProjectDir,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="In migration plan, không ghi dữ liệu")
    ] = False,
) -> None:
    """Migrate project v1 sang một sibling v2 mới, không sửa nguồn."""
    try:
        plan = plan_migration(project_dir)
        if dry_run:
            typer.echo(_format_migration_plan(plan))
            return
        destination = migrate_project(
            project_dir,
            now=datetime.now().astimezone(),
            migration_id=uuid4(),
        )
    except (FileNotFoundError, FileExistsError, OSError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(f"Migrated project: {destination}")


def _format_migration_plan(plan: MigrationPlan) -> str:
    lines = [
        f"Source: {plan.source}",
        f"Destination: {plan.destination}",
        f"State: {plan.source_state.value} -> {plan.proposed_state.value}",
        f"Approval: {plan.approval_disposition.value}",
        f"Destination conflict: {'yes' if plan.destination_conflict else 'no'}",
        "Files:",
    ]
    for item in plan.files:
        source = item.source.as_posix() if item.source is not None else "<derived>"
        destination = item.destination.as_posix()
        lines.append(f"  {source} -> {destination} [{plan.hashes[destination]}]")
    return "\n".join(lines)


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


@review_app.command("approve")
def review_approve(
    project_dir: ProjectDir, gate: Gate, reviewer: Reviewer, note: Note = "", yes: SkipConfirmation = False
) -> None:
    """Duyệt cổng y khoa hoặc video cho project schema 2.0."""
    if not yes:
        typed = typer.prompt(f"Gõ {CONFIRMATION} để duyệt {gate.value}")
        if typed.strip() != CONFIRMATION:
            typer.echo(f"Đã hủy: cần gõ {CONFIRMATION} để xác nhận.")
            raise typer.Exit(code=1)
    try:
        record = approve_gate(
            project_dir, gate, reviewer=reviewer, note=note, now=datetime.now().astimezone()
        )
    except (FileNotFoundError, FileExistsError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(f"Đã duyệt {gate.value}: {record.reviewed_at.isoformat()}")


@review_app.command("reject")
def review_reject(
    project_dir: ProjectDir,
    gate: Gate,
    reviewer: Reviewer,
    reason: Reason,
    resume_to: ResumeTo,
    yes: SkipConfirmation = False,
) -> None:
    """Từ chối cổng y khoa hoặc video, ghi lý do và điểm nối lại."""
    if not yes:
        typed = typer.prompt(f"Gõ {REJECT_CONFIRMATION} để từ chối {gate.value}")
        if typed.strip() != REJECT_CONFIRMATION:
            typer.echo(f"Đã hủy: cần gõ {REJECT_CONFIRMATION} để xác nhận.")
            raise typer.Exit(code=1)
    try:
        resume_state = WorkflowState(resume_to)
        reject_gate(
            project_dir,
            gate,
            reviewer=reviewer,
            reason=reason,
            resume_state=resume_state,
            now=datetime.now().astimezone(),
        )
    except (FileNotFoundError, FileExistsError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(f"Đã từ chối {gate.value}, nối lại tại {resume_state.value}")


@review_app.command("open")
def review_open(project_dir: ProjectDir, gate: Gate) -> None:
    """Render gói HTML duyệt hiện tại và in đường dẫn; không tự mở trình duyệt."""
    try:
        manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
        revision_root = project_dir / "revisions" / manifest.active_revision
        html = _RENDER_PACKET[gate](revision_root)
    except (FileNotFoundError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    packet_path = revision_root / "reviews" / _PACKET_NAME[gate]
    write_text_atomic(packet_path, html)
    typer.echo(str(packet_path))


@review_app.command("resume")
def review_resume(
    project_dir: ProjectDir, gate: Gate, to: ResumeTarget, reason_class: ReasonClass = None
) -> None:
    """Thoát needs_medical_revision/needs_production_revision về trạng thái chính."""
    try:
        target = WorkflowState(to)
        new_state = resume_gate(
            project_dir, gate, target=target, reason_code=reason_class, now=datetime.now().astimezone()
        )
    except (FileNotFoundError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(f"Trạng thái mới: {new_state.value}")


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


@revision_app.command("create")
def revision_create(
    project_dir: ProjectDir,
    reason: Annotated[str, typer.Option("--reason", help="Lý do tạo revision mới")],
) -> None:
    """Tạo một revision workflow mới, bất biến, từ revision đang active."""
    try:
        revision = create_revision(project_dir, reason, now=datetime.now().astimezone())
    except (FileNotFoundError, FileExistsError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(f"Created revision: {revision}")


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
