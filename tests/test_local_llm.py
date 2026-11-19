"""Tests for bounded Ollama ~4B local router, resource guards, and single OmniRoute fallback."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from healthvideo.local_llm import (
    LOCAL_ALLOWED_TASKS,
    NEVER_LOCAL_ROLES,
    ChatStatusSummary,
    LocalFeedbackAnalysis,
    LocalLLMConfig,
    TopicDedupeHint,
    load_local_llm_config,
    route_local_or_fallback,
    try_local_task,
)
from healthvideo.storage.files import write_yaml_atomic
from healthvideo.workflows.runner import gpu_mutex


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _make_urlopen(
    *,
    tags: list[str] | None = None,
    generate_response: dict | None = None,
    ps_models: list[dict] | None = None,
    captured_requests: list[tuple[str, dict | None]] | None = None,
    error_on: str | None = None,
):
    installed = tags if tags is not None else ["qwen3:4b"]

    def fake_urlopen(request, timeout: float = 5.0):
        url = request.full_url
        body = json.loads(request.data.decode("utf-8")) if request.data else None
        if captured_requests is not None:
            captured_requests.append((url, body))
        if error_on and url.endswith(error_on):
            raise TimeoutError("simulated timeout")
        if url.endswith("/api/tags"):
            return _FakeResponse({"models": [{"name": name, "model": name} for name in installed]})
        if url.endswith("/api/generate"):
            if body and body.get("prompt") == "":
                return _FakeResponse({"done": True})
            return _FakeResponse(generate_response or {})
        if url.endswith("/api/ps"):
            return _FakeResponse({"models": ps_models if ps_models is not None else []})
        raise AssertionError(f"Unexpected URL: {url}")

    return fake_urlopen


def test_hard_constants_and_never_local_roles_raise_value_error(tmp_path: Path) -> None:
    assert LOCAL_ALLOWED_TASKS == frozenset({
        "feedback_inbox",
        "chat_status_summary",
        "topic_dedupe_hint",
    })
    expected_never = frozenset({
        "medical_expert",
        "writer",
        "script_critic",
        "product_critic",
        "art_director",
        "storyboard_director",
        "editor",
        "repair_engineer",
        "coordinator_senior",
    })
    assert NEVER_LOCAL_ROLES == expected_never

    cfg = LocalLLMConfig(enabled=True)
    for role in expected_never:
        with pytest.raises(ValueError, match="cấm"):
            try_local_task(root=tmp_path, task="feedback_inbox", prompt="p", role=role, config=cfg)
        with pytest.raises(ValueError, match="cấm"):
            route_local_or_fallback(
                root=tmp_path,
                task="feedback_inbox",
                prompt="p",
                role=role,
                fallback=lambda: pytest.fail("fallback must not run on forbidden role"),
                config=cfg,
            )


def test_default_config_disabled_and_loopback_enforced(tmp_path: Path) -> None:
    default_cfg = load_local_llm_config(tmp_path)
    assert default_cfg.enabled is False

    with pytest.raises(ValueError):
        LocalLLMConfig(endpoint="http://192.168.1.50:11434")
    with pytest.raises(ValueError):
        LocalLLMConfig(allowed_tasks=("draft",))

    fallback_calls = 0

    def fallback() -> str:
        nonlocal fallback_calls
        fallback_calls += 1
        return "omniroute-ok"

    outcome = route_local_or_fallback(
        root=tmp_path,
        task="feedback_inbox",
        prompt="test",
        fallback=fallback,
    )
    assert outcome.used_local is False
    assert outcome.fallback_reason == "local_llm_disabled"
    assert outcome.fallback_result == "omniroute-ok"
    assert fallback_calls == 1


def test_disallowed_task_falls_back_once_without_calling_ollama(tmp_path: Path) -> None:
    cfg = LocalLLMConfig(enabled=True)
    fallback_calls = 0

    def fallback() -> str:
        nonlocal fallback_calls
        fallback_calls += 1
        return "omniroute"

    outcome = route_local_or_fallback(
        root=tmp_path,
        task="draft",
        prompt="test",
        fallback=fallback,
        config=cfg,
        urlopen_fn=lambda *a, **kw: pytest.fail("Ollama must not be called for disallowed task"),
    )
    assert outcome.used_local is False
    assert outcome.fallback_reason == "task_not_allowed"
    assert fallback_calls == 1


@pytest.mark.parametrize(
    ("vram", "ram", "tags", "expected_reason"),
    [
        (None, 16384, ["qwen3:4b"], "vram_probe_failed"),
        ({"free_mib": 4000, "total_mib": 12288, "used_mib": 8288}, 16384, ["qwen3:4b"], "insufficient_vram"),
        ({"free_mib": 9000, "total_mib": 12288, "used_mib": 3288}, 4096, ["qwen3:4b"], "insufficient_ram"),
        ({"free_mib": 9000, "total_mib": 12288, "used_mib": 3288}, 16384, ["llama3:8b"], "model_not_installed"),
    ],
)
def test_resource_and_model_preflight_guards_fall_back_once(
    tmp_path: Path, vram, ram, tags, expected_reason: str
) -> None:
    cfg = LocalLLMConfig(enabled=True, model="qwen3:4b", peak_vram_mib=3500)
    fallback_calls = 0

    def fallback() -> str:
        nonlocal fallback_calls
        fallback_calls += 1
        return "omniroute"

    outcome = route_local_or_fallback(
        root=tmp_path,
        task="chat_status_summary",
        prompt="status?",
        fallback=fallback,
        config=cfg,
        vram_probe=lambda: vram,
        ram_probe=lambda: ram,
        urlopen_fn=_make_urlopen(tags=tags),
    )
    assert outcome.used_local is False
    assert outcome.fallback_reason is not None and expected_reason in outcome.fallback_reason
    assert fallback_calls == 1


def test_gpu_worker_mutex_contention_falls_back_immediately(tmp_path: Path) -> None:
    cfg = LocalLLMConfig(enabled=True)
    fallback_calls = 0

    def fallback() -> str:
        nonlocal fallback_calls
        fallback_calls += 1
        return "omniroute"

    with gpu_mutex(tmp_path):
        outcome = route_local_or_fallback(
            root=tmp_path,
            task="chat_status_summary",
            prompt="status?",
            fallback=fallback,
            config=cfg,
            vram_probe=lambda: {"free_mib": 10000, "total_mib": 12288, "used_mib": 2288},
            ram_probe=lambda: 16384,
            urlopen_fn=lambda *a, **kw: pytest.fail("Ollama must not run while gpu_mutex is held"),
        )
    assert outcome.used_local is False
    assert outcome.fallback_reason == "gpu_worker_busy"
    assert fallback_calls == 1

    # Also honor explicit cache/gpu-worker file lock.
    worker_file = tmp_path / "cache/gpu-worker"
    worker_file.parent.mkdir(parents=True, exist_ok=True)
    with worker_file.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            outcome2 = route_local_or_fallback(
                root=tmp_path,
                task="chat_status_summary",
                prompt="status?",
                fallback=fallback,
                config=cfg,
                vram_probe=lambda: {"free_mib": 10000, "total_mib": 12288, "used_mib": 2288},
                ram_probe=lambda: 16384,
            )
            assert outcome2.used_local is False
            assert outcome2.fallback_reason == "gpu_worker_busy"
            assert fallback_calls == 2
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def test_cpu_offload_and_bad_schema_discard_local_and_fallback_once(tmp_path: Path) -> None:
    cfg = LocalLLMConfig(enabled=True, model="qwen3:4b", peak_vram_mib=3000)
    fallback_calls = 0

    def fallback() -> str:
        nonlocal fallback_calls
        fallback_calls += 1
        return "omniroute"

    # CPU offload detected in /api/ps (size_vram < size)
    requests: list[tuple[str, dict | None]] = []
    outcome = route_local_or_fallback(
        root=tmp_path,
        task="feedback_inbox",
        prompt="classify",
        fallback=fallback,
        config=cfg,
        vram_probe=lambda: {"free_mib": 9000, "total_mib": 12288, "used_mib": 3288},
        ram_probe=lambda: 16384,
        urlopen_fn=_make_urlopen(
            tags=["qwen3:4b"],
            generate_response={"response": json.dumps({"summary": "ok", "tasks": [{"kind": "xuong", "target": "a", "request": "b", "done_when": "c"}]})},
            ps_models=[{"name": "qwen3:4b", "size": 3_000_000_000, "size_vram": 1_500_000_000}],
            captured_requests=requests,
        ),
    )
    assert outcome.used_local is False
    assert outcome.fallback_reason == "cpu_offload_detected"
    assert fallback_calls == 1
    # Verify num_ctx=4096 and keep_alive=0 were sent, and best-effort unload followed.
    gen_reqs = [body for url, body in requests if url.endswith("/api/generate") and body and body.get("prompt")]
    assert gen_reqs[0]["options"]["num_ctx"] == 4096
    assert gen_reqs[0]["keep_alive"] == 0

    # Invalid schema output -> discard local and fall back once
    outcome2 = route_local_or_fallback(
        root=tmp_path,
        task="feedback_inbox",
        prompt="classify",
        fallback=fallback,
        config=cfg,
        vram_probe=lambda: {"free_mib": 9000, "total_mib": 12288, "used_mib": 3288},
        ram_probe=lambda: 16384,
        urlopen_fn=_make_urlopen(
            tags=["qwen3:4b"],
            generate_response={"response": '{"summary": "missing tasks"}'},
            ps_models=[],
        ),
    )
    assert outcome2.used_local is False
    assert outcome2.fallback_reason is not None and "schema_validation_failed" in outcome2.fallback_reason
    assert fallback_calls == 2


def test_local_success_for_all_three_allowed_tasks_skips_fallback(tmp_path: Path) -> None:
    write_yaml_atomic(
        tmp_path / "profiles/local-llm.yaml",
        {"enabled": True, "model": "qwen3:4b", "peak_vram_mib": 3200},
    )
    cfg = load_local_llm_config(tmp_path)
    assert cfg.enabled is True

    samples = [
        (
            "feedback_inbox",
            LocalFeedbackAnalysis,
            {"summary": "Đổi prompt", "tasks": [{"kind": "xuong", "target": "prompts/draft.md", "request": "Sửa", "done_when": "Test pass"}]},
        ),
        (
            "chat_status_summary",
            ChatStatusSummary,
            {"reply": "Dự án đang chờ duyệt y khoa.", "action": "status", "escalate": False, "highlights": ["Awaiting PIN"]},
        ),
        (
            "topic_dedupe_hint",
            TopicDedupeHint,
            {"is_potential_duplicate": True, "matched_slug": "men-gan-tang", "confidence": 0.91, "reason": "Trùng cơ chế"},
        ),
    ]
    for task, expected_cls, payload in samples:
        requests: list[tuple[str, dict | None]] = []
        outcome = route_local_or_fallback(
            root=tmp_path,
            task=task,
            prompt="prompt",
            role="feedback_analyst",
            fallback=lambda: pytest.fail("fallback must not run when local succeeds"),
            config=cfg,
            vram_probe=lambda: {"free_mib": 9000, "total_mib": 12288, "used_mib": 3288},
            ram_probe=lambda: 16384,
            urlopen_fn=_make_urlopen(
                tags=["qwen3:4b"],
                generate_response={
                    "response": json.dumps(payload, ensure_ascii=False),
                    "prompt_eval_count": 120,
                    "eval_count": 48,
                    "eval_duration": 1_000_000_000,
                },
                ps_models=[{"name": "qwen3:4b", "size": 2_800_000_000, "size_vram": 2_800_000_000}],
                captured_requests=requests,
            ),
        )
        assert outcome.used_local is True
        assert isinstance(outcome.data, expected_cls)
        assert outcome.attempt is not None
        assert outcome.attempt.eval_tok_per_s == 48.0
        assert outcome.attempt.total_tokens == 168
        # Verify keep_alive: 0 unload followed when /api/ps showed resident model.
        unload_reqs = [body for url, body in requests if url.endswith("/api/generate") and body and body.get("prompt") == ""]
        assert len(unload_reqs) == 1 and unload_reqs[0]["keep_alive"] == 0
