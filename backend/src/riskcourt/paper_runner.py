"""Operator-safe entry points for one credentialed Alpaca paper cycle.

The core orchestration lives in :mod:`riskcourt.paper_loop`; this module keeps
the command boundary small, explicit, and fail-closed.  It never stores or
prints credentials, account identifiers, or broker order identifiers.
"""

from __future__ import annotations

import importlib
from decimal import Decimal
from types import ModuleType
from typing import Any, cast

from riskcourt.alpaca_account import PaperAccountState
from riskcourt.model_provider import ProviderClient
from riskcourt.paper_loop import PaperCycleResult
from riskcourt.risk_limits import PortfolioRiskSnapshot, RiskStateStore


def load_provider_client(spec: str | None) -> ProviderClient:
    """Load a private provider factory from ``module:attribute``.

    A provider is deliberately supplied by the operator rather than bundled in
    the runner.  This prevents accidental publication of credentials or model
    integrations and makes the paper command unusable without an explicit
    provider choice.
    """

    if spec is None or not spec.strip() or ":" not in spec:
        raise ValueError("paper submission requires --provider module:attribute")
    module_name, attribute = (part.strip() for part in spec.split(":", 1))
    if not module_name or not attribute:
        raise ValueError("provider must use module:attribute syntax")
    module: ModuleType = importlib.import_module(module_name)
    factory: Any = getattr(module, attribute)
    candidate = factory() if isinstance(factory, type) else factory
    if callable(candidate) and not hasattr(candidate, "complete"):
        candidate = candidate()
    if not callable(getattr(candidate, "complete", None)):
        raise TypeError("provider must expose a callable complete(request) method")
    return cast(ProviderClient, candidate)


def build_risk_state(account: PaperAccountState, *, daily_pnl: Decimal) -> RiskStateStore:
    """Build a conservative portfolio snapshot from one account read.

    Existing option positions cannot be safely valued from the minimal account
    contract alone, so the runner refuses to submit when any are present.  This
    is safer than silently assuming zero risk after a restart.
    """

    equity = account.account.equity
    if equity is None or equity <= 0:
        raise ValueError("account equity is unavailable for risk state")
    option_positions = tuple(
        position
        for position in account.positions
        if "option" in position.asset_class.lower()
    )
    if option_positions:
        raise ValueError("existing option risk cannot be reconstructed safely")
    pending_option_orders = sum(
        1 for order in account.pending_orders if order.order_class.lower() in {"mleg", "option"}
    )
    return RiskStateStore(
        PortfolioRiskSnapshot(
            account_equity=equity,
            open_options_risk=Decimal("0"),
            open_option_positions=0,
            pending_option_orders=pending_option_orders,
            daily_pnl=daily_pnl,
            kill_switch_enabled=False,
            revision=0,
        )
    )


def sanitize_result(result: PaperCycleResult | Any) -> dict[str, object]:
    """Return a submission summary safe for terminal output and evidence files."""

    execution = getattr(result, "execution", None)
    lifecycle = getattr(result, "lifecycle", None)
    pnl = getattr(result, "pnl_snapshot", None)
    pnl_summary: dict[str, object] | None = None
    if pnl is not None:
        pnl_summary = {
            "observed_at": pnl.observed_at.isoformat(),
            "position_value": str(pnl.position_value),
            "cost_basis": str(pnl.cost_basis),
            "unrealized_pnl": str(pnl.unrealized_pnl),
            "realized_pnl": str(pnl.realized_pnl),
        }
    return {
        "case_id": result.case_id,
        "status": result.status,
        "reason": result.reason,
        "order_attempted": result.order_attempted,
        "account": result.account.sanitized_summary(),
        "market": (
            result.market.sanitized_summary() if result.market is not None else None
        ),
        "chain": result.chain.sanitized_summary() if result.chain is not None else None,
        "execution_status": _enum_value(getattr(execution, "status", None)),
        "lifecycle_status": _enum_value(getattr(lifecycle, "status", None)),
        "pnl": pnl_summary,
    }


def _enum_value(value: object | None) -> str | None:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    return str(raw)
