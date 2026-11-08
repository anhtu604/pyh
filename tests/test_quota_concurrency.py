"""Quota updates from separate factory and dashboard processes must survive."""

import subprocess
import sys
from datetime import UTC, datetime

from healthvideo.agents import QuotaBook
from healthvideo.company import ModelSlot


def test_concurrent_processes_preserve_both_quota_rests(tmp_path):
    script = tmp_path / 'rest.py'
    script.write_text('''
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from healthvideo.agents import QuotaBook
from healthvideo.company import ModelSlot

root, model = Path(sys.argv[1]), sys.argv[2]
class SlowBook(QuotaBook):
    def _entries(self):
        entries = super()._entries()
        (root / model).touch()
        deadline = time.monotonic() + 1
        while len(list(root.glob('gpt-*'))) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        return entries

SlowBook(root / 'quota.yaml').rest(
    ModelSlot(cli='codex', model=model),
    datetime.now(UTC) + timedelta(hours=5), 'usage limit')
''', encoding='utf-8')
    models = ('gpt-6-astra', 'gpt-6.1-sol')
    processes = [subprocess.Popen([sys.executable, str(script), str(tmp_path), model])
                 for model in models]
    try:
        for process in processes:
            assert process.wait(timeout=15) == 0
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait()
    book = QuotaBook(tmp_path / 'quota.yaml')
    for model in models:
        assert book.resting(ModelSlot(cli='codex', model=model), datetime.now(UTC))
