"""Screen orientation candidate records into an advisory revision research CSV."""

import csv
import io
import json
from pathlib import Path

from healthvideo.domain.evidence import CandidateSource
from healthvideo.domain.project_v2 import ProjectManifestV2
from healthvideo.evidence.screening import (
    CommandJudge,
    DualLLMScreener,
    Screener,
    ScreeningCriteria,
)
from healthvideo.storage.files import read_yaml, write_text_atomic

CSV_COLUMNS = (
    "id",
    "title",
    "year",
    "pub_type",
    "decision",
    "reason",
    "reviewer_1",
    "reviewer_2",
    "arbiter",
)


def screen_candidates(
    project_dir: Path,
    criteria_path: Path,
    input_path: Path,
    *,
    screener: Screener | None = None,
) -> Path:
    """Validate all inputs before reviewing; never change manifest or ledger."""
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    criteria = ScreeningCriteria.model_validate(read_yaml(criteria_path))
    candidates = [
        CandidateSource.model_validate_json(line)
        for line in input_path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    if screener is None:
        screener = DualLLMScreener(
            CommandJudge("reviewer_1"),
            CommandJudge("reviewer_2"),
            CommandJudge("arbiter"),
        )
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for candidate in candidates:
        result = screener.screen(candidate, criteria)
        row = {
            "id": candidate.source_id,
            "title": candidate.title,
            "year": candidate.year,
            "pub_type": candidate.pub_type,
            "decision": result.final.decision,
            "reason": result.final.reason,
        }
        for column in ("reviewer_1", "reviewer_2", "arbiter"):
            review = getattr(result, column)
            row[column] = (
                json.dumps(review.model_dump(mode="json"), ensure_ascii=False)
                if review is not None
                else ""
            )
        writer.writerow(row)
    output = (
        project_dir
        / "revisions"
        / manifest.active_revision
        / "research"
        / "screening.csv"
    )
    # Existing UTF-8 atomic writer plus BOM yields UTF-8-sig for Excel.
    write_text_atomic(output, "\ufeff" + stream.getvalue())
    return output
