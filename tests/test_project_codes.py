import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from healthvideo.storage.files import read_yaml, write_yaml_atomic


def project(root, slug):
    path = root / 'projects' / slug / 'project.yaml'
    write_yaml_atomic(path, {'slug': slug})
    return path


def test_codes_stay_fixed_and_removed_codes_are_never_reused(tmp_path):
    from healthvideo.project_codes import project_codes

    first = project(tmp_path, 'alpha')
    project(tmp_path, 'bravo')
    assert project_codes(tmp_path) == {'alpha': 'PYH-001', 'bravo': 'PYH-002'}
    first.unlink()
    project(tmp_path, 'aardvark')
    codes = project_codes(tmp_path)
    assert codes == {'alpha': 'PYH-001', 'bravo': 'PYH-002', 'aardvark': 'PYH-003'}
    path = tmp_path / 'topics/project-codes.yaml'
    before = path.stat().st_mtime_ns
    assert project_codes(tmp_path) == codes
    assert path.stat().st_mtime_ns == before


def test_initial_codes_follow_queue_dates_then_unqueued_slugs(tmp_path):
    from healthvideo.project_codes import project_codes

    project(tmp_path, 'alpha')
    project(tmp_path, 'zulu')
    write_yaml_atomic(tmp_path / 'topics/queue.yaml', {
        'version': 1,
        'entries': [
            {'slug': 'zulu', 'title': 'Z', 'question': 'Z?', 'added': '2026-11-15'},
            {'slug': 'bravo', 'title': 'B', 'question': 'B?', 'added': '2026-11-14'},
        ],
    })
    assert project_codes(tmp_path) == {
        'bravo': 'PYH-001', 'zulu': 'PYH-002', 'alpha': 'PYH-003',
    }


def test_parallel_requests_share_one_allocation(tmp_path):
    from healthvideo.project_codes import project_codes

    for slug in ['alpha', 'bravo', 'charlie']:
        project(tmp_path, slug)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: project_codes(tmp_path), range(20)))
    assert all(result == results[0] for result in results)
    assert len(set(results[0].values())) == 3
    assert read_yaml(tmp_path / 'topics/project-codes.yaml')['codes'] == results[0]


def test_separate_processes_share_one_registry(tmp_path):
    for slug in ['alpha', 'bravo', 'charlie']:
        project(tmp_path, slug)
    code = ('import json,sys; from pathlib import Path; '
            'from healthvideo.project_codes import project_codes; '
            'print(json.dumps(project_codes(Path(sys.argv[1]))))')

    def read_in_child(_):
        result = subprocess.run([sys.executable, '-c', code, str(tmp_path)],
                                capture_output=True, text=True, check=True, timeout=30)
        return json.loads(result.stdout)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(read_in_child, range(4)))
    assert all(result == {'alpha': 'PYH-001', 'bravo': 'PYH-002', 'charlie': 'PYH-003'}
               for result in results)


def test_corrupt_queue_does_not_hide_existing_projects(tmp_path):
    from healthvideo.project_codes import project_codes

    project(tmp_path, 'alpha')
    write_yaml_atomic(tmp_path / 'topics/queue.yaml', {'version': 99})
    assert project_codes(tmp_path) == {'alpha': 'PYH-001'}


def test_empty_factory_does_not_write_empty_registry(tmp_path):
    from healthvideo.project_codes import project_codes

    assert project_codes(tmp_path) == {}
    assert not (tmp_path / 'topics/project-codes.yaml').exists()


def test_numbering_extends_past_three_digits(tmp_path):
    from healthvideo.project_codes import project_codes

    write_yaml_atomic(tmp_path / 'topics/project-codes.yaml', {
        'version': 1, 'codes': {'retired': 'PYH-999'},
    })
    project(tmp_path, 'alpha')
    assert project_codes(tmp_path)['alpha'] == 'PYH-1000'


@pytest.mark.parametrize('payload', [
    {'version': 2, 'codes': {}},
    {'version': 1, 'codes': []},
    {'version': 1, 'codes': {'alpha': 'PYH-001', 'bravo': 'PYH-001'}},
    {'version': 1, 'codes': {'alpha': 'PYH-000'}},
    {'version': 1, 'codes': {'alpha': 'garbage'}},
    {'version': 1, 'codes': {'': 'PYH-001'}},
])
def test_malformed_registry_is_never_overwritten(tmp_path, payload):
    from healthvideo.project_codes import project_codes

    project(tmp_path, 'charlie')
    path = tmp_path / 'topics/project-codes.yaml'
    write_yaml_atomic(path, payload)
    before = path.read_bytes()
    with pytest.raises(ValueError, match='project.code'):
        project_codes(tmp_path)
    assert path.read_bytes() == before
