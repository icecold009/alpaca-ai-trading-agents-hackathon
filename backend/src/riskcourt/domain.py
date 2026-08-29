"""Strict domain contracts shared by RiskCourt strategy, audit, and execution code."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    Field,
    JsonValue,
    PositiveInt,
    model_validator,
)

ID_PATTERN = r"^[a-z][a-z0-9_-]{2,63}$"
SYMBOL_PATTERN = r"^[A-Z][A-Z0-9.-]{0,9}$"
OCC_PATTERN = re.compile(r"^(?P<root>[A-Z]{1,6})(?P<expiry>\d{6})(?P<right>[CP])(?P<strike>\d{8})$")


def _reject_binary_float(value: Any) -> Any:
    if isinstance(value, float):
        raise ValueError("decimal values must be supplied as strings, integers, or Decimal objects")
    return value


Money = Annotated[
    Decimal,
    BeforeValidator(_reject_binary_float),
    Field(max_digits=18, decimal_places=6),
]
NonNegativeMoney = Annotated[Money, Field(ge=0)]
PositiveMoney = Annotated[Money, Field(gt=0)]
Probability = Annotated[
    Decimal,
    BeforeValidator(_reject_binary_float),
    Field(ge=0, le=1, max_digits=8, decimal_places=7),
]
Identifier = Annotated[str, Field(pattern=ID_PATTERN, min_length=3, max_length=64)]
Ticker = Annotated[str, Field(pattern=SYMBOL_PATTERN)]
OccSymbol = Annotated[str, Field(pattern=OCC_PATTERN.pattern)]
EvidenceIds = Annotated[tuple[Identifier, ...], Field(min_length=1)]


class ContractModel(BaseModel):
    """Default to immutable, explicit contracts with no ignored input fields."""

    model_config = {
        "extra": "forbid",
        "frozen": True,
        "str_strip_whitespace": True,
        "validate_default": True,
    }


class EvidenceType(StrEnum):
    UNDERLYING_QUOTE = "underlying_quote"
    OPTION_QUOTE = "option_quote"
    MARKET_BAR = "market_bar"
    NEWS = "news"
    ACCOUNT = "account"
    POLICY = "policy"


class OptionRight(StrEnum):
    CALL = "call"
    PUT = "put"


class PositionIntent(StrEnum):
    BUY_TO_OPEN = "buy_to_open"
    SELL_TO_OPEN = "sell_to_open"
    BUY_TO_CLOSE = "buy_to_close"
    SELL_TO_CLOSE = "sell_to_close"


class ForecastOutcome(StrEnum):
    ABOVE_STRIKE = "above_strike"
    BELOW_STRIKE = "below_strike"


class TradeDirection(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class VerdictDecision(StrEnum):
    APPROVE = "approve"
    RESIZE = "resize"
    VETO = "veto"
    ABSTAIN = "abstain"


class DecisionEventType(StrEnum):
    CASE_OPENED = "case_opened"
    FORECAST_RECORDED = "forecast_recorded"
    INTENT_PROPOSED = "intent_proposed"
    RISK_EVALUATED = "risk_evaluated"
    APPROVAL_ISSUED = "approval_issued"
    EXECUTION_UPDATED = "execution_updated"
    PNL_RECORDED = "pnl_recorded"


class ExecutionStatus(StrEnum):
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"


class EvidenceItem(ContractModel):
    evidence_id: Identifier
    evidence_type: EvidenceType
    source: Annotated[str, Field(min_length=1, max_length=120)]
    symbol: Ticker
    observed_at: AwareDatetime
    payload_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    summary: Annotated[str, Field(min_length=1, max_length=1000)]
    raw_reference: Annotated[str, Field(min_length=1, max_length=500)]


class OptionContract(ContractModel):
    occ_symbol: OccSymbol
    underlying_symbol: Ticker
    expiry: date
    strike: PositiveMoney
    right: OptionRight

    @model_validator(mode="after")
    def match_occ_components(self) -> Self:
        match = OCC_PATTERN.fullmatch(self.occ_symbol)
        if match is None:  # pragma: no cover - the field pattern rejects this first
            raise ValueError("invalid OCC option symbol")

        occ_expiry = datetime.strptime(match.group("expiry"), "%y%m%d").date()
        occ_right = OptionRight.CALL if match.group("right") == "C" else OptionRight.PUT
        occ_strike = Decimal(match.group("strike")) / Decimal("1000")
        if match.group("root") != self.underlying_symbol:
            raise ValueError("OCC root must match underlying_symbol")
        if occ_expiry != self.expiry:
            raise ValueError("OCC expiry must match expiry")
        if occ_right is not self.right:
            raise ValueError("OCC right must match right")
        if occ_strike != self.strike:
            raise ValueError("OCC strike must match strike")
        return self


class OptionQuote(OptionContract):
    evidence_id: Identifier
    bid: NonNegativeMoney
    ask: NonNegativeMoney
    quoted_at: AwareDatetime

    @model_validator(mode="after")
    def reject_crossed_market(self) -> Self:
        if self.ask < self.bid:
            raise ValueError("option ask must be greater than or equal to bid")
        return self


class OptionLeg(OptionContract):
    position_intent: PositionIntent
    quantity: PositiveInt
    quote_evidence_id: Identifier


class ProbabilityForecast(ContractModel):
    forecast_id: Identifier
    case_id: Identifier
    juror_id: Identifier
    outcome: ForecastOutcome
    probability: Probability
    calibration_score: Probability
    confidence_stake: Probability
    produced_at: AwareDatetime
    horizon_at: AwareDatetime
    evidence_ids: EvidenceIds
    rationale: Annotated[str, Field(min_length=1, max_length=2000)]
    invalidation: Annotated[str, Field(min_length=1, max_length=1000)]
    model_version: Annotated[str, Field(min_length=1, max_length=120)]
    prompt_version: Annotated[str, Field(min_length=1, max_length=120)]

    @model_validator(mode="after")
    def require_future_horizon(self) -> Self:
        if self.horizon_at <= self.produced_at:
            raise ValueError("forecast horizon must be after produced_at")
        return self


class TradeIntent(ContractModel):
    intent_id: Identifier
    case_id: Identifier
    underlying_symbol: Ticker
    direction: TradeDirection
    legs: Annotated[tuple[OptionLeg, ...], Field(min_length=1, max_length=2)]
    maximum_loss: PositiveMoney
    created_at: AwareDatetime
    expires_at: AwareDatetime
    evidence_ids: EvidenceIds
    thesis: Annotated[str, Field(min_length=1, max_length=2000)]
    invalidation: Annotated[str, Field(min_length=1, max_length=1000)]

    @model_validator(mode="after")
    def validate_leg_bindings(self) -> Self:
        if self.expires_at <= self.created_at:
            raise ValueError("trade intent expiry must be after created_at")
        if any(leg.underlying_symbol != self.underlying_symbol for leg in self.legs):
            raise ValueError("every option leg must match the trade underlying")
        if len({leg.occ_symbol for leg in self.legs}) != len(self.legs):
            raise ValueError("trade intent cannot contain duplicate option legs")
        leg_evidence = {leg.quote_evidence_id for leg in self.legs}
        if not leg_evidence.issubset(self.evidence_ids):
            raise ValueError("every option leg quote must appear in evidence_ids")
        return self


class RiskVerdict(ContractModel):
    verdict_id: Identifier
    case_id: Identifier
    intent_id: Identifier
    decision: VerdictDecision
    approved_quantity: Annotated[int, Field(ge=0)]
    maximum_loss: NonNegativeMoney
    evaluated_at: AwareDatetime
    evidence_ids: EvidenceIds
    policy_version: Annotated[str, Field(min_length=1, max_length=120)]
    reasons: Annotated[tuple[str, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def match_decision_to_quantity(self) -> Self:
        approved = self.decision in (VerdictDecision.APPROVE, VerdictDecision.RESIZE)
        if approved and self.approved_quantity < 1:
            raise ValueError("approved or resized verdicts require a positive quantity")
        if not approved and self.approved_quantity != 0:
            raise ValueError("vetoed or abstained verdicts require zero quantity")
        return self


class ApprovalArtifact(ContractModel):
    approval_id: Identifier
    case_id: Identifier
    intent_id: Identifier
    verdict_id: Identifier
    approved_at: AwareDatetime
    expires_at: AwareDatetime
    approved_quantity: PositiveInt
    maximum_loss: PositiveMoney
    evidence_ids: EvidenceIds
    policy_version: Annotated[str, Field(min_length=1, max_length=120)]

    @model_validator(mode="after")
    def require_future_expiry(self) -> Self:
        if self.expires_at <= self.approved_at:
            raise ValueError("approval expiry must be after approved_at")
        return self


class DecisionEvent(ContractModel):
    event_id: Identifier
    case_id: Identifier
    sequence: Annotated[int, Field(ge=0)]
    event_type: DecisionEventType
    occurred_at: AwareDatetime
    evidence_ids: EvidenceIds
    payload: dict[str, JsonValue]


class ExecutionRecord(ContractModel):
    execution_id: Identifier
    case_id: Identifier
    intent_id: Identifier
    approval_id: Identifier
    client_order_id: Annotated[str, Field(min_length=1, max_length=48)]
    status: ExecutionStatus
    legs: Annotated[tuple[OptionLeg, ...], Field(min_length=1, max_length=2)]
    submitted_at: AwareDatetime
    filled_at: AwareDatetime | None = None
    filled_debit: NonNegativeMoney | None = None
    evidence_ids: EvidenceIds

    @model_validator(mode="after")
    def require_fill_details(self) -> Self:
        if self.status is ExecutionStatus.FILLED and (
            self.filled_at is None or self.filled_debit is None
        ):
            raise ValueError("filled executions require filled_at and filled_debit")
        return self


class PnLSnapshot(ContractModel):
    snapshot_id: Identifier
    case_id: Identifier
    execution_id: Identifier
    observed_at: AwareDatetime
    position_value: NonNegativeMoney
    cost_basis: NonNegativeMoney
    unrealized_pnl: Money
    realized_pnl: Money
    maximum_loss: PositiveMoney
    evidence_ids: EvidenceIds
