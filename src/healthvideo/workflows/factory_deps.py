"""Default production dependencies for running the factory topic queue."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.queue import QueueEntry
from healthvideo.domain.topic import TopicCard
from healthvideo.process import prepare_subprocess_argv, resolve_pnpm_argv
from healthvideo.storage.files import read_yaml
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.tts.base import TTSProvider
from healthvideo.tts.command import CommandTTS
from healthvideo.tts.normalize import NormalizedTTS
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.create_project_v2 import create_project_v2
from healthvideo.workflows.gate_review import check_revision_posts
from healthvideo.workflows.produce import produce_project
from healthvideo.workflows.runner import RunDeps
from healthvideo.workflows.topic import select_topic

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TTS_PYTHON = REPO_ROOT / "cache" / "tts-venv" / "Scripts" / "python.exe"
VIENEU_WRAPPER = REPO_ROOT / "tools" / "tts" / "vieneu_synth.py"
_EXCLUDED_TOP_DIRS = frozenset({"projects", "topics", "cache", ".claude"})


def _build_vieneu_tts(*, python: Path, voice: str, precision: str) -> NormalizedTTS:
    """Build VieNeu v3 Turbo TTS provider with FFmpeg loudnorm."""
    voice_alias = (
        re.sub(r"[^A-Za-z0-9._-]", "-", voice).strip("-").lower() or "voice"
    )
    inner = CommandTTS(
        executable=str(python),
        arguments=(
            str(VIENEU_WRAPPER),
            "--input",
            "{input}",
            "--output",
            "{output}",
            "--backend",
            "onnx",
            "--voice",
            voice,
            "--precision",
            precision,
        ),
        model_id="vieneu-v3-turbo",
        voice_id=voice_alias,
        runtime_id=f"onnx-cpu-{precision}",
    )
    return NormalizedTTS(inner)


def _run_render_argv(argv: list[str]) -> int:
    """Run a render/concat argv without a shell; pnpm goes through its resolver."""
    resolved = (
        resolve_pnpm_argv(argv[1:])
        if argv[0] == "pnpm"
        else prepare_subprocess_argv(argv)
    )
    return subprocess.run(resolved, check=False, shell=False).returncode


def build_default_producer(
    *,
    tts: str = "silent",
    voice: str | None = None,
    tts_python: Path = DEFAULT_TTS_PYTHON,
    precision: str = "fp32",
) -> Callable[[Path], None]:
    """Build the default producer callable matching CLI ``produce`` defaults."""
    if tts == "silent":
        provider: TTSProvider = SilentTTS()
    elif tts == "vieneu":
        if not voice:
            msg = "--tts vieneu cần --voice <preset> do bác sĩ chọn"
            raise ValueError(msg)
        provider = _build_vieneu_tts(
            python=tts_python, voice=voice, precision=precision
        )
    else:
        msg = f"Unsupported TTS provider: {tts}"
        raise ValueError(msg)

    def _produce(project_dir: Path) -> None:
        produce_project(project_dir, provider, _run_render_argv, dry_run=False)

    return _produce


FACTORY_VOICE = "Thái Sơn"  # giọng kênh đã chốt qua nghe mù (VieNeu)


def _produce_with_channel_voice(project_dir: Path) -> None:
    """Build the VieNeu producer on demand so a missing TTS venv blocks one topic, not the run."""
    tts_python = Path(os.environ.get("HEALTHVIDEO_TTS_PYTHON", str(DEFAULT_TTS_PYTHON)))
    build_default_producer(tts="vieneu", voice=FACTORY_VOICE, tts_python=tts_python)(project_dir)


def create_project(root: Path, entry: QueueEntry) -> Path:
    """Create a v2 project under ``root / 'projects' / entry.slug`` and select its card."""
    now = datetime.now().astimezone()
    project_dir = create_project_v2(
        root / "projects",
        entry.slug,
        entry.title,
        now=now,
    )
    card = TopicCard(
        slug=entry.slug,
        title=entry.title,
        question=entry.question,
    )
    select_topic(project_dir, card, now=now)
    return project_dir


def read_state(project_dir: Path) -> WorkflowState:
    """Read the current workflow state of ``project_dir``."""
    return resolve_project_layout(project_dir).manifest.state


def reject_note(project_dir: Path) -> str | None:
    """Read the rejection note, including semantic rework carried into a revision."""
    layout = resolve_project_layout(project_dir)
    state = layout.manifest.state
    if state is WorkflowState.DRAFT_READY:
        provenance = layout.artifact_root / 'workflow.yaml'
        reason = read_yaml(provenance).get('reason', '') if provenance.exists() else ''
        return reason if reason.startswith('semantic_issue: ') else None
    if state == WorkflowState.NEEDS_MEDICAL_REVISION:
        gate_dir = layout.artifact_root / "reviews" / "medical"
    elif state == WorkflowState.NEEDS_PRODUCTION_REVISION:
        gate_dir = layout.artifact_root / "reviews" / "video"
    else:
        return None

    if not gate_dir.is_dir():
        return None
    rejected_files = sorted(
        gate_dir.glob("*-rejected*.yaml"),
        key=lambda path: path.name,
    )
    if not rejected_files:
        return None
    data = read_yaml(rejected_files[-1])
    if not isinstance(data, dict):
        return None
    reason = data.get("reason") or data.get("note")
    return str(reason) if reason else None


def posts_ready(project_dir: Path) -> bool:
    """Return True when the active revision has a valid ``posts/posts.yaml``."""
    try:
        layout = resolve_project_layout(project_dir)
        errors = check_revision_posts(
            layout.artifact_root,
            require_medical_approval=True,
        )
    except Exception:  # noqa: BLE001
        return False
    return not errors


def code_snapshot(
    root: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, str]:
    """Snapshot each dirty code path's SHA-1, including individual untracked files."""
    completed = runner(
        ["git", "status", "--porcelain", "-z", "--untracked-files=all"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"Cannot snapshot git status: {completed.stderr}")
    snapshot: dict[str, str] = {}
    records = iter((completed.stdout or "").split("\0"))
    for record in records:
        if not record:
            continue
        normalized = Path(record[3:])
        if "R" in record[:2] or "C" in record[:2]:
            next(records, None)  # -z emits destination first, then the original path.
        if not normalized.parts or normalized.parts[0] in _EXCLUDED_TOP_DIRS:
            continue
        path = root / normalized
        try:
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha1").hexdigest()
        except FileNotFoundError:
            digest = "missing"
        snapshot[normalized.as_posix()] = digest
    return snapshot


def changed_code_paths(
    root: Path,
    before: dict[str, str] | None = None,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> list[Path]:
    """Return new or content-changed dirty paths relative to the step's snapshot."""
    baseline = before if before is not None else {}
    after = code_snapshot(root, runner=runner)
    return [
        Path(path) for path in dict.fromkeys([*after, *baseline])
        if baseline.get(path) != after.get(path)
    ]


def default_run_deps(
    root: Path,
    *,
    git_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> RunDeps:
    """Construct the default ``RunDeps`` for ``healthvideo run``."""
    del root
    return RunDeps(
        create_project=create_project,
        read_state=read_state,
        reject_note=reject_note,
        python_steps={"produce": _produce_with_channel_voice},
        changed_code_paths=lambda repo_root: changed_code_paths(
            repo_root, runner=git_runner
        ),
        posts_ready=posts_ready,
        code_snapshot=lambda repo_root: code_snapshot(repo_root, runner=git_runner),
    )
