"""Unified deterministic QA runner across script, SRT subtitles, and safe-zone plans."""

from __future__ import annotations

from pathlib import Path

from healthvideo.domain.project_v2 import ProjectManifestV2
from healthvideo.domain.script import Script
from healthvideo.qa.safe_zone import review_vertical_safe_zone
from healthvideo.qa.script import QAIssue, lint_project_script
from healthvideo.qa.subtitles import review_srt_file
from healthvideo.storage.files import read_yaml


def lint_project_qa(project_dir: Path) -> list[QAIssue]:
    """Run non-mutating deterministic QA checks on existing artifacts of the active revision.

    Script QA always runs; SRT and 9:16 safe-zone checks run when their corresponding
    artifacts exist so legacy projects/fixtures without packaged subtitles remain valid.
    """
    issues = list(lint_project_script(project_dir))
    project = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    revision = project_dir / "revisions" / project.active_revision
    script = Script.model_validate(read_yaml(revision / "script" / "script.yaml"))

    for srt_rel in ("publish/subtitles.vi.srt", "renders/subtitles.vi.srt"):
        srt_path = revision / srt_rel
        if srt_path.is_file():
            issues.extend(review_srt_file(srt_path, script=script, require_nonempty=True))

    shorts_plan_path = revision / "posts" / "shorts-plan.yaml"
    if shorts_plan_path.is_file():
        shorts_data = read_yaml(shorts_plan_path)
        for clip in shorts_data.get("clips") or ():
            if isinstance(clip, dict):
                issues.extend(review_vertical_safe_zone(clip, require_flag=True))

    clip_plan_path = revision / "script" / "clip-plan.yaml"
    if clip_plan_path.is_file():
        clip_data = read_yaml(clip_plan_path)
        for clip in clip_data.get("clips") or ():
            if isinstance(clip, dict):
                issues.extend(review_vertical_safe_zone(clip, require_flag=False))

    return issues
