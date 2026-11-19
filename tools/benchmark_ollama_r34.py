"""Headless Ollama ~4B local LLM benchmark for PYH R3.4 (6 Vietnamese samples).

Starts headless ``ollama serve`` on 127.0.0.1:11434 (never the GUI tray), measures
real GPU VRAM (``nvidia-smi``) and Win32 free RAM (``GlobalMemoryStatusEx``), runs
3 ``feedback_inbox`` + 3 ``chat_status_summary`` Vietnamese prompts with ``num_ctx: 4096``,
checks ``/api/ps`` for silent CPU offload, unloads with ``keep_alive: 0``, stops the
temporary server, and writes measured results to ``docs/reference/ollama-r34-benchmark.md``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from healthvideo.env import (
    background_popen_kwargs,
    child_env,
    hide_child_consoles,
)
from healthvideo.local_llm import (
    ChatStatusSummary,
    LocalFeedbackAnalysis,
    _parse_schema_response,
    check_ps_gpu_only,
    list_installed_models,
    measure_free_ram_mib,
    measure_vram_mib,
)
from healthvideo.process import terminate_process_tree

ENDPOINT = "http://127.0.0.1:11434"
CANDIDATE_MODELS: tuple[str, ...] = ("qwen3:4b", "qwen2.5:3b")

SAMPLES: tuple[dict[str, Any], ...] = (
    {
        "id": "FB-01",
        "task": "feedback_inbox",
        "schema": LocalFeedbackAnalysis,
        "prompt": (
            "Phân loại ý kiến bác sĩ thành JSON theo schema.\n"
            "Ý kiến (dự án chung): Phụ đề video vẫn còn hơi nhanh ở đoạn đọc số liệu, "
            "giúp tôi cập nhật rule trong dashboard và prompt dựng để giữ mỗi trang tối thiểu 4 từ.\n"
            "Chỉ trả JSON hợp lệ, không thêm giải thích ngoài JSON."
        ),
    },
    {
        "id": "FB-02",
        "task": "feedback_inbox",
        "schema": LocalFeedbackAnalysis,
        "prompt": (
            "Phân loại ý kiến bác sĩ thành JSON theo schema.\n"
            "Ý kiến (dự án men-gan-tang): Cảnh B2 cần thêm chú thích rõ đường máu động mạch gan "
            "hợp lưu với tĩnh mạch cửa trong storyboard của video này.\n"
            "Chỉ trả JSON hợp lệ, không thêm giải thích ngoài JSON."
        ),
    },
    {
        "id": "FB-03",
        "task": "feedback_inbox",
        "schema": LocalFeedbackAnalysis,
        "prompt": (
            "Phân loại ý kiến bác sĩ thành JSON theo schema.\n"
            "Ý kiến (dự án chung): Từ nay mọi video kênh đều không dùng gạch chân từng chữ "
            "và tuyệt đối không tự vẽ giải phẫu bằng code.\n"
            "Chỉ trả JSON hợp lệ, không thêm giải thích ngoài JSON."
        ),
    },
    {
        "id": "CS-01",
        "task": "chat_status_summary",
        "schema": ChatStatusSummary,
        "prompt": (
            "Tóm tắt trạng thái ngắn bằng tiếng Việt cho bác sĩ (trả JSON theo schema, action='status').\n"
            "Dữ liệu: dự án men-gan-tang đang ở trạng thái awaiting_medical_review (chờ PIN bác sĩ); "
            "dự án gout-tinh-the-urat đang bị chặn ở bước produce; xưởng nền đang tạm dừng.\n"
            "Chỉ trả JSON hợp lệ."
        ),
    },
    {
        "id": "CS-02",
        "task": "chat_status_summary",
        "schema": ChatStatusSummary,
        "prompt": (
            "Tóm tắt trạng thái ngắn bằng tiếng Việt cho bác sĩ (trả JSON theo schema, action='status').\n"
            "Dữ liệu: có 2 chủ đề trong queue (an-gao-lut, uong-c-sui), không có job nào đang chạy, "
            "model codex/gpt-6.1-sol đang nghỉ quota tới 17:00.\n"
            "Chỉ trả JSON hợp lệ."
        ),
    },
    {
        "id": "CS-03",
        "task": "chat_status_summary",
        "schema": ChatStatusSummary,
        "prompt": (
            "Tóm tắt trạng thái ngắn bằng tiếng Việt cho bác sĩ (trả JSON theo schema, action='status').\n"
            "Dữ liệu: dự án an-gao-lut đã hoàn tất packaged tại revisions/001/publish, "
            "chưa đăng lên YouTube hay TikTok.\n"
            "Chỉ trả JSON hợp lệ."
        ),
    },
)


def _find_ollama_executable() -> str | None:
    found = shutil.which("ollama")
    if found and Path(found).name.casefold() != "ollama app.exe":
        return found
    local_app = os.environ.get("LOCALAPPDATA", "")
    if local_app:
        candidate = Path(local_app) / "Programs" / "Ollama" / "ollama.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def _http_json(url: str, *, payload: dict[str, Any] | None = None, timeout: float = 120.0) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw) if raw.strip() else {}


def _is_ollama_up() -> bool:
    try:
        list_installed_models(ENDPOINT, timeout=1.5)
        return True
    except (OSError, URLError, ValueError, TimeoutError):
        return False


def _start_headless_serve(ollama_exe: str, log_path: Path) -> subprocess.Popen[bytes]:
    hide_child_consoles()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = child_env()
    env["OLLAMA_HOST"] = "127.0.0.1:11434"
    env["OLLAMA_NOHISTORY"] = "1"
    with log_path.open("ab") as stream:
        proc = subprocess.Popen(
            [ollama_exe, "serve"],
            cwd=REPO_ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=stream,
            shell=False,
            **background_popen_kwargs(),
        )
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        if _is_ollama_up():
            return proc
        if proc.poll() is not None:
            raise RuntimeError(f"headless `ollama serve` exited early with code {proc.returncode}")
        time.sleep(0.25)
    terminate_process_tree(proc.pid)
    raise TimeoutError("headless `ollama serve` did not become ready on 127.0.0.1:11434 within 20s")


def _pull_model(ollama_exe: str, model: str, *, timeout: float) -> tuple[bool, str]:
    env = child_env()
    env["OLLAMA_HOST"] = "127.0.0.1:11434"
    kwargs: dict[str, Any] = {
        "cwd": REPO_ROOT,
        "env": env,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
        "shell": False,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run([ollama_exe, "pull", model], check=False, **kwargs)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    detail = (completed.stderr or completed.stdout or "").strip()[-400:]
    return completed.returncode == 0, detail


def _unload_model(model: str) -> None:
    try:
        _http_json(
            f"{ENDPOINT}/api/generate",
            payload={"model": model, "prompt": "", "stream": False, "keep_alive": 0},
            timeout=10.0,
        )
    except (OSError, URLError, ValueError, TimeoutError):
        pass


def run_benchmark(
    *,
    models: tuple[str, ...] = CANDIDATE_MODELS,
    pull_timeout_s: float = 300.0,
    gen_timeout_s: float = 120.0,
) -> dict[str, Any]:
    """Run headless Ollama benchmark and return structured measured results."""
    ollama_exe = _find_ollama_executable()
    baseline_vram = measure_vram_mib()
    baseline_ram = measure_free_ram_mib()
    report: dict[str, Any] = {
        "measured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ollama_executable": ollama_exe,
        "endpoint": ENDPOINT,
        "baseline": {
            "vram_mib": baseline_vram,
            "free_ram_mib": baseline_ram,
        },
        "selected_model": None,
        "pull_attempts": [],
        "samples": [],
        "summary": {
            "samples_total": len(SAMPLES),
            "samples_passed": 0,
            "schema_pass_rate": None,
            "avg_tok_per_s": None,
            "peak_vram_used_mib": None,
            "min_free_vram_mib": None,
            "min_free_ram_mib": baseline_ram,
            "cpu_offload_detected": None,
            "ps_size_bytes": None,
            "ps_size_vram_bytes": None,
            "unloaded_cleanly": None,
        },
        "blocker_reason": None,
    }

    if ollama_exe is None:
        report["blocker_reason"] = "Không tìm thấy CLI `ollama` trên PATH hoặc LOCALAPPDATA."
        return report

    version_text = None
    try:
        ver_proc = subprocess.run(
            [ollama_exe, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5.0,
            check=False,
            shell=False,
        )
        version_text = (ver_proc.stdout or ver_proc.stderr or "").strip() or None
    except (OSError, subprocess.SubprocessError):
        pass
    report["ollama_version"] = version_text

    serve_proc: subprocess.Popen[bytes] | None = None
    started_by_us = False
    serve_log = REPO_ROOT / "cache" / "ollama-benchmark-serve.log"
    try:
        if not _is_ollama_up():
            serve_proc = _start_headless_serve(ollama_exe, serve_log)
            started_by_us = True

        installed = list_installed_models(ENDPOINT, timeout=3.0)
        report["installed_models_before"] = sorted(installed)
        chosen_model: str | None = None
        for candidate in models:
            if candidate in installed or (":" not in candidate and f"{candidate}:latest" in installed):
                chosen_model = candidate
                break

        if chosen_model is None:
            for candidate in models:
                ok, detail = _pull_model(ollama_exe, candidate, timeout=pull_timeout_s)
                report["pull_attempts"].append({"model": candidate, "ok": ok, "detail": detail})
                if ok:
                    chosen_model = candidate
                    break

        if chosen_model is None:
            report["blocker_reason"] = (
                "Không có sẵn hoặc không kéo được model Ollama (~4B) trong môi trường hiện tại."
            )
            return report

        report["selected_model"] = chosen_model
        peak_vram_used = baseline_vram["used_mib"] if baseline_vram else None
        min_free_vram = baseline_vram["free_mib"] if baseline_vram else None
        min_free_ram = baseline_ram
        tok_rates: list[float] = []
        offload_seen = False
        ps_size = None
        ps_size_vram = None

        # Run 6 real Vietnamese samples; hold short keep_alive during sample loop to inspect
        # /api/ps VRAM allocation accurately, then immediately unload with keep_alive: 0.
        for idx, sample in enumerate(SAMPLES):
            schema_cls: type[BaseModel] = sample["schema"]
            keep_alive: int | str = "30s" if idx == 0 else 0
            t0 = time.monotonic()
            sample_row: dict[str, Any] = {
                "id": sample["id"],
                "task": sample["task"],
                "schema_pass": False,
                "latency_s": None,
                "prompt_eval_count": None,
                "eval_count": None,
                "tok_per_s": None,
                "vram_after_mib": None,
                "free_ram_after_mib": None,
                "error": None,
            }
            try:
                payload = {
                    "model": chosen_model,
                    "prompt": sample["prompt"],
                    "stream": False,
                    "keep_alive": keep_alive,
                    "format": schema_cls.model_json_schema(),
                    "options": {"num_ctx": 4096, "temperature": 0.1},
                }
                if chosen_model.startswith("qwen3"):
                    payload["think"] = False
                resp = _http_json(f"{ENDPOINT}/api/generate", payload=payload, timeout=gen_timeout_s)
                sample_row["latency_s"] = round(time.monotonic() - t0, 3)
                vram_now = measure_vram_mib()
                ram_now = measure_free_ram_mib()
                sample_row["vram_after_mib"] = vram_now
                sample_row["free_ram_after_mib"] = ram_now
                if vram_now is not None:
                    peak_vram_used = (
                        vram_now["used_mib"]
                        if peak_vram_used is None
                        else max(peak_vram_used, vram_now["used_mib"])
                    )
                    min_free_vram = (
                        vram_now["free_mib"]
                        if min_free_vram is None
                        else min(min_free_vram, vram_now["free_mib"])
                    )
                if ram_now is not None:
                    min_free_ram = ram_now if min_free_ram is None else min(min_free_ram, ram_now)

                gpu_only, ps_info = check_ps_gpu_only(ENDPOINT, chosen_model, timeout=3.0)
                if ps_info.get("resident"):
                    ps_size = ps_info.get("size")
                    ps_size_vram = ps_info.get("size_vram")
                if not gpu_only:
                    offload_seen = True

                p_eval = resp.get("prompt_eval_count")
                e_count = resp.get("eval_count")
                e_ns = resp.get("eval_duration")
                sample_row["prompt_eval_count"] = p_eval if isinstance(p_eval, int) else None
                sample_row["eval_count"] = e_count if isinstance(e_count, int) else None
                if isinstance(e_count, int) and isinstance(e_ns, int) and e_ns > 0:
                    rate = round(float(e_count) / (float(e_ns) / 1_000_000_000.0), 2)
                    sample_row["tok_per_s"] = rate
                    tok_rates.append(rate)

                raw_text = str(resp.get("response") or "")
                _parse_schema_response(raw_text, schema_cls)
                sample_row["schema_pass"] = True
            except (OSError, URLError, ValueError, TimeoutError, ValidationError) as exc:
                sample_row["latency_s"] = sample_row["latency_s"] or round(time.monotonic() - t0, 3)
                sample_row["error"] = f"{type(exc).__name__}: {exc}"
            report["samples"].append(sample_row)

        _unload_model(chosen_model)
        time.sleep(0.5)
        try:
            ps_after = _http_json(f"{ENDPOINT}/api/ps", timeout=3.0)
            unloaded = not (ps_after.get("models") or [])
        except (OSError, URLError, ValueError, TimeoutError):
            unloaded = None

        passed = sum(1 for row in report["samples"] if row["schema_pass"])
        baseline_used = baseline_vram["used_mib"] if baseline_vram else None
        model_peak_vram_delta = (
            max(0, peak_vram_used - baseline_used)
            if peak_vram_used is not None and baseline_used is not None
            else None
        )
        ps_vram_mib = round(ps_size_vram / (1024 * 1024), 1) if isinstance(ps_size_vram, int) else None
        report["summary"] = {
            "samples_total": len(SAMPLES),
            "samples_passed": passed,
            "schema_pass_rate": round(passed / len(SAMPLES), 3),
            "avg_tok_per_s": round(sum(tok_rates) / len(tok_rates), 2) if tok_rates else None,
            "peak_vram_used_mib": peak_vram_used,
            "model_vram_delta_mib": model_peak_vram_delta,
            "ps_vram_mib": ps_vram_mib,
            "min_free_vram_mib": min_free_vram,
            "min_free_ram_mib": min_free_ram,
            "cpu_offload_detected": offload_seen,
            "ps_size_bytes": ps_size,
            "ps_size_vram_bytes": ps_size_vram,
            "unloaded_cleanly": unloaded,
        }
        return report
    finally:
        if report.get("selected_model"):
            _unload_model(str(report["selected_model"]))
        if started_by_us and serve_proc is not None:
            terminate_process_tree(serve_proc.pid)


def render_markdown_report(report: dict[str, Any]) -> str:
    """Render honest benchmark Markdown report from measured JSON results."""
    base = report["baseline"]
    vram = base.get("vram_mib") or {}
    summary = report["summary"]
    lines = [
        "# Benchmark Ollama ~4B Local Router (R3.4 / 4b)",
        "",
        f"- Thời điểm đo: `{report['measured_at']}`",
        f"- Ollama CLI: `{report.get('ollama_executable') or 'null'}` (`{report.get('ollama_version') or 'null'}`)",
        f"- Endpoint headless: `{report['endpoint']}`",
        f"- Model được đo: `{report.get('selected_model') or 'null'}`",
        "",
        "## Phần cứng đo thực tế",
        "",
        "| Chỉ số | Giá trị đo thực |",
        "|---|---|",
        f"| VRAM tổng (`nvidia-smi`) | `{vram.get('total_mib', 'null')}` MiB |",
        f"| VRAM rảnh nền (`nvidia-smi`) | `{vram.get('free_mib', 'null')}` MiB |",
        f"| VRAM đang dùng nền (`nvidia-smi`) | `{vram.get('used_mib', 'null')}` MiB |",
        f"| RAM trống nền (`GlobalMemoryStatusEx`) | `{base.get('free_ram_mib', 'null')}` MiB |",
        "",
    ]

    if report.get("blocker_reason"):
        lines.extend([
            "## Trạng thái bị chặn / Chưa bật routing local",
            "",
            f"- Nguyên nhân: {report['blocker_reason']}",
        ])
        if report.get("pull_attempts"):
            lines.append("")
            lines.append("| Model thử | Thành công | Chi tiết |")
            lines.append("|---|---|---|")
            for attempt in report["pull_attempts"]:
                lines.append(
                    f"| `{attempt['model']}` | `{attempt['ok']}` | `{attempt['detail'] or '—'}` |"
                )
        lines.extend([
            "",
            "- Quyết định: Giữ `local_llm` ở trạng thái **tắt** (`enabled: false`), mọi tác vụ vẫn đi qua OmniRoute.",
            "",
        ])
        return "\n".join(lines)

    lines.extend([
        "## Tổng hợp đo 6 mẫu tiếng Việt (`num_ctx: 4096`, `keep_alive: 0`)",
        "",
        "| Chỉ số | Giá trị |",
        "|---|---|",
        f"| Mẫu đạt schema Pydantic | `{summary['samples_passed']}/{summary['samples_total']}` (`{summary['schema_pass_rate']}`) |",
        f"| Tốc độ trung bình | `{summary['avg_tok_per_s']}` tok/s |",
        f"| VRAM tổng đỉnh lúc chạy | `{summary['peak_vram_used_mib']}` MiB |",
        f"| VRAM model theo `/api/ps` | `{summary['ps_vram_mib']}` MiB (`size_vram={summary['ps_size_vram_bytes']}`, `size={summary['ps_size_bytes']}`) |",
        f"| VRAM rảnh tối thiểu | `{summary['min_free_vram_mib']}` MiB |",
        f"| RAM trống tối thiểu | `{summary['min_free_ram_mib']}` MiB |",
        f"| CPU offload ngầm (`/api/ps`) | `{summary['cpu_offload_detected']}` |",
        f"| Đã unload sạch (`keep_alive: 0`) | `{summary['unloaded_cleanly']}` |",
        "",
        "## Chi tiết 6 mẫu tiếng Việt",
        "",
        "| ID | Task | Schema Pass | Latency (s) | Prompt Tok | Eval Tok | tok/s | Lỗi |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ])
    for row in report["samples"]:
        lines.append(
            f"| `{row['id']}` | `{row['task']}` | `{row['schema_pass']}` | "
            f"`{row['latency_s']}` | `{row['prompt_eval_count']}` | `{row['eval_count']}` | "
            f"`{row['tok_per_s']}` | `{row['error'] or '—'}` |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark local Ollama ~4B model for PYH R3.4.")
    parser.add_argument(
        "--json-out",
        type=Path,
        default=REPO_ROOT / "cache" / "ollama-r34-benchmark.json",
    )
    parser.add_argument(
        "--md-out",
        type=Path,
        default=REPO_ROOT / "docs" / "reference" / "ollama-r34-benchmark.md",
    )
    parser.add_argument("--pull-timeout", type=float, default=300.0)
    parser.add_argument("--gen-timeout", type=float, default=120.0)
    args = parser.parse_args()

    report = run_benchmark(
        pull_timeout_s=args.pull_timeout,
        gen_timeout_s=args.gen_timeout,
    )
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.md_out.parent.mkdir(parents=True, exist_ok=True)
    args.md_out.write_text(render_markdown_report(report), encoding="utf-8")
    print(json.dumps({"selected_model": report["selected_model"], "summary": report["summary"], "blocker_reason": report["blocker_reason"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
