import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "path",
    [
        "projects/2026/09/topic/revisions/001/assets/ai-clips/S04.mp4",
        "projects/2026/09/topic/revisions/001/workflow/staged-ai-clips/S04-0a.mp4",
        "projects/2026/09/topic/revisions/001/renders/video.mp4",
        "projects/2026/09/topic/revisions/001/audio/narration.wav",
        "projects/2026/09/topic/.healthvideo/write-lease.yaml",
        "projects/2026/09/topic/.healthvideo/stale-leases/old.yaml",
    ],
)
def test_generated_project_media_is_never_tracked(path: str) -> None:
    if shutil.which("git") is None or not (REPO / ".git").exists():
        pytest.skip("git work tree unavailable")
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--quiet", path],
        cwd=REPO,
        check=False,
    )
    assert result.returncode == 0, f"{path} is not ignored"
