"""Tests for Company 2.0 parallel execution, gpu_mutex, voice_prep merge, and Leader chat."""

import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.agents import AgentResult
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.pronunciation import PronunciationEntry, PronunciationLexicon
from healthvideo.domain.script import Script
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.queue import load_queue
from healthvideo.tts.pronunciation import apply_pronunciation, pronunciation_hash
from healthvideo.workflows import (
    chat,
    researcher,
    shorts_plan,
    storyboard_design,
    voice_prep,
)
from healthvideo.workflows.draft import submit_script_draft
from healthvideo.workflows.factory_deps import read_state, reject_note
from healthvideo.workflows.gate_review import approve_gate, check_revision_posts
from healthvideo.workflows.runner import RunDeps, gpu_mutex, run_queue
from tests.helpers import (
    create_long_form_project_fixture,
    create_v2_project_fixture,
    write_posts_fixture,
)
from tests.workflows.test_draft import SOURCE, _evidence_ready


def test_storyboard_ready_requires_estimated_layout_preflight(tmp_path, monkeypatch):
    project = create_v2_project_fixture(tmp_path / 'projects')

    def fail_preflight(*args, **kwargs):
        raise ValueError('Estimated layout precheck failed: visual budget')

    monkeypatch.setattr(storyboard_design, 'validate_estimated_layout', fail_preflight)
    assert not storyboard_design.storyboard_ready(project)


@pytest.mark.parametrize('change', ['approval', 'retry', 'new_topic'])
def test_dispatches_newly_ready_topic_while_another_is_running(tmp_path, monkeypatch, change):
    from healthvideo.domain.queue import QueueEntry
    from healthvideo.workflows import runner

    entries = [QueueEntry(slug=slug, title=slug, question='Fixture?', added='2026-11-15')
               for slug in ('slow-topic', 'ready-topic')]
    queue = tmp_path / 'topics/queue.yaml'
    write_yaml_atomic(queue, {'version': 1, 'entries': [e.model_dump(mode='json') for e in entries]})
    control = (tmp_path / 'projects/ready-topic/project.yaml' if change == 'approval'
               else tmp_path / 'topics/logs/ready-topic/agent-retry.yaml')
    write_yaml_atomic(control, {'status': 'held'})
    slow_started = threading.Event()
    checked = threading.Event()
    dispatched = threading.Event()
    release = threading.Event()
    calls = []
    failures = []

    def run_topic(root, deps, entry, report, **kwargs):
        calls.append(entry.slug)
        if entry.slug == 'slow-topic':
            slow_started.set()
            assert release.wait(8)
        elif entry.slug == 'new-topic' or (read_yaml(control).get('status') == 'ready'):
            dispatched.set()
        else:
            checked.set()
        return False

    monkeypatch.setattr(runner, '_run_topic', run_topic)

    def dispatch():
        try:
            run_queue(tmp_path, object(), max_parallel_topics=2)
        except (AssertionError, OSError, ValueError, RuntimeError) as error:
            failures.append(error)

    thread = threading.Thread(target=dispatch)
    thread.start()
    try:
        assert slow_started.wait(2)
        assert checked.wait(2)
        # Allow the first ready-topic invocation to finish before changing its input.
        time.sleep(0.1)
        if change == 'new_topic':
            new = QueueEntry(slug='new-topic', title='New', question='Fixture?', added='2026-11-15')
            write_yaml_atomic(queue, {'version': 1, 'entries': [e.model_dump(mode='json') for e in [*entries, new]]})
        else:
            write_yaml_atomic(control, {'status': 'ready'})
        assert dispatched.wait(3), 'Ready work waited for the unrelated slow topic'
        time.sleep(0.1)
        assert calls.count('slow-topic') == 1
        assert calls.count('ready-topic') == (1 if change == 'new_topic' else 2)
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert failures == []


@pytest.mark.parametrize('granular', [False, True])
def test_submit_script_draft_then_parallel_storyboard_and_voice_prep_before_critic(
    tmp_path: Path, monkeypatch, granular,
):
    from healthvideo.workflows import storyboard_parts

    project_dir = _evidence_ready(tmp_path / "projects")
    manifest = submit_script_draft(
        project_dir,
        SOURCE / "script/script.yaml",
    )
    assert manifest.state is WorkflowState.DRAFT_READY
    assert not (project_dir / "revisions/001/storyboard/storyboard.yaml").is_file()
    assert not (project_dir / "revisions/001/script/voice-prep.yaml").is_file()
    if not granular:
        # Existing incomplete monolithic projects keep the legacy submit transaction.
        write_yaml_atomic(project_dir / 'revisions/001/storyboard/storyboard.yaml',
                          {'title': 'Legacy incomplete board', 'scenes': []})

    slug = project_dir.name
    write_yaml_atomic(
        tmp_path / "topics/queue.yaml",
        {
            "version": 1,
            "entries": [
                {"slug": slug, "title": "Draft Split", "question": "Q?", "added": "2026-11-15"}
            ],
        },
    )

    observed_steps: list[str] = []
    lock = threading.Lock()
    active_parallel = 0
    max_parallel = 0
    prepared_revision = threading.Event()
    voice_saving = threading.Event()
    voice_saved = threading.Event()
    promote_revision = storyboard_design.replace_directory_atomic

    def promote_after_voice_starts(staging, revision):
        prepared_revision.set()
        assert voice_saving.wait(5)
        assert not voice_saved.wait(0.2)
        promote_revision(staging, revision)

    monkeypatch.setattr(storyboard_design, "replace_directory_atomic", promote_after_voice_starts)
    validate_parts = storyboard_parts._validation_error

    def validate_after_voice_starts(root):
        prepared_revision.set()
        assert voice_saving.wait(5)
        assert not voice_saved.wait(0.2)
        return validate_parts(root)

    monkeypatch.setattr(storyboard_parts, '_validation_error', validate_after_voice_starts)

    def fake_invoke(slots, prompt, **kwargs):
        nonlocal active_parallel, max_parallel
        step = kwargs["step"]
        with lock:
            observed_steps.append(step)
            if step in {"storyboard_design", "voice_prep"}:
                active_parallel += 1
                max_parallel = max(max_parallel, active_parallel)
        if step in {"storyboard_design", "voice_prep"}:
            time.sleep(0.08)
        with lock:
            if step in {"storyboard_design", "voice_prep"}:
                active_parallel -= 1
        if step == "storyboard_design":
            if granular:
                revision = project_dir / 'revisions/001'
                board = read_yaml(SOURCE / 'storyboard/storyboard.yaml')
                write_yaml_atomic(revision / storyboard_parts.METADATA,
                                  {k: v for k, v in board.items() if k != 'scenes'})
                hashes = storyboard_parts.script_hashes(revision)
                for index, scene in enumerate(board['scenes'], 1):
                    scene_id = f'S{index:02}'
                    write_yaml_atomic(revision / f'storyboard/parts/{scene_id}.yaml',
                                      scene | {'id': scene_id, 'script_sha256': hashes[scene_id]})
                write_yaml_atomic(revision / 'assets/asset-manifest.yaml',
                                  read_yaml(SOURCE / 'assets/asset-manifest.yaml'))
            else:
                storyboard_design.submit_storyboard_design(
                    project_dir,
                    SOURCE / "storyboard/storyboard.yaml",
                    SOURCE / "assets/asset-manifest.yaml",
                )
        elif step == "voice_prep":
            vp_file = tmp_path / "vp.yaml"
            write_yaml_atomic(
                vp_file,
                {
                    "schema_version": "1.0",
                    "pronunciations": [{"written": "HbA1c", "spoken": "hát bê a một xê"}],
                    "pacing_notes": ["Nghỉ nhẹ sau số liệu"],
                },
            )
            assert prepared_revision.wait(5)
            voice_saving.set()
            voice_prep.save_voice_prep(project_dir, vp_file)
            voice_saved.set()
        elif step == "script_review":
            write_yaml_atomic(
                project_dir / "revisions/001/reviews/script-review.yaml",
                {
                    "schema_version": "1.0",
                    "action": "submit_medical",
                    "reason": "Đạt",
                    "issues": [],
                    "checked": ["Claim khớp ledger"],
                    "decisions": [],
                },
            )
        return AgentResult("fake", True, False, kwargs["log_dir"] / f"{step}.log")

    def fake_create(root, entry):
        return project_dir

    deps = RunDeps(
        create_project=fake_create,
        read_state=read_state,
        reject_note=reject_note,
        python_steps={},
        changed_code_paths=lambda _: [],
        invoke=fake_invoke,
        storyboard_ready=storyboard_design.storyboard_ready,
        voice_prep_ready=voice_prep.voice_prep_ready,
        shorts_plan_ready=shorts_plan.shorts_plan_ready,
        parallel_branches=True,
    )

    run_queue(tmp_path, deps, once=True)
    assert "storyboard_design" in observed_steps
    assert "voice_prep" in observed_steps
    assert max_parallel == 2
    assert storyboard_design.storyboard_ready(project_dir)
    assert voice_prep.voice_prep_ready(project_dir)


def test_post_medical_parallel_branches_and_gpu_mutex_exclusivity(tmp_path: Path):
    proj_a = create_long_form_project_fixture(tmp_path / "projects")
    approve_gate(proj_a, GateKind.MEDICAL, reviewer="BS Nguyễn Văn An", now=datetime.now(UTC))
    (proj_a / "revisions/001/posts/posts.yaml").unlink(missing_ok=True)
    slug = proj_a.name
    write_yaml_atomic(
        tmp_path / "topics/queue.yaml",
        {
            "version": 1,
            "entries": [
                {"slug": slug, "title": "Parallel Post Med", "question": "Q?", "added": "2026-11-15"}
            ],
        },
    )

    ran_steps: list[str] = []
    lock = threading.Lock()
    concurrent_branches = 0
    max_concurrent = 0

    def fake_invoke(slots, prompt, **kwargs):
        nonlocal concurrent_branches, max_concurrent
        step = kwargs["step"]
        with lock:
            ran_steps.append(step)
            concurrent_branches += 1
            max_concurrent = max(max_concurrent, concurrent_branches)
        time.sleep(0.08)
        with lock:
            concurrent_branches -= 1
        if step == "posts":
            write_posts_fixture(proj_a / "revisions/001")
        elif step == "shorts_plan":
            sp_file = tmp_path / "shorts-plan.yaml"
            write_yaml_atomic(
                sp_file,
                {
                    "schema_version": "1.0",
                    "clips": [
                        {
                            "id": "CL01",
                            "title": "Hook ngắn",
                            "hook_text": "Sự thật về ăn mặn",
                            "start_scene_id": "S01",
                            "end_scene_id": "S02",
                            "target_seconds": 60,
                            "caption": "Giảm muối giúp kiểm soát huyết áp [claim:C01].",
                            "safety_caveat": "Không tự ý ngưng thuốc khi chưa hỏi bác sĩ.",
                            "safe_zone_checked": True,
                        }
                    ],
                },
            )
            shorts_plan.save_shorts_plan(proj_a, sp_file)
        return AgentResult("fake", True, False, kwargs["log_dir"] / f"{step}.log")

    def fake_produce(project_dir: Path) -> None:
        nonlocal concurrent_branches, max_concurrent
        with lock:
            ran_steps.append("produce")
            concurrent_branches += 1
            max_concurrent = max(max_concurrent, concurrent_branches)
        time.sleep(0.08)
        with lock:
            concurrent_branches -= 1
        manifest = read_yaml(project_dir / "project.yaml")
        write_yaml_atomic(
            project_dir / "project.yaml",
            {**manifest, "state": WorkflowState.AWAITING_VIDEO_REVIEW.value},
        )

    deps = RunDeps(
        create_project=lambda root, entry: proj_a,
        read_state=read_state,
        reject_note=reject_note,
        python_steps={"produce": fake_produce},
        changed_code_paths=lambda _: [],
        invoke=fake_invoke,
        posts_ready=lambda p: not check_revision_posts(p / "revisions/001", require_medical_approval=True),
        shorts_plan_ready=shorts_plan.shorts_plan_ready,
        parallel_branches=True,
    )

    report = run_queue(tmp_path, deps, once=True)
    assert set(ran_steps) == {"posts", "shorts_plan", "produce"}
    assert max_concurrent >= 2
    assert report.advanced == [slug]
    report_gate = run_queue(tmp_path, deps, once=False)
    assert report_gate.at_gate == [slug]

    # Verify gpu_mutex enforces strict mutual exclusion across threads.
    gpu_active = 0
    gpu_max = 0
    gpu_lock = threading.Lock()

    def worker():
        nonlocal gpu_active, gpu_max
        with gpu_mutex(tmp_path):
            with gpu_lock:
                gpu_active += 1
                gpu_max = max(gpu_max, gpu_active)
            time.sleep(0.05)
            with gpu_lock:
                gpu_active -= 1

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert gpu_max == 1


def test_voice_prep_lexicon_merge_changes_pronunciation_and_hash(tmp_path: Path):
    project_dir = _evidence_ready(tmp_path / "projects")
    rev = project_dir / "revisions/001"
    script_data = read_yaml(SOURCE / "script/script.yaml")
    write_yaml_atomic(rev / "script/script.yaml", script_data)
    Script.model_validate(script_data)

    vp_file = tmp_path / "vp.yaml"
    write_yaml_atomic(
        vp_file,
        {
            "schema_version": "1.0",
            "pronunciations": [
                {"written": "huyết áp", "spoken": "huyết-áp"},
            ],
        },
    )
    voice_prep.save_voice_prep(project_dir, vp_file)

    base = PronunciationLexicon(
        schema_version="1.0",
        language="vi",
        version="1.0",
        entries=(PronunciationEntry(written="mg/dL", spoken="mi li gam trên đề xi lít"),),
    )
    merged = voice_prep.load_voice_prep_lexicon(rev, base)
    assert len(merged.entries) == 2
    assert any(entry.written == "huyết áp" for entry in merged.entries)
    assert "huyết-áp" in apply_pronunciation("Đo huyết áp và mg/dL", merged)
    assert pronunciation_hash(merged) != pronunciation_hash(base)


def test_leader_coordinator_dispatch_auto_executes_safe_ops_and_holds_approved_gate(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(chat, "start", lambda *a: None)

    # Seed an inbox dossier to promote safely via Leader dispatch.
    def fake_fetcher(url: str) -> str:
        if "gid=728612942" in url:
            return (
                "phát_ngôn,câu_hỏi_kiểm_chứng,điểm_tranh_cãi,điểm_giáo_dục,độ_chắc_chắn,khả_năng_video,"
                "PMID_DOI,điểm_cần_bác_sĩ_duyệt,hook_trung_lập\n"
                "Uống trà xanh mỗi sáng,Trà xanh ảnh hưởng huyết áp ra sao?,4/5,4/5,4/5,4/5,"
                "PMID 888,Lưu ý tương tác thuốc,Trà xanh buổi sáng có tốt cho tim mạch?\n"
            )
        return ""

    sync_res = researcher.sync_reference_sheet(tmp_path, fetcher=fake_fetcher)
    inbox_slug = sync_res["items"][0]["slug"]

    # 1. Safe Leader dispatch auto-executes immediately.
    msg1 = chat.post(tmp_path, None, "Đưa chủ đề trà xanh vào queue giúp tôi", {})

    def invoke_safe(slots, prompt, **kwargs):
        assert "company_summary" in prompt
        write_yaml_atomic(
            kwargs["log_dir"] / f"{msg1['id']}.yaml",
            {
                "reply": "Đã giao Researcher kiểm tra và đưa chủ đề vào hàng đợi.",
                "action": "dispatch",
                "assignments": [
                    {
                        "role": "researcher",
                        "step": "promote_inbox_topic",
                        "task": "Đưa chủ đề vào queue",
                        "action": "promote_inbox_topic",
                        "inbox_slug": inbox_slug,
                    }
                ],
            },
        )
        return AgentResult("fake", True, False, kwargs["log_dir"] / "coord.log")

    res1 = chat.run_coordinator(tmp_path, msg1["id"], invoke=invoke_safe)
    assert res1["status"] == "done"
    assert len(res1["execution_results"]) == 1
    assert [e.slug for e in load_queue(tmp_path)] == [inbox_slug]

    # 2. Target project in MEDICALLY_APPROVED must stay pending until doctor confirms.
    approved_proj = create_v2_project_fixture(tmp_path / "projects", state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    approve_gate(approved_proj, GateKind.MEDICAL, reviewer="BS Nguyễn Văn An", now=datetime.now(UTC))
    msg2 = chat.post(tmp_path, approved_proj.name, "Sửa kịch bản đoạn mở đầu", {})

    def invoke_gate(slots, prompt, **kwargs):
        write_yaml_atomic(
            kwargs["log_dir"] / f"{msg2['id']}.yaml",
            {
                "reply": "Dự án đã qua cổng y khoa; xin bác sĩ xác nhận mở lại để sửa.",
                "action": "dispatch",
                "assignments": [
                    {
                        "role": "writer",
                        "step": "revise_medical",
                        "task": "Sửa mở đầu",
                        "slug": approved_proj.name,
                        "action": "edit_script",
                        "brief": "Chỉnh lại câu mở đầu cho gọn hơn.",
                    }
                ],
            },
        )
        return AgentResult("fake", True, False, kwargs["log_dir"] / "coord2.log")

    res2 = chat.run_coordinator(tmp_path, msg2["id"], invoke=invoke_gate)
    assert res2["status"] == "pending"
    assert not list(approved_proj.rglob("*-requested.yaml"))
    confirmed = chat.confirm(tmp_path, approved_proj.name, res2["id"])
    assert confirmed["status"] == "done"
    assert list(approved_proj.rglob("*-requested.yaml"))
    assert not (approved_proj / "revisions/001/reviews/medical-approval.yaml").exists()
    assert not (approved_proj / "revisions/001/reviews/video-approval.yaml").exists()
    assert list(approved_proj.rglob("*-superseded-approval.yaml"))


def test_maker_slots_for_critic_uses_latest_per_role_and_falls_back_to_primary_author(tmp_path):
    import json

    from healthvideo.agents import ACTIVITY_FILE
    from healthvideo.company import Company, ModelSlot, Role
    from healthvideo.workflows.runner import _maker_slots_for_critic

    slot_a = ModelSlot(cli="agy", model="model-a")
    slot_b = ModelSlot(cli="codex", model="model-b")
    slot_c = ModelSlot(cli="agy", model="model-c")
    company = Company(
        roles={
            "script_critic": Role(
                id="script_critic",
                name="Kiểm duyệt kịch bản",
                tier="hard",
                skills=("pyh-script-critic",),
                steps=("script_review",),
                models=(slot_a, slot_b, slot_c),
            ),
        },
        tiers={"hard": (slot_a, slot_b, slot_c)},
    )
    act_path = tmp_path / ACTIVITY_FILE
    act_path.parent.mkdir(parents=True, exist_ok=True)

    # (a) 3 historical writer runs on 3 models + storyboard_director -> excludes only latest writer (slot_b) + latest storyboard_director (slot_a), leaving slot_c
    rows_a = [
        {"slug": "topic-a", "role": "writer", "ok": True, "cli": slot_a.cli, "model": slot_a.model},
        {"slug": "topic-a", "role": "writer", "ok": True, "cli": slot_c.cli, "model": slot_c.model},
        {"slug": "topic-a", "role": "writer", "ok": True, "cli": slot_b.cli, "model": slot_b.model},
        {"slug": "topic-a", "role": "storyboard_director", "ok": True, "cli": slot_a.cli, "model": slot_a.model},
    ]
    act_path.write_text("\n".join(json.dumps(r) for r in rows_a) + "\n", encoding="utf-8")
    excluded_a = _maker_slots_for_critic(tmp_path, "topic-a", "script_critic", company=company)
    assert set(excluded_a) == {slot_b, slot_a}
    assert [s for s in company.chain("script_critic") if s not in excluded_a] == [slot_c]

    # (b) writer + storyboard_director occupy all models in script_critic's chain -> excludes all maker models (no fallback to maker)
    company_two = Company(
        roles={
            "script_critic": Role(
                id="script_critic",
                name="Kiểm duyệt kịch bản",
                tier="hard",
                skills=("pyh-script-critic",),
                steps=("script_review",),
                models=(slot_a, slot_b),
            ),
        },
        tiers={"hard": (slot_a, slot_b)},
    )
    rows_b = [
        {"slug": "topic-b", "role": "writer", "ok": True, "cli": slot_b.cli, "model": slot_b.model},
        {"slug": "topic-b", "role": "storyboard_director", "ok": True, "cli": slot_a.cli, "model": slot_a.model},
    ]
    act_path.write_text("\n".join(json.dumps(r) for r in rows_b) + "\n", encoding="utf-8")
    excluded_b = _maker_slots_for_critic(tmp_path, "topic-b", "script_critic", company=company_two)
    assert set(excluded_b) == {slot_b, slot_a}
    remaining_b = [s for s in company_two.chain("script_critic") if s not in excluded_b]
    assert remaining_b == []


def test_maker_slots_for_critic_skips_malformed_rows_and_resets_after_critic(tmp_path: Path):
    import json

    from healthvideo.agents import ACTIVITY_FILE
    from healthvideo.company import Company, ModelSlot, Role
    from healthvideo.workflows.runner import _maker_slots_for_critic

    slot_a = ModelSlot(cli="agy", model="model-a")
    slot_b = ModelSlot(cli="codex", model="model-b")
    slot_c = ModelSlot(cli="agy", model="model-c")
    company = Company(
        roles={
            "script_critic": Role(
                id="script_critic",
                name="Kiểm duyệt kịch bản",
                tier="hard",
                skills=("pyh-script-critic",),
                steps=("script_review",),
                models=(slot_a, slot_b, slot_c),
            ),
        },
        tiers={"hard": (slot_a, slot_b, slot_c)},
    )
    act_path = tmp_path / ACTIVITY_FILE
    act_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "{not-json",
        json.dumps({"slug": "topic-c", "role": "writer", "ok": True, "cli": "ollama", "model": "qwen3"}),
        json.dumps({"slug": "topic-c", "role": "storyboard_director", "ok": True, "cli": slot_a.cli, "model": slot_a.model}),
        json.dumps({"slug": "topic-c", "role": "script_critic", "ok": True, "cli": slot_b.cli, "model": slot_b.model}),
        json.dumps({"slug": "topic-c", "role": "writer", "ok": True, "cli": slot_c.cli, "model": slot_c.model}),
    ]
    act_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert _maker_slots_for_critic(tmp_path, "topic-c", "script_critic", company=company) == (slot_c,)


def test_gpu_mutex_is_thread_reentrant_and_mutually_exclusive(tmp_path: Path):
    entered_nested = False
    with gpu_mutex(tmp_path), gpu_mutex(tmp_path):
        entered_nested = True
    assert entered_nested

    concurrent = 0
    max_concurrent = 0
    guard = threading.Lock()

    def thread_worker():
        nonlocal concurrent, max_concurrent
        with gpu_mutex(tmp_path), gpu_mutex(tmp_path):
            with guard:
                concurrent += 1
                max_concurrent = max(max_concurrent, concurrent)
            time.sleep(0.05)
            with guard:
                concurrent -= 1

    workers = [threading.Thread(target=thread_worker) for _ in range(3)]
    for th in workers:
        th.start()
    for th in workers:
        th.join()
    assert max_concurrent == 1


def test_parallel_branches_aggregates_errors_and_preserves_waiting_model_step(
    tmp_path: Path, monkeypatch
):
    from datetime import timedelta

    from healthvideo.agents import AllAgentsExhausted
    from healthvideo.storage.files import canonical_json_hash

    proj = create_v2_project_fixture(tmp_path / "projects", state=WorkflowState.DRAFT_READY)
    slug = proj.name
    write_yaml_atomic(
        tmp_path / "topics/queue.yaml",
        {
            "version": 1,
            "entries": [
                {"slug": slug, "title": "Parallel Fail", "question": "Q?", "added": "2026-11-18"}
            ],
        },
    )
    (proj / "revisions/001/script/voice-prep.yaml").unlink(missing_ok=True)
    monkeypatch.setattr(
        storyboard_design,
        "validate_estimated_layout",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ValueError("Estimated layout precheck failed: whiteboard_svg outside 11-14%")
        ),
    )

    def invoke_both_invalid(slots, prompt, **kwargs):
        del slots, prompt
        step = kwargs["step"]
        if step == "voice_prep":
            vp_path = proj / "revisions/001/script/voice-prep.yaml"
            script_data = read_yaml(proj / "revisions/001/script/script.yaml")
            sheet = voice_prep.VoicePrepSheet(
                script_hash="0" * 64 if canonical_json_hash(script_data) != "0" * 64 else "1" * 64,
                notes="mismatched",
            )
            write_yaml_atomic(vp_path, sheet.model_dump(mode="json"))
        return AgentResult("fake", True, False, kwargs["log_dir"] / f"{step}.log")

    deps = RunDeps(
        create_project=lambda root, entry: proj,
        read_state=read_state,
        reject_note=reject_note,
        python_steps={},
        changed_code_paths=lambda _: [],
        invoke=invoke_both_invalid,
        expert_brief_ready=lambda _: True,
        storyboard_ready=storyboard_design.storyboard_ready,
        voice_prep_ready=voice_prep.voice_prep_ready,
        parallel_branches=True,
    )
    report = run_queue(tmp_path, deps, once=True)
    assert report.blocked == [slug]
    blocked_text = (tmp_path / "topics/logs" / slug / "blocked.txt").read_text(encoding="utf-8")
    assert "Estimated layout precheck failed" in blocked_text
    assert "voice-prep.yaml script_hash lệch" in blocked_text
    retry_data = read_yaml(tmp_path / "topics/logs" / slug / "agent-retry.yaml")
    assert "Estimated layout precheck failed" in retry_data["steps"]["storyboard_design"]["reason"]
    assert "voice-prep.yaml script_hash lệch" in retry_data["steps"]["voice_prep"]["reason"]

    # Sibling branch succeeding in post-medical fan-out must NOT wipe waiting-model-step.yaml of a quota-hit branch.
    root2 = tmp_path / "fanout-quota"
    proj2 = create_v2_project_fixture(root2 / "projects", state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    approve_gate(proj2, GateKind.MEDICAL, reviewer="BS An", now=datetime.now(UTC))
    (proj2 / "revisions/001/posts/posts.yaml").unlink(missing_ok=True)
    slug2 = proj2.name
    write_yaml_atomic(
        root2 / "topics/queue.yaml",
        {
            "version": 1,
            "entries": [
                {"slug": slug2, "title": "Quota Fanout", "question": "Q?", "added": "2026-11-18"}
            ],
        },
    )

    def invoke_quota_branch(slots, prompt, **kwargs):
        del slots, prompt
        step = kwargs["step"]
        if step == "posts":
            time.sleep(0.08)
            write_posts_fixture(proj2 / "revisions/001")
            return AgentResult("fake", True, False, kwargs["log_dir"] / "posts.log")
        raise AllAgentsExhausted(datetime.now(UTC) + timedelta(minutes=15))

    deps2 = RunDeps(
        create_project=lambda root, entry: proj2,
        read_state=read_state,
        reject_note=reject_note,
        python_steps={"produce": lambda p: None},
        changed_code_paths=lambda _: [],
        invoke=invoke_quota_branch,
        posts_ready=lambda p: not check_revision_posts(p / "revisions/001", require_medical_approval=True),
        shorts_plan_ready=lambda p: (p / "revisions/001/posts/shorts-plan.yaml").is_file(),
        parallel_branches=True,
    )
    report2 = run_queue(root2, deps2, once=True)
    assert report2.waiting_model == [slug2]
    assert report2.blocked == []
    resume = read_yaml(root2 / "topics/logs" / slug2 / "waiting-model-step.yaml")
    assert resume["step"] == "shorts_plan"


def test_unchanged_state_diagnostics_surface_exact_causes_across_steps(tmp_path: Path):
    from healthvideo.workflows.gate_review import POSTS_ARTIFACT

    # 1. draft fails M6.4 final outro mismatch -> exact cause in blocked.txt + agent-retry.yaml
    root1 = tmp_path / "draft-outro"
    proj1 = _evidence_ready(root1 / "projects")
    slug1 = proj1.name
    rev1 = proj1 / "revisions/001"
    (rev1 / "evidence/expert-brief.md").parent.mkdir(parents=True, exist_ok=True)
    (rev1 / "evidence/expert-brief.md").write_text("# Brief\n", encoding="utf-8")
    write_yaml_atomic(
        root1 / "topics/queue.yaml",
        {
            "version": 1,
            "entries": [{"slug": slug1, "title": "Draft Outro", "question": "Q?", "added": "2026-11-18"}],
        },
    )

    def invoke_bad_outro(slots, prompt, **kwargs):
        del slots, prompt
        write_yaml_atomic(
            rev1 / "script/script.yaml",
            {
                "schema_version": "1.0",
                "title": "Test",
                "format_profile": "hook_outro_v1",
                "lines": [
                    {"id": "N01", "text": "Mở đầu.", "purpose": "content"},
                    {"id": "N99", "text": "Outro tự chế sai text.", "purpose": "outro"},
                ],
            },
        )
        return AgentResult("fake", True, False, kwargs["log_dir"] / "draft.log")

    deps1 = RunDeps(
        create_project=lambda root, entry: proj1,
        read_state=read_state,
        reject_note=reject_note,
        python_steps={},
        changed_code_paths=lambda _: [],
        invoke=invoke_bad_outro,
        expert_brief_ready=lambda _: True,
    )
    report1 = run_queue(root1, deps1, once=True)
    assert report1.blocked == [slug1]
    blocked1 = (root1 / "topics/logs" / slug1 / "blocked.txt").read_text(encoding="utf-8")
    assert "agent không làm đổi trạng thái" in blocked1
    assert "M6.4 final outro must match pinned text" in blocked1
    retry1 = read_yaml(root1 / "topics/logs" / slug1 / "agent-retry.yaml")
    assert "M6.4 final outro must match pinned text" in retry1["steps"]["draft"]["reason"]

    # 2. posts step leaves posts/posts.yaml missing -> exact cause in blocked.txt + agent-retry.yaml
    root2 = tmp_path / "missing-posts"
    proj2 = create_v2_project_fixture(root2 / "projects", state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    approve_gate(proj2, GateKind.MEDICAL, reviewer="BS An", now=datetime.now(UTC))
    (proj2 / "revisions/001" / POSTS_ARTIFACT).unlink(missing_ok=True)
    slug2 = proj2.name
    write_yaml_atomic(
        root2 / "topics/queue.yaml",
        {
            "version": 1,
            "entries": [{"slug": slug2, "title": "Posts Fail", "question": "Q?", "added": "2026-11-18"}],
        },
    )
    deps2 = RunDeps(
        create_project=lambda root, entry: proj2,
        read_state=read_state,
        reject_note=reject_note,
        python_steps={},
        changed_code_paths=lambda _: [],
        invoke=lambda slots, prompt, **kw: AgentResult("fake", True, False, kw["log_dir"] / "posts.log"),
        posts_ready=lambda p: not check_revision_posts(p / "revisions/001", require_medical_approval=True),
        shorts_plan_ready=lambda _: True,
        product_review_pending=lambda _: True,
        parallel_branches=False,
    )
    report2 = run_queue(root2, deps2, once=True)
    assert report2.blocked == [slug2]
    blocked2 = (root2 / "topics/logs" / slug2 / "blocked.txt").read_text(encoding="utf-8")
    assert "agent không làm đổi trạng thái (posts)" in blocked2
    assert POSTS_ARTIFACT in blocked2
    retry2 = read_yaml(root2 / "topics/logs" / slug2 / "agent-retry.yaml")
    assert POSTS_ARTIFACT in retry2["steps"]["posts"]["reason"]

    # 3. research at TOPIC_SELECTED leaves evidence/question.yaml missing -> exact cause
    root3 = tmp_path / "missing-question"
    proj3 = create_v2_project_fixture(root3 / "projects")
    manifest3 = read_yaml(proj3 / "project.yaml")
    write_yaml_atomic(
        proj3 / "project.yaml",
        {**manifest3, "state": WorkflowState.TOPIC_SELECTED.value},
    )
    (proj3 / "revisions/001/evidence/question.yaml").unlink(missing_ok=True)
    slug3 = proj3.name
    write_yaml_atomic(
        root3 / "topics/queue.yaml",
        {
            "version": 1,
            "entries": [{"slug": slug3, "title": "Research Fail", "question": "Q?", "added": "2026-11-18"}],
        },
    )
    deps3 = RunDeps(
        create_project=lambda root, entry: proj3,
        read_state=read_state,
        reject_note=reject_note,
        python_steps={},
        changed_code_paths=lambda _: [],
        invoke=lambda slots, prompt, **kw: AgentResult("fake", True, False, kw["log_dir"] / "research.log"),
        expert_brief_ready=lambda _: True,
    )
    report3 = run_queue(root3, deps3, once=True)
    assert report3.blocked == [slug3]
    blocked3 = (root3 / "topics/logs" / slug3 / "blocked.txt").read_text(encoding="utf-8")
    assert "agent không làm đổi trạng thái (research, trạng thái topic_selected)" in blocked3
    assert "evidence/question.yaml" in blocked3

    # 4. revise_production when a medical-gated artifact drifted from medical-approval.yaml
    root4 = tmp_path / "drifted-medical"
    proj4 = create_v2_project_fixture(root4 / "projects", state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    approve_gate(proj4, GateKind.MEDICAL, reviewer="BS An", now=datetime.now(UTC))
    manifest4 = read_yaml(proj4 / "project.yaml")
    write_yaml_atomic(
        proj4 / "project.yaml",
        {
            **manifest4,
            "state": WorkflowState.NEEDS_PRODUCTION_REVISION.value,
            "side_state": {
                "type": WorkflowState.NEEDS_PRODUCTION_REVISION.value,
                "resume_state": WorkflowState.PRODUCTION_IN_PROGRESS.value,
                "reason_code": "need_prod_fix",
                "entered_at": datetime.now(UTC).isoformat(),
            },
        },
    )
    script4_path = proj4 / "revisions/001/script/script.yaml"
    script4 = read_yaml(script4_path)
    script4["title"] = "Modified behind medical gate"
    write_yaml_atomic(script4_path, script4)
    slug4 = proj4.name
    write_yaml_atomic(
        root4 / "topics/queue.yaml",
        {
            "version": 1,
            "entries": [{"slug": slug4, "title": "Revise Prod Fail", "question": "Q?", "added": "2026-11-18"}],
        },
    )
    deps4 = RunDeps(
        create_project=lambda root, entry: proj4,
        read_state=read_state,
        reject_note=reject_note,
        python_steps={},
        changed_code_paths=lambda _: [],
        invoke=lambda slots, prompt, **kw: AgentResult("fake", True, False, kw["log_dir"] / "revise.log"),
    )
    report4 = run_queue(root4, deps4, once=True)
    assert report4.blocked == [slug4]
    blocked4 = (root4 / "topics/logs" / slug4 / "blocked.txt").read_text(encoding="utf-8")
    assert "script/script.yaml" in blocked4
    assert "medical-approval.yaml" in blocked4
