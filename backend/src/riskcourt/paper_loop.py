"""Fail-closed orchestration for a single Alpaca paper-options decision cycle.

The public UI can replay recorded cases, while this module is the credentialed
paper boundary.  It deliberately returns typed, sanitized records and never
lets a model decide quantity, maximum loss, or whether a rejected cycle retries.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol, cast

from pydantic import JsonValue

from riskcourt.alpaca_account import AlpacaAccountAdapter, PaperAccountState
from riskcourt.alpaca_market_data import (
    AlpacaUnderlyingAdapter,
    MarketDataUnavailable,
    UnderlyingMarketState,
)
from riskcourt.alpaca_option_chain import (
    AlpacaOptionChainAdapter,
    OptionChainState,
    OptionChainUnavailable,
)
from riskcourt.alpaca_order import AlpacaOrderAdapter, SubmissionResult
from riskcourt.approval_guard import (
    IdempotencyRegistry,
    SubmissionAction,
    create_approval_binding,
    validate_approval_for_execution,
)
from riskcourt.domain import (
    ApprovalArtifact,
    DecisionEvent,
    DecisionEventType,
    EvidenceItem,
    EvidenceType,
    ExecutionRecord,
    ExecutionStatus,
    ForecastOutcome,
    OptionLeg,
    OptionRight,
    PnLSnapshot,
    PositionIntent,
    RiskVerdict,
    TradeDirection,
    TradeIntent,
    VerdictDecision,
)
from riskcourt.edge_policy import EdgeDecision
from riskcourt.event_store import AppendOnlyDecisionLog, PersistentDecisionLog
from riskcourt.exit_policy import (
    DEFAULT_EXIT_POLICY,
    ExitPolicy,
    PositionAction,
    PositionDecision,
    PositionState,
    evaluate_position,
)
from riskcourt.model_provider import ProviderBoundary, ProviderUnavailable
from riskcourt.orchestrator import JuryDecision
from riskcourt.order_lifecycle import OrderLifecycleSnapshot, OrderLifecycleTracker
from riskcourt.pnl import create_pnl_snapshot
from riskcourt.risk_limits import RiskStateStore
from riskcourt.sizing import SizingDecision, size_defined_risk_position
from riskcourt.spread_selector import SpreadCandidate, select_vertical_spreads


class PaperCycleUnavailable(RuntimeError):
    """A safe failure that must result in abstention and no order attempt."""


class OrderReader(Protocol):
    def get_order_by_client_id(self, client_order_id: str) -> Any: ...


@dataclass(frozen=True, slots=True)
class PaperCycleResult:
    case_id: str
    status: str
    reason: str
    account: PaperAccountState
    market: UnderlyingMarketState | None
    chain: OptionChainState | None
    candidate: SpreadCandidate | None
    jury: JuryDecision | None
    intent: TradeIntent | None
    verdict: RiskVerdict | None
    approval: ApprovalArtifact | None
    submission: SubmissionResult | None
    execution: ExecutionRecord | None
    lifecycle: OrderLifecycleSnapshot | None
    pnl_snapshot: PnLSnapshot | None

    @property
    def order_attempted(self) -> bool:
        return self.submission is not None


@dataclass(frozen=True, slots=True)
class PaperCycleDependencies:
    """Adapters and stores injected into the orchestration boundary."""

    account: AlpacaAccountAdapter
    market: AlpacaUnderlyingAdapter
    chain: AlpacaOptionChainAdapter
    orders: AlpacaOrderAdapter
    provider: ProviderBoundary
    risk: RiskStateStore
    event_log: AppendOnlyDecisionLog | PersistentDecisionLog


def run_paper_cycle(
    dependencies: PaperCycleDependencies,
    *,
    case_id: str,
    now: datetime | None = None,
    symbol: str = "SPY",
    expiration_from: date | None = None,
    expiration_to: date | None = None,
    strike_from: Decimal = Decimal("1"),
    strike_to: Decimal = Decimal("1000"),
    requested_quantity: int = 1,
    minimum_edge: Decimal = Decimal("0.08"),
    policy_version: str = "risk-v1",
) -> PaperCycleResult:
    """Run one paper-only cycle and fail closed on every incomplete dependency."""

    observed_at = now or datetime.now(UTC)
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    account = dependencies.account.fetch()

    if not account.clock.is_open:
        return _blocked(case_id, account, "market_closed")
    if account.account.equity is None or account.account.equity <= 0:
        return _blocked(case_id, account, "account_equity_unavailable")
    if account.account.trading_blocked or account.account.account_blocked:
        return _blocked(case_id, account, "account_blocked")
    if account.account.trade_suspended_by_user:
        return _blocked(case_id, account, "trade_suspended_by_user")
    if account.account.options_trading_level is None or account.account.options_trading_level < 3:
        return _blocked(case_id, account, "options_trading_level_unavailable")

    try:
        market = dependencies.market.fetch(symbol=symbol, now=observed_at)
    except MarketDataUnavailable:
        return _blocked(case_id, account, "market_data_unavailable")
    if market.quote.stale:
        return _blocked(case_id, account, "underlying_quote_stale", market=market)

    from_day = expiration_from or observed_at.date()
    to_day = expiration_to or (from_day + timedelta(days=21))
    try:
        chain = dependencies.chain.fetch(
            symbol,
            expiration_from=from_day,
            expiration_to=to_day,
            strike_from=strike_from,
            strike_to=strike_to,
        )
    except OptionChainUnavailable:
        return _blocked(case_id, account, "option_chain_unavailable", market=market)
    candidates = select_vertical_spreads(chain, as_of=observed_at)
    if not candidates:
        return _blocked(case_id, account, "no_liquid_supported_spread", market=market, chain=chain)
    candidate = candidates[0]
    proposed_client_order_id = _client_order_id_for_candidate(case_id, candidate)
    if any(item.client_order_id == proposed_client_order_id for item in account.pending_orders):
        return _blocked(
            case_id,
            account,
            "duplicate_pending_order",
            market=market,
            chain=chain,
            candidate=candidate,
        )
    evidence = _build_evidence(case_id, account, market, candidate)
    evidence_ids = tuple(item.evidence_id for item in evidence)
    _append_event(
        dependencies.event_log,
        case_id,
        DecisionEventType.CASE_OPENED,
        observed_at,
        evidence_ids,
        {"symbol": symbol, "mode": "paper", "evidence_count": len(evidence_ids)},
    )
    outcome = (
        ForecastOutcome.ABOVE_STRIKE
        if candidate.long_contract.right is OptionRight.CALL
        else ForecastOutcome.BELOW_STRIKE
    )

    try:
        jury = _run_jury(
            dependencies.provider,
            candidate,
            case_id=case_id,
            outcome=outcome,
            observed_at=observed_at,
            evidence_ids=evidence_ids,
            minimum_edge=minimum_edge,
        )
    except ProviderUnavailable:
        return _blocked(
            case_id, account, "provider_failure", market=market, chain=chain, candidate=candidate
        )

    _append_event(
        dependencies.event_log,
        case_id,
        DecisionEventType.FORECAST_RECORDED,
        observed_at,
        evidence_ids,
        {
            "forecast_count": len(jury.forecasts),
            "aggregate_probability": (
                None if jury.aggregate.probability is None else str(jury.aggregate.probability)
            ),
            "decision": jury.decision.value,
        },
    )

    intent = _build_intent(case_id, candidate, observed_at, evidence_ids)
    _append_event(
        dependencies.event_log,
        case_id,
        DecisionEventType.INTENT_PROPOSED,
        observed_at,
        evidence_ids,
        {"intent_id": intent.intent_id, "maximum_loss": str(intent.maximum_loss)},
    )
    if jury.decision is not EdgeDecision.PASS:
        verdict = _build_verdict(
            case_id,
            intent,
            VerdictDecision.ABSTAIN if jury.reason == "provider_failure" else VerdictDecision.VETO,
            0,
            Decimal("0"),
            observed_at,
            evidence_ids,
            policy_version,
            jury.reason,
        )
        _append_event(
            dependencies.event_log,
            case_id,
            DecisionEventType.RISK_EVALUATED,
            observed_at,
            evidence_ids,
            {"decision": verdict.decision.value, "reason": jury.reason},
        )
        return _result(
            case_id,
            "abstained",
            jury.reason,
            account,
            market,
            chain,
            candidate,
            jury,
            intent,
            verdict,
        )

    sizing = size_defined_risk_position(
        account.account.equity,
        candidate.geometry,
        requested_quantity=requested_quantity,
    )
    portfolio = dependencies.risk.authorize_execution(candidate.geometry.maximum_loss)
    if sizing.approved_quantity == 0:
        verdict = _build_verdict(
            case_id,
            intent,
            VerdictDecision.VETO,
            0,
            Decimal("0"),
            observed_at,
            evidence_ids,
            policy_version,
            sizing.reason,
        )
        return _result(
            case_id,
            "vetoed",
            sizing.reason,
            account,
            market,
            chain,
            candidate,
            jury,
            intent,
            verdict,
        )
    if not portfolio.passed:
        reason = ";".join(portfolio.reasons)
        verdict = _build_verdict(
            case_id,
            intent,
            VerdictDecision.VETO,
            0,
            Decimal("0"),
            observed_at,
            evidence_ids,
            policy_version,
            reason,
        )
        return _result(
            case_id,
            "vetoed",
            reason,
            account,
            market,
            chain,
            candidate,
            jury,
            intent,
            verdict,
        )

    decision = (
        VerdictDecision.APPROVE
        if sizing.decision is SizingDecision.APPROVE
        else VerdictDecision.RESIZE
    )
    verdict = _build_verdict(
        case_id,
        intent,
        decision,
        sizing.approved_quantity,
        sizing.approved_maximum_loss,
        observed_at,
        evidence_ids,
        policy_version,
        sizing.reason,
    )
    _append_event(
        dependencies.event_log,
        case_id,
        DecisionEventType.RISK_EVALUATED,
        observed_at,
        evidence_ids,
        {
            "decision": verdict.decision.value,
            "approved_quantity": verdict.approved_quantity,
            "reason": sizing.reason,
        },
    )
    approval = ApprovalArtifact(
        approval_id=f"approval_{case_id}",
        case_id=case_id,
        intent_id=intent.intent_id,
        verdict_id=verdict.verdict_id,
        approved_at=observed_at,
        expires_at=observed_at + timedelta(seconds=30),
        approved_quantity=sizing.approved_quantity,
        maximum_loss=sizing.approved_maximum_loss,
        evidence_ids=evidence_ids,
        policy_version=policy_version,
    )
    client_order_id = proposed_client_order_id
    binding = create_approval_binding(approval, intent, evidence, client_order_id)
    approval_check = validate_approval_for_execution(
        binding,
        intent,
        evidence,
        policy_version,
        client_order_id,
        observed_at,
        IdempotencyRegistry(),
    )
    if approval_check.action is not SubmissionAction.SUBMIT:
        return _result(
            case_id,
            "vetoed",
            approval_check.reason,
            account,
            market,
            chain,
            candidate,
            jury,
            intent,
            verdict,
            approval=approval,
        )

    _append_event(
        dependencies.event_log,
        case_id,
        DecisionEventType.APPROVAL_ISSUED,
        observed_at,
        evidence_ids,
        {"approval_id": approval.approval_id, "client_order_id": client_order_id},
    )

    request = dependencies.orders.build_vertical_order(candidate, client_order_id=client_order_id)
    submission = dependencies.orders.submit(request, approved=True)
    execution = _execution_from_response(
        case_id,
        intent,
        approval,
        submission,
        observed_at,
        evidence_ids,
        client_order_id,
    )
    lifecycle = _lifecycle_from_submission(submission)
    _append_event(
        dependencies.event_log,
        case_id,
        DecisionEventType.EXECUTION_UPDATED,
        observed_at,
        evidence_ids,
        {"status": execution.status.value, "client_order_id": client_order_id},
    )
    return _result(
        case_id,
        "submitted",
        "paper_order_submitted",
        account,
        market,
        chain,
        candidate,
        jury,
        intent,
        verdict,
        approval=approval,
        submission=submission,
        execution=execution,
        lifecycle=lifecycle,
    )


def evaluate_and_submit_exit(
    *,
    candidate: SpreadCandidate,
    adapter: AlpacaOrderAdapter,
    state: PositionState,
    client_order_id: str,
    approved: bool,
    policy: ExitPolicy = DEFAULT_EXIT_POLICY,
) -> tuple[PositionDecision, SubmissionResult | None]:
    """Evaluate a position and submit only a deterministic closing order."""

    decision = evaluate_position(state, policy)
    if decision.action is not PositionAction.EXIT:
        return decision, None
    request = adapter.build_vertical_exit_order(
        candidate,
        client_order_id=client_order_id,
        credit_price=state.current_value,
    )
    return decision, adapter.submit(request, approved=approved)


def record_filled_pnl(
    result: PaperCycleResult,
    *,
    event_log: AppendOnlyDecisionLog | PersistentDecisionLog,
    position_value: Decimal,
    realized_pnl: Decimal = Decimal("0"),
    observed_at: datetime | None = None,
) -> PnLSnapshot:
    """Create and append an immutable dollar P&L snapshot for a filled cycle."""

    if result.execution is None or result.execution.status is not ExecutionStatus.FILLED:
        raise ValueError("P&L can only be recorded for a filled paper execution")
    if result.execution.filled_debit is None or result.verdict is None:
        raise ValueError("filled execution is missing cost and risk details")
    at = observed_at or result.execution.filled_at
    if at is None:
        raise ValueError("filled execution is missing a fill timestamp")
    contract_count = result.execution.legs[0].quantity
    cost_basis = result.execution.filled_debit * Decimal("100") * Decimal(contract_count)
    snapshot = create_pnl_snapshot(
        snapshot_id=f"pnl_{result.case_id.removeprefix('case_')}_{at.timestamp():.0f}",
        case_id=result.case_id,
        execution_id=result.execution.execution_id,
        observed_at=at,
        position_value=position_value,
        cost_basis=cost_basis,
        realized_pnl=realized_pnl,
        maximum_loss=result.verdict.maximum_loss,
        evidence_ids=result.execution.evidence_ids,
    )
    _append_event(
        event_log,
        result.case_id,
        DecisionEventType.PNL_RECORDED,
        at,
        result.execution.evidence_ids,
        {
            "snapshot_id": snapshot.snapshot_id,
            "unrealized_pnl": str(snapshot.unrealized_pnl),
            "realized_pnl": str(snapshot.realized_pnl),
        },
    )
    return snapshot


def _run_jury(
    provider: ProviderBoundary,
    candidate: SpreadCandidate,
    *,
    case_id: str,
    outcome: ForecastOutcome,
    observed_at: datetime,
    evidence_ids: tuple[str, ...],
    minimum_edge: Decimal,
) -> JuryDecision:
    from riskcourt.orchestrator import run_jury

    horizon = datetime.combine(candidate.long_contract.expiry, datetime.min.time(), tzinfo=UTC)
    return run_jury(
        provider,
        candidate.geometry,
        case_id=case_id,
        outcome=outcome,
        produced_at=observed_at,
        horizon_at=max(horizon, observed_at + timedelta(hours=1)),
        evidence_ids=evidence_ids,
        minimum_edge=minimum_edge,
    )


def _blocked(
    case_id: str,
    account: PaperAccountState,
    reason: str,
    *,
    market: UnderlyingMarketState | None = None,
    chain: OptionChainState | None = None,
    candidate: SpreadCandidate | None = None,
) -> PaperCycleResult:
    return _result(case_id, "blocked", reason, account, market, chain, candidate)


def _result(
    case_id: str,
    status: str,
    reason: str,
    account: PaperAccountState,
    market: UnderlyingMarketState | None = None,
    chain: OptionChainState | None = None,
    candidate: SpreadCandidate | None = None,
    jury: JuryDecision | None = None,
    intent: TradeIntent | None = None,
    verdict: RiskVerdict | None = None,
    *,
    approval: ApprovalArtifact | None = None,
    submission: SubmissionResult | None = None,
    execution: ExecutionRecord | None = None,
    lifecycle: OrderLifecycleSnapshot | None = None,
    pnl_snapshot: PnLSnapshot | None = None,
) -> PaperCycleResult:
    return PaperCycleResult(
        case_id,
        status,
        reason,
        account,
        market,
        chain,
        candidate,
        jury,
        intent,
        verdict,
        approval,
        submission,
        execution,
        lifecycle,
        pnl_snapshot,
    )


def _build_evidence(
    case_id: str,
    account: PaperAccountState,
    market: UnderlyingMarketState,
    candidate: SpreadCandidate,
) -> tuple[EvidenceItem, ...]:
    items: list[EvidenceItem] = []
    items.append(
        _evidence(
            case_id,
            "account",
            EvidenceType.ACCOUNT,
            "SPY",
            account.account.observed_at,
            account.account.model_dump(mode="json"),
            "Alpaca paper account snapshot",
        )
    )
    items.append(
        _evidence(
            case_id,
            "underlying",
            EvidenceType.UNDERLYING_QUOTE,
            market.quote.symbol,
            market.quote.quoted_at,
            market.quote.model_dump(mode="json"),
            "Alpaca underlying quote",
        )
    )
    for suffix, contract in (
        ("long", candidate.long_contract),
        ("short", candidate.short_contract),
    ):
        items.append(
            _evidence(
                case_id,
                suffix,
                EvidenceType.OPTION_QUOTE,
                contract.underlying_symbol,
                contract.quoted_at or market.fetched_at,
                contract.model_dump(mode="json"),
                f"Alpaca option quote {suffix} leg",
            )
        )
    items.append(
        _evidence(
            case_id,
            "policy",
            EvidenceType.POLICY,
            candidate.geometry.underlying_symbol,
            market.fetched_at,
            {
                "policy_version": "risk-v1",
                "maximum_loss": str(candidate.geometry.maximum_loss),
            },
            "RiskCourt deterministic policy",
        )
    )
    return tuple(items)


def _evidence(
    case_id: str,
    suffix: str,
    kind: EvidenceType,
    symbol: str,
    observed_at: datetime,
    payload: object,
    summary: str,
) -> EvidenceItem:
    evidence_id = f"ev_{case_id.removeprefix('case_')}_{suffix}"
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    return EvidenceItem(
        evidence_id=evidence_id,
        evidence_type=kind,
        source="alpaca-paper",
        symbol=symbol,
        observed_at=observed_at,
        payload_sha256=digest,
        summary=summary,
        raw_reference=f"paper-cycle:{case_id}:{suffix}",
    )


def _build_intent(
    case_id: str,
    candidate: SpreadCandidate,
    observed_at: datetime,
    evidence_ids: tuple[str, ...],
) -> TradeIntent:
    direction = (
        TradeDirection.BULLISH
        if candidate.long_contract.right is OptionRight.CALL
        else TradeDirection.BEARISH
    )
    legs = (
        OptionLeg(
            occ_symbol=candidate.long_contract.occ_symbol,
            underlying_symbol=candidate.long_contract.underlying_symbol,
            expiry=candidate.long_contract.expiry,
            strike=candidate.long_contract.strike,
            right=candidate.long_contract.right,
            position_intent=PositionIntent.BUY_TO_OPEN,
            quantity=1,
            quote_evidence_id=next(item for item in evidence_ids if item.endswith("_long")),
        ),
        OptionLeg(
            occ_symbol=candidate.short_contract.occ_symbol,
            underlying_symbol=candidate.short_contract.underlying_symbol,
            expiry=candidate.short_contract.expiry,
            strike=candidate.short_contract.strike,
            right=candidate.short_contract.right,
            position_intent=PositionIntent.SELL_TO_OPEN,
            quantity=1,
            quote_evidence_id=next(item for item in evidence_ids if item.endswith("_short")),
        ),
    )
    return TradeIntent(
        intent_id=f"intent_{case_id.removeprefix('case_')}",
        case_id=case_id,
        underlying_symbol=candidate.geometry.underlying_symbol,
        direction=direction,
        legs=legs,
        maximum_loss=candidate.geometry.maximum_loss,
        created_at=observed_at,
        expires_at=observed_at + timedelta(seconds=30),
        evidence_ids=evidence_ids,
        thesis="Calibrated jury probability clears the option-implied hurdle after risk gates.",
        invalidation="Re-evaluate only with fresh evidence and a policy-compliant edge.",
    )


def _build_verdict(
    case_id: str,
    intent: TradeIntent,
    decision: VerdictDecision,
    quantity: int,
    maximum_loss: Decimal,
    evaluated_at: datetime,
    evidence_ids: tuple[str, ...],
    policy_version: str,
    reason: str,
) -> RiskVerdict:
    return RiskVerdict(
        verdict_id=f"verdict_{case_id.removeprefix('case_')}",
        case_id=case_id,
        intent_id=intent.intent_id,
        decision=decision,
        approved_quantity=quantity,
        maximum_loss=maximum_loss,
        evaluated_at=evaluated_at,
        evidence_ids=evidence_ids,
        policy_version=policy_version,
        reasons=(reason,),
    )


def _client_order_id(case_id: str, intent: TradeIntent) -> str:
    digest = hashlib.sha256(intent.model_dump_json().encode()).hexdigest()[:10]
    return f"riskcourt-{case_id.removeprefix('case_')[:20]}-{digest}"


def _client_order_id_for_candidate(case_id: str, candidate: SpreadCandidate) -> str:
    material = "|".join(
        (
            candidate.long_contract.occ_symbol,
            candidate.short_contract.occ_symbol,
            str(candidate.geometry.net_debit),
        )
    )
    digest = hashlib.sha256(material.encode()).hexdigest()[:10]
    return f"riskcourt-{case_id.removeprefix('case_')[:20]}-{digest}"


def _execution_from_response(
    case_id: str,
    intent: TradeIntent,
    approval: ApprovalArtifact,
    submission: SubmissionResult,
    observed_at: datetime,
    evidence_ids: tuple[str, ...],
    client_order_id: str,
) -> ExecutionRecord:
    response = submission.response
    raw_status = getattr(
        getattr(response, "status", None), "value", getattr(response, "status", None)
    )
    status = _execution_status(raw_status)
    submitted_at = getattr(response, "submitted_at", observed_at)
    if not isinstance(submitted_at, datetime) or submitted_at.tzinfo is None:
        submitted_at = observed_at
    filled_at = getattr(response, "filled_at", None)
    filled_price = getattr(response, "filled_avg_price", None)
    filled_debit = None if filled_price is None else Decimal(str(filled_price))
    if status is ExecutionStatus.FILLED and (filled_at is None or filled_debit is None):
        status = ExecutionStatus.SUBMITTED
        filled_at = None
        filled_debit = None
    response_client_order_id = (
        getattr(response, "client_order_id", None) if response is not None else None
    )
    return ExecutionRecord(
        execution_id=f"execution_{case_id.removeprefix('case_')}",
        case_id=case_id,
        intent_id=intent.intent_id,
        approval_id=approval.approval_id,
        client_order_id=(
            str(response_client_order_id) if response_client_order_id else client_order_id
        ),
        status=status,
        legs=intent.legs,
        submitted_at=submitted_at,
        filled_at=filled_at,
        filled_debit=filled_debit,
        evidence_ids=evidence_ids,
    )


def _execution_status(raw_status: object) -> ExecutionStatus:
    value = getattr(raw_status, "value", raw_status)
    if value in {"filled"}:
        return ExecutionStatus.FILLED
    if value in {"accepted", "accepted_for_bidding", "held", "calculated"}:
        return ExecutionStatus.ACCEPTED
    if value in {"partially_filled"}:
        return ExecutionStatus.PARTIALLY_FILLED
    if value in {"canceled", "expired", "done_for_day", "pending_cancel"}:
        return ExecutionStatus.CANCELED
    if value in {"rejected", "stopped", "suspended"}:
        return ExecutionStatus.REJECTED
    return ExecutionStatus.SUBMITTED


def _lifecycle_from_submission(submission: SubmissionResult) -> OrderLifecycleSnapshot | None:
    if submission.response is None:
        return None
    try:
        return OrderLifecycleTracker(submission.response).snapshot
    except (AttributeError, TypeError, ValueError):
        # A provider response without lifecycle fields is still represented by
        # ExecutionRecord; polling can hydrate the tracker after reconnect.
        return None


def _append_event(
    log: AppendOnlyDecisionLog | PersistentDecisionLog,
    case_id: str,
    event_type: DecisionEventType,
    occurred_at: datetime,
    evidence_ids: tuple[str, ...],
    payload: dict[str, object],
) -> None:
    log.append(
        DecisionEvent(
            event_id=f"event_{case_id.removeprefix('case_')}_{event_type.value}",
            case_id=case_id,
            sequence=len(log.events),
            event_type=event_type,
            occurred_at=occurred_at,
            evidence_ids=evidence_ids,
            payload=cast(dict[str, JsonValue], payload),
        )
    )
