"""Regression tests for PYH-003 recovery: double-lock loop, TTS cache, port fallback, status & summary."""

from __future__ import annotations

import json
import os
import wave
from datetime import UTC, date, datetime
from pathlib import Path

from typer.testing import CliRunner

from healthvideo import cli
from healthvideo.agents import AgentResult
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.pronunciation import PronunciationEntry, PronunciationLexicon
from healthvideo.domain.queue import QueueEntry
from healthvideo.project_codes import project_codes
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.queue import add_to_queue
from healthvideo.tts.base import TTSRequest, TTSResult
from healthvideo.tts.pronunciation import apply_pronunciation, pronunciation_hash
from healthvideo.workflows import (
    chat,
    dashboard,
    dashboard_operations,
    doctor_questions,
    produce,
)
from healthvideo.workflows import product_review as pr
from healthvideo.workflows.gate_review import approve_gate
from healthvideo.workflows.runner import RunDeps, run_queue
from tests.helpers import create_v2_project_fixture

SLUG = 'muoi-va-huyet-ap-v2'
REV = Path('revisions/001')


def _write_valid_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(48000)
        audio.writeframes(b'\x01\x00' * 4800)


def test_pyh003_double_lock_recovery_supersedes_duplicate_question_and_rebuilds(tmp_path: Path) -> None:
    add_to_queue(tmp_path, QueueEntry(
        slug=SLUG, title='Men gan', question='Vì sao?', added=date(2026, 11, 20),
    ))
    project = create_v2_project_fixture(tmp_path / 'projects', state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    rev = project / REV

    # Simulate an older render + 2 failed Station 12 rounds + old pending marker.
    manifest_path = rev / pr.RENDER_MANIFEST
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({'input_hash': '1' * 64, 'pronunciation_sha256': '0' * 64}),
        encoding='utf-8',
    )
    video_path = rev / 'renders/video.mp4'
    video_path.write_bytes(b'old-video')
    old_ts = datetime(2026, 11, 21, 13, 12, tzinfo=UTC).timestamp()
    os.utime(manifest_path, (old_ts, old_ts))
    os.utime(video_path, (old_ts, old_ts))
    pr.hold(rev, '1' * 64)

    issue = {
        'issue_id': 'PR-04',
        'at': 'S08@01:34',
        'criterion': 'hinh_khop_loi',
        'problem': 'Chưa khớp Scale Zoom.',
        'fix': 'Dựng lại.',
        'fixable': True,
    }
    scores = dict.fromkeys(pr.CRITERIA, 8) | {'hinh_khop_loi': 6}
    for _ in (1, 2):
        write_yaml_atomic(rev / pr.REPORT, {'scores': scores, 'summary': 'Cũ.', 'issues': [issue]})
        pr.record_review(project, pr.render_hash(project))

    # Doctor answered dq-1 at 16:57 UTC with free text ("Dựng lại rồi chấm..."),
    # and medical-approval.yaml was approved at 16:49 UTC, but a duplicate dq-2 was opened at 16:59 UTC.
    approve_gate(
        project,
        GateKind.MEDICAL,
        reviewer='Tu',
        note='Scale Zoom mới',
        now=datetime(2026, 11, 21, 16, 49, 54, tzinfo=UTC),
    )
    # Transition fixture state to production_in_progress as in PYH-003.
    manifest_yaml = read_yaml(project / 'project.yaml')
    manifest_yaml['state'] = WorkflowState.PRODUCTION_IN_PROGRESS.value
    write_yaml_atomic(project / 'project.yaml', manifest_yaml)

    ctx = [{'code': 'PR-04', 'location': 'S08@01:34', 'summary': 'Chưa khớp Scale Zoom.'}]
    opts = [
        {'id': 'fix_visuals', 'label': 'Sửa hình', 'detail': '...'},
        {'id': 'split_long_scenes', 'label': 'Tách cảnh', 'detail': '...'},
    ]
    q1 = doctor_questions.ask(
        tmp_path, SLUG, station='12', kind='stuck_issue',
        question='Trạm 12 kẹt', context=ctx, options=opts,
        now=datetime(2026, 11, 21, 16, 41, 23, tzinfo=UTC),
    )
    doctor_questions.answer(
        tmp_path, SLUG, q1['id'], None,
        'Dựng lại rồi chấm: bản cũ đã được thay bằng storyboard Scale Zoom đã duyệt y khoa '
        'và cách đọc ALT/AST mới; dựng lại video (kể cả giọng), rồi cho Trạm 12 chấm lại từ đầu.',
        now=datetime(2026, 11, 21, 16, 57, 0, tzinfo=UTC),
    )
    doctor_questions.ask(
        tmp_path, SLUG, station='12', kind='stuck_issue',
        question='Trạm 12 kẹt', context=ctx, options=opts,
        now=datetime(2026, 11, 21, 16, 59, 32, tzinfo=UTC),
    )
    assert doctor_questions.open_question(tmp_path, SLUG) is not None

    state = {'value': WorkflowState.PRODUCTION_IN_PROGRESS}
    events: list[str] = []

    def fake_produce(proj: Path) -> None:
        events.append('produce')
        r = proj / REV
        current_pron = pr.current_pronunciation_sha256(r) or 'current-pron'
        (r / pr.RENDER_MANIFEST).write_text(
            json.dumps({'input_hash': '2' * 64, 'pronunciation_sha256': current_pron}),
            encoding='utf-8',
        )
        (r / 'renders/video.mp4').write_bytes(b'new-scale-zoom-video')
        pr.hold(r, '2' * 64)

    def fake_submit(proj: Path) -> None:
        events.append('submit_video')
        pr.mark_submitted(proj / REV)
        state['value'] = WorkflowState.AWAITING_VIDEO_REVIEW

    def fake_invoke(agents, prompt, *, cwd, log_dir, **_):
        del cwd
        log_dir.mkdir(parents=True, exist_ok=True)
        assert '(`product_review`)' in prompt
        events.append('product_review')
        write_yaml_atomic(rev / pr.REPORT, {
            'scores': dict.fromkeys(pr.CRITERIA, 8),
            'summary': 'Bản dựng Scale Zoom mới đạt.',
            'issues': [],
        })
        return AgentResult(agents[0].cli, True, False, log_dir / 'fake.log')

    deps = RunDeps(
        create_project=lambda *_: project,
        read_state=lambda _: state['value'],
        reject_note=lambda _: None,
        python_steps={'produce': fake_produce, 'submit_video': fake_submit},
        changed_code_paths=lambda _: [],
        invoke=fake_invoke,
        posts_ready=lambda _: True,
        shorts_plan_ready=lambda _: True,
        visual_review_pending=lambda _: False,
    )

    report = run_queue(tmp_path, deps, once=False)
    assert report.waiting_doctor == []
    assert report.blocked == []
    assert report.at_gate == [SLUG]
    assert events == ['produce', 'product_review', 'submit_video']
    assert doctor_questions.open_question(tmp_path, SLUG) is None
    assert any(item.get('status') == 'superseded' for item in doctor_questions.history(tmp_path, SLUG))


def test_doctor_answer_endpoint_marks_rebuild_and_avoids_duplicate_question(tmp_path: Path, monkeypatch) -> None:
    project = create_v2_project_fixture(tmp_path / 'projects')
    rev = project / REV
    (rev / 'renders').mkdir(parents=True, exist_ok=True)
    (rev / pr.RENDER_MANIFEST).write_text(json.dumps({'version': 1}), encoding='utf-8')
    pr.hold(rev, '1' * 64)
    issue = {
        'issue_id': 'PR-04', 'at': 'S08', 'criterion': 'hinh_khop_loi',
        'problem': 'Cũ.', 'fix': 'Sửa.', 'fixable': True,
    }
    scores = dict.fromkeys(pr.CRITERIA, 8) | {'hinh_khop_loi': 6}
    for v in (1, 2):
        (rev / pr.RENDER_MANIFEST).write_text(json.dumps({'version': v}), encoding='utf-8')
        pr.hold(rev, f'{v:064}')
        write_yaml_atomic(rev / pr.REPORT, {'scores': scores, 'summary': 'Cũ.', 'issues': [issue]})
        pr.record_review(project, pr.render_hash(project))

    assert pr.next_product_action(project, root=tmp_path) == 'wait_doctor'
    q = doctor_questions.open_question(tmp_path, SLUG)
    assert q is not None and q.get('fingerprint')

    monkeypatch.setattr(chat, 'start', lambda root, msg_id: None)
    resp = dashboard.answer_doctor_question(tmp_path, SLUG, {
        'question_id': q['id'],
        'option_id': None,
        'text': 'Dựng lại rồi chấm từ đầu',
        'expected_revision': '001',
    })
    assert resp['answered']['status'] == 'answered'
    assert pr.rebuild_requested(rev) is True
    assert not (rev / pr.PENDING).exists()
    assert pr.next_product_action(project, root=tmp_path) == 'produce'
    assert doctor_questions.open_question(tmp_path, SLUG) is None

    # Also verify non-rebuild accept_for_video_gate never reopens a duplicate question on same round.
    root2 = tmp_path / 'accept_case'
    proj2 = create_v2_project_fixture(root2 / 'projects')
    rev2 = proj2 / REV
    (rev2 / 'renders').mkdir(parents=True, exist_ok=True)
    for v in (1, 2):
        (rev2 / pr.RENDER_MANIFEST).write_text(json.dumps({'version': v}), encoding='utf-8')
        pr.hold(rev2, f'{v:064}')
        write_yaml_atomic(rev2 / pr.REPORT, {'scores': scores, 'summary': 'Cũ.', 'issues': [issue]})
        pr.record_review(proj2, pr.render_hash(proj2))
    assert pr.next_product_action(proj2, root=root2) == 'wait_doctor'
    q2 = doctor_questions.open_question(root2, proj2.name)
    dashboard.answer_doctor_question(root2, proj2.name, {
        'question_id': q2['id'],
        'option_id': 'accept_for_video_gate',
        'text': '',
        'expected_revision': '001',
    })
    assert pr.next_product_action(proj2, root=root2) == 'wait_doctor'
    assert doctor_questions.open_question(root2, proj2.name) is None


def test_tts_line_cache_invalidates_when_alt_ast_pronunciation_changes(tmp_path: Path) -> None:
    class FakeVibiTTS:
        provider_name = 'vibi_minimax'
        require_signal = True

        def __init__(self) -> None:
            self.calls: list[str] = []

        def cache_identity(self) -> dict[str, str]:
            return {
                'provider': self.provider_name,
                'model_id': 'speech-2.8-hd',
                'voice_id': 'clone-1',
                'runtime_id': 'rest-test',
            }

        def synthesize(self, request: TTSRequest, output: Path) -> TTSResult:
            self.calls.append(request.text)
            _write_valid_wav(output)
            return TTSResult(provider=self.provider_name, audio_file=output, duration_ms=100)

    tts = FakeVibiTTS()
    cache_dir = tmp_path / 'cache/tts'
    lex_old = PronunciationLexicon(
        schema_version='1.0',
        language='vi',
        version='3',
        entries=(
            PronunciationEntry(written='ALT', spoken='ây-eo-ti'),
            PronunciationEntry(written='AST', spoken='ây-ét-ti'),
        ),
    )
    lex_new = PronunciationLexicon(
        schema_version='1.0',
        language='vi',
        version='3+voiceprep',
        entries=(
            PronunciationEntry(written='ALT', spoken='a lờ tê'),
            PronunciationEntry(written='AST', spoken='a ét tê'),
        ),
    )
    assert pronunciation_hash(lex_old) != pronunciation_hash(lex_new)

    line_with_terms = 'Phiếu báo ALT và AST tăng cao.'
    line_without_terms = 'Uống đủ nước mỗi ngày.'

    req_old_terms = TTSRequest(text=apply_pronunciation(line_with_terms, lex_old), language='vi')
    req_old_plain = TTSRequest(text=apply_pronunciation(line_without_terms, lex_old), language='vi')
    produce._synthesize_cached_line(tts, req_old_terms, tmp_path / 'out/n01.wav', cache_dir=cache_dir)
    produce._synthesize_cached_line(tts, req_old_plain, tmp_path / 'out/n02.wav', cache_dir=cache_dir)
    assert len(tts.calls) == 2

    req_new_terms = TTSRequest(text=apply_pronunciation(line_with_terms, lex_new), language='vi')
    req_new_plain = TTSRequest(text=apply_pronunciation(line_without_terms, lex_new), language='vi')
    assert produce.tts_cache_key(tts, req_new_terms) != produce.tts_cache_key(tts, req_old_terms)
    assert produce.tts_cache_key(tts, req_new_plain) == produce.tts_cache_key(tts, req_old_plain)

    produce._synthesize_cached_line(tts, req_new_terms, tmp_path / 'out/n01_v2.wav', cache_dir=cache_dir)
    produce._synthesize_cached_line(tts, req_new_plain, tmp_path / 'out/n02_v2.wav', cache_dir=cache_dir)
    # Only the line whose ALT/AST pronunciation changed triggers a new synthesis call.
    assert len(tts.calls) == 3
    assert 'a lờ tê' in tts.calls[-1] and 'a ét tê' in tts.calls[-1]


def test_cli_status_company_summary_and_coordinator_reply_topic(tmp_path: Path) -> None:
    slug1 = 'chu-de-tam-dung'
    slug2 = 'chu-de-hoi-bac-si'
    add_to_queue(tmp_path, QueueEntry(slug=slug1, title='Chủ đề 1', question='Q1?', added=date(2026, 11, 20)))
    add_to_queue(tmp_path, QueueEntry(slug=slug2, title='Chủ đề 2', question='Q2?', added=date(2026, 11, 21)))

    p1 = create_v2_project_fixture(tmp_path / 'projects', state=WorkflowState.DRAFT_READY)
    p1_target = tmp_path / 'projects' / slug1
    p1.rename(p1_target)
    p2 = create_v2_project_fixture(tmp_path / 'projects', state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    p2_target = tmp_path / 'projects' / slug2
    p2.rename(p2_target)
    approve_gate(p2_target, GateKind.MEDICAL, reviewer='Tu', note='OK', now=datetime.now(UTC))
    p2_manifest = read_yaml(p2_target / 'project.yaml')
    p2_manifest['state'] = WorkflowState.PRODUCTION_IN_PROGRESS.value
    write_yaml_atomic(p2_target / 'project.yaml', p2_manifest)

    write_yaml_atomic(tmp_path / 'topics/logs' / slug1 / 'paused.yaml', {'reason': 'Tạm dừng'})
    doctor_questions.ask(
        tmp_path, slug2, station='12', kind='stuck_issue', question='Chọn hướng xử lý?',
        options=[
            {'id': 'fix_visuals', 'label': 'Sửa hình', 'detail': 'A'},
            {'id': 'split_long_scenes', 'label': 'Tách cảnh', 'detail': 'B'},
        ],
    )

    codes = project_codes(tmp_path)
    res = CliRunner().invoke(cli.app, ['status', '--root', str(tmp_path)])
    assert res.exit_code == 0, res.output
    assert codes[slug1] in res.output
    assert codes[slug2] in res.output
    assert '[tạm dừng]' in res.output
    assert '[chờ ý kiến bác sĩ]' in res.output
    assert 'Đang chờ bác sĩ: 1' in res.output

    summary = chat._company_summary(tmp_path)
    by_slug = {item['slug']: item for item in summary['projects']}
    assert by_slug[slug1]['code'] == codes[slug1]
    assert by_slug[slug1]['paused'] is True
    assert by_slug[slug1]['doctor_question'] is None
    assert by_slug[slug2]['code'] == codes[slug2]
    assert by_slug[slug2]['paused'] is False
    assert by_slug[slug2]['doctor_question']['station'] == '12'

    ops = dashboard_operations.project_operations(tmp_path, slug2)
    assert ops['code'] == codes[slug2]
    assert ops['doctor_question']['station'] == '12'

    # CoordinatorReply.topic accepts string outputs from LLM without crashing Pydantic.
    r1 = chat.CoordinatorReply.model_validate({'reply': 'OK', 'action': 'status', 'topic': 'PYH-003'})
    assert r1.topic is None
    r2 = chat.CoordinatorReply.model_validate({'reply': 'OK', 'action': 'none', 'topic': ''})
    assert r2.topic is None
    r3 = chat.CoordinatorReply.model_validate({
        'reply': 'OK',
        'action': 'queue_topic',
        'brief': 'Thêm chủ đề',
        'topic': '{"slug": "abc", "title": "T", "question": "Q"}',
    })
    assert r3.topic == {'slug': 'abc', 'title': 'T', 'question': 'Q'}


def test_factory_wakeup_stamp_interrupts_sleep_and_runner_auto_voice_prep(
    tmp_path: Path, monkeypatch,
) -> None:
    import time

    from healthvideo.workflows import factory, runner, voice_prep

    # 1. _sleep_until_wakeup exits early when cache/xuong-wakeup.stamp is touched.
    sleeps: list[float] = []
    factory.wake_background(tmp_path)

    def fake_real_sleep(sec: float) -> None:
        sleeps.append(sec)
        factory.wake_background(tmp_path)

    monkeypatch.setattr(time, 'sleep', fake_real_sleep)
    factory._sleep_until_wakeup(tmp_path, 120.0, sleep=time.sleep)
    assert sleeps == [1.0]

    # 2. runner skips voice_prep agent invocation via 0-token try_auto_voice_prep when all terms are covered.
    project = create_v2_project_fixture(tmp_path / 'projects', state=WorkflowState.DRAFT_READY)
    slug = project.name
    rev = project / REV
    (rev / 'script/voice-prep.yaml').unlink(missing_ok=True)
    write_yaml_atomic(rev / 'script/script.yaml', {
        'schema_version': '2.0',
        'title': 'Uống đủ nước mỗi ngày',
        'lines': [
            {'id': 'L01', 'text': 'Uống đủ nước giúp cơ thể khỏe mạnh hơn mỗi ngày.'},
        ],
    })
    write_yaml_atomic(tmp_path / 'topics/queue.yaml', {
        'version': 1,
        'entries': [{'slug': slug, 'title': 'Nước', 'question': 'Q?', 'added': '2026-11-23'}],
    })
    invoked: list[str] = []

    def fake_invoke(slots, prompt, **kwargs):
        invoked.append(kwargs['step'])
        return runner.AgentResult('fake', True, False, kwargs['log_dir'] / 'fake.log')

    deps = runner.RunDeps(
        create_project=lambda *_: project,
        read_state=lambda p: WorkflowState(read_yaml(p / 'project.yaml')['state']),
        reject_note=lambda _: None,
        python_steps={},
        changed_code_paths=lambda _: [],
        invoke=fake_invoke,
        storyboard_ready=lambda _: True,
        voice_prep_ready=voice_prep.voice_prep_ready,
    )
    runner.run_queue(tmp_path, deps, once=True)
    assert 'voice_prep' not in invoked
    assert voice_prep.voice_prep_ready(project) is True
