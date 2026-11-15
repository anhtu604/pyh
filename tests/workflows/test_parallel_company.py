"""Tests for Company 2.0 parallel execution, gpu_mutex, voice_prep merge, and Leader chat."""

import threading
import time
from datetime import UTC, datetime
from pathlib import Path

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
from tests.helpers import create_v2_project_fixture, write_posts_fixture
from tests.workflows.test_draft import SOURCE, _evidence_ready


def test_submit_script_draft_then_parallel_storyboard_and_voice_prep_before_critic(
    tmp_path: Path, monkeypatch,
):
    project_dir = _evidence_ready(tmp_path / "projects")
    manifest = submit_script_draft(
        project_dir,
        SOURCE / "script/script.yaml",
    )
    assert manifest.state is WorkflowState.DRAFT_READY
    assert not (project_dir / "revisions/001/storyboard/storyboard.yaml").is_file()
    assert not (project_dir / "revisions/001/script/voice-prep.yaml").is_file()

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
    proj_a = create_v2_project_fixture(tmp_path / "projects", state=WorkflowState.AWAITING_MEDICAL_REVIEW)
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
