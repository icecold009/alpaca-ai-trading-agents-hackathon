"""Local personal-workstation APIs with explicit paper-only mutation gates."""

# FastAPI's dependency declarations intentionally use call expressions in
# defaults; the framework resolves them per request.
# ruff: noqa: B008

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from riskcourt.alpaca_account import AlpacaAccountAdapter
from riskcourt.alpaca_market_data import AlpacaUnderlyingAdapter, MarketDataUnavailable
from riskcourt.alpaca_option_chain import (
    AlpacaOptionChainAdapter,
    ChainContract,
    OptionChainUnavailable,
)
from riskcourt.alpaca_order import (
    AlpacaOrderAdapter,
    SubmissionOutcomeUnknown,
    SubmissionRejected,
    client_order_id_for_approval,
    request_fingerprint,
)
from riskcourt.case_repository import RecordedCaseRepository
from riskcourt.domain import OptionQuote
from riskcourt.exit_policy import PositionAction, PositionState, evaluate_position
from riskcourt.model_provider import ProviderBoundary, ProviderUnavailable
from riskcourt.option_hurdle import calculate_vertical_debit_spread
from riskcourt.paper_loop import PaperCycleDependencies, run_paper_cycle
from riskcourt.paper_runner import build_risk_state, load_configured_provider
from riskcourt.personal_store import PersonalStore, parse_iso
from riskcourt.recorded_case import RecordedCase
from riskcourt.risk_limits import DEFAULT_PORTFOLIO_LIMITS
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


def _decision_for_mode(
    store: PersonalStore, decision_id: str, mode: RuntimeMode
) -> dict[str, Any]:
    decision = store.get_decision(decision_id)
    if decision is None or decision["mode"] != mode.value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="decision not found")
    return decision


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
    return _account_summary_payload(state)


def _account_summary_payload(state: Any) -> dict[str, Any]:
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
    if settings.riskcourt_mode is RuntimeMode.PAPER:
        try:
            account_state = AlpacaAccountAdapter.from_settings(settings).fetch()
            reconciliation = _reconcile_paper_state(store, settings, account_state)
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="paper portfolio reconciliation is unavailable",
            ) from error
        account = _account_summary_payload(account_state)
    else:
        reconciliation = {"status": "recorded", "updated_orders": 0}
        account = account_summary(settings)
    return {
        "account": account,
        "positions": store.positions(mode=settings.riskcourt_mode.value),
        "orders": store.orders(mode=settings.riskcourt_mode.value),
        "kill_switch": store.kill_switch(),
        "reconciliation": reconciliation,
    }


@router.post("/reconcile")
def reconcile(
    store: PersonalStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if settings.riskcourt_mode is RuntimeMode.RECORDED:
        return {"status": "recorded", "updated_orders": 0}
    try:
        account_state = AlpacaAccountAdapter.from_settings(settings).fetch()
        return _reconcile_paper_state(store, settings, account_state)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="paper reconciliation is unavailable",
        ) from error


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
            for symbol in symbols:
                try:
                    result = _run_paper_preview(settings, symbol, store)
                    payload = _paper_result_payload(result, settings)
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
def get_scan(
    scan_id: str,
    store: PersonalStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    decisions = [
        item
        for item in store.list_decisions(mode=settings.riskcourt_mode.value)
        if item["scan_id"] == scan_id
    ]
    return {"scan_id": scan_id, "decisions": decisions}


@router.get("/decisions")
def decisions(
    store: PersonalStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return {"decisions": store.list_decisions(mode=settings.riskcourt_mode.value)}


@router.get("/decisions/{decision_id}")
def decision(
    decision_id: str,
    store: PersonalStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return _decision_for_mode(store, decision_id, settings.riskcourt_mode)


@router.post("/decisions/{decision_id}/veto")
def veto_decision(
    decision_id: str,
    store: PersonalStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _decision_for_mode(store, decision_id, settings.riskcourt_mode)
    try:
        return store.veto_decision(decision_id)
    except KeyError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/decisions/{decision_id}/approve")
def approve_decision(
    decision_id: str,
    store: PersonalStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        decision = _decision_for_mode(store, decision_id, settings.riskcourt_mode)
        binding: dict[str, str] = {}
        if decision["mode"] == "paper":
            if settings.riskcourt_option_feed != "opra":
                raise ValueError("paper approvals require executable OPRA option quotes")
            approval_id = f"approval_{uuid.uuid4().hex[:20]}"
            client_order_id = client_order_id_for_approval(approval_id)
            candidate = _candidate_from_payload(decision["payload"])
            if any(
                contract.feed.lower() != "opra"
                for contract in (candidate.long_contract, candidate.short_contract)
            ):
                raise ValueError("paper approval requires OPRA quote evidence")
            quantity = int(decision["payload"]["verdict"]["approved_quantity"])
            request = AlpacaOrderAdapter.build_vertical_order(
                candidate,
                client_order_id=client_order_id,
                quantity=quantity,
            )
            account_payload = decision["payload"].get("account")
            if not isinstance(account_payload, dict):
                raise ValueError("paper decision is missing its account snapshot")
            account = account_payload.get("account")
            if not isinstance(account, dict):
                raise ValueError("paper decision is missing its account snapshot")
            equity = account.get("equity")
            last_equity = account.get("last_equity")
            if equity is None or last_equity is None:
                raise ValueError("paper approval requires known current and prior equity")
            binding = {
                "approval_id": approval_id,
                "client_order_id": client_order_id,
                "request_sha256": request_fingerprint(request),
                "account_equity": str(equity),
                "account_last_equity": str(last_equity),
            }
        approval = store.create_approval(decision_id, **binding)
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
    decision = store.get_decision(approval["decision_id"])
    if decision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="decision not found")
    adapter = AlpacaOrderAdapter.from_settings(settings)
    existing_order = store.order_for_approval(approval_id)
    terminal_order_states = {"filled", "rejected", "canceled", "cancelled", "expired"}
    if existing_order is not None:
        existing_status = existing_order["status"].lower()
        if existing_status in terminal_order_states:
            return {"approval": approval, "order": existing_order, "replayed": True}
        try:
            broker_order = adapter.lookup_order_by_client_id(existing_order["client_order_id"])
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="paper order outcome is unknown; retry reconciliation later",
            ) from error
        if broker_order is not None:
            broker_status = _enum_text(getattr(broker_order, "status", None)) or "unknown"
            filled_at = getattr(broker_order, "filled_at", None)
            filled_avg_price = getattr(broker_order, "filled_avg_price", None)
            reconciled_order = store.reconcile_order_update(
                existing_order["order_id"],
                status=broker_status,
                filled_qty=str(getattr(broker_order, "filled_qty", "0") or "0"),
                filled_avg_price=(
                    None if filled_avg_price is None else str(filled_avg_price)
                ),
                filled_at=filled_at.isoformat()
                if isinstance(filled_at, datetime)
                else None,
            )
            return {
                "approval": store.get_approval(approval_id),
                "order": reconciled_order,
                "replayed": True,
            }
        reserved_at = parse_iso(existing_order["submitted_at"])
        if (
            existing_status not in {"unknown", "submitting"}
            or datetime.now(UTC) - reserved_at < timedelta(seconds=60)
        ):
            if existing_status not in {"unknown", "submitting"}:
                store.update_order(existing_order["order_id"], status="unknown")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="paper order is awaiting broker reconciliation; retry later",
            )
    try:
        client_order_id = client_order_id_for_approval(approval_id)
        if approval["kind"] == "exit":
            candidate, credit_price = _refresh_and_validate_exit(
                settings,
                store,
                decision,
                approval,
            )
            request = adapter.build_vertical_exit_order(
                candidate,
                client_order_id=client_order_id,
                credit_price=credit_price,
                quantity=int(approval["quantity"]),
            )
            if request_fingerprint(request) != approval["request_sha256"]:
                store.expire_prepared_approval(approval_id, reason="exit_quote_changed")
                raise ValueError("current exit order differs from preview; prepare a fresh exit")
        else:
            candidate, account = _refresh_and_validate_entry(
                settings,
                store,
                decision,
                approval,
            )
            request = adapter.build_vertical_order(
                candidate,
                client_order_id=client_order_id,
                quantity=int(approval["quantity"]),
            )
            if request_fingerprint(request) != approval["request_sha256"]:
                raise ValueError("current order differs from the approved request; prepare again")
            risk = _personal_risk_state(account, store)
            pending_statuses = {
                "submitting",
                "unknown",
                "submitted",
                "partially_filled",
            }
            pending_local = sum(
                order["status"].lower() in pending_statuses
                and order["approval_id"] != approval_id
                for order in store.orders(mode="paper")
            )
            if pending_local:
                raise ValueError("a local paper order is still pending reconciliation")
            risk_verdict = risk.authorize_execution(
                Decimal(approval["maximum_loss"]), DEFAULT_PORTFOLIO_LIMITS
            )
            if not risk_verdict.passed:
                raise ValueError("current portfolio risk blocks this entry")
        reservation = store.reserve_approval_submission(
            approval_id,
            client_order_id,
            request_fingerprint(request),
        )
        if reservation["replayed"] and reservation["order"]["status"] == "submitting":
            reserved_at = parse_iso(reservation["order"]["submitted_at"])
            if datetime.now(UTC) - reserved_at < timedelta(seconds=60):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="paper submission is still in progress; reconcile before retrying",
                )
        if reservation["replayed"] and reservation["order"]["status"] in {
            "filled",
            "canceled",
            "cancelled",
            "expired",
        }:
            return reservation
    except KeyError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

    try:
        submission = adapter.submit(request, approved=True)
    except SubmissionRejected as error:
        store.update_order(reservation["order"]["order_id"], status="rejected")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Alpaca rejected the paper order; prepare a new approval",
        ) from error
    except SubmissionOutcomeUnknown as error:
        store.update_order(reservation["order"]["order_id"], status="unknown")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="paper order outcome is unknown; retry to reconcile before submitting again",
        ) from error
    except ValueError as error:
        store.update_order(reservation["order"]["order_id"], status="unknown")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="local order identity conflict; the broker outcome must be reconciled",
        ) from error
    except Exception as error:
        store.update_order(reservation["order"]["order_id"], status="unknown")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="paper order outcome is unknown; retry to reconcile before submitting again",
        ) from error

    response = submission.response
    if response is None:
        store.update_order(reservation["order"]["order_id"], status="unknown")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="paper order outcome is unknown; retry to reconcile before submitting again",
        )
    broker_status = _enum_text(getattr(response, "status", None)) or "submitted"
    filled_at = getattr(response, "filled_at", None)
    filled_avg_price = getattr(response, "filled_avg_price", None)
    order = store.reconcile_order_update(
        reservation["order"]["order_id"],
        status=broker_status,
        filled_qty=str(getattr(response, "filled_qty", "0") or "0"),
        filled_avg_price=(
            None if filled_avg_price is None else str(filled_avg_price)
        ),
        filled_at=filled_at.isoformat() if isinstance(filled_at, datetime) else None,
    )
    return {
        "approval": store.get_approval(approval_id),
        "order": order,
        "replayed": reservation["replayed"] or submission.action.value == "replay",
    }


@router.get("/orders")
def orders(
    store: PersonalStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return {"orders": store.orders(mode=settings.riskcourt_mode.value)}


@router.post("/orders", include_in_schema=False)
def reject_legacy_order_mutation() -> None:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="order mutation route not found",
    )


@router.get("/positions")
def positions(
    store: PersonalStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return {"positions": store.positions(mode=settings.riskcourt_mode.value)}


@router.post("/positions/{position_id}/exit-preview")
def exit_preview(
    position_id: str,
    store: PersonalStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    position = _position_for_id(store, position_id)
    if settings.riskcourt_mode is not RuntimeMode.PAPER:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="paper mode is required")
    try:
        account_state = AlpacaAccountAdapter.from_settings(settings).fetch()
        _reconcile_paper_state(store, settings, account_state)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="current position state is unavailable",
        ) from error
    position = _position_for_id(store, position_id)
    if position["reconciliation_status"] != "matched" or not position["mark_at"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="position legs or fresh exit mark could not be reconciled",
        )
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
    try:
        candidate = _candidate_from_payload(decision["payload"])
        approval_id = f"approval_{uuid.uuid4().hex[:20]}"
        client_order_id = client_order_id_for_approval(approval_id)
        quantity = int(Decimal(position["quantity"]))
        credit_price = Decimal(position["position_value"]) / (
            Decimal("100") * Decimal(quantity)
        )
        request = AlpacaOrderAdapter.build_vertical_exit_order(
            candidate,
            client_order_id=client_order_id,
            credit_price=credit_price,
            quantity=quantity,
        )
        approval = store.create_exit_approval(
            position_id,
            approval_id=approval_id,
            client_order_id=client_order_id,
            request_sha256=request_fingerprint(request),
        )
    except (KeyError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="fresh exit preview unavailable",
        ) from error
    return {
        "position_id": position_id,
        "status": "approval_ready",
        "action": policy_decision.action.value,
        "reason": (
            policy_decision.reason
            if policy_decision.action is PositionAction.EXIT
            else "operator_requested_exit"
        ),
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
        return {"entry": entry}
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error


def _reconcile_paper_state(
    store: PersonalStore,
    settings: Settings,
    account_state: Any,
) -> dict[str, Any]:
    order_adapter = AlpacaOrderAdapter.from_settings(settings)
    updated_orders = 0
    checked_orders = 0
    terminal = {"filled", "rejected", "canceled", "cancelled", "expired"}
    for local_order in store.orders(mode="paper"):
        if local_order["status"].lower() in terminal:
            continue
        checked_orders += 1
        broker_order = order_adapter.lookup_order_by_client_id(local_order["client_order_id"])
        if broker_order is None:
            if (
                local_order["status"].lower() == "submitting"
                and datetime.now(UTC) - parse_iso(local_order["submitted_at"])
                >= timedelta(seconds=60)
            ):
                store.update_order(local_order["order_id"], status="unknown")
            continue
        broker_status = _enum_text(getattr(broker_order, "status", None)) or "unknown"
        filled_at = getattr(broker_order, "filled_at", None)
        filled_avg_price = getattr(broker_order, "filled_avg_price", None)
        store.reconcile_order_update(
            local_order["order_id"],
            status=broker_status,
            filled_qty=str(getattr(broker_order, "filled_qty", "0") or "0"),
            filled_avg_price=(
                None if filled_avg_price is None else str(filled_avg_price)
            ),
            filled_at=filled_at.isoformat() if isinstance(filled_at, datetime) else None,
        )
        updated_orders += 1

    broker_options = {
        position.symbol: position
        for position in account_state.positions
        if "option" in position.asset_class.lower()
    }
    matched_positions = 0
    discrepant_positions = 0
    stale_marks = 0
    for position in store.positions(mode="paper"):
        if position["status"] != "open":
            continue
        decision = store.get_decision(position["decision_id"])
        if decision is None:
            store.set_position_reconciliation(
                position["position_id"], state="discrepancy", reason="entry decision is missing"
            )
            discrepant_positions += 1
            continue
        try:
            candidate = _candidate_from_payload(decision["payload"])
        except (KeyError, ValueError):
            store.set_position_reconciliation(
                position["position_id"], state="discrepancy", reason="approved legs are missing"
            )
            discrepant_positions += 1
            continue
        quantity = Decimal(position["quantity"])
        long_position = broker_options.get(candidate.long_contract.occ_symbol)
        short_position = broker_options.get(candidate.short_contract.occ_symbol)
        legs_match = (
            long_position is not None
            and short_position is not None
            and long_position.side.lower() == "long"
            and short_position.side.lower() == "short"
            and abs(long_position.quantity) == quantity
            and abs(short_position.quantity) == quantity
        )
        if not legs_match:
            store.set_position_reconciliation(
                position["position_id"],
                state="discrepancy",
                reason="broker option legs do not match the local spread quantity",
            )
            discrepant_positions += 1
            continue

        if settings.riskcourt_option_feed != "opra":
            store.set_position_reconciliation(
                position["position_id"],
                state="stale_quote",
                reason="current executable marks require the OPRA feed",
            )
            stale_marks += 1
            continue
        now = datetime.now(UTC)
        expiry = candidate.long_contract.expiry
        try:
            chain = AlpacaOptionChainAdapter.from_settings(settings).fetch(
                position["symbol"],
                expiration_from=expiry,
                expiration_to=expiry,
                strike_from=min(candidate.long_contract.strike, candidate.short_contract.strike),
                strike_to=max(candidate.long_contract.strike, candidate.short_contract.strike),
            )
            current = {item.occ_symbol: item for item in chain.contracts}
            long_quote = current[candidate.long_contract.occ_symbol]
            short_quote = current[candidate.short_contract.occ_symbol]
            quote_times = (long_quote.quoted_at, short_quote.quoted_at)
            if (
                chain.feed.lower() != "opra"
                or any(item is None for item in quote_times)
                or any(item.bid is None or item.ask is None for item in (long_quote, short_quote))
                or any(
                    time is None
                    or now - time < timedelta(seconds=-5)
                    or now - time > timedelta(seconds=30)
                    for time in quote_times
                )
            ):
                raise ValueError("position quote is stale or incomplete")
            assert long_quote.bid is not None and short_quote.ask is not None
            close_credit = long_quote.bid - short_quote.ask
            if close_credit <= 0 or close_credit > candidate.geometry.spread_width:
                raise ValueError("current spread mark is outside supported payoff bounds")
        except Exception:
            store.set_position_reconciliation(
                position["position_id"],
                state="stale_quote",
                reason="fresh OPRA spread mark is unavailable",
            )
            stale_marks += 1
            continue
        mark_at = min(time for time in quote_times if time is not None)
        position_value = close_credit * Decimal("100") * quantity
        cost_basis = Decimal(position["cost_basis"])
        store.update_position(
            position["position_id"],
            status="open",
            position_value=str(position_value),
            unrealized_pnl=str(position_value - cost_basis),
            realized_pnl=position["realized_pnl"],
            mark_at=mark_at.isoformat(),
            reconciliation_status="matched",
            reconciliation_reason="",
        )
        matched_positions += 1

    local_open_legs = {
        contract
        for position in store.positions(mode="paper")
        if position["status"] == "open"
        for contract in _position_contract_symbols(store, position)
    }
    external_option_positions = len(set(broker_options) - local_open_legs)
    return {
        "status": "complete",
        "checked_orders": checked_orders,
        "updated_orders": updated_orders,
        "matched_positions": matched_positions,
        "discrepant_positions": discrepant_positions,
        "stale_marks": stale_marks,
        "unmapped_broker_option_legs": external_option_positions,
    }


def _position_contract_symbols(
    store: PersonalStore,
    position: dict[str, Any],
) -> tuple[str, ...]:
    decision = store.get_decision(position["decision_id"])
    if decision is None:
        return ()
    try:
        candidate = _candidate_from_payload(decision["payload"])
    except (KeyError, ValueError):
        return ()
    return candidate.long_contract.occ_symbol, candidate.short_contract.occ_symbol


def _position_for_id(store: PersonalStore, position_id: str) -> dict[str, Any]:
    position = next(
        (
            item
            for item in store.positions(mode="paper")
            if item["position_id"] == position_id
        ),
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
    if position["reconciliation_status"] != "matched" or not position["mark_at"]:
        raise ValueError("position has no reconciled current mark")
    quote_age = datetime.now(UTC) - parse_iso(position["mark_at"])
    quantity = Decimal(position["quantity"])
    if quantity <= 0:
        raise ValueError("position quantity is unavailable")
    return evaluate_position(
        PositionState(
            has_position=True,
            entry_debit=Decimal(position["cost_basis"]) / (Decimal("100") * quantity),
            current_value=Decimal(position["position_value"]) / (Decimal("100") * quantity),
            probability_edge=Decimal("1"),
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


def _run_paper_preview(settings: Settings, symbol: str, store: PersonalStore) -> Any:
    account = AlpacaAccountAdapter.from_settings(settings)
    state = account.fetch()
    reconciliation = _reconcile_paper_state(store, settings, state)
    if reconciliation["discrepant_positions"] or reconciliation["unmapped_broker_option_legs"]:
        raise ValueError("existing broker option exposure could not be matched safely")
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
        provider=ProviderBoundary(
            load_configured_provider(settings, settings.riskcourt_provider_spec),
            timeout_seconds=settings.typesafe_timeout_seconds,
            max_calls=settings.typesafe_max_calls,
            max_cost_units=settings.typesafe_max_cost_units,
            total_timeout_seconds=settings.typesafe_total_timeout_seconds,
        ),
        risk=_personal_risk_state(state, store),
        event_log=log,
    )
    result = run_paper_cycle(dependencies, case_id=case_id, symbol=symbol, submit=False)
    if result.execution is not None:
        raise RuntimeError("paper preview unexpectedly submitted an order")
    return result


def _personal_risk_state(state: Any, store: PersonalStore) -> Any:
    observed = state.account.observed_at.astimezone(ZoneInfo("America/New_York"))
    baseline = store.daily_equity_baseline(
        trading_day=observed.date().isoformat(),
        broker_last_equity=state.account.last_equity,
    )
    exposure = store.risk_exposure(mode="paper")
    has_broker_option_positions = any(
        "option" in position.asset_class.lower() for position in state.positions
    )
    return build_risk_state(
        state,
        exposure=exposure,
        last_equity_baseline=baseline,
        broker_positions_reconciled=not has_broker_option_positions
        or exposure.open_option_positions > 0,
    )


def _paper_result_payload(result: Any, settings: Settings) -> dict[str, Any]:
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
        "juror_abstentions": [
            {"juror_id": juror_id, "reason": reason}
            for juror_id, reason in result.jury.abstentions
        ],
        "provider": {
            "mode": settings.riskcourt_ai_mode.value,
            "simulated": (
                settings.riskcourt_ai_mode.value == "deterministic"
                and settings.riskcourt_provider_spec is None
            ),
            "model": settings.typesafe_model
            if settings.riskcourt_ai_mode.value == "typesafe"
            else "operator-provider" if settings.riskcourt_provider_spec else "deterministic-stub",
            "call_count": len(result.jury.forecasts),
            "cost_units": str(
                sum(
                    (Decimal(str(forecast.provider_metadata.get("cost_units", "0")))
                     for forecast in result.jury.forecasts),
                    Decimal("0"),
                )
            ),
        },
        "forecast_event": {
            "symbol": result.intent.underlying_symbol,
            "threshold": str(geometry.break_even_underlying),
            "condition": (
                "underlying_price_above_threshold"
                if result.intent.direction.value == "bullish"
                else "underlying_price_at_or_below_threshold"
            ),
            "observed_at": result.account.clock.timestamp.isoformat(),
            "horizon_at": (
                result.jury.forecasts[0].horizon_at.isoformat()
                if result.jury.forecasts
                else None
            ),
            "settlement_rule": "last regular-session underlying quote at the broker calendar close",
            "calendar_source": "Alpaca trading calendar",
            "role_mode": "two-role-no-news",
            "minimum_quorum": 2,
        },
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
        "account": {
            "account": {
                "status": result.account.account.status,
                "equity": _decimal_text(result.account.account.equity),
                "last_equity": _decimal_text(result.account.account.last_equity),
                "options_buying_power": _decimal_text(
                    result.account.account.options_buying_power
                ),
                "options_trading_level": result.account.account.options_trading_level,
                "trading_blocked": result.account.account.trading_blocked,
                "account_blocked": result.account.account.account_blocked,
                "trade_suspended_by_user": result.account.account.trade_suspended_by_user,
            },
            "clock": {
                "timestamp": result.account.clock.timestamp.isoformat(),
                "is_open": result.account.clock.is_open,
            },
        },
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


def _refresh_and_validate_entry(
    settings: Settings,
    store: PersonalStore,
    decision: dict[str, Any],
    approval: dict[str, Any],
) -> tuple[SpreadCandidate, Any]:
    """Re-read paper state and reconstruct the exact reviewed order before reservation."""

    now = datetime.now(UTC)
    if decision["mode"] != "paper":
        raise ValueError("only paper decisions can authorize paper entries")
    if settings.riskcourt_option_feed != "opra":
        raise ValueError("paper submissions require executable OPRA option quotes")
    if parse_iso(decision["freshness_until"]) <= now:
        raise ValueError("decision snapshot is stale; run a fresh scan and approval")
    if parse_iso(approval["expires_at"]) <= now:
        raise ValueError("approval has expired; prepare a new approval")

    account = AlpacaAccountAdapter.from_settings(settings).fetch()
    reconciliation = _reconcile_paper_state(store, settings, account)
    if reconciliation["discrepant_positions"] or reconciliation["unmapped_broker_option_legs"]:
        raise ValueError("existing broker option exposure could not be matched safely")
    if not account.clock.is_open:
        raise ValueError("market is closed")
    if account.account.status.lower() != "active":
        raise ValueError("paper account is not active")
    if (
        account.account.trading_blocked
        or account.account.account_blocked
        or account.account.trade_suspended_by_user
    ):
        raise ValueError("paper account trading is blocked")
    if account.account.options_trading_level is None or account.account.options_trading_level < 3:
        raise ValueError("paper account options trading level is insufficient")
    if account.account.options_buying_power is None or account.account.options_buying_power <= 0:
        raise ValueError("paper account options buying power is unavailable")
    if account.account.equity is None or account.account.last_equity is None:
        raise ValueError("paper account equity or daily P&L is unavailable")
    if (
        account.account.equity != Decimal(str(approval.get("account_equity")))
        or account.account.last_equity
        != Decimal(str(approval.get("account_last_equity")))
    ):
        raise ValueError("paper account equity changed; prepare a fresh approval")

    original = _candidate_from_payload(decision["payload"])
    symbol = decision["symbol"]
    market = AlpacaUnderlyingAdapter.from_settings(settings).fetch(symbol=symbol, now=now)
    if market.quote.stale:
        raise ValueError("underlying quote is stale")
    expiry = original.long_contract.expiry
    if expiry <= now.date():
        raise ValueError("approved option contract has expired")
    chain = AlpacaOptionChainAdapter.from_settings(settings).fetch(
        symbol,
        expiration_from=expiry,
        expiration_to=expiry,
        strike_from=min(original.long_contract.strike, original.short_contract.strike),
        strike_to=max(original.long_contract.strike, original.short_contract.strike),
    )
    if chain.feed.lower() != "opra":
        raise ValueError("current option quotes are not from OPRA")
    by_symbol = {contract.occ_symbol: contract for contract in chain.contracts}
    refreshed_legs = []
    for approved_leg in (original.long_contract, original.short_contract):
        refreshed = by_symbol.get(approved_leg.occ_symbol)
        if refreshed is None or refreshed.feed.lower() != "opra":
            raise ValueError("approved option legs are no longer present in the OPRA chain")
        if refreshed.quoted_at is None or refreshed.bid is None or refreshed.ask is None:
            raise ValueError("current option quote is incomplete")
        quote_age = now - refreshed.quoted_at
        if quote_age < timedelta(seconds=-5) or quote_age > timedelta(seconds=30):
            raise ValueError("current option quote is stale or timestamped in the future")
        if refreshed.bid < 0 or refreshed.ask <= 0 or refreshed.ask < refreshed.bid:
            raise ValueError("current option market is crossed or invalid")
        refreshed_legs.append(refreshed)

    current_candidate = _candidate_from_payload(
        {
            "candidate": {
                "long_contract": refreshed_legs[0].model_dump(mode="json"),
                "short_contract": refreshed_legs[1].model_dump(mode="json"),
            }
        }
    )
    return current_candidate, account


def _refresh_and_validate_exit(
    settings: Settings,
    store: PersonalStore,
    decision: dict[str, Any],
    approval: dict[str, Any],
) -> tuple[SpreadCandidate, Decimal]:
    now = datetime.now(UTC)
    if decision["mode"] != "paper" or settings.riskcourt_option_feed != "opra":
        raise ValueError("paper exits require a paper position and current OPRA quotes")
    if parse_iso(approval["expires_at"]) <= now:
        raise ValueError("exit approval has expired; preview the exit again")
    account = AlpacaAccountAdapter.from_settings(settings).fetch()
    if not account.clock.is_open:
        raise ValueError("market is closed")
    _reconcile_paper_state(store, settings, account)
    position = _position_for_id(store, approval["position_id"])
    if Decimal(position["quantity"]) != Decimal(approval["quantity"]):
        raise ValueError("position quantity changed; preview the exit again")
    if position["reconciliation_status"] != "matched" or not position["mark_at"]:
        raise ValueError("position legs or current mark could not be reconciled")
    if now - parse_iso(position["mark_at"]) > timedelta(seconds=30):
        raise ValueError("current position mark is stale")
    candidate = _candidate_from_payload(decision["payload"])
    expiry = candidate.long_contract.expiry
    chain = AlpacaOptionChainAdapter.from_settings(settings).fetch(
        position["symbol"],
        expiration_from=expiry,
        expiration_to=expiry,
        strike_from=min(candidate.long_contract.strike, candidate.short_contract.strike),
        strike_to=max(candidate.long_contract.strike, candidate.short_contract.strike),
    )
    if chain.feed.lower() != "opra":
        raise ValueError("current spread marks are not from OPRA")
    by_symbol = {contract.occ_symbol: contract for contract in chain.contracts}
    long_quote = by_symbol.get(candidate.long_contract.occ_symbol)
    short_quote = by_symbol.get(candidate.short_contract.occ_symbol)
    if long_quote is None or short_quote is None:
        raise ValueError("approved spread legs are no longer present")
    quote_times = (long_quote.quoted_at, short_quote.quoted_at)
    if (
        any(item is None for item in quote_times)
        or any(item.bid is None or item.ask is None for item in (long_quote, short_quote))
        or any(
            time is None
            or now - time < timedelta(seconds=-5)
            or now - time > timedelta(seconds=30)
            for time in quote_times
        )
    ):
        raise ValueError("current spread quote is stale or incomplete")
    assert long_quote.bid is not None and short_quote.ask is not None
    credit = long_quote.bid - short_quote.ask
    if credit <= 0 or credit > candidate.geometry.spread_width:
        raise ValueError("current exit credit is outside defined-risk spread bounds")
    refreshed = _candidate_from_payload(
        {
            "candidate": {
                "long_contract": long_quote.model_dump(mode="json"),
                "short_contract": short_quote.model_dump(mode="json"),
            }
        }
    )
    return refreshed, credit


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
