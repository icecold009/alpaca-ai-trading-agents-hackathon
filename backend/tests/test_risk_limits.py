from dataclasses import replace
from decimal import Decimal
from threading import Event, Thread

import pytest

from riskcourt.risk_limits import (
    PortfolioRiskSnapshot,
    RiskStateStore,
    assess_portfolio_limits,
)


def safe_snapshot() -> PortfolioRiskSnapshot:
    return PortfolioRiskSnapshot(
        account_equity=Decimal("100000"),
        open_options_risk=Decimal("0"),
        open_option_positions=0,
        pending_option_orders=0,
        daily_pnl=Decimal("0"),
        kill_switch_enabled=False,
        revision=1,
    )


def test_safe_portfolio_passes() -> None:
    result = assess_portfolio_limits(safe_snapshot(), Decimal("150"))

    assert result.passed is True
    assert result.reasons == ()


@pytest.mark.parametrize(
    ("snapshot", "reason"),
    [
        (replace(safe_snapshot(), open_options_risk=Decimal("1900")), "open_options_risk_cap"),
        (replace(safe_snapshot(), open_option_positions=3), "option_position_cap"),
        (replace(safe_snapshot(), pending_option_orders=1), "pending_order_cap"),
        (replace(safe_snapshot(), daily_pnl=Decimal("-2000")), "daily_drawdown_cap"),
        (replace(safe_snapshot(), kill_switch_enabled=True), "kill_switch_enabled"),
    ],
)
def test_each_portfolio_limit_fails_closed(
    snapshot: PortfolioRiskSnapshot,
    reason: str,
) -> None:
    result = assess_portfolio_limits(snapshot, Decimal("150"))

    assert result.passed is False
    assert reason in result.reasons


def test_kill_switch_race_after_approval_blocks_execution() -> None:
    store = RiskStateStore(safe_snapshot())
    initial_approval = store.authorize_execution(Decimal("150"))
    execution_can_check = Event()
    execution_checked = Event()
    results: list[bool] = []

    def execution_attempt() -> None:
        execution_can_check.wait(timeout=2)
        results.append(store.authorize_execution(Decimal("150")).passed)
        execution_checked.set()

    worker = Thread(target=execution_attempt)
    worker.start()
    store.set_kill_switch(True)
    execution_can_check.set()
    execution_checked.wait(timeout=2)
    worker.join(timeout=2)

    assert initial_approval.passed is True
    assert results == [False]
