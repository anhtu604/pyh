from datetime import UTC, datetime

import pytest

from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows.external_revision import import_revision, validate_import


def bundle(tmp_path):
    root = tmp_path / 'bundle'
    write_yaml_atomic(root / 'script/script.yaml', {
        'title': 'Gan', 'lines': [{'id': 'L01', 'text': 'Lời hiển thị',
                                 'delivery': 'Lời hiển thị', 'claim_id': 'C01'}],
    })
    write_yaml_atomic(root / 'evidence/ledger.yaml', {
        'claims': [{'id': 'C01', 'text_public': 'Thông tin', 'text_technical': 'Thông tin',
                    'type': 'evidence', 'sources': ['R01']}],
        'records': [{'id': 'R01', 'title': 'Nguồn thật trong fixture'}],
    })
    write_yaml_atomic(root / 'posts/posts.yaml', {
        'youtube_titles': ['Gan', 'Tìm hiểu gan'], 'youtube_description': 'Bản nháp\nNguồn thật trong fixture',
        'facebook_post': 'Bản nháp', 'youtube_community': 'Bản nháp',
        'clip_captions': {'CL01': dict.fromkeys(['tiktok', 'shorts', 'reels'], 'Bản nháp')},
    })
    for name in ('renders/video.mp4', 'renders/clips/CL01.mp4'):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'fixture media')
    return root


def project(tmp_path):
    root = tmp_path / 'project'
    write_yaml_atomic(root / 'project.yaml', {
        'schema_version': '2.0', 'slug': 'project', 'language': 'vi',
        'active_revision': '001', 'state': 'production_in_progress',
    })
    old = root / 'revisions/001/script/script.yaml'
    write_yaml_atomic(old, {'old': True})
    return root


def test_import_and_invalid_input_are_atomic(tmp_path):
    source, target = bundle(tmp_path), project(tmp_path)
    before = (target / 'project.yaml').read_bytes()
    (source / 'renders/video.mp4').unlink()
    with pytest.raises(ValueError, match='renders/video.mp4'):
        import_revision(target, source, reason='Nhập bản dựng', now=datetime.now(UTC))
    assert (target / 'project.yaml').read_bytes() == before
    assert not (target / 'revisions/002').exists()
    (source / 'renders/video.mp4').write_bytes(b'fixture')
    assert import_revision(target, source, reason='Nhập bản dựng', now=datetime.now(UTC)) == '002'
    assert read_yaml(target / 'project.yaml')['state'] == 'awaiting_medical_review'
    rev = target / 'revisions/002'
    assert read_yaml(rev / 'workflow.yaml')['parent_revision'] == '001'
    assert not list((rev / 'reviews').glob('*approval*'))
    assert read_yaml(target / 'revisions/001/script/script.yaml') == {'old': True}


def test_missing_source_rejected(tmp_path):
    root = bundle(tmp_path)
    ledger = read_yaml(root / 'evidence/ledger.yaml')
    ledger['records'] = []
    write_yaml_atomic(root / 'evidence/ledger.yaml', ledger)
    with pytest.raises(ValueError, match='R01'):
        validate_import(root)


@pytest.mark.parametrize('relative', ['script/script.yaml', 'evidence/ledger.yaml', 'posts/posts.yaml'])
def test_invalid_yaml_reports_file_in_vietnamese(tmp_path, relative):
    source, target = bundle(tmp_path), project(tmp_path)
    (source / relative).write_text('broken: [\n', encoding='utf-8')
    with pytest.raises(ValueError, match=relative + '.*không hợp lệ'):
        import_revision(target, source, reason='Invalid YAML')
    assert not (target / 'revisions/002').exists()


def imported(tmp_path):
    source, target = bundle(tmp_path), project(tmp_path)
    import_revision(target, source, reason='Nhập bản dựng', now=datetime.now(UTC))
    return target, target / 'revisions/002'


def approve_medical(target):
    from healthvideo.approver_pin import set_pin
    from healthvideo.domain.gate_review import GateKind
    from healthvideo.workflows.gate_review import approve_gate
    from tests.helpers import write_critic_review_fixture

    write_critic_review_fixture(target)
    pin_file = target / 'synthetic-pin.json'
    if not pin_file.exists():
        set_pin('fixture-only-pin', path=pin_file)
    approve_gate(target, GateKind.MEDICAL, reviewer='Synthetic doctor fixture', now=datetime.now(UTC),
                 doctor_pin='fixture-only-pin', pin_file=pin_file)


def fake_probe(path, *, vertical):
    from healthvideo.storage.files import sha256_file

    return {'duration_seconds': 90 if vertical else 790,
            'width': 1080 if vertical else 1920, 'height': 1920 if vertical else 1080,
            'audio_channels': 2, 'sha256': sha256_file(path)}


def make_advisory(revision, *, product, blocking=False):
    from healthvideo.workflows import product_review, script_review

    critic = product_review if product else script_review
    path = revision / critic.LOG
    log = read_yaml(path)
    latest = log['rounds'][-1]
    key = next(iter(critic.CRITERIA))
    latest.update(passed=False, summary='Nhận xét tham khảo <an toàn>')
    latest['scores'][key] = 5
    latest['issues'] = [{('at' if product else 'line'): 'L01', 'criterion': key,
                         'problem': 'Ý dài <cần xem>', 'fix': 'Rút gọn',
                         'blocking_safety': blocking, **({'fixable': False} if product else {})}]
    write_yaml_atomic(path, log)
    return critic


@pytest.mark.parametrize('product', [False, True])
@pytest.mark.parametrize('case', ['advisory', 'safety', 'missing', 'stale', 'schema'])
def test_external_current_valid_review_required(tmp_path, monkeypatch, product, case):
    from healthvideo.approver_pin import set_pin
    from healthvideo.domain.gate_review import GateKind
    from healthvideo.domain.project_v2 import ProjectManifestV2
    from healthvideo.workflows import external_revision, factory, gate_review, produce
    from tests.helpers import write_critic_review_fixture

    target, revision = imported(tmp_path)
    if product:
        approve_medical(target)
        monkeypatch.setattr(external_revision, 'probe_media', fake_probe)
        external_revision.produce_external(target, hold=True)
    write_critic_review_fixture(target, product=product)
    critic = make_advisory(revision, product=product, blocking=case == 'safety')
    path = revision / critic.LOG
    if case == 'missing':
        path.unlink()
    elif case in {'stale', 'schema'}:
        log = read_yaml(path)
        if case == 'stale':
            log['rounds'][-1]['render_sha256' if product else 'script_sha256'] = 'obsolete'
        else:
            log['rounds'][-1]['scores'] = {}
        write_yaml_atomic(path, log)
    pin_file = target / 'synthetic-pin.json'
    if not pin_file.exists():
        set_pin('fixture-only-pin', path=pin_file)
    kind = GateKind.VIDEO if product else GateKind.MEDICAL
    if case == 'advisory':
        critic.require_passed_review(target)
        action = critic.next_product_action(target) if product else critic.next_script_action(target)
        assert action == ('submit_video' if product else 'submit_medical')
        if product:
            produce.submit_video(target)
        manifest = ProjectManifestV2.model_validate(read_yaml(target / 'project.yaml'))
        assert factory.gate_for_project(target, manifest) == kind.value
        with pytest.raises(ValueError, match='PIN'):
            gate_review.approve_gate(target, kind, reviewer='Fixture', now=datetime.now(UTC))
        gate_review.approve_gate(target, kind, reviewer='Fixture', now=datetime.now(UTC),
                                doctor_pin='fixture-only-pin', pin_file=pin_file)
    else:
        with pytest.raises(ValueError):
            critic.require_passed_review(target)
        if product:
            with pytest.raises(ValueError):
                produce.submit_video(target)
        else:
            with pytest.raises(ValueError):
                gate_review.approve_gate(target, kind, reviewer='Fixture', now=datetime.now(UTC),
                                        doctor_pin='fixture-only-pin', pin_file=pin_file)
        assert not (revision / f'reviews/{kind.value}-approval.yaml').is_file()


@pytest.mark.parametrize('tag', ['001', '002', None])
def test_external_holds_only_clear_explicit_obsolete_revision(tmp_path, tag):
    from healthvideo.workflows.external_revision import clear_obsolete_holds

    target, _ = imported(tmp_path / 'projects')
    logs = tmp_path / 'topics/logs' / target.name
    data = {'status': 'open', 'reason': 'Synthetic old hold', **({'revision': tag} if tag else {})}
    for name in ('blocked.txt', 'agent-retry.yaml', 'doctor-question.yaml'):
        write_yaml_atomic(logs / name, data)
    clear_obsolete_holds(tmp_path, target)
    for name in ('blocked.txt', 'agent-retry.yaml', 'doctor-question.yaml'):
        assert (logs / name).exists() is (tag != '001')


@pytest.mark.parametrize('product', [False, True])
def test_regular_revision_still_requires_passing_critic(tmp_path, monkeypatch, product):
    from healthvideo.workflows import external_revision
    from tests.helpers import write_critic_review_fixture

    target, revision = imported(tmp_path)
    if product:
        approve_medical(target)
        monkeypatch.setattr(external_revision, 'probe_media', fake_probe)
        external_revision.produce_external(target, hold=True)
    (revision / external_revision.EXTERNAL).unlink()
    write_critic_review_fixture(target, product=product)
    critic = make_advisory(revision, product=product)
    with pytest.raises(ValueError, match='chưa đạt'):
        critic.require_passed_review(target)


def test_external_retry_keeps_current_and_untagged_steps(tmp_path):
    from healthvideo.workflows.external_revision import clear_obsolete_holds

    target, _ = imported(tmp_path / 'projects')
    path = tmp_path / 'topics/logs' / target.name / 'agent-retry.yaml'
    write_yaml_atomic(path, {'version': 1, 'steps': {
        'old': {'revision': '001'}, 'current': {'revision': '002'}, 'unknown': {},
    }})
    clear_obsolete_holds(tmp_path, target)
    assert set(read_yaml(path)['steps']) == {'current', 'unknown'}


@pytest.mark.parametrize('relative', ['posts/posts.yaml', 'posts/thumbnail.png'])
def test_external_product_review_binds_current_posts(tmp_path, monkeypatch, relative):
    from healthvideo.workflows import external_revision, product_review
    from tests.helpers import write_critic_review_fixture

    target, revision = imported(tmp_path)
    approve_medical(target)
    monkeypatch.setattr(external_revision, 'probe_media', fake_probe)
    external_revision.produce_external(target, hold=True)
    write_critic_review_fixture(target, product=True)
    make_advisory(revision, product=True)
    product_review.require_passed_review(target)
    path = revision / relative
    if relative.endswith('.yaml'):
        posts = read_yaml(path)
        posts['facebook_post'] = 'Nội dung đã đổi'
        write_yaml_atomic(path, posts)
    else:
        path.write_bytes(b'new synthetic thumbnail')
    with pytest.raises(ValueError, match='hiện hành'):
        product_review.require_passed_review(target)
    assert product_review.next_product_action(target) == 'product_review'


@pytest.mark.parametrize('relative', ['script/script.yaml', 'evidence/ledger.yaml',
                                      'workflow/external.yaml', 'profiles/pronunciation.vi.yaml',
                                      'reviews/script-review-log.yaml'])
def test_medical_hash_invalidates_every_external_input(tmp_path, relative):
    from healthvideo.workflows.produce import _ensure_v2_medical_approval_current

    target, revision = imported(tmp_path)
    approve_medical(target)
    path = revision / relative
    data = read_yaml(path)
    data['changed'] = True
    write_yaml_atomic(path, data)
    with pytest.raises(ValueError, match='current medical approval'):
        _ensure_v2_medical_approval_current(revision)


@pytest.mark.parametrize('advisory', [False, True])
def test_full_external_flow_preserves_critic_and_bytes(tmp_path, monkeypatch, advisory):
    import json

    from healthvideo.domain.gate_review import GateKind
    from healthvideo.workflows import external_revision, gate_review, package, produce
    from healthvideo.workflows.review_html import (
        render_medical_packet,
        render_video_packet,
    )
    from tests.helpers import write_critic_review_fixture

    target, revision = imported(tmp_path / 'projects')
    from healthvideo.approver_pin import set_pin

    pin_file = target / 'synthetic-pin.json'
    set_pin('fixture-only-pin', path=pin_file)
    with pytest.raises(ValueError, match='PIN'):
        gate_review.approve_gate(target, GateKind.MEDICAL, reviewer='Fixture', now=datetime.now(UTC))
    with pytest.raises(ValueError, match='Trạm 07'):
        gate_review.approve_gate(target, GateKind.MEDICAL, reviewer='Fixture', now=datetime.now(UTC),
                                doctor_pin='fixture-only-pin', pin_file=pin_file)
    assert 'Lời hiển thị' in render_medical_packet(revision)
    assert 'Nguồn thật' in render_medical_packet(revision)
    if advisory:
        write_critic_review_fixture(target)
        make_advisory(revision, product=False)
        gate_review.approve_gate(target, GateKind.MEDICAL, reviewer='Fixture', now=datetime.now(UTC),
                                doctor_pin='fixture-only-pin', pin_file=pin_file)
    else:
        approve_medical(target)
    medical = read_yaml(revision / 'reviews/medical-approval.yaml')
    assert 'reviews/script-review-log.yaml' in medical['artifact_hashes']
    assert 'Ý kiến agent chấm (tham khảo)' in render_medical_packet(revision)
    if advisory:
        assert 'Ý dài &lt;cần xem&gt;' in render_medical_packet(revision)
        assert 'Nhận xét tham khảo &lt;an toàn&gt;' in render_medical_packet(revision)
    monkeypatch.setattr(external_revision, 'probe_media', fake_probe)
    def forbidden(*args, **kwargs):
        pytest.fail('External branch called renderer/TTS')
    monkeypatch.setattr(produce, '_produce_v2', forbidden)
    video_before = (revision / 'renders/video.mp4').read_bytes()
    produce.produce_project(target, None, forbidden, hold_for_product_review=True)
    assert read_yaml(target / 'project.yaml')['state'] == 'production_in_progress'
    with pytest.raises(ValueError, match='Trạm 12'):
        produce.submit_video(target)
    write_critic_review_fixture(target, product=True)
    if advisory:
        make_advisory(revision, product=True)
    produce.submit_video(target)
    assert read_yaml(target / 'project.yaml')['state'] == 'awaiting_video_review'
    assert 'CL01' in render_video_packet(revision)
    assert 'Ý kiến agent chấm (tham khảo)' in render_video_packet(revision)
    if advisory:
        assert 'Ý dài &lt;cần xem&gt;' in render_video_packet(revision)
    gate_review.approve_gate(target, GateKind.VIDEO, reviewer='Fixture', now=datetime.now(UTC),
                            doctor_pin='fixture-only-pin', pin_file=pin_file)
    video = read_yaml(revision / 'reviews/video-approval.yaml')
    assert 'reviews/product-review-log.yaml' in video['artifact_hashes']
    output = package.package_project(target)
    manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
    assert {'video.mp4', 'clips/CL01.mp4'} <= manifest['payload_sha256'].keys()
    assert read_yaml(target / 'project.yaml')['state'] == 'packaged'
    assert (output / 'video.mp4').read_bytes() == video_before
    from healthvideo.workflows import channel_publishing

    monkeypatch.setattr(channel_publishing, '_account', lambda *a: {'id': 'synthetic-connected-account'})
    for platform, clip_id in [('youtube', None), ('youtube', 'CL01'), ('tiktok', 'CL01')]:
        preview, asset = channel_publishing._validated(tmp_path, 'project', platform, clip_id, 0)
        assert preview['gates_current'] is True
        assert asset.is_file()
    report_path = revision / 'reviews/product-review-log.yaml'
    before_report = report_path.read_bytes()
    report = read_yaml(report_path)
    report['rounds'][-1]['summary'] = 'Nhận xét đã đổi sau PIN'
    write_yaml_atomic(report_path, report)
    with pytest.raises(ValueError, match='current video approval'):
        package._ensure_v2_gate_approval(revision, GateKind.VIDEO)
    report_path.write_bytes(before_report)
    (revision / 'renders/video.mp4').write_bytes(b'modified')
    with pytest.raises(ValueError, match='current video approval'):
        package._ensure_v2_gate_approval(revision, GateKind.VIDEO)


def test_import_rolls_back_failure_during_staging(tmp_path, monkeypatch):
    from healthvideo.workflows import external_revision

    source, target = bundle(tmp_path), project(tmp_path)
    before = (target / 'project.yaml').read_bytes()
    original = external_revision.shutil.copy2
    def fail_video(src, dst, *args, **kwargs):
        if str(src).endswith('video.mp4'):
            raise OSError('Injected copy failure')
        return original(src, dst, *args, **kwargs)
    monkeypatch.setattr(external_revision.shutil, 'copy2', fail_video)
    with pytest.raises(OSError, match='Injected'):
        import_revision(target, source, reason='Copy failed')
    assert (target / 'project.yaml').read_bytes() == before
    assert sorted(p.name for p in (target / 'revisions').iterdir()) == ['001']


@pytest.mark.parametrize('duration,width,height,audio', [
    (599, 1920, 1080, True), (1501, 1920, 1080, True),
    (790, 1080, 1920, True), (790, 1920, 1080, False),
])
def test_probe_rejects_invalid_long_video(tmp_path, monkeypatch, duration, width, height, audio):
    import json
    from types import SimpleNamespace

    from healthvideo.workflows.external_revision import probe_media

    path = tmp_path / 'video.mp4'
    path.write_bytes(b'fixture')
    streams = [{'codec_type': 'video', 'width': width, 'height': height}]
    if audio:
        streams.append({'codec_type': 'audio', 'channels': 2})
    result = SimpleNamespace(returncode=0, stderr='', stdout=json.dumps({
        'streams': streams, 'format': {'duration': duration}}))
    monkeypatch.setattr('healthvideo.workflows.external_revision.subprocess.run', lambda *a, **kw: result)
    with pytest.raises(ValueError, match='video/tiếng/thời lượng'):
        probe_media(path, vertical=False)


def test_project_write_failure_rolls_back_promoted_revision(tmp_path, monkeypatch):
    from healthvideo.storage import revisions

    source, target = bundle(tmp_path), project(tmp_path)
    before = (target / 'project.yaml').read_bytes()
    original = revisions.write_yaml_atomic
    def fail_manifest(path, data):
        if path == target / 'project.yaml':
            raise OSError('Injected manifest failure')
        return original(path, data)
    monkeypatch.setattr(revisions, 'write_yaml_atomic', fail_manifest)
    with pytest.raises(OSError, match='manifest failure'):
        import_revision(target, source, reason='Atomic rollback')
    assert (target / 'project.yaml').read_bytes() == before
    assert sorted(p.name for p in (target / 'revisions').iterdir()) == ['001']


def test_import_refuses_approval_files(tmp_path):
    source, target = bundle(tmp_path), project(tmp_path)
    write_yaml_atomic(source / 'reviews/medical-approval.yaml', {'bogus': True})
    with pytest.raises(ValueError, match='bản duyệt'):
        import_revision(target, source, reason='Do not import approvals')
    assert not (target / 'revisions/002').exists()


def test_external_transition_cannot_approve(tmp_path):
    from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
    from healthvideo.domain.state_graph import (
        TransitionContext,
        TransitionError,
        transition_v2,
    )

    target = project(tmp_path)
    manifest = ProjectManifestV2.model_validate(read_yaml(target / 'project.yaml'))
    for state in (WorkflowState.MEDICALLY_APPROVED, WorkflowState.VIDEO_APPROVED):
        with pytest.raises(TransitionError):
            transition_v2(manifest, state, TransitionContext(
                active_revision='001', current_input_hash='0' * 64,
                validated_artifacts=frozenset(), external_import=True))


def test_clip_tamper_and_failed_qa_block_video_gate(tmp_path, monkeypatch):
    import json

    from healthvideo.domain.gate_review import GateKind
    from healthvideo.workflows import external_revision, gate_review
    from healthvideo.workflows.produce import submit_video
    from tests.helpers import write_critic_review_fixture

    target, revision = imported(tmp_path)
    approve_medical(target)
    monkeypatch.setattr(external_revision, 'probe_media', fake_probe)
    external_revision.produce_external(target, hold=True)
    write_critic_review_fixture(target, product=True)
    submit_video(target)
    kwargs = {'reviewer': 'Synthetic doctor fixture', 'now': datetime.now(UTC),
              'doctor_pin': 'fixture-only-pin', 'pin_file': target / 'synthetic-pin.json'}
    clip = revision / 'renders/clips/CL01.mp4'
    before = clip.read_bytes()
    clip.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='byte video'):
        gate_review.approve_gate(target, GateKind.VIDEO, **kwargs)
    clip.write_bytes(before)
    qa = revision / 'reviews/video-qa.json'
    report = json.loads(qa.read_text(encoding='utf-8'))
    report['status'] = 'failed'
    qa.write_text(json.dumps(report), encoding='utf-8')
    with pytest.raises(ValueError, match='failed video QA'):
        gate_review.approve_gate(target, GateKind.VIDEO, **kwargs)
    assert not (revision / 'reviews/video-approval.yaml').exists()


def test_adapter_reports_unmapped_claim_without_guessing(tmp_path):
    import json

    from tools.build_pyh003_import import build

    source = tmp_path / 'prototype'
    source.mkdir()
    (source / 'script-full-lines.json').write_text(json.dumps([
        {'id': 'C1-L01', 'text': 'Missing mapping', 'sources': 'SRC'},
    ]), encoding='utf-8')
    (source / 'timeline-full-v5.json').write_text(json.dumps({'lines': [
        {'id': 'C1-L01', 'words': [{'word': 'Missing'}, {'word': 'mapping'}]}]}), encoding='utf-8')
    (source / 'script-full.md').write_text('Chủ đề: Gan\n', encoding='utf-8')
    (source / 'sources-full.md').write_text(
        '| [SRC] | Author; 2026; Journal | Source title | PMID 123 | Existing source |\n'
        '| F01 | Existing claim | [SRC] Abstract | Keep limits |\n', encoding='utf-8')
    (source / 'research-ledger.json').write_text(json.dumps({
        'data': {'resultList': {'result': []}}}), encoding='utf-8')
    write_yaml_atomic(source / 'evidence-rev001/ledger.yaml', {'records': []})
    for name in ('pyh003-full.mp4', 'short-bo-gan.mp4', 'short-di-kham.mp4', 'thumb-a.png'):
        (source / name).write_bytes(b'fixture')
    # An orphan source cannot be assigned to an unlinked narration line.
    output = tmp_path / 'output'
    report = build(source, output)
    assert report['schema_valid'] is False
    assert report['missing_support'][0]['line'] == 'C1-L01'
    assert read_yaml(output / 'evidence/ledger.yaml')['claims'] == []
    assert (output / 'import-report.json').is_file()
    with pytest.raises(ValueError, match='unresolved-claims'):
        validate_import(output)


@pytest.mark.parametrize('stage', ['medical', 'product'])
@pytest.mark.parametrize('advisory', [False, True, 'safety'])
def test_runner_external_only_calls_critics(tmp_path, monkeypatch, stage, advisory):
    from healthvideo.domain.project_v2 import WorkflowState
    from healthvideo.domain.queue import QueueEntry
    from healthvideo.workflows import external_revision, produce, runner
    from tests.helpers import write_critic_review_fixture

    source = bundle(tmp_path)
    target = project(tmp_path / 'projects')
    import_revision(target, source, reason='External factory')
    if stage == 'product':
        approve_medical(target)
    logs = tmp_path / 'topics/logs' / target.name
    for name in ('blocked.txt', 'agent-retry.yaml', 'doctor-question.yaml'):
        write_yaml_atomic(logs / name, {'revision': '001', 'status': 'open',
                                      'reason': 'Hold from previous revision'})
    monkeypatch.setattr(external_revision, 'probe_media', fake_probe)
    calls = []
    def invoke(root, deps, entry, project_dir, report, *, step, **kwargs):
        calls.append(step)
        critic = runner.product_review if step == 'product_review' else external_script_review
        digest = critic.render_hash(project_dir) if step == 'product_review' else critic.script_hash(project_dir)
        # Synthetic reports only in tmp_path. The runner records them itself.
        write_yaml_atomic(project_dir / 'revisions/002' / critic.REPORT, {
            'scores': {key: 5 if advisory and n == 0 else 8
                       for n, key in enumerate(critic.CRITERIA)},
            'summary': 'Synthetic critic fixture',
            'issues': ([{('at' if step == 'product_review' else 'line'): 'L01',
                        'criterion': next(iter(critic.CRITERIA)), 'problem': 'Ý dài',
                        'fix': 'Rút gọn', 'blocking_safety': advisory == 'safety',
                        **({'fixable': False} if step == 'product_review' else {})}]
                       if advisory else []),
            'checked': ['Synthetic fixture'], 'decisions': [],
        })
        assert digest
        return 'ok', None, None, {}
    from healthvideo.workflows import script_review as external_script_review

    monkeypatch.setattr(runner, '_run_agent_invocation', invoke)
    def forbidden(*args, **kwargs):
        pytest.fail('External runner dispatched production/maker')
    deps = runner.RunDeps(
        create_project=lambda *a: target,
        read_state=lambda p: WorkflowState(read_yaml(p / 'project.yaml')['state']),
        reject_note=lambda _: None,
        python_steps={'produce': forbidden, 'submit_video': produce.submit_video},
        changed_code_paths=lambda _: [],
        shorts_plan_ready=forbidden, visual_review_pending=forbidden,
        parallel_branches=True,
    )
    entry = QueueEntry(slug=target.name, title='External fixture', question='Test?', added='2026-11-25')
    report = runner.RunReport()
    runner._run_topic(tmp_path, deps, entry, report, once=False, max_steps_per_topic=4)
    assert calls == ['script_review' if stage == 'medical' else 'product_review']
    log_name = 'script' if stage == 'medical' else 'product'
    rounds = read_yaml(target / f'revisions/002/reviews/{log_name}-review-log.yaml')['rounds']
    assert len(rounds) == 1
    assert rounds[-1]['passed'] is (not bool(advisory))
    if advisory == 'safety':
        assert report.blocked == [target.name]
        runner._run_topic(tmp_path, deps, entry, runner.RunReport(), max_steps_per_topic=4)
        assert len(calls) == 1
        assert not (target / 'revisions/002/reviews/video-approval.yaml').exists()
        return
    assert report.blocked == []
    expected = 'awaiting_medical_review' if stage == 'medical' else 'awaiting_video_review'
    assert read_yaml(target / 'project.yaml')['state'] == expected
    if stage == 'medical':
        write_critic_review_fixture(target)  # still no approval; only a test critic



def test_import_refuses_thumbnail_file_without_spec(tmp_path):
    """PYH-003: a bare thumbnail.png was packaged but never uploaded to YouTube."""
    root = bundle(tmp_path)
    validate_import(root, importing=True)
    (root / 'posts/thumbnail.png').write_bytes(b'png')
    with pytest.raises(ValueError, match='thiếu khai báo ảnh bìa'):
        validate_import(root, importing=True)
    validate_import(root)  # already-imported revisions keep working
