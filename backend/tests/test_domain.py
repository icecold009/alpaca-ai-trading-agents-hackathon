from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from riskcourt.domain import (
    ApprovalArtifact,
    ContractModel,
    DecisionEvent,
    DecisionEventType,
    EvidenceItem,
    EvidenceType,
    ExecutionRecord,
    ExecutionStatus,
    ForecastOutcome,
    OptionLeg,
    OptionQuote,
    OptionRight,
    PnLSnapshot,
    PositionIntent,
    ProbabilityForecast,
    RiskVerdict,
    TradeDirection,
    TradeIntent,
    VerdictDecision,
)

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
EXPIRY = date(2026, 9, 18)
EVIDENCE_ID = "ev_spy_quote"
OCC_SYMBOL = "SPY260918C00600000"


def option_leg() -> OptionLeg:
    return OptionLeg(
        occ_symbol=OCC_SYMBOL,
        underlying_symbol="SPY",
        expiry=EXPIRY,
        strike=Decimal("600"),
        right=OptionRight.CALL,
        position_intent=PositionIntent.BUY_TO_OPEN,
        quantity=1,
        quote_evidence_id=EVIDENCE_ID,
    )


def valid_contracts() -> list[ContractModel]:
    leg = option_leg()
    evidence_ids = (EVIDENCE_ID,)
    return [
        EvidenceItem(
            evidence_id=EVIDENCE_ID,
            evidence_type=EvidenceType.OPTION_QUOTE,
            source="alpaca-recorded",
            symbol="SPY",
            observed_at=NOW,
            payload_sha256="a" * 64,
            summary="Recorded SPY option quote.",
            raw_reference="fixtures/cases/edge-positive.json#/evidence/0",
        ),
        OptionQuote(
            occ_symbol=OCC_SYMBOL,
            underlying_symbol="SPY",
            expiry=EXPIRY,
            strike=Decimal("600"),
            right=OptionRight.CALL,
            evidence_id=EVIDENCE_ID,
            bid=Decimal("3.10"),
            ask=Decimal("3.20"),
            quoted_at=NOW,
        ),
        leg,
        ProbabilityForecast(
            forecast_id="forecast_market",
            case_id="case_edge_positive",
            juror_id="juror_market",
            outcome=ForecastOutcome.ABOVE_STRIKE,
            probability=Decimal("0"),
            calibration_score=Decimal("0.9"),
            confidence_stake=Decimal("1"),
            produced_at=NOW,
            horizon_at=NOW + timedelta(days=7),
            evidence_ids=evidence_ids,
            rationale="Boundary probability fixture.",
            invalidation="The quote becomes stale.",
            model_version="recorded-v1",
            prompt_version="jury-v1",
        ),
        TradeIntent(
            intent_id="intent_edge_positive",
            case_id="case_edge_positive",
            underlying_symbol="SPY",
            direction=TradeDirection.BULLISH,
            legs=(leg,),
            maximum_loss=Decimal("320"),
            created_at=NOW,
            expires_at=NOW + timedelta(minutes=2),
            evidence_ids=evidence_ids,
            thesis="Jury odds clear the option hurdle.",
            invalidation="The edge falls below policy minimum.",
        ),
        RiskVerdict(
            verdict_id="verdict_edge_positive",
            case_id="case_edge_positive",
            intent_id="intent_edge_positive",
            decision=VerdictDecision.APPROVE,
            approved_quantity=1,
            maximum_loss=Decimal("320"),
            evaluated_at=NOW,
            evidence_ids=evidence_ids,
            policy_version="risk-v1",
            reasons=("Within the fixed loss cap.",),
        ),
        ApprovalArtifact(
            approval_id="approval_edge_positive",
            case_id="case_edge_positive",
            intent_id="intent_edge_positive",
            verdict_id="verdict_edge_positive",
            approved_at=NOW,
            expires_at=NOW + timedelta(seconds=30),
            approved_quantity=1,
            maximum_loss=Decimal("320"),
            evidence_ids=evidence_ids,
            policy_version="risk-v1",
        ),
        DecisionEvent(
            event_id="event_approval",
            case_id="case_edge_positive",
            sequence=0,
            event_type=DecisionEventType.APPROVAL_ISSUED,
            occurred_at=NOW,
            evidence_ids=evidence_ids,
            payload={"approval_id": "approval_edge_positive", "approved": True},
        ),
        ExecutionRecord(
            execution_id="execution_edge_positive",
            case_id="case_edge_positive",
            intent_id="intent_edge_positive",
            approval_id="approval_edge_positive",
            client_order_id="riskcourt-case-edge-positive-v1",
            status=ExecutionStatus.FILLED,
            legs=(leg,),
            submitted_at=NOW,
            filled_at=NOW + timedelta(seconds=2),
            filled_debit=Decimal("318"),
            evidence_ids=evidence_ids,
        ),
        PnLSnapshot(
            snapshot_id="pnl_edge_positive",
            case_id="case_edge_positive",
            execution_id="execution_edge_positive",
            observed_at=NOW + timedelta(hours=1),
            position_value=Decimal("350"),
            cost_basis=Decimal("318"),
            unrealized_pnl=Decimal("32"),
            realized_pnl=Decimal("0"),
            maximum_loss=Decimal("318"),
            evidence_ids=evidence_ids,
        ),
    ]


def test_all_contracts_round_trip_through_json() -> None:
    for contract in valid_contracts():
        contract_type = type(contract)
        restored = contract_type.model_validate_json(contract.model_dump_json())
        assert restored == contract


def test_probability_boundaries_are_valid() -> None:
    forecast = valid_contracts()[3]
    assert isinstance(forecast, ProbabilityForecast)
    assert forecast.probability == 0

    upper = forecast.model_copy(update={"probability": Decimal("1")})
    assert ProbabilityForecast.model_validate(upper.model_dump()).probability == 1


@pytest.mark.parametrize(
    ("contract_type", "payload", "message"),
    [
        (
            EvidenceItem,
            {
                "evidence_id": EVIDENCE_ID,
                "evidence_type": "option_quote",
                "source": "recorded",
                "symbol": "SPY",
                "observed_at": datetime(2026, 8, 29, 12, 0),
                "payload_sha256": "a" * 64,
                "summary": "Naive timestamp is unsafe.",
                "raw_reference": "fixture",
            },
            "timezone",
        ),
        (
            OptionQuote,
            {
                "occ_symbol": "SPY-BAD",
                "underlying_symbol": "SPY",
                "expiry": EXPIRY,
                "strike": Decimal("600"),
                "right": "call",
                "evidence_id": EVIDENCE_ID,
                "bid": Decimal("3.10"),
                "ask": Decimal("3.20"),
                "quoted_at": NOW,
            },
            "string_pattern_mismatch",
        ),
        (
            TradeIntent,
            {
                "intent_id": "intent_invalid",
                "case_id": "case_invalid",
                "underlying_symbol": "SPY",
                "direction": "bullish",
                "legs": (option_leg(),),
                "maximum_loss": 320.0,
                "created_at": NOW,
                "expires_at": NOW + timedelta(minutes=1),
                "evidence_ids": (EVIDENCE_ID,),
                "thesis": "Unsafe binary float.",
                "invalidation": "None.",
            },
            "decimal values must be supplied",
        ),
        (
            ProbabilityForecast,
            {
                **valid_contracts()[3].model_dump(),
                "evidence_ids": (),
            },
            "too_short",
        ),
    ],
)
def test_malformed_contracts_are_rejected(
    contract_type: type[EvidenceItem | OptionQuote | TradeIntent | ProbabilityForecast],
    payload: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        contract_type.model_validate(payload)
