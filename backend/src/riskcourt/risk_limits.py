"""Portfolio-level capital controls and atomic execution-time kill switch."""

from dataclasses import dataclass, replace
from decimal import Decimal
from threading import Lock


@dataclass(frozen=True, slots=True)
class PortfolioRiskSnapshot:
    account_equity: Decimal
    open_options_risk: Decimal
    open_option_positions: int
    pending_option_orders: int
    daily_pnl: Decimal
    kill_switch_enabled: bool
    revision: int


@dataclass(frozen=True, slots=True)
class PortfolioLimits:
    maximum_open_risk_fraction: Decimal = Decimal("0.02")
    maximum_option_positions: int = 3
    maximum_pending_orders: int = 1
    maximum_daily_drawdown_fraction: Decimal = Decimal("0.02")


DEFAULT_PORTFOLIO_LIMITS = PortfolioLimits()


@dataclass(frozen=True, slots=True)
class PortfolioRiskVerdict:
    passed: bool
    reasons: tuple[str, ...]
    snapshot_revision: int


def assess_portfolio_limits(
    snapshot: PortfolioRiskSnapshot,
    proposed_maximum_loss: Decimal,
    limits: PortfolioLimits = DEFAULT_PORTFOLIO_LIMITS,
) -> PortfolioRiskVerdict:
    if snapshot.account_equity <= 0 or proposed_maximum_loss <= 0:
        raise ValueError("account equity and proposed maximum loss must be positive")

    reasons: list[str] = []
    if snapshot.kill_switch_enabled:
        reasons.append("kill_switch_enabled")
    if (
        snapshot.open_options_risk + proposed_maximum_loss
        > snapshot.account_equity * limits.maximum_open_risk_fraction
    ):
        reasons.append("open_options_risk_cap")
    if snapshot.open_option_positions >= limits.maximum_option_positions:
        reasons.append("option_position_cap")
    if snapshot.pending_option_orders >= limits.maximum_pending_orders:
        reasons.append("pending_order_cap")
    if snapshot.daily_pnl <= -(snapshot.account_equity * limits.maximum_daily_drawdown_fraction):
        reasons.append("daily_drawdown_cap")

    return PortfolioRiskVerdict(
        passed=not reasons,
        reasons=tuple(reasons),
        snapshot_revision=snapshot.revision,
    )


class RiskStateStore:
    """Serialize kill-switch updates and the final pre-submit risk check."""

    def __init__(self, snapshot: PortfolioRiskSnapshot) -> None:
        self._snapshot = snapshot
        self._lock = Lock()

    def set_kill_switch(self, enabled: bool) -> PortfolioRiskSnapshot:
        with self._lock:
            self._snapshot = replace(
                self._snapshot,
                kill_switch_enabled=enabled,
                revision=self._snapshot.revision + 1,
            )
            return self._snapshot

    def authorize_execution(
        self,
        proposed_maximum_loss: Decimal,
        limits: PortfolioLimits = DEFAULT_PORTFOLIO_LIMITS,
    ) -> PortfolioRiskVerdict:
        with self._lock:
            return assess_portfolio_limits(self._snapshot, proposed_maximum_loss, limits)
