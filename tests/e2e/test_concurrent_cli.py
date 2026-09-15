import os
import subprocess
import sys
from pathlib import Path

from healthvideo.storage.files import read_yaml
from tests.helpers import create_v2_project_fixture

HOLDER = r"""
import os
import sys
from pathlib import Path
from healthvideo.workflows.operations import mutation_lease

project = Path(os.environ["HEALTHVIDEO_TEST_PROJECT"])
with mutation_lease(project, "test_holder"):
    print("READY", flush=True)
    signal = sys.stdin.readline().strip()
    if signal == "FAIL":
        raise RuntimeError("controlled holder failure")
    if not signal:
        raise SystemExit("parent pipe closed")
print("RELEASED", flush=True)
"""

CONTENDER = r"""
import sys
from typer.testing import CliRunner
from healthvideo.cli import app

result = CliRunner().invoke(
    app,
    ["agent", "review-request", sys.argv[1], "--reason", "conflicting_evidence"],
)
sys.stdout.write(result.stdout)
raise SystemExit(result.exit_code)
"""

STATUS = r"""
import sys
from typer.testing import CliRunner
from healthvideo.cli import app

result = CliRunner().invoke(app, ["operator", "status", sys.argv[1], "--json"])
sys.stdout.buffer.write(result.stdout.encode("utf-8"))
raise SystemExit(result.exit_code)
"""


def test_two_processes_serialize_one_project_mutation(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path)
    before = (project / "project.yaml").read_bytes()
    environment = os.environ.copy()
    environment["HEALTHVIDEO_TEST_PROJECT"] = str(project)
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLDER],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "READY"
        blocked = subprocess.run(
            [sys.executable, "-c", CONTENDER, str(project)],
            capture_output=True,
            text=True,
            check=False,
        )

        assert blocked.returncode == 1
        assert "Project busy" in blocked.stdout
        assert (project / "project.yaml").read_bytes() == before
        readable = subprocess.run(
            [sys.executable, "-c", STATUS, str(project)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert readable.returncode == 0, readable.stdout + readable.stderr
        assert '"busy": true' in readable.stdout.lower()
    finally:
        assert holder.stdin is not None
        holder.stdin.write("FAIL\n")
        holder.stdin.flush()
        stdout, stderr = holder.communicate(timeout=10)
        assert holder.returncode != 0
        assert "controlled holder failure" in stderr
        assert "RELEASED" not in stdout
        assert not (project / ".healthvideo" / "write-lease.yaml").exists()

    retried = subprocess.run(
        [sys.executable, "-c", CONTENDER, str(project)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert retried.returncode == 0, retried.stdout + retried.stderr
    assert read_yaml(project / "project.yaml")["state"] == "awaiting_second_model_review"
    assert not (project / ".healthvideo" / "write-lease.yaml").exists()
