from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from healthvideo.domain.topic import (
    TopicCard,
    TopicScores,
    TopicSignal,
    calculate_triage_rank,
)
from healthvideo.storage.files import read_yaml


def test_topic_signal_model() -> None:
    now = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)
    signal = TopicSignal(
        platform="tiktok",
        url="https://example.com/trend",
        query="an man co tang huyet ap",
        timestamp=now,
        trend_metric=85.5,
    )
    assert signal.platform == "tiktok"
    assert signal.trend_metric == 85.5


def test_topic_scores_validation() -> None:
    scores = TopicScores(
        novelty=0.8,
        preventive_value=0.9,
        evidence_readiness=0.7,
        clarity=0.85,
        harm_risk=0.2,
        production_cost=0.3,
    )
    assert scores.preventive_value == 0.9

    with pytest.raises(ValidationError):
        TopicScores(novelty=1.5)

    with pytest.raises(ValidationError):
        TopicScores(harm_risk=-0.1)


def test_calculate_triage_rank_prioritizes_high_prevention_and_evidence() -> None:
    high_priority = TopicScores(
        preventive_value=0.95,
        evidence_readiness=0.9,
        clarity=0.9,
        novelty=0.7,
        harm_risk=0.1,
        production_cost=0.2,
    )
    low_priority = TopicScores(
        preventive_value=0.2,
        evidence_readiness=0.3,
        clarity=0.4,
        novelty=0.2,
        harm_risk=0.8,
        production_cost=0.9,
    )
    rank_high = calculate_triage_rank(high_priority)
    rank_low = calculate_triage_rank(low_priority)
    assert rank_high > rank_low
    assert 0.0 <= rank_high <= 1.0


def test_topic_card_model_and_backward_compatibility() -> None:
    now = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)
    card = TopicCard(
        id="T001",
        slug="muoi-va-huyet-ap",
        title="Ăn mặn và tăng huyết áp",
        question="Ăn mặn có thực sự làm tăng huyết áp không?",
        target_audience="Người trưởng thành",
        created_at=now,
    )
    assert card.schema_version == "2.0"
    assert card.status == "inbox"
    assert card.scores.preventive_value == 0.5

    # Test compatibility with migration fixture card.yaml format
    fixture_dict = {
        "schema_version": "2.0",
        "synthetic_test_record": True,
        "slug": "muoi-va-huyet-ap",
        "title": "Ăn mặn và tăng huyết áp",
        "origin": "migration_fixture",
    }
    loaded = TopicCard.model_validate(fixture_dict)
    assert loaded.slug == "muoi-va-huyet-ap"
    assert loaded.synthetic_test_record is True
    assert loaded.id == "muoi-va-huyet-ap"

    golden_card = Path("tests/fixtures/golden-project-v2/revisions/001/topic/card.yaml")
    assert golden_card.is_file()
    validated_golden = TopicCard.model_validate(read_yaml(golden_card))
    assert validated_golden.slug == "muoi-va-huyet-ap"
    assert validated_golden.title == "Ăn mặn và tăng huyết áp"
