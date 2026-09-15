import re
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

import typer

from healthvideo import __version__
from healthvideo.commands.operator import app as operator_app
from healthvideo.domain.agent_review import AgentReviewResponse
from healthvideo.domain.evidence import (
    EvidenceClaim,
    EvidenceQuestion,
    SourceRecord,
    SourceSelection,
)
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project import ProjectManifest
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.review import ReviewKind, ReviewRecord
from healthvideo.domain.topic import TopicCard
from healthvideo.evidence.clients import EuropePMCClient, PubMedClient
from healthvideo.process import resolve_pnpm_argv
from healthvideo.render.remotion import build_render_argv
from healthvideo.storage.files import read_yaml, write_text_atomic
from healthvideo.storage.revisions import create_revision
from healthvideo.tts.asr import CommandASR
from healthvideo.tts.base import TTSProvider
from healthvideo.tts.benchmark import (
    BenchmarkThresholds,
    evaluate_benchmark,
    load_benchmark_cases,
    run_benchmark,
)
from healthvideo.tts.command import CommandTTS
from healthvideo.tts.normalize import NormalizedTTS
from healthvideo.tts.silent import SilentTTS
from healthvideo.video_ai.veo import GoogleVeoTransport
from healthvideo.workflows.agent_review import (
    complete_second_model_review,
    request_second_model_review,
)
from healthvideo.workflows.ai_clips import AIClipRights, generate_ai_clip
from healthvideo.workflows.create_project import create_project
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
from healthvideo.workflows.gate_review import approve_gate, reject_gate, resume_gate
from healthvideo.workflows.hook_outro import author_hook_outro
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
from healthvideo.workflows.topic import (
    create_topic,
    list_topics,
    reject_topic,
    select_topic,
)

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


app = typer.Typer(no_args_is_help=True)
project_app = typer.Typer(no_args_is_help=True)
review_app = typer.Typer(no_args_is_help=True)
revision_app = typer.Typer(no_args_is_help=True)
topic_app = typer.Typer(no_args_is_help=True)
evidence_app = typer.Typer(no_args_is_help=True)
agent_app = typer.Typer(no_args_is_help=True)
outro_app = typer.Typer(no_args_is_help=True)
ai_clip_app = typer.Typer(no_args_is_help=True)
app.add_typer(project_app, name="project")
app.add_typer(review_app, name="review")
app.add_typer(revision_app, name="revision")
app.add_typer(topic_app, name="topic")
app.add_typer(evidence_app, name="evidence")
app.add_typer(operator_app, name="operator")
app.add_typer(agent_app, name="agent")
app.add_typer(outro_app, name="outro")
app.add_typer(ai_clip_app, name="ai-clip")


def _gcloud_access_token() -> str:
    completed = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        check=True,
        capture_output=True,
        text=True,
        shell=False,
    )
    token = completed.stdout.strip()
    if not token:
        raise ValueError("Google access token is unavailable")
    return token


@ai_clip_app.command("generate")
def ai_clip_generate(
    project_dir: Annotated[Path, typer.Argument(help="Thư mục dự án v2")],
    scene_id: Annotated[str, typer.Option("--scene-id")],
    prompt: Annotated[str, typer.Option("--prompt")],
    duration_seconds: Annotated[int, typer.Option("--duration-seconds")],
    google_project: Annotated[str, typer.Option("--google-project")],
    location: Annotated[str, typer.Option("--location")],
    source: Annotated[str, typer.Option("--source")],
    creator: Annotated[str, typer.Option("--creator")],
    license: Annotated[str, typer.Option("--license")],
    rights_basis: Annotated[str, typer.Option("--rights-basis")],
    allow_live_generation: Annotated[
        bool, typer.Option("--allow-live-generation")
    ] = False,
    requested_seed: Annotated[int | None, typer.Option("--requested-seed")] = None,
) -> None:
    """Tạo một clip Veo đã yêu cầu rõ ràng trước duyệt y khoa."""
    if not allow_live_generation:
        typer.echo("Live AI generation requires --allow-live-generation.")
        raise typer.Exit(code=1)
    try:
        transport = GoogleVeoTransport(
            project_id=google_project,
            location=location,
            token_provider=_gcloud_access_token,
        )
        output = generate_ai_clip(
            project_dir,
            scene_id=scene_id,
            prompt=prompt,
            duration_seconds=duration_seconds,
            requested_seed=requested_seed,
            rights=AIClipRights(
                source=source,
                creator=creator,
                license=license,
                rights_basis=rights_basis,
            ),
            transport=transport,
            now=datetime.now().astimezone(),
        )
    except (OSError, subprocess.SubprocessError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(str(output))


@outro_app.command("author")
def outro_author(
    project_dir: Annotated[Path, typer.Argument(help="Thư mục dự án v2")],
    duration_frames: Annotated[int, typer.Option("--duration-frames", help="Số frame của câu kết")],
) -> None:
    """Thêm câu kết PHY cố định trước cổng duyệt y khoa."""
    try:
        author_hook_outro(project_dir, duration_frames=duration_frames)
    except (OSError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo("Đã chuẩn bị câu kết để duyệt y khoa.")


@agent_app.command("review-request")
def agent_review_request(
    project_dir: Annotated[Path, typer.Argument(help="Thư mục dự án")],
    reason: Annotated[str, typer.Option("--reason", help="Lý do yêu cầu phản biện")],
) -> None:
    """Tạo gói phản biện mô hình thứ hai để chuyển thủ công."""
    try:
        request_dir = request_second_model_review(
            project_dir, reason_code=reason, now=datetime.now().astimezone()
        )
    except (OSError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(str(request_dir))


@agent_app.command("review-complete")
def agent_review_complete(
    project_dir: Annotated[Path, typer.Argument(help="Thư mục dự án")],
    file: Annotated[Path, typer.Option("--file", help="Response YAML đã nhận")],
) -> None:
    """Xác minh response và tiếp tục từ side state hiện có."""
    try:
        response = AgentReviewResponse.model_validate(read_yaml(file))
        changed = complete_second_model_review(
            project_dir, response, now=datetime.now().astimezone()
        )
    except (OSError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(changed.state.value)

ProjectDir = Annotated[Path, typer.Argument(help="Thư mục dự án")]
Reviewer = Annotated[str, typer.Option("--reviewer", help="Tên bác sĩ duyệt")]
Note = Annotated[str, typer.Option("--note", help="Ghi chú của người duyệt")]
SkipConfirmation = Annotated[
    bool, typer.Option("--yes", help=f"Bỏ qua xác nhận gõ {CONFIRMATION}")
]
REJECT_CONFIRMATION = "REJECT"
Gate = Annotated[GateKind, typer.Option("--gate", help="medical hoặc video")]
Reason = Annotated[str, typer.Option("--reason", help="Lý do từ chối")]
ResumeTo = Annotated[
    str, typer.Option("--resume-to", help="Trạng thái nối lại sau khi sửa")
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
_PACKET_NAME = {
    GateKind.MEDICAL: "medical-packet.html",
    GateKind.VIDEO: "video-packet.html",
}


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


@app.command()
def produce(
    project_dir: Annotated[
        Path, typer.Argument(help="Thư mục dự án đã duyệt kịch bản")
    ],
    tts: Annotated[str, typer.Option("--tts", help="Nhà cung cấp TTS: silent | vieneu")] = "silent",
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
) -> None:
    """Tạo video từ script/storyboard đã duyệt y khoa."""
    if tts == "silent":
        provider: TTSProvider = SilentTTS()
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

    def run_remotion(argv: list[str]) -> int:
        resolved = resolve_pnpm_argv(argv[1:])
        return subprocess.run(resolved, check=False, shell=False).returncode

    try:
        output = produce_project(project_dir, provider, run_remotion, dry_run=dry_run)
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


@app.command("tts-benchmark")
def tts_benchmark(
    cases_file: Annotated[Path, typer.Argument(help="YAML `cases: [{id, text}]` tiếng Việt")],
    output_dir: Annotated[Path, typer.Option("--output", help="Thư mục WAV/báo cáo (nên dưới cache/)")],
    command: Annotated[str, typer.Option("--command", help="Lệnh TTS cục bộ, không qua shell")],
    args: Annotated[list[str], typer.Option("--arg", help="Tham số, cần một {input} và một {output}")],
    model_id: Annotated[str, typer.Option("--model-id", help="Alias công khai của model")],
    voice_id: Annotated[str, typer.Option("--voice-id", help="Alias công khai của giọng")],
    runtime_id: Annotated[str, typer.Option("--runtime-id")] = "operator-configured",
    max_rtf: Annotated[float, typer.Option("--max-rtf", help="Ngưỡng realtime factor")] = 1.0,
    asr_command: Annotated[
        str | None, typer.Option("--asr-command", help="Lệnh ASR cục bộ để back-check")
    ] = None,
    asr_args: Annotated[
        list[str] | None, typer.Option("--asr-arg", help="Tham số ASR, một {input} và một {output}")
    ] = None,
    asr_model_id: Annotated[str, typer.Option("--asr-model-id")] = "asr",
    max_wer: Annotated[float, typer.Option("--max-wer", help="Ngưỡng word error rate")] = 0.2,
) -> None:
    """Chạy benchmark TTS khách quan (WAV, thời gian, tốc độ đọc, WER); không chấm chất lượng giọng."""
    import json
    from dataclasses import asdict

    thresholds = BenchmarkThresholds(max_realtime_factor=max_rtf, max_wer=max_wer)
    try:
        cases = load_benchmark_cases(cases_file)
        provider = CommandTTS(
            executable=command, arguments=tuple(args), model_id=model_id,
            voice_id=voice_id, runtime_id=runtime_id,
        )
        asr = (
            CommandASR(
                executable=asr_command, arguments=tuple(asr_args or ()), model_id=asr_model_id
            )
            if asr_command
            else None
        )
    except (KeyError, TypeError, ValueError, OSError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    records = run_benchmark(cases, [provider], output_dir, asr=asr)
    verdicts = evaluate_benchmark(records, cases, thresholds)
    report = {
        "thresholds": asdict(thresholds),
        "records": [asdict(record) for record in records],
        "verdicts": [asdict(verdict) for verdict in verdicts],
        "summary": {"passed": sum(v.passed for v in verdicts), "total": len(verdicts)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    write_text_atomic(output_dir / "benchmark.json", text)
    typer.echo(text)
    if report["summary"]["passed"] != report["summary"]["total"]:
        raise typer.Exit(code=1)


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
    except (
        FileNotFoundError,
        FileExistsError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
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
    project_dir: ProjectDir,
    gate: Gate,
    reviewer: Reviewer,
    note: Note = "",
    yes: SkipConfirmation = False,
) -> None:
    """Duyệt cổng y khoa hoặc video cho project schema 2.0."""
    if not yes:
        typed = typer.prompt(f"Gõ {CONFIRMATION} để duyệt {gate.value}")
        if typed.strip() != CONFIRMATION:
            typer.echo(f"Đã hủy: cần gõ {CONFIRMATION} để xác nhận.")
            raise typer.Exit(code=1)
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
        manifest = ProjectManifestV2.model_validate(
            read_yaml(project_dir / "project.yaml")
        )
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


def get_default_clients() -> list[Any]:
    return [PubMedClient(), EuropePMCClient()]


@topic_app.command("list")
def topic_list(
    inbox: Annotated[
        Path, typer.Option("--inbox", help="Thư mục hộp thư chủ đề")
    ] = Path("topics"),
    status_filter: Annotated[
        str | None, typer.Option("--status", help="Lọc theo trạng thái")
    ] = None,
) -> None:
    """Liệt kê các chủ đề trong inbox theo thứ tự ưu tiên triage."""
    cards = list_topics(inbox, status=status_filter)
    if not cards:
        typer.echo("Không có chủ đề nào.")
        return
    for card in cards:
        typer.echo(f"{card.slug} [{card.status}]: {card.title}")


@topic_app.command("create")
def topic_create(
    title: Annotated[str, typer.Option("--title", help="Tiêu đề chủ đề")],
    question: Annotated[str, typer.Option("--question", help="Câu hỏi trọng tâm")],
    slug: Annotated[str, typer.Option("--slug", help="Slug định danh")] = "",
    inbox: Annotated[
        Path, typer.Option("--inbox", help="Thư mục hộp thư chủ đề")
    ] = Path("topics"),
    audience: Annotated[
        str, typer.Option("--audience", help="Đối tượng khán giả")
    ] = "",
) -> None:
    """Tạo một thẻ chủ đề mới trong inbox."""
    effective_slug = slug or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    card = create_topic(
        inbox_dir=inbox,
        title=title,
        question=question,
        slug=effective_slug,
        target_audience=audience,
    )
    typer.echo(f"Đã tạo chủ đề: {card.slug} ({card.title})")


@topic_app.command("reject")
def topic_reject(
    topic_path: Annotated[Path, typer.Argument(help="Đường dẫn file card chủ đề")],
    reason: Annotated[str, typer.Option("--reason", help="Lý do từ chối")],
) -> None:
    """Từ chối một chủ đề và ghi nhận lý do."""
    try:
        card = reject_topic(topic_path, reason=reason)
    except (FileNotFoundError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(f"Đã từ chối chủ đề: {card.slug} - Lý do: {card.rejection_reason}")


@topic_app.command("select")
def topic_select(
    project_dir: ProjectDir,
    slug: Annotated[str, typer.Option("--slug", help="Slug chủ đề trong inbox")] = "",
    file: Annotated[
        Path | None, typer.Option("--file", help="Đường dẫn file card chủ đề")
    ] = None,
    inbox: Annotated[
        Path, typer.Option("--inbox", help="Thư mục hộp thư chủ đề")
    ] = Path("topics"),
) -> None:
    """Chọn chủ đề cho dự án v2 và chuyển trạng thái sang topic_selected."""
    if file is not None:
        card_path = file
    elif slug:
        card_path = inbox / f"{slug}.yaml"
    else:
        typer.echo("Cần cung cấp --slug hoặc --file.")
        raise typer.Exit(code=1)

    if not card_path.is_file():
        typer.echo(f"Không tìm thấy thẻ chủ đề tại: {card_path}")
        raise typer.Exit(code=1)

    try:
        data = read_yaml(card_path)
        card = TopicCard.model_validate(data)
        select_topic(project_dir, card)
    except (FileNotFoundError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(f"Đã chọn chủ đề: {card.slug} cho dự án {project_dir.name}")


@evidence_app.command("search")
def evidence_search(
    project_dir: ProjectDir,
    query: Annotated[str, typer.Option("--query", help="Từ khóa tìm kiếm")] = "",
    limit: Annotated[int, typer.Option("--limit", help="Số lượng kết quả tối đa")] = 10,
) -> None:
    """Tìm kiếm y văn từ các nguồn và ghi nhận candidates."""
    try:
        manifest = ProjectManifestV2.model_validate(
            read_yaml(project_dir / "project.yaml")
        )
        ev_dir = project_dir / "revisions" / manifest.active_revision / "evidence"
        q_file = ev_dir / "question.yaml"
        if q_file.is_file():
            q_data = read_yaml(q_file)
            question = EvidenceQuestion.model_validate(q_data)
            if query:
                question = question.model_copy(
                    update={
                        "search_keywords": [
                            k.strip() for k in query.split() if k.strip()
                        ]
                    }
                )
        else:
            question = EvidenceQuestion(
                patient_population="general",
                intervention=query or "general",
                outcome="health",
                search_keywords=[k.strip() for k in query.split() if k.strip()]
                if query
                else ["health"],
            )
            record_question(project_dir, question)

        clients = get_default_clients()
        log = search_literature(project_dir, question, clients=clients)
    except (FileNotFoundError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(f"Tìm thấy {log.retrieved_count} tài liệu ứng viên.")


@evidence_app.command("ingest")
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


@evidence_app.command("build-ledger")
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

        if ledger_path.is_file():
            data = read_yaml(ledger_path)
            claims = [EvidenceClaim.model_validate(c) for c in data.get("claims", [])]
            sources = [SourceRecord.model_validate(r) for r in data.get("records", [])]
        elif claims_path.is_file() and sources_path.is_file():
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
