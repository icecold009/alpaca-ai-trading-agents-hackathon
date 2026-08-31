from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from riskcourt.approval_guard import (
    ApprovalCheck,
    IdempotencyRegistry,
    SubmissionAction,
    create_approval_binding,
    validate_approval_for_execution,
)
from riskcourt.domain import (
    ApprovalArtifact,
    EvidenceItem,
    EvidenceType,
    OptionLeg,
    OptionRight,
    PositionIntent,
    TradeDirection,
    TradeIntent,
)

NOW = datetime(2026, 8, 29, 12, tzinfo=UTC)
EVIDENCE_IDS = ("ev_underlying", "ev_call_600", "ev_call_605", "ev_account")


def evidence_item(evidence_id: str, evidence_type: EvidenceType, marker: str) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        evidence_type=evidence_type,
        source="recorded",
        symbol="SPY",
        observed_at=NOW,
        payload_sha256=marker * 64,
        summary=f"{evidence_type} snapshot.",
        raw_reference=f"fixture#/{evidence_id}",
    )


def evidence() -> tuple[EvidenceItem, ...]:
    return (
        evidence_item("ev_underlying", EvidenceType.UNDERLYING_QUOTE, "1"),
        evidence_item("ev_call_600", EvidenceType.OPTION_QUOTE, "2"),
        evidence_item("ev_call_605", EvidenceType.OPTION_QUOTE, "3"),
        evidence_item("ev_account", EvidenceType.ACCOUNT, "4"),
    )


def intent() -> TradeIntent:
    expiry = date(2026, 9, 18)
    return TradeIntent(
        intent_id="intent_approval",
        case_id="case_approval",
        underlying_symbol="SPY",
        direction=TradeDirection.BULLISH,
        legs=(
            OptionLeg(
                occ_symbol="SPY260918C00600000",
                underlying_symbol="SPY",
                expiry=expiry,
                strike=Decimal("600"),
                right=OptionRight.CALL,
                position_intent=PositionIntent.BUY_TO_OPEN,
                quantity=1,
                quote_evidence_id="ev_call_600",
            ),
            OptionLeg(
                occ_symbol="SPY260918C00605000",
                underlying_symbol="SPY",
                expiry=expiry,
                strike=Decimal("605"),
                right=OptionRight.CALL,
                position_intent=PositionIntent.SELL_TO_OPEN,
                quantity=1,
                quote_evidence_id="ev_call_605",
            ),
        ),
        maximum_loss=Decimal("150"),
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=2),
        evidence_ids=EVIDENCE_IDS,
        thesis="Bound approval test.",
        invalidation="Any input changes.",
    )


def approval() -> ApprovalArtifact:
    return ApprovalArtifact(
        approval_id="approval_bound",
        case_id="case_approval",
        intent_id="intent_approval",
        verdict_id="verdict_bound",
        approved_at=NOW,
        expires_at=NOW + timedelta(seconds=30),
        approved_quantity=1,
        maximum_loss=Decimal("150"),
        evidence_ids=EVIDENCE_IDS,
        policy_version="risk-v1",
    )


def validate(
    *,
    current_intent: TradeIntent | None = None,
    current_evidence: tuple[EvidenceItem, ...] | None = None,
    policy_version: str = "risk-v1",
    now: datetime = NOW + timedelta(seconds=1),
    registry: IdempotencyRegistry | None = None,
) -> ApprovalCheck:
    original_intent = intent()
    original_evidence = evidence()
    binding = create_approval_binding(
        approval(),
        original_intent,
        original_evidence,
        "riskcourt-case-approval-v1",
    )
    return validate_approval_for_execution(
        binding=binding,
        current_intent=current_intent or original_intent,
        current_evidence=current_evidence or original_evidence,
        current_policy_version=policy_version,
        client_order_id="riskcourt-case-approval-v1",
        now=now,
        registry=registry or IdempotencyRegistry(),
    )


@pytest.mark.parametrize("evidence_id", EVIDENCE_IDS)
def test_evidence_mutation_matrix_rejects_each_bound_input(evidence_id: str) -> None:
    mutated = tuple(
        item.model_copy(update={"payload_sha256": "f" * 64})
        if item.evidence_id == evidence_id
        else item
        for item in evidence()
    )

    result = validate(current_evidence=mutated)

    assert result.action is SubmissionAction.REJECT
    assert result.reason == "evidence_changed"


def test_intent_policy_and_expiry_mutations_are_rejected() -> None:
    changed_intent = intent().model_copy(update={"maximum_loss": Decimal("151")})

    assert validate(current_intent=changed_intent).reason == "intent_changed"
    assert validate(policy_version="risk-v2").reason == "policy_version_changed"
    assert validate(now=NOW + timedelta(seconds=30)).reason == "approval_expired"


def test_identical_retry_replays_without_second_submission() -> None:
    registry = IdempotencyRegistry()

    first = validate(registry=registry)
    retry = validate(registry=registry)

    assert first.action is SubmissionAction.SUBMIT
    assert retry.action is SubmissionAction.REPLAY
    assert retry.reason == "idempotent_replay"


def test_conflicting_idempotency_key_is_rejected() -> None:
    registry = IdempotencyRegistry()

    assert registry.reserve("order-1", "a" * 64) is SubmissionAction.SUBMIT
    assert registry.reserve("order-1", "b" * 64) is SubmissionAction.REJECT


def test_idempotency_registry_recovers_reservations_after_restart(tmp_path: Path) -> None:
    path = tmp_path / "idempotency.json"
    first = IdempotencyRegistry(path)
    assert first.reserve("order-1", "a" * 64) is SubmissionAction.SUBMIT

    restored = IdempotencyRegistry(path)
    assert restored.reserve("order-1", "a" * 64) is SubmissionAction.REPLAY
    assert restored.reserve("order-1", "b" * 64) is SubmissionAction.REJECT
