"""Validated aggregate contract for credential-free recorded demonstrations."""

from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from riskcourt.domain import (
    ApprovalArtifact,
    ContractModel,
    DecisionEvent,
    DecisionEventType,
    EvidenceItem,
    ExecutionRecord,
    ExecutionStatus,
    Identifier,
    NonNegativeMoney,
    OptionQuote,
    PnLSnapshot,
    PositionIntent,
    ProbabilityForecast,
    RiskVerdict,
    Ticker,
    TradeIntent,
    VerdictDecision,
)
from riskcourt.strategy_math import (
    OPTION_MULTIPLIER,
    JurorEstimate,
    calculate_edge,
)

CalculatedProbability = Annotated[Decimal, Field(ge=0, le=1)]
SignedProbability = Annotated[Decimal, Field(ge=-1, le=1)]


class StrategySnapshot(ContractModel):
    jury_probability: CalculatedProbability
    market_hurdle: CalculatedProbability
    probability_edge: SignedProbability
    minimum_edge: CalculatedProbability
    net_debit: NonNegativeMoney
    spread_width: NonNegativeMoney
    slippage_buffer: NonNegativeMoney


class RecordedCase(ContractModel):
    case_id: Identifier
    name: Annotated[str, Field(min_length=1, max_length=120)]
    recorded: Literal[True]
    underlying_symbol: Ticker
    as_of: AwareDatetime
    evidence: Annotated[tuple[EvidenceItem, ...], Field(min_length=1)]
    option_quotes: Annotated[tuple[OptionQuote, ...], Field(min_length=1)]
    forecasts: Annotated[tuple[ProbabilityForecast, ...], Field(min_length=1)]
    strategy: StrategySnapshot
    intent: TradeIntent
    verdict: RiskVerdict
    approval: ApprovalArtifact | None
    events: Annotated[tuple[DecisionEvent, ...], Field(min_length=1)]
    executions: tuple[ExecutionRecord, ...]
    pnl_snapshots: tuple[PnLSnapshot, ...]

    @model_validator(mode="after")
    def validate_references_and_calculations(self) -> Self:
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("evidence IDs must be unique")
        available_evidence = set(evidence_ids)

        for forecast in self.forecasts:
            self._check_binding(forecast.case_id, forecast.evidence_ids, available_evidence)
        self._check_binding(self.intent.case_id, self.intent.evidence_ids, available_evidence)
        self._check_binding(self.verdict.case_id, self.verdict.evidence_ids, available_evidence)
        for event in self.events:
            self._check_binding(event.case_id, event.evidence_ids, available_evidence)
        for execution in self.executions:
            self._check_binding(execution.case_id, execution.evidence_ids, available_evidence)
        for snapshot in self.pnl_snapshots:
            self._check_binding(snapshot.case_id, snapshot.evidence_ids, available_evidence)
        if self.approval is not None:
            self._check_binding(
                self.approval.case_id,
                self.approval.evidence_ids,
                available_evidence,
            )
        for option_quote in self.option_quotes:
            if option_quote.evidence_id not in available_evidence:
                raise ValueError("every option quote evidence ID must resolve")

        if self.intent.intent_id != self.verdict.intent_id:
            raise ValueError("risk verdict must reference the trade intent")
        if [event.sequence for event in self.events] != list(range(len(self.events))):
            raise ValueError("decision event sequences must be contiguous from zero")

        quote_by_symbol = {quote.occ_symbol: quote for quote in self.option_quotes}
        candidate_debit = Decimal("0")
        for leg in self.intent.legs:
            candidate_quote = quote_by_symbol.get(leg.occ_symbol)
            if candidate_quote is None:
                raise ValueError("every trade intent leg must have an option quote")
            if leg.position_intent is PositionIntent.BUY_TO_OPEN:
                candidate_debit += candidate_quote.ask
            elif leg.position_intent is PositionIntent.SELL_TO_OPEN:
                candidate_debit -= candidate_quote.bid
            else:
                raise ValueError("recorded candidate legs must use opening position intents")
        if candidate_debit != self.strategy.net_debit:
            raise ValueError("strategy net debit must be reconstructable from option quotes")
        if len(self.intent.legs) == 2:
            strikes = [leg.strike for leg in self.intent.legs]
            if max(strikes) - min(strikes) != self.strategy.spread_width:
                raise ValueError("strategy spread width must match the option legs")

        calculation = calculate_edge(
            estimates=tuple(
                JurorEstimate(
                    probability=forecast.probability,
                    calibration_score=forecast.calibration_score,
                    confidence_stake=forecast.confidence_stake,
                )
                for forecast in self.forecasts
            ),
            net_debit=self.strategy.net_debit,
            spread_width=self.strategy.spread_width,
            slippage_buffer=self.strategy.slippage_buffer,
            minimum_edge=self.strategy.minimum_edge,
        )
        if (
            calculation.jury_probability != self.strategy.jury_probability
            or calculation.market_hurdle != self.strategy.market_hurdle
            or calculation.probability_edge != self.strategy.probability_edge
        ):
            raise ValueError("recorded strategy values must match deterministic calculations")

        approved = self.verdict.decision in (
            VerdictDecision.APPROVE,
            VerdictDecision.RESIZE,
        )
        if approved:
            self._validate_approved_path()
        else:
            forbidden_events = {
                DecisionEventType.APPROVAL_ISSUED,
                DecisionEventType.EXECUTION_UPDATED,
                DecisionEventType.PNL_RECORDED,
            }
            if (
                self.approval is not None
                or self.executions
                or self.pnl_snapshots
                or any(event.event_type in forbidden_events for event in self.events)
            ):
                raise ValueError("a vetoed or abstained case cannot have execution artifacts")
        return self

    def _check_binding(
        self,
        case_id: str,
        evidence_ids: tuple[str, ...],
        available_evidence: set[str],
    ) -> None:
        if case_id != self.case_id:
            raise ValueError("every downstream record must reference the case")
        if not set(evidence_ids).issubset(available_evidence):
            raise ValueError("every referenced evidence ID must resolve")

    def _validate_approved_path(self) -> None:
        if self.approval is None:
            raise ValueError("an approved case requires an approval artifact")
        if self.approval.intent_id != self.intent.intent_id:
            raise ValueError("approval must reference the trade intent")
        if self.approval.verdict_id != self.verdict.verdict_id:
            raise ValueError("approval must reference the risk verdict")
        if self.approval.approved_quantity != self.verdict.approved_quantity:
            raise ValueError("approval quantity must match the risk verdict")

        quote_by_symbol = {quote.occ_symbol: quote for quote in self.option_quotes}
        for execution in self.executions:
            if execution.intent_id != self.intent.intent_id:
                raise ValueError("execution must reference the trade intent")
            if execution.approval_id != self.approval.approval_id:
                raise ValueError("execution must reference the approval")
            if any(leg.quantity != self.approval.approved_quantity for leg in execution.legs):
                raise ValueError("execution leg quantities must match the approval")

        filled = next(
            (item for item in self.executions if item.status is ExecutionStatus.FILLED),
            None,
        )
        if filled is None or filled.filled_debit is None:
            raise ValueError("an approved recorded case requires a filled execution")

        reconstructed_debit = Decimal("0")
        for leg in filled.legs:
            quote = quote_by_symbol.get(leg.occ_symbol)
            if quote is None:
                raise ValueError("every execution leg must have an option quote")
            if leg.position_intent is PositionIntent.BUY_TO_OPEN:
                reconstructed_debit += quote.ask
            elif leg.position_intent is PositionIntent.SELL_TO_OPEN:
                reconstructed_debit -= quote.bid
            else:
                raise ValueError("recorded entry legs must use opening position intents")

        if reconstructed_debit != self.strategy.net_debit:
            raise ValueError("recorded net debit must be reconstructable from option quotes")
        if filled.filled_debit != reconstructed_debit:
            raise ValueError("filled debit must match the recorded net debit")

        reconstructed_loss = (
            reconstructed_debit * OPTION_MULTIPLIER * self.approval.approved_quantity
        )
        if self.approval.maximum_loss != reconstructed_loss:
            raise ValueError("approval maximum loss must be reconstructable")
        if self.verdict.maximum_loss != reconstructed_loss:
            raise ValueError("risk verdict maximum loss must match the approved risk")
        if any(snapshot.execution_id != filled.execution_id for snapshot in self.pnl_snapshots):
            raise ValueError("P&L snapshots must reference the filled execution")
