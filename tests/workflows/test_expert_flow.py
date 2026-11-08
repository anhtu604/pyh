"""Medical expert and viral writer split (spec 2026-11-08 §5.8) in the factory loop."""

from datetime import date
from pathlib import Path

from healthvideo.agents import AgentResult
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.queue import QueueEntry
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.queue import add_to_queue
from healthvideo.workflows.expert import (
    EXPERT_BRIEF,
    QUESTIONS,
    answered_questions,
    expert_brief_ready,
    open_questions,
)
from healthvideo.workflows.runner import RunDeps, run_queue
from healthvideo.workflows.script_review import CRITERIA, REPORT
from tests.helpers import create_v2_project_fixture

SLUG = 'muoi-va-huyet-ap-v2'
REV = Path('revisions/001')


def _queue(root: Path) -> Path:
    add_to_queue(root, QueueEntry(slug=SLUG, title='Muối', question='Vì sao?',
                                  added=date(2026, 11, 8)))
    project = create_v2_project_fixture(root / 'projects')
    _script(project, 'Muối kéo nước vào mạch.')
    return project


def _script(project: Path, text: str) -> None:
    write_yaml_atomic(project / REV / 'script/script.yaml',
                      {'lines': [{'id': 'N01', 'text': text}]})


def _questions(project: Path, *questions: dict) -> None:
    write_yaml_atomic(project / REV / QUESTIONS, {'questions': list(questions)})


def _passing_report(project: Path) -> None:
    write_yaml_atomic(project / REV / REPORT, {
        'scores': dict.fromkeys(CRITERIA, 8), 'summary': 'Ổn.', 'issues': [],
    })


def _deps(state: dict, invoke, **extra) -> RunDeps:
    def submit(_project):
        state['value'] = WorkflowState.AWAITING_MEDICAL_REVIEW

    return RunDeps(
        create_project=lambda *_: None,
        read_state=lambda _project: state['value'],
        reject_note=lambda _project: None,
        python_steps={'submit_medical': submit},
        changed_code_paths=lambda _root: [],
        invoke=invoke,
        **extra,
    )


def _result(slots, log_dir: Path) -> AgentResult:
    log_dir.mkdir(parents=True, exist_ok=True)
    return AgentResult(slots[0].cli, True, False, log_dir / 'fake.log')


def test_question_helpers_read_open_and_answered(tmp_path):
    project = create_v2_project_fixture(tmp_path)
    assert open_questions(project) == [] and answered_questions(project) == []
    _questions(project,
               {'id': 'Q1', 'ask': 'Giảm bao nhiêu muối thì huyết áp giảm?'},
               {'id': 'Q2', 'ask': 'Có ai không nên giảm muối?', 'answer': 'Có.',
                'claim_ids': ['C01']})
    assert [item['id'] for item in open_questions(project)] == ['Q1']
    assert [item['id'] for item in answered_questions(project)] == ['Q2']


def test_writer_questions_route_back_to_research(tmp_path):
    project = _queue(tmp_path)
    _questions(project, {'id': 'Q1', 'line': 'N01', 'ask': 'Muối giữ nước ở đâu?'})
    state = {'value': WorkflowState.DRAFT_READY}
    steps: list[tuple[str, str]] = []

    def invoke(slots, prompt, *, cwd, log_dir, **kwargs):
        del cwd
        steps.append((kwargs['step'], kwargs['role']))
        if kwargs['step'] == 'research':
            _questions(project, {'id': 'Q1', 'line': 'N01', 'ask': 'Muối giữ nước ở đâu?',
                                 'answer': 'Natri kéo nước vào lòng mạch.',
                                 'claim_ids': ['C01']})
        elif kwargs['step'] == 'draft':
            assert 'Natri kéo nước vào lòng mạch.' in prompt
            assert 'Q1' in prompt
            _script(project, 'Natri kéo nước vào mạch, huyết áp lên.')
            (project / REV / QUESTIONS).unlink()
        else:
            _passing_report(project)
        return _result(slots, log_dir)

    report = run_queue(tmp_path, _deps(state, invoke))

    assert steps == [('research', 'medical_expert'), ('draft', 'writer'),
                     ('script_review', 'script_critic')]
    assert report.blocked == []
    assert report.at_gate == [SLUG]


def test_unanswered_questions_after_research_block(tmp_path):
    project = _queue(tmp_path)
    _questions(project, {'id': 'Q1', 'ask': 'Muối giữ nước ở đâu?'})
    state = {'value': WorkflowState.DRAFT_READY}

    def invoke(slots, prompt, *, cwd, log_dir, **kwargs):
        del prompt, cwd, kwargs
        return _result(slots, log_dir)

    report = run_queue(tmp_path, _deps(state, invoke))

    assert report.blocked == [SLUG]
    blocked = (tmp_path / 'topics/logs' / SLUG / 'blocked.txt').read_text(encoding='utf-8')
    assert 'questions.yaml' in blocked


def test_writer_must_use_expert_answers(tmp_path):
    project = _queue(tmp_path)
    _questions(project, {'id': 'Q1', 'ask': 'Muối giữ nước ở đâu?', 'answer': 'Trong mạch.'})
    state = {'value': WorkflowState.DRAFT_READY}
    steps = []

    def invoke(slots, prompt, *, cwd, log_dir, **kwargs):
        del prompt, cwd
        steps.append(kwargs['step'])
        _script(project, 'Bản viết lại nhưng quên câu trả lời.')
        return _result(slots, log_dir)

    report = run_queue(tmp_path, _deps(state, invoke))

    assert steps == ['draft']
    assert report.blocked == [SLUG]
    blocked = (tmp_path / 'topics/logs' / SLUG / 'blocked.txt').read_text(encoding='utf-8')
    assert 'câu trả lời' in blocked


def test_malformed_questions_block_with_readable_error(tmp_path):
    project = _queue(tmp_path)
    (project / REV / QUESTIONS).write_text('questions: [{id: Q1}]\n', encoding='utf-8')
    state = {'value': WorkflowState.DRAFT_READY}

    def invoke(slots, prompt, *, cwd, log_dir, **kwargs):
        raise AssertionError('no agent may run on a malformed questions file')

    report = run_queue(tmp_path, _deps(state, invoke))

    assert report.blocked == [SLUG]
    blocked = (tmp_path / 'topics/logs' / SLUG / 'blocked.txt').read_text(encoding='utf-8')
    assert 'questions.yaml' in blocked


def test_evidence_ready_requires_expert_brief(tmp_path):
    project = _queue(tmp_path)
    state = {'value': WorkflowState.TOPIC_SELECTED}
    steps = []

    def lazy_expert(slots, prompt, *, cwd, log_dir, **kwargs):
        del prompt, cwd
        steps.append(kwargs['step'])
        state['value'] = WorkflowState.EVIDENCE_READY  # ledger built, brief forgotten
        return _result(slots, log_dir)

    deps = _deps(state, lazy_expert, expert_brief_ready=expert_brief_ready)
    report = run_queue(tmp_path, deps)

    assert steps == ['research']
    assert report.blocked == [SLUG]
    blocked = (tmp_path / 'topics/logs' / SLUG / 'blocked.txt').read_text(encoding='utf-8')
    assert 'expert-brief.md' in blocked
    assert not expert_brief_ready(project)

    # Next run: an evidence_ready project without a brief goes back to the expert, not the writer.
    def expert_then_writer(slots, prompt, *, cwd, log_dir, **kwargs):
        del prompt, cwd
        steps.append(kwargs['step'])
        if kwargs['step'] == 'research':
            (project / REV / EXPERT_BRIEF).write_text(
                '# Brief\n- Cơ chế: C01\n', encoding='utf-8')
        else:
            state['value'] = WorkflowState.AWAITING_MEDICAL_REVIEW
        return _result(slots, log_dir)

    deps = _deps(state, expert_then_writer, expert_brief_ready=expert_brief_ready)
    report = run_queue(tmp_path, deps)

    assert steps == ['research', 'research', 'draft']
    assert expert_brief_ready(project)
    assert report.blocked == []
    assert report.at_gate == [SLUG]


def test_default_factory_deps_require_the_brief(tmp_path):
    from healthvideo.workflows.factory_deps import default_run_deps

    assert default_run_deps(tmp_path).expert_brief_ready is expert_brief_ready


def test_questions_file_is_kept_in_the_revision(tmp_path):
    project = create_v2_project_fixture(tmp_path)
    _questions(project, {'id': 'Q1', 'ask': 'Hỏi?'})
    assert read_yaml(project / REV / 'script/questions.yaml')['questions'][0]['id'] == 'Q1'
