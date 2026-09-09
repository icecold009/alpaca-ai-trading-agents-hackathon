"""Local personal-workstation APIs with explicit paper-only mutation gates."""

# FastAPI's dependency declarations intentionally use call expressions in
# defaults; the framework resolves them per request.
# ruff: noqa: B008

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from riskcourt.alpaca_account import AlpacaAccountAdapter
from riskcourt.alpaca_market_data import MarketDataUnavailable
from riskcourt.alpaca_option_chain import ChainContract, OptionChainUnavailable
from riskcourt.alpaca_order import AlpacaOrderAdapter
from riskcourt.case_repository import RecordedCaseRepository
from riskcourt.domain import OptionQuote
from riskcourt.exit_policy import PositionAction, PositionState, evaluate_position
from riskcourt.model_provider import ProviderBoundary, ProviderUnavailable
from riskcourt.option_hurdle import calculate_vertical_debit_spread
from riskcourt.paper_loop import PaperCycleDependencies, run_paper_cycle
from riskcourt.paper_runner import build_risk_state, load_provider_client
from riskcourt.personal_store import PersonalStore, parse_iso
from riskcourt.recorded_case import RecordedCase
from riskcourt.settings import RuntimeMode, Settings
from riskcourt.spread_selector import SpreadCandidate

router = APIRouter(prefix="/api", tags=["personal workstation"])


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class WatchlistRequest(StrictModel):
    symbols: list[str] = Field(min_length=1, max_length=2)


class ScanRequest(StrictModel):
    symbols: list[str] | None = Field(default=None, max_length=2)


class SubmitRequest(StrictModel):
    confirm: bool
    idempotency_key: str = Field(min_length=8, max_length=120, pattern=r"^[A-Za-z0-9_-]+$")


class JournalRequest(StrictModel):
    body: str = Field(min_length=1, max_length=4000)
    decision_id: str | None = Field(default=None, max_length=80)


class KillSwitchRequest(StrictModel):
    enabled: bool
    reason: str = Field(default="", max_length=240)


def get_store(request: Request) -> PersonalStore:
    return cast(PersonalStore, request.app.state.personal_store)


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_cases(request: Request) -> RecordedCaseRepository:
    return cast(RecordedCaseRepository, request.app.state.recorded_case_repository)


@router.get("/account/summary")
def account_summary(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    if settings.riskcourt_mode is RuntimeMode.RECORDED:
        return {
            "mode": "recorded",
            "paper": True,
            "status": "recorded",
            "equity": None,
            "buying_power": None,
            "options_trading_level": None,
            "market_open": False,
            "position_count": 0,
            "pending_order_count": 0,
            "message": "Recorded mode is active; no broker credentials are used.",
        }
    try:
        state = AlpacaAccountAdapter.from_settings(settings).fetch()
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="paper account read unavailable",
        ) from error
    return {
        "mode": "paper",
        "paper": True,
        "status": state.account.status,
        "equity": _decimal_text(state.account.equity),
        "buying_power": _decimal_text(state.account.options_buying_power),
        "options_approved_level": state.account.options_approved_level,
        "options_trading_level": state.account.options_trading_level,
        "market_open": state.clock.is_open,
        "clock_timestamp": state.clock.timestamp.isoformat(),
        "next_open": state.clock.next_open.isoformat(),
        "next_close": state.clock.next_close.isoformat(),
        "position_count": len(state.positions),
        "pending_order_count": len(state.pending_orders),
    }


@router.get("/portfolio")
def portfolio(
    store: PersonalStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return {
        "account": account_summary(settings),
        "positions": store.positions(),
        "orders": store.orders(),
        "kill_switch": store.kill_switch(),
    }


@router.get("/watchlist")
def watchlist(store: PersonalStore = Depends(get_store)) -> dict[str, Any]:
    return {"symbols": store.watchlist()}


@router.post("/watchlist")
def update_watchlist(
    body: WatchlistRequest,
    store: PersonalStore = Depends(get_store),
) -> dict[str, Any]:
    try:
        symbols = store.replace_watchlist(body.symbols)
        store.record_audit("watchlist.updated", "watchlist", {"symbols": symbols})
        return {"symbols": symbols}
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error


@router.post("/scans")
def start_scan(
    body: ScanRequest | None = None,
    store: PersonalStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
    cases: RecordedCaseRepository = Depends(get_cases),
) -> dict[str, Any]:
    requested = (
        body.symbols if body and body.symbols else [item["symbol"] for item in store.watchlist()]
    )
    try:
        symbols = _normalize_symbols(requested)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    scan_id = store.create_scan(settings.riskcourt_mode.value, symbols)
    decisions: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    try:
        if settings.riskcourt_mode is RuntimeMode.RECORDED:
            available: dict[str, RecordedCase] = {}
            for case in cases.list_cases():
                existing = available.get(case.underlying_symbol)
                if existing is None or case.verdict.decision.value in {"approve", "resize"}:
                    available[case.underlying_symbol] = case
            for symbol in symbols:
                recorded_case = available.get(symbol)
                if recorded_case is None:
                    failures.append({"symbol": symbol, "reason": "recorded_case_unavailable"})
                    continue
                payload = recorded_case.model_dump(mode="json")
                payload["source"] = "bundled_fixture"
                payload["mode"] = "recorded"
                decision_id = store.save_decision(
                    scan_id=scan_id,
                    mode="recorded",
                    payload=payload,
                    status="ready",
                )
                decision = store.get_decision(decision_id)
                if decision is not None:
                    decisions.append(decision)
        else:
            if not settings.riskcourt_provider_spec:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="paper scan requires RISKCOURT_PROVIDER_SPEC",
                )
            for symbol in symbols:
                try:
                    result = _run_paper_preview(settings, symbol)
                    payload = _paper_result_payload(result)
                    decision_id = store.save_decision(
                        scan_id=scan_id,
                        mode="paper",
                        payload=payload,
                        status="ready" if result.verdict is not None else "blocked",
                    )
                    decision = store.get_decision(decision_id)
                    if decision is not None:
                        decisions.append(decision)
                except (
                    MarketDataUnavailable,
                    OptionChainUnavailable,
                    ProviderUnavailable,
                    ValueError,
                ) as error:
                    failures.append({"symbol": symbol, "reason": _safe_reason(error)})
    except HTTPException:
        store.finish_scan(scan_id, status="failed", error="paper_scan_unavailable")
        raise
    except Exception as error:
        store.finish_scan(scan_id, status="failed", error="scan_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="scan failed safely",
        ) from error
    store.finish_scan(scan_id, status="completed", error=None if not failures else "partial_scan")
    store.record_audit(
        "scan.completed",
        scan_id,
        {"decision_count": len(decisions), "failure_count": len(failures)},
    )
    return {
        "scan_id": scan_id,
        "mode": settings.riskcourt_mode.value,
        "status": "completed",
        "decisions": decisions,
        "failures": failures,
    }


@router.get("/scans/{scan_id}")
def get_scan(scan_id: str, store: PersonalStore = Depends(get_store)) -> dict[str, Any]:
    decisions = [item for item in store.list_decisions() if item["scan_id"] == scan_id]
    return {"scan_id": scan_id, "decisions": decisions}


@router.get("/decisions")
def decisions(store: PersonalStore = Depends(get_store)) -> dict[str, Any]:
    return {"decisions": store.list_decisions()}


@router.get("/decisions/{decision_id}")
def decision(decision_id: str, store: PersonalStore = Depends(get_store)) -> dict[str, Any]:
    result = store.get_decision(decision_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="decision not found")
    return result


@router.post("/decisions/{decision_id}/veto")
def veto_decision(decision_id: str, store: PersonalStore = Depends(get_store)) -> dict[str, Any]:
    decision = store.get_decision(decision_id)
    if decision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="decision not found")
    if decision["status"] in {"submitted", "vetoed"}:
        return decision
    store.mark_decision(decision_id, "vetoed")
    store.record_audit("decision.vetoed", decision_id, {})
    return store.get_decision(decision_id) or decision


@router.post("/decisions/{decision_id}/approve")
def approve_decision(decision_id: str, store: PersonalStore = Depends(get_store)) -> dict[str, Any]:
    try:
        approval = store.create_approval(decision_id)
        store.record_audit(
            "decision.approved",
            decision_id,
            {"approval_id": approval["approval_id"]},
        )
        return {"approval": approval}
    except KeyError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/approvals/{approval_id}/submit")
def submit_approval(
    approval_id: str,
    body: SubmitRequest,
    store: PersonalStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if not body.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="explicit confirmation is required",
        )
    if settings.riskcourt_mode is RuntimeMode.RECORDED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="recorded mode cannot submit paper orders; switch to paper mode",
        )
    approval = store.get_approval(approval_id)
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="approval not found")
    if approval["kind"] == "entry" and store.kill_switch()["enabled"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="kill switch blocks new entries",
        )
    decision = store.get_decision(approval["decision_id"])
    if decision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="decision not found")
    reservation: dict[str, Any] | None = None
    try:
        reservation = store.submit_approval(approval_id, body.idempotency_key)
        if reservation["replayed"]:
            return reservation
        candidate = _candidate_from_payload(decision["payload"])
        adapter = AlpacaOrderAdapter.from_settings(settings)
        if approval["kind"] == "exit":
            position = _position_for_id(store, approval["position_id"])
            credit_price = Decimal(position["position_value"]) / Decimal("100")
            request = adapter.build_vertical_exit_order(
                candidate,
                client_order_id=body.idempotency_key,
                credit_price=credit_price,
            )
        else:
            request = adapter.build_vertical_order(candidate, client_order_id=body.idempotency_key)
        submission = adapter.submit(request, approved=True)
        response = submission.response
        broker_status = _enum_text(getattr(response, "status", None)) or "submitted"
        filled_at = getattr(response, "filled_at", None)
        filled_debit = getattr(response, "filled_avg_price", None)
        order = store.update_order(
            reservation["order"]["order_id"],
            status=broker_status,
            filled_at=filled_at.isoformat() if isinstance(filled_at, datetime) else None,
            filled_debit=None if filled_debit is None else str(filled_debit),
        )
        if approval["kind"] == "entry" and broker_status == "filled" and filled_debit is not None:
            store.create_position(
                decision_id=decision["decision_id"],
                order_id=order["order_id"],
                symbol=decision["symbol"],
                direction=decision["payload"]["intent"]["direction"],
                cost_basis=str(Decimal(filled_debit) * Decimal("100")),
            )
        elif approval["kind"] == "exit" and broker_status == "filled":
            position = _position_for_id(store, approval["position_id"])
            cost_basis = Decimal(position["cost_basis"])
            current_value = Decimal(position["position_value"])
            store.update_position(
                position["position_id"],
                status="closed",
                position_value="0",
                unrealized_pnl="0",
                realized_pnl=str(current_value - cost_basis),
            )
        store.record_audit(
            "order.submitted",
            approval_id,
            {"kind": approval["kind"], "status": broker_status},
        )
        return {"approval": store.get_approval(approval_id), "order": order, "replayed": False}
    except HTTPException:
        if reservation is not None:
            store.update_order(reservation["order"]["order_id"], status="rejected")
        raise
    except (ValueError, TypeError, RuntimeError) as error:
        if reservation is not None:
            store.update_order(reservation["order"]["order_id"], status="rejected")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="paper submission rejected",
        ) from error
    except Exception as error:
        if reservation is not None:
            store.update_order(reservation["order"]["order_id"], status="rejected")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="paper submission unavailable",
        ) from error


@router.get("/orders")
def orders(store: PersonalStore = Depends(get_store)) -> dict[str, Any]:
    return {"orders": store.orders()}


@router.post("/orders", include_in_schema=False)
def reject_legacy_order_mutation() -> None:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="order mutation route not found",
    )


@router.get("/positions")
def positions(store: PersonalStore = Depends(get_store)) -> dict[str, Any]:
    return {"positions": store.positions()}


@router.post("/positions/{position_id}/exit-preview")
def exit_preview(position_id: str, store: PersonalStore = Depends(get_store)) -> dict[str, Any]:
    position = _position_for_id(store, position_id)
    decision = store.get_decision(position["decision_id"])
    if decision is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="position decision unavailable",
        )
    try:
        policy_decision = _evaluate_position(store, position, decision)
    except (KeyError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="position preview unavailable",
        ) from error
    if policy_decision.action is not PositionAction.EXIT:
        return {
            "position_id": position_id,
            "status": "hold",
            "action": policy_decision.action.value,
            "reason": policy_decision.reason,
        }
    approval = store.create_exit_approval(position_id)
    return {
        "position_id": position_id,
        "status": "approval_ready",
        "action": policy_decision.action.value,
        "reason": policy_decision.reason,
        "approval": approval,
        "confirm_required": True,
    }


@router.post("/positions/{position_id}/exit-submit")
def exit_submit(
    position_id: str,
    body: SubmitRequest,
    store: PersonalStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _position_for_id(store, position_id)
    approval = store.prepared_exit_approval(position_id)
    if approval is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="fresh exit preview required",
        )
    if not body.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="explicit confirmation is required",
        )
    return submit_approval(approval["approval_id"], body, store, settings)


@router.post("/kill-switch")
def set_kill_switch(
    body: KillSwitchRequest, store: PersonalStore = Depends(get_store)
) -> dict[str, Any]:
    try:
        kill_switch = store.set_kill_switch(body.enabled, body.reason)
        store.record_audit("kill_switch.changed", "kill_switch", kill_switch)
        return {"kill_switch": kill_switch}
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error


@router.get("/journal")
def journal(store: PersonalStore = Depends(get_store)) -> dict[str, Any]:
    return {"entries": store.journal()}


@router.get("/audit")
def audit(store: PersonalStore = Depends(get_store)) -> dict[str, Any]:
    return {"events": store.audit_history()}


@router.post("/journal")
def add_journal_entry(
    body: JournalRequest, store: PersonalStore = Depends(get_store)
) -> dict[str, Any]:
    try:
        entry = store.add_journal_entry(body.body, body.decision_id)
        store.record_audit(
            "journal.created",
            entry["entry_id"],
            {"decision_id": body.decision_id},
        )
        return {"entry": entry}
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error


def _position_for_id(store: PersonalStore, position_id: str) -> dict[str, Any]:
    position = next(
        (item for item in store.positions() if item["position_id"] == position_id),
        None,
    )
    if position is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="position not found")
    if position["status"] != "open":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="position is not open")
    return position


def _evaluate_position(
    store: PersonalStore,
    position: dict[str, Any],
    decision: dict[str, Any],
) -> Any:
    candidate = _candidate_from_payload(decision["payload"])
    updated_at = parse_iso(position["updated_at"])
    quote_age = max(datetime.now(UTC) - updated_at, timedelta(0))
    return evaluate_position(
        PositionState(
            has_position=True,
            entry_debit=Decimal(position["cost_basis"]) / Decimal("100"),
            current_value=Decimal(position["position_value"]) / Decimal("100"),
            probability_edge=Decimal(decision["payload"]["strategy"].get("probability_edge", "0")),
            quote_age=quote_age,
            days_to_expiry=(candidate.long_contract.expiry - datetime.now(UTC).date()).days,
            kill_switch_enabled=store.kill_switch()["enabled"],
        )
    )


def _normalize_symbols(symbols: list[str]) -> list[str]:
    normalized = [symbol.strip().upper() for symbol in symbols]
    if not normalized or len(set(normalized)) != len(normalized):
        raise ValueError("symbols must be unique and non-empty")
    unsupported = set(normalized) - {"SPY", "QQQ"}
    if unsupported:
        raise ValueError("only SPY and QQQ are supported in personal V1")
    return normalized


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _enum_text(value: object | None) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _safe_reason(error: BaseException) -> str:
    message = str(error).lower()
    if "provider" in message:
        return "provider_unavailable"
    if "option" in message:
        return "option_chain_unavailable"
    if "market" in message:
        return "market_data_unavailable"
    return "scan_unavailable"


def _run_paper_preview(settings: Settings, symbol: str) -> Any:
    account = AlpacaAccountAdapter.from_settings(settings)
    state = account.fetch()
    case_id = f"paper_{symbol.lower()}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
    event_path = settings.riskcourt_state_dir / "events" / f"{case_id}.json"
    from riskcourt.alpaca_market_data import AlpacaUnderlyingAdapter
    from riskcourt.alpaca_option_chain import AlpacaOptionChainAdapter
    from riskcourt.event_store import PersistentDecisionLog

    log = PersistentDecisionLog(case_id, event_path)
    dependencies = PaperCycleDependencies(
        account=account,
        market=AlpacaUnderlyingAdapter.from_settings(settings),
        chain=AlpacaOptionChainAdapter.from_settings(settings),
        orders=AlpacaOrderAdapter.from_settings(settings),
        provider=ProviderBoundary(load_provider_client(settings.riskcourt_provider_spec)),
        risk=build_risk_state(state, daily_pnl=Decimal("0")),
        event_log=log,
    )
    result = run_paper_cycle(dependencies, case_id=case_id, symbol=symbol, submit=False)
    if result.execution is not None:
        raise RuntimeError("paper preview unexpectedly submitted an order")
    return result


def _paper_result_payload(result: Any) -> dict[str, Any]:
    if (
        result.candidate is None
        or result.jury is None
        or result.intent is None
        or result.verdict is None
    ):
        raise ValueError("paper scan did not produce a decision")
    candidate = result.candidate
    edge = result.jury.edge
    geometry = candidate.geometry
    return {
        "case_id": result.case_id,
        "name": f"{result.intent.underlying_symbol} paper scan",
        "recorded": False,
        "source": "alpaca-paper",
        "mode": "paper",
        "underlying_symbol": result.intent.underlying_symbol,
        "as_of": result.account.clock.timestamp.isoformat(),
        "forecasts": [forecast.model_dump(mode="json") for forecast in result.jury.forecasts],
        "strategy": {
            "jury_probability": _decimal_text(
                edge.jury_probability if edge else result.jury.aggregate.probability
            )
            or "0",
            "market_hurdle": str(geometry.option_implied_hurdle),
            "probability_edge": _decimal_text(
                edge.probability_edge
                if edge and edge.probability_edge is not None
                else Decimal("0")
            )
            or "0",
            "minimum_edge": str(edge.minimum_edge if edge else Decimal("0.08")),
            "net_debit": str(geometry.net_debit),
            "spread_width": str(geometry.spread_width),
            "slippage_buffer": "0",
        },
        "intent": result.intent.model_dump(mode="json"),
        "verdict": result.verdict.model_dump(mode="json"),
        "approval": None if result.approval is None else result.approval.model_dump(mode="json"),
        "executions": [],
        "pnl_snapshots": [],
        "candidate": {
            "geometry": {
                "net_debit": str(geometry.net_debit),
                "spread_width": str(geometry.spread_width),
            },
            "long_contract": candidate.long_contract.model_dump(mode="json"),
            "short_contract": candidate.short_contract.model_dump(mode="json"),
        },
    }


def _candidate_from_payload(payload: dict[str, Any]) -> SpreadCandidate:
    candidate_payload = payload.get("candidate")
    if not isinstance(candidate_payload, dict):
        raise ValueError("decision does not contain a paper candidate")
    long_contract = ChainContract.model_validate(candidate_payload["long_contract"])
    short_contract = ChainContract.model_validate(candidate_payload["short_contract"])
    long_quote = OptionQuote(
        evidence_id="personal-long-quote",
        occ_symbol=long_contract.occ_symbol,
        underlying_symbol=long_contract.underlying_symbol,
        expiry=long_contract.expiry,
        strike=long_contract.strike,
        right=long_contract.right,
        bid=long_contract.bid or Decimal("0"),
        ask=long_contract.ask or Decimal("0"),
        quoted_at=_required_quote_time(long_contract.quoted_at),
    )
    short_quote = OptionQuote(
        evidence_id="personal-short-quote",
        occ_symbol=short_contract.occ_symbol,
        underlying_symbol=short_contract.underlying_symbol,
        expiry=short_contract.expiry,
        strike=short_contract.strike,
        right=short_contract.right,
        bid=short_contract.bid or Decimal("0"),
        ask=short_contract.ask or Decimal("0"),
        quoted_at=_required_quote_time(short_contract.quoted_at),
    )
    geometry = calculate_vertical_debit_spread(long_quote, short_quote)
    return SpreadCandidate(geometry, long_contract, short_contract)


def _required_quote_time(value: datetime | None) -> datetime:
    if value is None:
        raise ValueError("paper candidate is missing quote freshness")
    return value
