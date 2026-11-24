import getpass
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any

import click
import typer

from healthvideo import __version__
from healthvideo.approver_pin import PinError, pin_path, set_pin, verify_pin
from healthvideo.commands import operator
from healthvideo.discovery import reddit, trends, youtube
from healthvideo.discovery.cards import build_card, collect, write_discovered
from healthvideo.discovery.models import SourceFailure
from healthvideo.domain.evidence import (
    EvidenceClaim,
    EvidenceQuestion,
    SourceRecord,
    SourceSelection,
)
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.queue import QueueEntry, QueueError
from healthvideo.domain.state_graph import SIDE_EXIT_RULES
from healthvideo.env import hide_child_consoles, load_dotenv
from healthvideo.evidence import elsevier
from healthvideo.evidence.clients import EuropePMCClient, PubMedClient
from healthvideo.process import prepare_subprocess_argv, resolve_pnpm_argv
from healthvideo.project_codes import project_codes
from healthvideo.qa.script import lint_project_script
from healthvideo.render.remotion import build_render_argv
from healthvideo.render.run import (
    PRODUCTION_ARTIFACT,
    RENDER_INPUT_NAME,
)
from healthvideo.storage.files import read_yaml
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.storage.queue import add_to_queue, load_queue
from healthvideo.storage.revisions import create_revision
from healthvideo.tts.base import TTSProvider
from healthvideo.tts.command import CommandTTS
from healthvideo.tts.normalize import NormalizedTTS
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows import doctor_questions, factory, factory_deps
from healthvideo.workflows.doctor import (
    check_environment,
    has_mandatory_failure,
    run_command,
)
from healthvideo.workflows.evidence import (
    build_evidence_ledger,
    record_question,
    record_source_selections,
    search_literature,
)
from healthvideo.workflows.factory_deps import default_run_deps
from healthvideo.workflows.gate_review import (
    approve_gate,
    check_revision_posts,
    reject_gate,
    reopen_gate,
    resume_gate,
)
from healthvideo.workflows.hook_outro import author_hook_outro
from healthvideo.workflows.package import package_project
from healthvideo.workflows.produce import produce_project
from healthvideo.workflows.review_frames import review_frames as create_review_frames
from healthvideo.workflows.review_html import render_medical_packet, render_video_packet
from healthvideo.workflows.runner import next_step, run_queue
from healthvideo.workflows.screening import screen_candidates

CONFIRMATION = "APPROVE"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TTS_PYTHON = REPO_ROOT / "cache" / "tts-venv" / "Scripts" / "python.exe"
VIENEU_WRAPPER = REPO_ROOT / "tools" / "tts" / "vieneu_synth.py"


def build_vieneu_tts(*, python: Path, voice: str, precision: str) -> NormalizedTTS:
    """VieNeu v3 Turbo through the local wrapper, then FFmpeg loudnorm; no paths in identity."""
    voice_alias = re.sub(r"[^A-Za-z0-9._-]", "-", voice).strip("-").lower() or "voice"
    inner = CommandTTS(
        executable=str(python),
        arguments=(
            str(VIENEU_WRAPPER), "--input", "{input}", "--output", "{output}",
            "--backend", "onnx", "--voice", voice, "--precision", precision,
        ),
        model_id="vieneu-v3-turbo",
        voice_id=voice_alias,
        runtime_id=f"onnx-cpu-{precision}",
    )
    return NormalizedTTS(inner)


# Configure before Typer handles eager options such as --help, including when
# Python's UTF-8 mode is disabled on Windows. Captured streams may lack this API.
for _stream in (sys.stdout, sys.stderr):
    if callable(getattr(_stream, "reconfigure", None)):
        _stream.reconfigure(encoding="utf-8")

app = typer.Typer(no_args_is_help=True)
review_app = typer.Typer(no_args_is_help=True)
topic_app = typer.Typer(no_args_is_help=True)
project_app = typer.Typer(no_args_is_help=True, help="Thao tác chuyển đổi hoặc quản lý project.")
channel_app = typer.Typer(no_args_is_help=True, help="Chỉ số hiệu quả kênh & báo cáo phân tích.")
telegram_app = typer.Typer(no_args_is_help=True, help="Bot Telegram điều khiển Trưởng nhóm Điều phối.")
step_app = typer.Typer(no_args_is_help=True)
evidence_app = typer.Typer(no_args_is_help=True, help="Tra cứu Elsevier qua API chính thức.")
app.add_typer(review_app, name="review")
app.add_typer(topic_app, name="topic")
app.add_typer(project_app, name="project")
app.add_typer(channel_app, name="channel")
app.add_typer(telegram_app, name="telegram")
app.add_typer(step_app, name="step", hidden=True)
app.add_typer(evidence_app, name="evidence")
step_app.command("new")(operator.new)
step_app.command("select")(operator.select)
step_app.command("draft")(operator.draft)
step_app.command("draft-script")(operator.draft_script)
step_app.command("storyboard")(operator.storyboard)
step_app.command("voice-prep")(operator.voice_prep)
step_app.command("shorts-plan")(operator.shorts_plan)
step_app.command("submit-medical")(operator.submit_medical)


def _echo_error(error: BaseException) -> None:
    typer.echo("\n".join([str(error), *getattr(error, "__notes__", [])]))


@step_app.command("lint")
def script_lint(project_dir: Annotated[Path, typer.Argument(help="Thư mục dự án")]) -> None:
    """Lint the active script; warnings do not cause a failing exit status."""
    try:
        issues = lint_project_script(project_dir)
    except (OSError, TypeError, ValueError) as error:
        _echo_error(error)
        raise typer.Exit(code=1) from error
    for issue in issues:
        typer.echo(f"{issue.severity}: {issue.code} [{issue.line_id}] {issue.message}")
    if any(issue.severity == "error" for issue in issues):
        raise typer.Exit(code=1)


@step_app.command("posts-check")
def posts_check(project_dir: Annotated[Path, typer.Argument(help="Thư mục dự án")]) -> None:
    """Kiểm tra bài đăng đa kênh trong revisions/<rev>/posts/posts.yaml."""
    try:
        layout = resolve_project_layout(project_dir)
        errors = check_revision_posts(layout.artifact_root)
    except (OSError, TypeError, ValueError) as error:
        _echo_error(error)
        raise typer.Exit(code=1) from error
    for err in errors:
        typer.echo(err)
    if errors:
        raise typer.Exit(code=1)


@step_app.command("outro-author")
def outro_author(
    project_dir: Annotated[Path, typer.Argument(help="Thư mục dự án v2")],
    duration_frames: Annotated[int, typer.Option("--duration-frames", help="Số frame của câu kết")],
) -> None:
    """Thêm câu kết PYH cố định trước cổng duyệt y khoa."""
    try:
        author_hook_outro(project_dir, duration_frames=duration_frames)
    except (OSError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo("Đã chuẩn bị câu kết để duyệt y khoa.")


ProjectDir = Annotated[Path, typer.Argument(help="Thư mục dự án")]
Reviewer = Annotated[str, typer.Option("--reviewer", help="Tên bác sĩ duyệt")]
Note = Annotated[str, typer.Option("--note", help="Ghi chú của người duyệt")]
SkipConfirmation = Annotated[
    bool, typer.Option("--yes", help=f"Bỏ qua xác nhận gõ {CONFIRMATION}")
]
REJECT_CONFIRMATION = "REJECT"
REOPEN_CONFIRMATION = "REOPEN"
Gate = Annotated[GateKind, typer.Option("--gate", help="medical hoặc video")]
Reason = Annotated[str, typer.Option("--reason", help="Lý do từ chối")]
ResumeTo = Annotated[
    str,
    typer.Option(
        "--resume-to",
        help="Trạng thái nối lại sau khi sửa ("
        + "; ".join(
            f"{gate}: " + "|".join(sorted(
                target.value for source, target in SIDE_EXIT_RULES if source is side
            ))
            for gate, side in (
                ("medical", WorkflowState.NEEDS_MEDICAL_REVISION),
                ("video", WorkflowState.NEEDS_PRODUCTION_REVISION),
            )
        )
        + ")",
    ),
]
ResumeTarget = Annotated[str, typer.Option("--to", help="Trạng thái muốn quay lại")]
ReasonClass = Annotated[
    str | None,
    typer.Option(
        "--reason-class",
        help='Bắt buộc là "semantic_issue" khi resume video về draft_ready',
    ),
]

_RENDER_PACKET = {
    GateKind.MEDICAL: render_medical_packet,
    GateKind.VIDEO: render_video_packet,
}


@app.callback()
def main() -> None:
    """Các lệnh healthvideo."""
    hide_child_consoles()
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            reconfigure = getattr(stream, "reconfigure", None)
            if reconfigure is not None:
                reconfigure(encoding="utf-8")
    dotenv_path = Path.cwd() / ".env"
    if dotenv_path.is_file():
        load_dotenv(dotenv_path)


@step_app.command()
def version() -> None:
    """In phiên bản healthvideo."""
    typer.echo(__version__)


@app.command()
def notify_test() -> None:
    """Gửi một tin Telegram thử; không in thông tin bí mật."""
    from healthvideo.workflows.factory import notify

    ok = notify('Kiểm tra thông báo', 'tin thử')
    typer.echo('Telegram: thành công' if ok else 'Telegram: thất bại hoặc chưa cấu hình')
    if not ok:
        raise typer.Exit(code=1)


@app.command()
def notify_setup() -> None:
    """Hướng dẫn cấu hình Telegram, tìm chat_id; không ghi .env."""
    from healthvideo.workflows.telegram import setup

    setup(echo=typer.echo)


@app.command()
def doctor() -> None:
    """Kiểm tra dependency của toolchain local."""
    results = check_environment(run_command)
    from healthvideo.render.openmontage import renderer_identity as openmontage_identity

    try:
        identity = openmontage_identity()
        typer.echo(f"INFO OpenMontage (optional): {identity['commit']} / {identity['hyperframes_version']}")
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        typer.echo(f"WARN OpenMontage (optional): {error}")
    for result in results:
        status = (
            "OK" if result.ok else "WARN" if result.required == "optional" else "FAIL"
        )
        typer.echo(
            f"{status} {result.name}: {result.detected} (requires {result.required})"
        )
        if not result.ok:
            typer.echo(f"  Remedy: {result.remedy}")
    if has_mandatory_failure(results):
        raise typer.Exit(code=1)


@app.command(hidden=True)
def openmontage_install() -> None:
    """Cài checkout OpenMontage ghim commit và HyperFrames tùy chọn."""
    from healthvideo.render.openmontage import install

    try:
        typer.echo(f"OpenMontage installed: {install()}")
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error


def run_render_argv(argv: list[str]) -> int:
    """Run a render/concat argv without a shell; pnpm goes through its resolver."""
    if argv[1:3] == ['-m', 'healthvideo.render.openmontage']:
        from healthvideo.render.openmontage import run_render_argv as run_openmontage

        return run_openmontage(argv)
    resolved = (
        resolve_pnpm_argv(argv[1:]) if argv[0] == "pnpm" else prepare_subprocess_argv(argv)
    )
    return subprocess.run(resolved, check=False, shell=False).returncode


@app.command()
def preview(
    project_dir: Annotated[Path, typer.Argument(help="Thư mục dự án có render")],
    port: Annotated[int, typer.Option("--port", min=1, max=65535)] = 3000,
    print_only: Annotated[
        bool, typer.Option("--print-only", help="Chỉ in lệnh và URL, không mở Studio")
    ] = False,
) -> None:
    """Xem video trong Remotion Studio; không ghi thay đổi hoặc duyệt video."""
    try:
        layout = resolve_project_layout(project_dir.resolve())
        input_hash = layout.manifest.artifact_hashes.get(PRODUCTION_ARTIFACT)
        run_dir = (layout.artifact_root / "renders").resolve()
        if not run_dir.is_relative_to(layout.artifact_root.resolve()):
            raise ValueError("Production run phải nằm trong thư mục dự án")
        props = run_dir / RENDER_INPUT_NAME
        if not input_hash or not props.is_file():
            typer.echo(
                "Chưa có render hiện hành; xem preview sau khi chạy produce "
                "(produce yêu cầu duyệt y khoa)."
            )
            raise typer.Exit(code=1)
        render_input = json.loads(props.read_text(encoding="utf-8"))
        composition = (
            "LongForm (16:9)" if render_input.get("format_profile") == "youtube_long"
            else "VerticalClip (9:16)"
        )
        argv = resolve_pnpm_argv([
            "--dir", str(REPO_ROOT / "video"), "exec", "remotion", "studio", "src/index.ts",
            "--props", str(props), "--port", str(port),
            "--public-dir", str(run_dir), "--no-open",
        ])
        typer.echo(f"http://localhost:{port}")
        typer.echo(f"Composition: {composition}; HealthVideo dùng cùng props.")
        typer.echo("Studio chỉ để xem; thay đổi không lưu vào dự án và không duyệt video.")
        if print_only:
            typer.echo(subprocess.list2cmdline(argv))
            return
        result = subprocess.run(argv, check=False, shell=False)
    except KeyboardInterrupt:
        return
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    raise typer.Exit(code=result.returncode)


@app.command()
def produce(
    project_dir: Annotated[
        Path, typer.Argument(help="Thư mục dự án đã duyệt kịch bản")
    ],
    tts: Annotated[str, typer.Option("--tts", help="Nhà cung cấp TTS: silent | auto | vibi | vieneu")] = "silent",
    voice: Annotated[
        str | None, typer.Option("--voice", help="Preset voice VieNeu do bác sĩ chọn")
    ] = None,
    tts_python: Annotated[
        Path, typer.Option("--tts-python", help="Python của môi trường TTS riêng")
    ] = DEFAULT_TTS_PYTHON,
    precision: Annotated[str, typer.Option("--precision", help="fp32 | int8")] = "fp32",
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", help="In lệnh render, không ghi artifact hoặc đổi state"
        ),
    ] = False,
    no_music: Annotated[bool, typer.Option("--no-music", help="Disable background music")] = False,
) -> None:
    """Tạo video từ script/storyboard đã duyệt y khoa."""
    if tts in {'auto', 'vibi'}:
        try:
            provider: TTSProvider = factory_deps.build_tts_provider(
                tts=tts, voice=voice, tts_python=tts_python, precision=precision,
            )
        except (OSError, ValueError) as error:
            typer.echo(str(error))
            raise typer.Exit(code=1) from error
    elif tts == "silent":
        provider = SilentTTS()
    elif tts == "vieneu":
        if not voice:
            typer.echo("--tts vieneu cần --voice <preset> do bác sĩ chọn")
            raise typer.Exit(code=1)
        try:
            provider = build_vieneu_tts(python=tts_python, voice=voice, precision=precision)
        except ValueError as error:
            typer.echo(str(error))
            raise typer.Exit(code=1) from error
    else:
        typer.echo(f"Unsupported TTS provider: {tts}")
        raise typer.Exit(code=1)

    try:
        output = produce_project(project_dir, provider, run_render_argv, dry_run=dry_run, music=not no_music)
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    if dry_run:
        from healthvideo.render.openmontage import selected_renderer

        renderer = selected_renderer()
        if renderer.__name__.endswith('.openmontage'):
            typer.echo(subprocess.list2cmdline(renderer.build_render_argv(
                output.parent / "render-input.json", output, output.parent,
            )))
            return
        logical = build_render_argv(
            output.parent / "render-input.json", output, output.parent, stage_fonts=False
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


@review_app.command("approve")
def review_approve(
    project_dir: ProjectDir,
    gate: Gate,
    reviewer: Reviewer,
    note: Note = "",
) -> None:
    """Duyệt cổng bằng PIN do bác sĩ gõ trực tiếp trong terminal."""
    _require_approval_pin()
    try:
        record = approve_gate(
            project_dir,
            gate,
            reviewer=reviewer,
            note=note,
            now=datetime.now().astimezone(),
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
    _require_approval_pin()
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


@review_app.command("reopen")
def review_reopen(
    project_dir: ProjectDir,
    gate: Gate,
    reviewer: Reviewer,
    reason: Reason,
    changed: Annotated[list[str], typer.Option("--changed", help="Revision-relative POSIX path")],
    resume_to: Annotated[str, typer.Option("--resume-to", help="draft_ready|research_in_progress")],
    yes: SkipConfirmation = False,
) -> None:
    """Mở lại cổng y khoa khi artifact đã duyệt cần thay đổi."""
    if not yes:
        typed = typer.prompt(f"Gõ {REOPEN_CONFIRMATION} để mở lại {gate.value}")
        if typed.strip() != REOPEN_CONFIRMATION:
            typer.echo(f"Đã hủy: cần gõ {REOPEN_CONFIRMATION} để xác nhận.")
            raise typer.Exit(code=1)
    try:
        record = reopen_gate(
            project_dir, gate, reviewer=reviewer, reason=reason, changed=changed,
            resume_state=WorkflowState(resume_to), now=datetime.now().astimezone(),
        )
    except (FileNotFoundError, FileExistsError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(
        f"Đã mở lại cổng {gate.value} ({record.from_state.value} → needs_medical_revision), "
        f"nối lại tại {record.resume_state.value}"
    )


@step_app.command("review-frames")
def review_frames(
    project_dir: ProjectDir,
    clip: Annotated[str | None, typer.Option(help="Clip ID, e.g. CL01; default: long video")] = None,
    start: Annotated[float | None, typer.Option("--from", help="Start time in seconds")] = None,
    end: Annotated[float | None, typer.Option("--to", help="Inclusive end time in seconds")] = None,
    every: Annotated[float | None, typer.Option(help="Sample interval in seconds")] = None,
) -> None:
    """Create 4x2 QA contact sheets; read-only project state, writes render artifacts."""
    try:
        output = create_review_frames(
            project_dir, runner=run_render_argv, clip=clip, start=start, end=end, every=every,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(str(output))


@review_app.command("open")
def review_open(project_dir: ProjectDir, gate: Gate) -> None:
    """In gói HTML duyệt hiện tại ra stdout, không ghi vào dự án."""
    try:
        from healthvideo.workflows import product_review, script_review

        manifest = ProjectManifestV2.model_validate(
            read_yaml(project_dir / "project.yaml")
        )
        script_review.require_passed_review(project_dir)
        if gate is GateKind.VIDEO:
            product_review.require_passed_review(project_dir)
        revision_root = project_dir / "revisions" / manifest.active_revision
        html = _RENDER_PACKET[gate](revision_root)
    except (FileNotFoundError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(html)


@step_app.command("resume")
def review_resume(
    project_dir: ProjectDir,
    gate: Gate,
    to: ResumeTarget,
    reason_class: ReasonClass = None,
) -> None:
    """Thoát needs_medical_revision/needs_production_revision về trạng thái chính."""
    try:
        target = WorkflowState(to)
        new_state = resume_gate(
            project_dir,
            gate,
            target=target,
            reason_code=reason_class,
            now=datetime.now().astimezone(),
        )
    except (FileNotFoundError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(f"Trạng thái mới: {new_state.value}")


Root = Annotated[Path, typer.Option("--root", help="Thư mục gốc xưởng")]


def _nonempty_prompt(label: str) -> str:
    while True:
        value = typer.prompt(label).strip()
        if value:
            return value
        typer.echo("Vui lòng nhập nội dung.")


@app.command()
def duyet(root: Root = Path('.')) -> None:
    """Đọc gói duyệt, chọn A/R/B và nhập PIN trực tiếp trong TTY."""

    from healthvideo.storage.files import write_yaml_atomic

    try:
        pending = [
            (p, m, gate_name)
            for p, m in factory.projects(root)
            if (gate_name := factory.gate_for_project(p, m)) is not None
        ]
        if pending:
            _require_tty()
            config = pin_path().parent / 'operator.yaml'
            reviewer = str(read_yaml(config).get('reviewer', '')).strip() if config.exists() else ''
            if not reviewer:
                reviewer = _nonempty_prompt('Tên bác sĩ duyệt (lưu cho lần sau)')
                write_yaml_atomic(config, {'reviewer': reviewer})
            for project_dir, project, gate_name in pending:
                gate = GateKind(gate_name)
                revision = project_dir / 'revisions' / project.active_revision
                packet = factory.write_review_packet(root, project_dir, project)
                factory.open_packet(packet)
                typer.echo(f'Chủ đề: {factory.project_title(project_dir, project)}')
                typer.echo(f'Cổng: {gate.value} — revision {project.active_revision}')
                if gate is GateKind.MEDICAL:
                    ledger = read_yaml(revision / 'evidence/ledger.yaml')
                    typer.echo(f"Claim: {len(ledger.get('claims', []))}; nguồn: {len(ledger.get('records', []))}")
                else:
                    render_input = revision / 'renders/render-input.json'
                    timeline = read_yaml(render_input if render_input.exists() else revision / 'storyboard/storyboard.yaml')
                    frames = max((s['start_frame'] + s['duration_frames'] for s in timeline.get('scenes', [])), default=0)
                    frames += (timeline.get('youtube_cta') or {}).get('duration_frames', 0)
                    manifest = revision / 'renders/render-manifest.json'
                    clips = read_yaml(manifest).get('clips', {}) if manifest.exists() else {}
                    typer.echo(f"Thời lượng: {frames / timeline.get('fps', 30):.1f}s; clip: {len(clips)}")
                    qa = revision / 'reviews/video-qa.json'
                    report = read_yaml(qa) if qa.exists() else {}
                    warnings = [*report.get('warnings', []), *report.get('errors', [])]
                    warnings.extend(key for key, ok in report.get('checks', {}).items() if ok is False)
                    typer.echo(f'QA: {warnings or report.get("status", "chưa có báo cáo")}')
                typer.echo(f'Gói duyệt: {packet}')
                choices = ['A', 'R', 'B']
                prompt = '[A] Duyệt  [R] Từ chối  [B] Bỏ qua'
                if gate is GateKind.VIDEO:
                    choices.append('P')
                    prompt += '  [P] Đã nghe, chấp nhận phát âm và duyệt'
                action = typer.prompt(prompt, type=click.Choice(choices, case_sensitive=False)).upper()
                if action == 'B':
                    continue
                if action in {'A', 'P'}:
                    note = typer.prompt('Ghi chú (Enter để bỏ qua)', default='', show_default=False)
                    approval_pin = _require_approval_pin()
                    approve_gate(project_dir, gate, reviewer=reviewer, note=note,
                                 accept_pronunciation=action == 'P',
                                 pronunciation_pin=approval_pin if action == 'P' else None,
                                 pin_file=pin_path(),
                                 now=datetime.now().astimezone())
                    typer.echo(f'Đã duyệt {gate.value}.')
                else:
                    reason = _nonempty_prompt('Lý do từ chối')
                    if gate is GateKind.MEDICAL:
                        typer.echo('1. Sửa kịch bản/storyboard\n2. Tìm thêm bằng chứng')
                        targets = [WorkflowState.DRAFT_READY, WorkflowState.RESEARCH_IN_PROGRESS]
                    else:
                        typer.echo('1. Chỉ dựng/render lại\n2. Sai nội dung, quay lại kịch bản')
                        targets = [WorkflowState.PRODUCTION_IN_PROGRESS, WorkflowState.DRAFT_READY]
                    choice = typer.prompt('Nơi làm lại', default=1, type=click.IntRange(1, 2))
                    _require_approval_pin()
                    reject_gate(project_dir, gate, reviewer=reviewer, reason=reason,
                                resume_state=targets[choice - 1], now=datetime.now().astimezone(),
                                reason_code='semantic_issue' if gate is GateKind.VIDEO and choice == 2 else None)
                    typer.echo(f'Đã từ chối {gate.value}.')
        else:
            typer.echo('Không có project đang chờ bác sĩ.')
        if factory.running_pid(root) is None and typer.confirm('Chạy tiếp xưởng ngay?', default=True):
            typer.echo(f'Xưởng đang chạy (PID {factory.start_background(root)}).')
    except (OSError, TypeError, ValueError, RuntimeError) as error:
        _echo_error(error)
        raise typer.Exit(code=1) from error


@app.command()
def xuong(
    root: Root = Path('.'),
    interval: Annotated[float, typer.Option('--interval', min=1)] = 120,
    once: Annotated[bool, typer.Option('--once')] = False,
    background: Annotated[bool, typer.Option('--background')] = False,
    stop: Annotated[bool, typer.Option('--stop')] = False,
) -> None:
    """Chạy xưởng liên tục, tự đóng gói sau cổng video; Ctrl+C để dừng."""
    if sum([once, background, stop]) > 1:
        raise typer.BadParameter('Chỉ chọn một trong --once, --background, --stop')
    from healthvideo.workflows import repair_service, telegram_bot

    try:
        if stop:
            pid = factory.stop_background(root)
            repair_pid = repair_service.stop_background(root)
            typer.echo(f'Đã dừng xưởng PID {pid}.' if pid else 'Xưởng không chạy.')
            if repair_pid is not None:
                typer.echo(f'Đã dừng tiến trình sửa lỗi PID {repair_pid}.')
        elif background:
            typer.echo(f'Xưởng đang chạy (PID {factory.start_background(root, interval)}).')
            telegram_bot.ensure_background(root)
            repair_service.ensure_background(root)
        else:
            from healthvideo.omniroute import ensure_ready

            ensure_ready(root)
            if not once:
                telegram_bot.ensure_background(root)
                repair_service.ensure_background(root)
            factory.run_factory(root, default_run_deps(root), interval=interval, once=once, echo=typer.echo)
    except factory.FactoryAlreadyRunning as error:
        typer.echo(str(error))
    except (OSError, TypeError, ValueError, RuntimeError) as error:
        _echo_error(error)
        raise typer.Exit(code=1) from error


@telegram_app.command('status')
def telegram_status(root: Root = Path('.')) -> None:
    """Xem trạng thái bot Telegram kết nối Trưởng nhóm Điều phối."""
    from healthvideo.workflows import telegram_bot

    info = telegram_bot.bot_status(root)
    state_txt = f"đang chạy (PID {info['pid']})" if info['running'] else 'đang tắt'
    cfg_txt = 'đã cấu hình' if info['configured'] else 'chưa cấu hình'
    scope_txt = info['active_slug'] or 'Toàn xưởng'
    typer.echo(f"Telegram bot ({cfg_txt}): {state_txt} · Ngữ cảnh: {scope_txt}")
    if info.get('last_poll_at'):
        typer.echo(f"Lần poll gần nhất: {info['last_poll_at']}")
    if info.get('last_error'):
        typer.echo(f"Lỗi gần nhất: {info['last_error']}")


@telegram_app.command('start')
def telegram_start(
    root: Root = Path('.'),
    poll_timeout: Annotated[int, typer.Option('--poll-timeout', min=1, max=50)] = 25,
) -> None:
    """Chạy nền bot Telegram nối với Trưởng nhóm Điều phối."""
    from healthvideo.workflows import telegram_bot

    try:
        pid = telegram_bot.start_background(root, poll_timeout=poll_timeout)
        typer.echo(f'Telegram bot đang chạy (PID {pid}).')
    except (OSError, TypeError, ValueError, RuntimeError, telegram_bot.TelegramBotAlreadyRunning) as error:
        _echo_error(error)
        raise typer.Exit(code=1) from error


@telegram_app.command('stop')
def telegram_stop(root: Root = Path('.')) -> None:
    """Dừng bot Telegram đang chạy nền."""
    from healthvideo.workflows import telegram_bot

    pid = telegram_bot.stop_background(root)
    typer.echo(f'Đã dừng Telegram bot PID {pid}.' if pid else 'Telegram bot không chạy.')


@telegram_app.command('run')
def telegram_run(
    root: Root = Path('.'),
    poll_timeout: Annotated[int, typer.Option('--poll-timeout', min=1, max=50)] = 25,
    max_polls: Annotated[int | None, typer.Option('--max-polls', min=1)] = None,
) -> None:
    """Chạy trực tiếp vòng lặp long-polling của bot Telegram (dùng Ctrl+C để dừng)."""
    from healthvideo.workflows import telegram_bot

    try:
        telegram_bot.run_bot(root, poll_timeout=poll_timeout, max_polls=max_polls, echo=typer.echo)
    except (OSError, TypeError, ValueError, RuntimeError, telegram_bot.TelegramBotAlreadyRunning) as error:
        _echo_error(error)
        raise typer.Exit(code=1) from error


@app.command('app')
def app_command(
    root: Root = Path('.'),
    port: Annotated[int, typer.Option('--port', min=1024, max=65535)] = 8765,
    shortcut: Annotated[bool, typer.Option('--shortcut', help='Tạo biểu tượng "Xưởng video" trên Desktop')] = False,
    no_browser: Annotated[bool, typer.Option('--no-browser')] = False,
) -> None:
    """Mở app điều khiển xưởng trong trình duyệt (chỉ trên máy này; không tự duyệt)."""
    from healthvideo.workflows import dashboard

    try:
        if shortcut:
            typer.echo(f'Đã tạo lối tắt: {dashboard.install_shortcut(root)}')
            return
        dashboard.serve(root, port=port, open_browser=not no_browser, echo=typer.echo)
    except (OSError, RuntimeError) as error:
        _echo_error(error)
        raise typer.Exit(code=1) from error


def _gate_for_project(project_dir: Path) -> str | None:
    manifest_path = project_dir / "project.yaml"
    if manifest_path.is_file():
        try:
            manifest = ProjectManifestV2.model_validate(read_yaml(manifest_path))
            return factory.gate_for_project(project_dir, manifest)
        except (OSError, TypeError, ValueError):
            pass
    return None


@app.command()
def run(
    root: Root = Path("."),
    once: Annotated[
        bool, typer.Option("--once", help="Chỉ chạy tối đa một bước rồi dừng")
    ] = False,
) -> None:
    """Chạy hàng đợi chủ đề tự động tới cổng duyệt tiếp theo."""
    try:
        report = run_queue(root, default_run_deps(root), once=once)
    except (OSError, QueueError, TypeError, ValueError) as error:
        _echo_error(error)
        raise typer.Exit(code=1) from error

    advanced_text = ", ".join(report.advanced) if report.advanced else "không có"
    typer.echo(f"Chủ đề đã tiến: {advanced_text}")

    gate_lines = [
        f"Chủ đề đang chờ cổng: {slug} — healthvideo review open {root / 'projects' / slug} --gate {gate}"
        for slug in report.at_gate
        if (gate := _gate_for_project(root / "projects" / slug)) is not None
    ]
    if gate_lines:
        for line in gate_lines:
            typer.echo(line)
    else:
        typer.echo("Chủ đề đang chờ cổng: không có")

    if report.blocked:
        for slug in report.blocked:
            blocked_path = (root / "topics" / "logs" / slug / "blocked.txt").as_posix()
            typer.echo(f"Chủ đề bị chặn: {slug} ({blocked_path})")
    else:
        typer.echo("Chủ đề bị chặn: không có")

    if report.code_changes:
        changed_list = ", ".join(path.as_posix() for path in report.code_changes)
        review_file = (root / "topics" / "code-review.yaml").as_posix()
        typer.echo(f"File code cần rà ({review_file}): {changed_list}")

    if report.waiting_model:
        typer.echo(f"Chủ đề chờ model (hết lượt): {', '.join(report.waiting_model)} — chạy lại sau.")
        raise typer.Exit(code=3)


def _queue_table(root: Path, *, include_next: bool) -> None:
    try:
        codes = project_codes(root)
        rows = []
        for entry in load_queue(root):
            manifest_path = root / "projects" / entry.slug / "project.yaml"
            project = ProjectManifestV2.model_validate(read_yaml(manifest_path)) if manifest_path.exists() else None
            state = project.state if project else None
            label = state.value if state is not None else "chưa bắt đầu"
            is_paused = factory.is_paused(root, entry.slug)
            open_q = doctor_questions.open_question(root, entry.slug)
            if is_paused:
                label = f"{label} [tạm dừng]"
            if open_q is not None:
                label = f"{label} [chờ ý kiến bác sĩ]"
            following = next_step(state)
            if state in {WorkflowState.AWAITING_MEDICAL_REVIEW, WorkflowState.AWAITING_VIDEO_REVIEW}:
                following = f"chờ cổng {state.value}"
            elif open_q is not None:
                following = f"chờ ý kiến bác sĩ ({open_q.get('id', '')})"
            rows.append([codes.get(entry.slug, "—"), entry.slug, entry.title, label, following or "—"])
    except (OSError, TypeError, ValueError) as error:
        _echo_error(error)
        raise typer.Exit(code=1) from error
    columns = ["code", "slug", "title", "state", "next_step"] if include_next else ["code", "slug", "title", "state"]
    # Plain tabular output stays readable in terminals and captured logs.
    typer.echo(" | ".join(columns))
    for row in rows:
        typer.echo(" | ".join(row[:len(columns)]))


@app.command()
def status(
    project_dir: Annotated[Path | None, typer.Argument(help="Thư mục project")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    root: Root = Path("."),
) -> None:
    """Xem hàng đợi hoặc bước kế tiếp của một project."""
    if project_dir is not None:
        operator.status(project_dir, json_output=json_output)
    else:
        _queue_table(root, include_next=True)
        pid = factory.running_pid(root)
        typer.echo(f'Xưởng nền: PID {pid}' if pid else 'Xưởng nền: không chạy')
        waiting = factory.waiting_doctor_count(root)
        typer.echo(f'Đang chờ bác sĩ: {waiting}')


@step_app.command("revision-create")
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


@project_app.command("adopt-r5")
def project_adopt_r5(
    slug: Annotated[str, typer.Argument(help="Slug dự án cần chuyển sang chuẩn R5")],
    reason: Annotated[str, typer.Option("--reason", help="Lý do làm lại theo chuẩn R5")],
    recover: Annotated[
        bool,
        typer.Option("--recover", help="Khôi phục idempotent nếu lượt chuyển trước bị gián đoạn"),
    ] = False,
    root: Root = Path("."),
) -> None:
    """Tạo revision mới ghim chuẩn R5 (r5_v1), đưa về bước viết lời; yêu cầu PIN bác sĩ."""
    from healthvideo.workflows.adopt_r5 import adopt_r5_project

    pin = _require_approval_pin()
    try:
        result = adopt_r5_project(
            root,
            slug,
            reason=reason,
            pin=pin,
            now=datetime.now().astimezone(),
            recover=recover,
        )
    except (FileNotFoundError, FileExistsError, PinError, TypeError, ValueError) as error:
        _echo_error(error)
        raise typer.Exit(code=1) from error
    typer.echo(
        f"Đã chuyển {result['slug']} sang chuẩn {result['quality_profile']} "
        f"(revision {result['parent_revision']} -> {result['revision']}, state: {result['state']})."
    )


@step_app.command("stage-r5-assets")
def step_stage_r5_assets(
    slug: Annotated[str, typer.Argument(help="Slug hoặc đường dẫn thư mục dự án")],
    catalog: Annotated[
        Path,
        typer.Option("--catalog", help="Đường dẫn tới library/medanim/<chủ đề>/assets.yaml trong repo"),
    ],
    ids: Annotated[
        str,
        typer.Option("--ids", help="Danh sách asset ID cách nhau bằng dấu phẩy"),
    ],
    root: Root = Path("."),
) -> None:
    """Chép asset có phép từ thư viện repo và ghi assets/r5/catalog.yaml vào revision hiện hành."""
    from healthvideo.workflows.adopt_r5 import stage_r5_assets

    asset_ids = [item.strip() for item in ids.split(",") if item.strip()]
    try:
        result = stage_r5_assets(root, slug, catalog=catalog, asset_ids=asset_ids)
    except (FileNotFoundError, OSError, TypeError, ValueError) as error:
        _echo_error(error)
        raise typer.Exit(code=1) from error
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


def _require_tty() -> None:
    if not sys.stdin.isatty():
        typer.echo("Cần terminal TTY của bác sĩ để nhập PIN.")
        raise typer.Exit(code=1)


def _require_approval_pin() -> str:
    _require_tty()
    try:
        path = pin_path()
        if not path.is_file():
            raise PinError("Chưa đặt PIN; chạy healthvideo review set-pin trong terminal.")
        pin = getpass.getpass("PIN duyệt: ")
        if not verify_pin(pin, path=path):
            raise PinError("PIN không đúng.")
        return pin
    except (OSError, EOFError, PinError) as error:
        _echo_error(error)
        raise typer.Exit(code=1) from error


@review_app.command("set-pin")
def review_set_pin() -> None:
    """Đặt hoặc đổi PIN duyệt trong terminal của bác sĩ."""
    _require_tty()
    try:
        path = pin_path()
        old = getpass.getpass("PIN cũ: ") if path.exists() else None
        new = getpass.getpass("PIN mới: ")
        confirmation = getpass.getpass("Nhập lại PIN mới: ")
        if new != confirmation:
            raise PinError("Hai PIN mới không khớp.")
        set_pin(new, old_pin=old, path=path)
    except (OSError, EOFError, PinError) as error:
        _echo_error(error)
        raise typer.Exit(code=1) from error
    typer.echo("Đã đặt PIN.")


def get_default_clients() -> list[Any]:
    clients: list[Any] = [PubMedClient(), EuropePMCClient()]
    scopus_client = elsevier.ElsevierClient()
    if scopus_client.available():
        clients.append(elsevier.ScopusProvider(scopus_client))
    return clients


@topic_app.command("list")
def topic_list(root: Root = Path(".")) -> None:
    """Liệt kê các thẻ trong hàng đợi."""
    _queue_table(root, include_next=False)


@topic_app.command("add")
def topic_add(
    slug: Annotated[str, typer.Option("--slug")],
    title: Annotated[str, typer.Option("--title")],
    question: Annotated[str, typer.Option("--question")],
    note: Annotated[str | None, typer.Option("--note")] = None,
    root: Root = Path("."),
) -> None:
    """Thêm chủ đề vào hàng đợi; không ghi đè project đã có."""
    try:
        add_to_queue(root, QueueEntry(slug=slug, title=title, question=question, doctor_note=note, added=date.today()))  # noqa: DTZ011 — queue uses the local calendar date.
    except (OSError, QueueError, ValueError) as error:
        _echo_error(error)
        raise typer.Exit(code=1) from error
    typer.echo(f"Đã thêm: {slug}")


@topic_app.command("discover")
def topic_discover(
    query: Annotated[str, typer.Option("--query")],
    title: Annotated[str | None, typer.Option("--title")] = None,
    question: Annotated[str | None, typer.Option("--question")] = None,
    layers: Annotated[str, typer.Option("--layers")] = "",
    root: Root = Path("."),
) -> None:
    """Tìm tín hiệu thật và lưu thẻ gợi ý để bác sĩ chọn."""
    signals, failures = collect(query, fetchers={
        "youtube": lambda q: youtube.fetch_signals(q, api_key=os.environ.get("YOUTUBE_API_KEY")),
        "trends": lambda q: [signal for signal in trends.fetch_signals() if q.casefold() in signal.text.casefold()],
        "reddit": reddit.fetch_signals,
    })
    try:
        pubmed_count = PubMedClient().count(query)
    except (OSError, RuntimeError, TypeError, ValueError, KeyError) as error:
        pubmed_count = None
        failures.append(SourceFailure(source="pubmed", reason=str(error)))
    try:
        card = build_card(title or query, question or query, signals,
                          layers=[layer.strip() for layer in layers.split(",") if layer.strip()],
                          pubmed_count=pubmed_count)
        output = write_discovered(root, [card], failures, today=date.today())  # noqa: DTZ011 — discovery files use the local date.
    except (OSError, TypeError, ValueError) as error:
        _echo_error(error)
        raise typer.Exit(code=1) from error
    typer.echo(str(output))
    for failure in failures:
        typer.echo(f"{failure.source}: {failure.reason}")


@topic_app.command("sync-sheet")
def topic_sync_sheet(
    sheet: Annotated[str | None, typer.Option("--sheet", help="ID hoặc URL Google Sheet tham khảo")] = None,
    tab: Annotated[str | None, typer.Option("--tab", help="Các tab cần đồng bộ, cách nhau dấu phẩy")] = None,
    max_rows: Annotated[int, typer.Option("--max-rows", min=1, max=500)] = 60,
    root: Root = Path("."),
) -> None:
    """Đồng bộ & chấm điểm 100 từ Google Sheet tham khảo vào Topic Inbox."""
    from healthvideo.workflows import researcher

    tabs = tuple(t.strip() for t in tab.split(",") if t.strip()) if tab else None
    try:
        summary = researcher.sync_reference_sheet(
            root,
            sheet_id_or_url=sheet,
            tabs=tabs,
            max_rows=max_rows,
        )
    except (OSError, RuntimeError, ValueError) as error:
        _echo_error(error)
        raise typer.Exit(code=1) from error
    typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))


@topic_app.command("discover-ai")
def topic_discover_ai(
    query: Annotated[str, typer.Option("--query", help="Hướng chủ đề cần tìm")] = "",
    max_topics: Annotated[int, typer.Option("--max-topics", min=1, max=10)] = 4,
    root: Root = Path("."),
) -> None:
    """Cho Researcher chủ động đề xuất & chấm điểm chủ đề mới vào Topic Inbox."""
    from healthvideo.workflows import researcher

    try:
        summary = researcher.discover_topics_with_agent(
            root, query=query or "phòng bệnh thường gặp tại Việt Nam", max_topics=max_topics
        )
    except (OSError, RuntimeError, ValueError) as error:
        _echo_error(error)
        raise typer.Exit(code=1) from error
    typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))


@step_app.command("evidence-search")
def evidence_search(
    project_dir: ProjectDir,
    query: Annotated[list[str] | None, typer.Option("--query", help="English search query; repeatable")] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, help="Maximum results per query and provider")] = 10,
) -> None:
    """Search literature and preserve each query and provider outcome."""
    try:
        manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
        ev_dir = project_dir / "revisions" / manifest.active_revision / "evidence"
        q_file = ev_dir / "question.yaml"
        if q_file.is_file():
            question = EvidenceQuestion.model_validate(read_yaml(q_file))
        else:
            card_file = project_dir / "revisions" / manifest.active_revision / "topic/card.yaml"
            fallback = read_yaml(card_file).get("question", "health") if card_file.is_file() else "health"
            question = EvidenceQuestion(
                patient_population="general", intervention="; ".join(query or [fallback]),
                outcome="health", search_keywords=query or [fallback],
            )
        record_question(project_dir, question)
        log = search_literature(project_dir, question, clients=get_default_clients(), queries=query or (), limit=limit)
    except (OSError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(f"Tìm thấy {log.retrieved_count} tài liệu ứng viên.")
    failed = [outcome for outcome in log.provider_outcomes if outcome.status == "failed"]
    for outcome in failed:
        typer.echo(f"{outcome.provider} ({outcome.query_id}): {outcome.failure_class}: {outcome.error_summary}")
    if log.provider_outcomes and len(failed) == len(log.provider_outcomes):
        raise typer.Exit(code=1)


@step_app.command("evidence-screen")
def evidence_screen(
    project_dir: ProjectDir,
    criteria: Annotated[Path, typer.Option("--criteria", help="Screening criteria YAML")],
    input_path: Annotated[Path, typer.Option("--input", help="Evidence candidates JSONL")],
) -> None:
    """Write advisory abstract screening for human review; no ledger selection."""
    try:
        output = screen_candidates(project_dir, criteria, input_path)
    except (OSError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(f"Advisory screening for human review: {output}")


@step_app.command("evidence-ingest")
def evidence_ingest(
    project_dir: ProjectDir,
    file: Annotated[
        Path | None,
        typer.Option("--file", help="File YAML chứa danh sách lựa chọn tài liệu"),
    ] = None,
    source_id: Annotated[
        str | None, typer.Option("--source-id", help="ID tài liệu ứng viên")
    ] = None,
    decision: Annotated[
        str, typer.Option("--decision", help="included hoặc excluded")
    ] = "included",
    rationale: Annotated[
        str, typer.Option("--rationale", help="Lý do lựa chọn hoặc loại trừ")
    ] = "",
) -> None:
    """Ghi nhận các tài liệu ứng viên được lựa chọn hoặc loại trừ."""
    selections: list[SourceSelection] = []
    try:
        if file is not None and file.is_file():
            data = read_yaml(file)
            raw_items = data.get("sources", data) if isinstance(data, dict) else data
            if isinstance(raw_items, list):
                selections = [
                    SourceSelection.model_validate(item) for item in raw_items
                ]
        elif source_id:
            selections = [
                SourceSelection(
                    source_id=source_id, decision=decision, reason=rationale
                )
            ]
        else:
            typer.echo("Cần cung cấp --file hoặc --source-id.")
            raise typer.Exit(code=1)

        inc, exc = record_source_selections(project_dir, selections)
    except (FileNotFoundError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(
        f"Đã nạp {len(selections)} lựa chọn bằng chứng ({inc.name}, {exc.name})."
    )


@step_app.command("fulltext")
def fulltext_acquire(project_dir: ProjectDir) -> None:
    """Lấy toàn văn OA hoặc PDF bác sĩ tự tải; chỉ báo nguồn thiếu."""
    from healthvideo.evidence.fulltext import CACHE_DIR
    from healthvideo.workflows.fulltext import acquire_fulltext

    try:
        rows = acquire_fulltext(project_dir)
    except (OSError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    for row in rows:
        typer.echo(f"{row['source_id']}: {row['origin']} — {row['license'] or 'license unknown'}")
        if row['origin'] == 'missing':
            typer.echo(f"  {row['doi_url'] or 'DOI unavailable'}")
            for name in row['inbox_filenames']:
                typer.echo(f"  PDF: {CACHE_DIR / 'inbox' / name}")
        if row.get('warning'):
            typer.echo(f"  {row['warning']}")


@step_app.command("fulltext-search")
def fulltext_search(
    project_dir: ProjectDir,
    source: Annotated[str, typer.Option("--source")],
    query: Annotated[str, typer.Option("--query")],
) -> None:
    """Tìm tối đa 5 đoạn toàn văn, mỗi đoạn tối đa 600 ký tự."""
    from healthvideo.evidence.fulltext import load_fulltext, search_fulltext
    from healthvideo.workflows.fulltext import project_sources

    try:
        _, records = project_sources(project_dir)
        record = next((r for r in records if r.id == source), None)
        if record is None:
            raise ValueError(f"Unknown source: {source}")
        if load_fulltext(source, record) is None:
            typer.echo(f"{source}: missing; run step fulltext")
            return
        for match in search_fulltext(source, query):
            typer.echo(f"[{source}; {match['locator']}] {match['text']}")
    except (OSError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error


@step_app.command("build-ledger")
def evidence_build_ledger(project_dir: ProjectDir) -> None:
    """Tổng hợp evidence ledger từ nguồn tài liệu và claims đã kiểm chứng."""
    try:
        manifest = ProjectManifestV2.model_validate(
            read_yaml(project_dir / "project.yaml")
        )
        ev_dir = project_dir / "revisions" / manifest.active_revision / "evidence"
        ledger_path = ev_dir / "ledger.yaml"
        claims_path = ev_dir / "claims.yaml"
        sources_path = ev_dir / "records.yaml"

        claims: list[EvidenceClaim] = []
        sources: list[SourceRecord] = []

        if claims_path.is_file() and sources_path.is_file():
            c_data = read_yaml(claims_path)
            s_data = read_yaml(sources_path)
            claims = [
                EvidenceClaim.model_validate(c)
                for c in (
                    c_data.get("claims", c_data) if isinstance(c_data, dict) else c_data
                )
            ]
            sources = [
                SourceRecord.model_validate(r)
                for r in (
                    s_data.get("records", s_data)
                    if isinstance(s_data, dict)
                    else s_data
                )
            ]
        elif ledger_path.is_file():
            data = read_yaml(ledger_path)
            claims = [EvidenceClaim.model_validate(c) for c in data.get("claims", [])]
            sources = [SourceRecord.model_validate(r) for r in data.get("records", [])]
        else:
            typer.echo(f"Không tìm thấy file bằng chứng tại: {ledger_path}")
            raise typer.Exit(code=1)

        built_path, new_manifest = build_evidence_ledger(
            project_dir, claims=claims, sources=sources
        )
    except (FileNotFoundError, TypeError, ValueError) as error:
        typer.echo(f"Lỗi: {error}")
        raise typer.Exit(code=1) from error
    typer.echo(
        f"Đã tổng hợp ledger: {built_path} (Trạng thái mới: {new_manifest.state.value})"
    )


def _elsevier_json(call: Any) -> None:
    """Run an Elsevier client call and print JSON; the API key is never printed."""
    from healthvideo.evidence import elsevier

    try:
        result = call(elsevier.ElsevierClient())
    except ValueError as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@evidence_app.command("elsevier-search")
def elsevier_search(
    query: Annotated[str, typer.Argument(help="Truy vấn Scopus (tiếng Anh)")],
    count: Annotated[int, typer.Option("--count", min=1, max=25, help="Số kết quả tối đa")] = 25,
) -> None:
    """Tìm Scopus qua API chính thức (cần ELSEVIER_API_KEY); in JSON metadata."""
    _elsevier_json(lambda client: client.search(query, count=count))


@evidence_app.command("elsevier-abstract")
def elsevier_abstract(
    doi: Annotated[str, typer.Argument(help="DOI của bài báo")],
) -> None:
    """Lấy tóm tắt theo DOI qua Abstract Retrieval API; in JSON."""
    _elsevier_json(lambda client: client.abstract(doi))


@channel_app.command("sync-sheet")
def channel_sync_sheet(
    sheet: Annotated[str | None, typer.Option("--sheet", help="ID hoặc URL Google Sheet chỉ số kênh")] = None,
    tab: Annotated[str, typer.Option("--tab", help="Tên tab chỉ số kênh")] = "KET_QUA_KENH",
    root: Root = Path("."),
) -> None:
    """Đồng bộ chỉ số hiệu quả video từ Google Sheet (mặc định tab KET_QUA_KENH)."""
    from healthvideo.workflows import channel_analytics

    try:
        result = channel_analytics.sync_channel_sheet(root, sheet_id_or_url=sheet, tab=tab)
    except (OSError, RuntimeError, ValueError) as error:
        _echo_error(error)
        raise typer.Exit(code=1) from error
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@channel_app.command("import-csv")
def channel_import_csv(
    csv_file: Annotated[Path, typer.Argument(help="File CSV xuất từ YouTube Studio hoặc TikTok")],
    platform: Annotated[str, typer.Option("--platform", help="Nền tảng mặc định (youtube/tiktok/facebook)")] = "youtube",
    root: Root = Path("."),
) -> None:
    """Nạp file CSV hiệu quả video vào bộ nhớ phân tích kênh."""
    from healthvideo.workflows import channel_analytics

    try:
        text = csv_file.read_text(encoding="utf-8-sig")
        result = channel_analytics.import_channel_csv(root, text, platform=platform)
    except (OSError, ValueError) as error:
        _echo_error(error)
        raise typer.Exit(code=1) from error
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@channel_app.command("analyze")
def channel_analyze(
    question: Annotated[str | None, typer.Option("--question", help="Câu hỏi trọng tâm bác sĩ muốn phân tích")] = None,
    root: Root = Path("."),
) -> None:
    """Cho Researcher phân tích hiệu quả các video đã đăng và đề xuất cải thiện."""
    from healthvideo.workflows import channel_analytics

    try:
        result = channel_analytics.analyze_channel_performance(root, question=question)
    except (OSError, RuntimeError, ValueError) as error:
        _echo_error(error)
        raise typer.Exit(code=1) from error
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@channel_app.command("create-sheet")
def channel_create_sheet(
    title: Annotated[str, typer.Option("--title", help="Tiêu đề Google Sheet mới")] = "PYH - Theo dõi Hiệu quả Kênh",
    root: Root = Path("."),
) -> None:
    """Tạo Google Sheet riêng có quyền ghi qua gsheets CLI để lưu tab KET_QUA_KENH."""
    from healthvideo.workflows import channel_analytics

    try:
        result = channel_analytics.create_channel_sheet(root, title=title)
    except (OSError, RuntimeError, ValueError) as error:
        _echo_error(error)
        raise typer.Exit(code=1) from error
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
