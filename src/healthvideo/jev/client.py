from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Protocol

from healthvideo.domain.jev_decision import (
    ClaimCheckFlag,
    ClaimTriageInput,
    JevAdvisoryRecord,
    JevDecisionKind,
    SecondModelRecommendation,
    SecondModelRoutingInput,
    TopicPriorityBand,
    TopicTriageInput,
)
from healthvideo.jev.config import JevConfig


class JevTransport(Protocol):
    def decide(
        self,
        *,
        decision_type: str,
        input_payload: dict[str, Any],
        model: str,
    ) -> dict[str, Any]:
        """Send decision request and return structured response payload."""
        ...


class FakeJevTransport:
    def __init__(self, default_response: dict[str, Any] | None = None) -> None:
        self.default_response = default_response or {
            "choice": "standard",
            "confidence": 0.95,
            "flags": [],
            "reason": "OK",
        }
        self.calls: list[dict[str, Any]] = []

    def decide(
        self,
        *,
        decision_type: str,
        input_payload: dict[str, Any],
        model: str,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "decision_type": decision_type,
                "input_payload": input_payload,
                "model": model,
            }
        )
        return dict(self.default_response)


class TypeSafeSdkTransport:
    def __init__(self, api_key: str | None, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url

    def decide(
        self,
        *,
        decision_type: str,
        input_payload: dict[str, Any],
        model: str,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise ValueError("TypeSafe API key is required")
        try:
            import typesafe  # type: ignore[import-not-found]
        except ImportError as err:
            try:
                import typesafe_sdk as typesafe  # type: ignore[import-not-found,no-redef]
            except ImportError:
                raise RuntimeError(
                    "Official typesafe-sdk package is not installed."
                ) from err

        client = typesafe.Client(api_key=self.api_key, base_url=self.base_url)
        return client.decisions.create(
            decision_type=decision_type,
            input=input_payload,
            model=model,
        )


def _canonical_hash(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class JevClient:
    def __init__(self, config: JevConfig, transport: JevTransport | None = None) -> None:
        self.config = config
        self.transport = transport or TypeSafeSdkTransport(
            api_key=config.api_key,
            base_url=config.base_url,
        )

    def _generate_decision_id(self, now: datetime) -> str:
        timestamp_str = now.strftime("%Y%m%dT%H%M%SZ")
        digest = hashlib.sha256(str(now.timestamp()).encode("utf-8")).hexdigest()[:8]
        return f"{timestamp_str}-{digest}"

    def evaluate_topic(
        self,
        input_data: TopicTriageInput,
        *,
        now: datetime | None = None,
    ) -> JevAdvisoryRecord:
        timestamp = now or datetime.now(UTC)
        payload = input_data.model_dump(mode="json")
        input_hash = _canonical_hash(payload)
        decision_id = self._generate_decision_id(timestamp)

        if not self.config.is_configured:
            return JevAdvisoryRecord(
                decision_id=decision_id,
                decision_kind=JevDecisionKind.TOPIC_TRIAGE,
                normalized_choice=TopicPriorityBand.MANUAL_REVIEW_REQUIRED.value,
                confidence=0.0,
                model_identifier=self.config.model,
                input_hash=input_hash,
                created_at=timestamp,
                reason="TYPESAFE_API_KEY chưa được cấu hình (fail-closed manual review)",
                policy_threshold=self.config.confidence_threshold,
                flags=[TopicPriorityBand.MANUAL_REVIEW_REQUIRED.value],
            )

        try:
            raw = self.transport.decide(
                decision_type="topic_triage",
                input_payload=payload,
                model=self.config.model,
            )
            raw_confidence = float(raw.get("confidence", 0.0))
            raw_choice = str(raw.get("choice", "")).strip().lower()
            flags = [str(f) for f in raw.get("flags", [])]
            raw_reason = str(raw.get("reason", "Topic triage evaluation")).strip()

            if raw_confidence < self.config.confidence_threshold:
                return JevAdvisoryRecord(
                    decision_id=decision_id,
                    decision_kind=JevDecisionKind.TOPIC_TRIAGE,
                    normalized_choice=TopicPriorityBand.MANUAL_REVIEW_REQUIRED.value,
                    confidence=raw_confidence,
                    model_identifier=self.config.model,
                    input_hash=input_hash,
                    created_at=timestamp,
                    reason=f"Độ tin cậy ({raw_confidence:.2f}) dưới ngưỡng tin cậy ({self.config.confidence_threshold:.2f})",
                    policy_threshold=self.config.confidence_threshold,
                    flags=flags or [TopicPriorityBand.MANUAL_REVIEW_REQUIRED.value],
                )

            valid_choices = {b.value for b in TopicPriorityBand}
            choice = raw_choice if raw_choice in valid_choices else TopicPriorityBand.MANUAL_REVIEW_REQUIRED.value

            return JevAdvisoryRecord(
                decision_id=decision_id,
                decision_kind=JevDecisionKind.TOPIC_TRIAGE,
                normalized_choice=choice,
                confidence=raw_confidence,
                model_identifier=self.config.model,
                input_hash=input_hash,
                created_at=timestamp,
                reason=raw_reason[:490],
                policy_threshold=self.config.confidence_threshold,
                flags=flags,
            )
        except Exception as exc:  # noqa: BLE001 - fail-closed boundary for external SDK/transport
            return JevAdvisoryRecord(
                decision_id=decision_id,
                decision_kind=JevDecisionKind.TOPIC_TRIAGE,
                normalized_choice=TopicPriorityBand.MANUAL_REVIEW_REQUIRED.value,
                confidence=0.0,
                model_identifier=self.config.model,
                input_hash=input_hash,
                created_at=timestamp,
                reason=f"Lỗi transport hoặc phản hồi không hợp lệ: {exc}"[:490],
                policy_threshold=self.config.confidence_threshold,
                flags=[TopicPriorityBand.MANUAL_REVIEW_REQUIRED.value],
            )

    def evaluate_claim(
        self,
        input_data: ClaimTriageInput,
        *,
        now: datetime | None = None,
    ) -> JevAdvisoryRecord:
        timestamp = now or datetime.now(UTC)
        payload = input_data.model_dump(mode="json")
        input_hash = _canonical_hash(payload)
        decision_id = self._generate_decision_id(timestamp)

        if not self.config.is_configured:
            return JevAdvisoryRecord(
                decision_id=decision_id,
                decision_kind=JevDecisionKind.CLAIM_TRIAGE,
                normalized_choice=ClaimCheckFlag.MANUAL_REVIEW_REQUIRED.value,
                confidence=0.0,
                model_identifier=self.config.model,
                input_hash=input_hash,
                created_at=timestamp,
                reason="TYPESAFE_API_KEY chưa được cấu hình (fail-closed manual review)",
                policy_threshold=self.config.confidence_threshold,
                flags=[ClaimCheckFlag.MANUAL_REVIEW_REQUIRED.value],
            )

        try:
            raw = self.transport.decide(
                decision_type="claim_triage",
                input_payload=payload,
                model=self.config.model,
            )
            raw_confidence = float(raw.get("confidence", 0.0))
            raw_choice = str(raw.get("choice", "")).strip().lower()
            flags = [str(f) for f in raw.get("flags", [])]
            raw_reason = str(raw.get("reason", "Claim triage evaluation")).strip()

            if raw_confidence < self.config.confidence_threshold:
                return JevAdvisoryRecord(
                    decision_id=decision_id,
                    decision_kind=JevDecisionKind.CLAIM_TRIAGE,
                    normalized_choice=ClaimCheckFlag.MANUAL_REVIEW_REQUIRED.value,
                    confidence=raw_confidence,
                    model_identifier=self.config.model,
                    input_hash=input_hash,
                    created_at=timestamp,
                    reason=f"Độ tin cậy ({raw_confidence:.2f}) dưới ngưỡng tin cậy ({self.config.confidence_threshold:.2f})",
                    policy_threshold=self.config.confidence_threshold,
                    flags=flags or [ClaimCheckFlag.MANUAL_REVIEW_REQUIRED.value],
                )

            valid_choices = {c.value for c in ClaimCheckFlag}
            choice = raw_choice if raw_choice in valid_choices else ClaimCheckFlag.MANUAL_REVIEW_REQUIRED.value

            return JevAdvisoryRecord(
                decision_id=decision_id,
                decision_kind=JevDecisionKind.CLAIM_TRIAGE,
                normalized_choice=choice,
                confidence=raw_confidence,
                model_identifier=self.config.model,
                input_hash=input_hash,
                created_at=timestamp,
                reason=raw_reason[:490],
                policy_threshold=self.config.confidence_threshold,
                flags=flags,
            )
        except Exception as exc:  # noqa: BLE001 - fail-closed boundary for external SDK/transport
            return JevAdvisoryRecord(
                decision_id=decision_id,
                decision_kind=JevDecisionKind.CLAIM_TRIAGE,
                normalized_choice=ClaimCheckFlag.MANUAL_REVIEW_REQUIRED.value,
                confidence=0.0,
                model_identifier=self.config.model,
                input_hash=input_hash,
                created_at=timestamp,
                reason=f"Lỗi transport hoặc phản hồi không hợp lệ: {exc}"[:490],
                policy_threshold=self.config.confidence_threshold,
                flags=[ClaimCheckFlag.MANUAL_REVIEW_REQUIRED.value],
            )

    def evaluate_second_model(
        self,
        input_data: SecondModelRoutingInput,
        *,
        now: datetime | None = None,
    ) -> JevAdvisoryRecord:
        timestamp = now or datetime.now(UTC)
        payload = input_data.model_dump(mode="json")
        input_hash = _canonical_hash(payload)
        decision_id = self._generate_decision_id(timestamp)

        if not self.config.is_configured:
            return JevAdvisoryRecord(
                decision_id=decision_id,
                decision_kind=JevDecisionKind.SECOND_MODEL_ROUTING,
                normalized_choice=SecondModelRecommendation.MANUAL_REVIEW_REQUIRED.value,
                confidence=0.0,
                model_identifier=self.config.model,
                input_hash=input_hash,
                created_at=timestamp,
                reason="TYPESAFE_API_KEY chưa được cấu hình (fail-closed manual review)",
                policy_threshold=self.config.confidence_threshold,
                flags=[SecondModelRecommendation.MANUAL_REVIEW_REQUIRED.value],
            )

        try:
            raw = self.transport.decide(
                decision_type="second_model_routing",
                input_payload=payload,
                model=self.config.model,
            )
            raw_confidence = float(raw.get("confidence", 0.0))
            raw_choice = str(raw.get("choice", "")).strip().lower()
            flags = [str(f) for f in raw.get("flags", [])]
            raw_reason = str(raw.get("reason", "Second-model routing recommendation")).strip()

            if raw_confidence < self.config.confidence_threshold:
                return JevAdvisoryRecord(
                    decision_id=decision_id,
                    decision_kind=JevDecisionKind.SECOND_MODEL_ROUTING,
                    normalized_choice=SecondModelRecommendation.MANUAL_REVIEW_REQUIRED.value,
                    confidence=raw_confidence,
                    model_identifier=self.config.model,
                    input_hash=input_hash,
                    created_at=timestamp,
                    reason=f"Độ tin cậy ({raw_confidence:.2f}) dưới ngưỡng tin cậy ({self.config.confidence_threshold:.2f})",
                    policy_threshold=self.config.confidence_threshold,
                    flags=flags or [SecondModelRecommendation.MANUAL_REVIEW_REQUIRED.value],
                )

            valid_choices = {r.value for r in SecondModelRecommendation}
            choice = raw_choice if raw_choice in valid_choices else SecondModelRecommendation.MANUAL_REVIEW_REQUIRED.value

            return JevAdvisoryRecord(
                decision_id=decision_id,
                decision_kind=JevDecisionKind.SECOND_MODEL_ROUTING,
                normalized_choice=choice,
                confidence=raw_confidence,
                model_identifier=self.config.model,
                input_hash=input_hash,
                created_at=timestamp,
                reason=raw_reason[:490],
                policy_threshold=self.config.confidence_threshold,
                flags=flags,
            )
        except Exception as exc:  # noqa: BLE001 - fail-closed boundary for external SDK/transport
            return JevAdvisoryRecord(
                decision_id=decision_id,
                decision_kind=JevDecisionKind.SECOND_MODEL_ROUTING,
                normalized_choice=SecondModelRecommendation.MANUAL_REVIEW_REQUIRED.value,
                confidence=0.0,
                model_identifier=self.config.model,
                input_hash=input_hash,
                created_at=timestamp,
                reason=f"Lỗi transport hoặc phản hồi không hợp lệ: {exc}"[:490],
                policy_threshold=self.config.confidence_threshold,
                flags=[SecondModelRecommendation.MANUAL_REVIEW_REQUIRED.value],
            )
