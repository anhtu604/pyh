from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from healthvideo.domain.topic import TopicCard
from healthvideo.jev.config import resolve_jev_config
from healthvideo.storage.files import read_yaml
from healthvideo.workflows.jev_triage import (
    recommend_second_model_review,
    triage_claims_advisory,
    triage_topic_advisory,
)
from healthvideo.workflows.operations import project_mutation

app = typer.Typer(help="Jev (TypeSafe) structured advisory decision-routing.")


@app.command("check")
def jev_check(
    as_json: Annotated[bool, typer.Option("--json", help="In JSON format")] = False,
) -> None:
    """Xác nhận cấu hình và trạng thái opt-in của Jev decision engine."""
    config = resolve_jev_config()
    payload = {
        "status": "configured" if config.is_configured else "unconfigured",
        "api_key": config.masked_key,
        "model": config.model,
        "confidence_threshold": config.confidence_threshold,
        "timeout_seconds": config.timeout_seconds,
        "max_input_bytes": config.max_input_bytes,
    }
    if as_json:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        typer.echo("TypeSafe Jev status:")
        typer.echo(f"  Configuration: {payload['status']}")
        typer.echo(f"  API Key: {payload['api_key']}")
        typer.echo(f"  Model: {payload['model']}")
        typer.echo(f"  Confidence threshold: {payload['confidence_threshold']}")


@app.command("triage-topic")
def jev_triage_topic(
    card_path: Annotated[Path, typer.Argument(help="Đường dẫn tới topic card YAML")],
    as_json: Annotated[bool, typer.Option("--json", help="In JSON format")] = False,
) -> None:
    """Chạy topic triage advisory không làm biến đổi topic card."""
    if not card_path.is_file():
        typer.echo(f"Không tìm thấy topic card: {card_path}", err=True)
        raise typer.Exit(code=1)
    card = TopicCard.model_validate(read_yaml(card_path))
    record = triage_topic_advisory(card)
    if as_json:
        typer.echo(record.model_dump_json(indent=2))
    else:
        typer.echo("Topic triage advisory:")
        typer.echo(f"  Priority band: {record.normalized_choice}")
        typer.echo(f"  Confidence: {record.confidence:.2f}")
        typer.echo(f"  Flags: {', '.join(record.flags) if record.flags else 'none'}")
        typer.echo(f"  Reason: {record.reason}")


@app.command("triage-claims")
@project_mutation("jev_triage_claims", skip_when=lambda values: not bool(values.get("save")))
def jev_triage_claims(
    project_dir: Annotated[Path, typer.Argument(help="Thư mục project v2")],
    save: Annotated[bool, typer.Option("--save", help="Lưu advisory record vào revision")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="In JSON format")] = False,
) -> None:
    """Chạy claim triage advisory cho các claim đã có nguồn."""
    if not project_dir.is_dir():
        typer.echo(f"Không tìm thấy project: {project_dir}", err=True)
        raise typer.Exit(code=1)
    records = triage_claims_advisory(project_dir, write_artifact=save)
    if as_json:
        typer.echo(json.dumps([r.model_dump(mode="json") for r in records], indent=2, ensure_ascii=False))
    else:
        typer.echo(f"Claim triage advisory: Đã đánh giá {len(records)} claim(s)")
        for r in records:
            typer.echo(f"  - Flag: {r.normalized_choice} (conf={r.confidence:.2f}) - {r.reason}")


@app.command("recommend-review")
@project_mutation("jev_recommend_review", skip_when=lambda values: not bool(values.get("save")))
def jev_recommend_review(
    project_dir: Annotated[Path, typer.Argument(help="Thư mục project v2")],
    save: Annotated[bool, typer.Option("--save", help="Lưu advisory record vào revision")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="In JSON format")] = False,
) -> None:
    """Đề xuất có nên chạy second-model review hay không theo policy."""
    if not project_dir.is_dir():
        typer.echo(f"Không tìm thấy project: {project_dir}", err=True)
        raise typer.Exit(code=1)
    record = recommend_second_model_review(project_dir, write_artifact=save)
    if as_json:
        typer.echo(record.model_dump_json(indent=2))
    else:
        typer.echo("Second-model recommendation:")
        typer.echo(f"  Recommendation: {record.normalized_choice}")
        typer.echo(f"  Confidence: {record.confidence:.2f}")
        typer.echo(f"  Reason: {record.reason}")
        if record.normalized_choice in ("consider_review", "manual_review_required"):
            typer.echo("  Lệnh tiếp theo (thủ công):")
            typer.echo("    healthvideo agent review-request <project> --reason high_risk_claim")
