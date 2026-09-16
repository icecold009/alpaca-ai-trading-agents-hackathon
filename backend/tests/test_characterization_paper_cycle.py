"""Deterministic characterization tests for PaperCycleResult — Package 1.

Every test in this file freezes observable behavior of the *current* production
code against fixed timestamps, IDs, prices, account states, and fake order
responses.  No production source is modified; only tests and fixtures are added.

The tests are 100 % offline — zero network calls and zero live-order activity.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from riskcourt.alpaca_account import PendingOrderSnapshot
from riskcourt.alpaca_market_data import MarketDataUnavailable
from riskcourt.alpaca_option_chain import OptionChainUnavailable
from riskcourt.domain import (
    DecisionEventType,
    ExecutionStatus,
    VerdictDecision,
)
from riskcourt.exit_policy import (
    PositionAction,
    PositionState,
)
from riskcourt.order_lifecycle import OrderLifecycleTracker
from riskcourt.paper_loop import (
    evaluate_and_submit_exit,
    record_filled_pnl,
    run_paper_cycle,
)
from riskcourt.spread_selector import SpreadCandidate
from tests.fixtures.paper_fakes import (
    FIXED_CASE_ID,
    FIXED_NOW,
    ConfigurableJurorProvider,
    FakeTradingClient,
    assert_events_strictly_ordered,
    assert_paper_cycle_result_shape,
    assert_zero_network_activity,
    build_fake_account_state,
    build_fake_market_state,
    build_fake_option_chain_state,
    build_fake_order_response,
    build_fake_risk_state,
    build_test_dependencies,
)

# ═══════════════════════════════════════════════════════════════════════
#  1. PaperCycleResult SHAPE FREEZE
# ═══════════════════════════════════════════════════════════════════════


class TestPaperCycleResultShape:
    """Freeze the PaperCycleResult dataclass schema to catch field additions,
    removals, or reorderings before they silently break downstream consumers."""

    def test_shape_has_exactly_fifteen_frozen_fields(self) -> None:
        result = run_paper_cycle(
            build_test_dependencies().dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert_paper_cycle_result_shape(result)

    def test_order_attempted_property_mirrors_submission(self) -> None:
        bundle = build_test_dependencies()
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.order_attempted is True
        assert result.submission is not None

    def test_blocked_result_has_no_submission(self) -> None:
        bundle = build_test_dependencies(
            account_state=build_fake_account_state(market_open=False),
        )
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert_paper_cycle_result_shape(result)
        assert result.order_attempted is False
        assert result.submission is None


# ═══════════════════════════════════════════════════════════════════════
#  2. ENTRY (HAPPY PATH) — deterministic submit
# ═══════════════════════════════════════════════════════════════════════


class TestEntry:
    """Verify a standard approved-and-submitted cycle with fixed inputs."""

    def test_submitted_status_and_reason(self) -> None:
        bundle = build_test_dependencies()
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.status == "submitted"
        assert result.reason == "paper_order_submitted"
        assert result.case_id == FIXED_CASE_ID

    def test_execution_record_present_with_submitted_status(self) -> None:
        bundle = build_test_dependencies()
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.execution is not None
        assert result.execution.status is ExecutionStatus.SUBMITTED
        assert result.execution.case_id == FIXED_CASE_ID

    def test_lifecycle_snapshot_present(self) -> None:
        bundle = build_test_dependencies()
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.lifecycle is not None
        assert result.lifecycle.status is ExecutionStatus.SUBMITTED

    def test_approval_artifact_present_with_correct_ids(self) -> None:
        bundle = build_test_dependencies()
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.approval is not None
        assert result.approval.approval_id == f"approval_{FIXED_CASE_ID}"
        assert result.approval.case_id == FIXED_CASE_ID
        assert result.approval.policy_version == "risk-v1"

    def test_intent_fields_match_case(self) -> None:
        bundle = build_test_dependencies()
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.intent is not None
        assert result.intent.case_id == FIXED_CASE_ID
        assert result.intent.underlying_symbol == "SPY"

    def test_verdict_approved(self) -> None:
        bundle = build_test_dependencies()
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.verdict is not None
        assert result.verdict.decision in (VerdictDecision.APPROVE, VerdictDecision.RESIZE)
        assert result.verdict.approved_quantity >= 1

    def test_exactly_one_order_submitted(self) -> None:
        bundle = build_test_dependencies()
        run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert_zero_network_activity(bundle, expected_orders=1)

    def test_dependency_call_counts_are_frozen(self) -> None:
        provider = ConfigurableJurorProvider()
        bundle = build_test_dependencies(juror_provider=provider)

        run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )

        assert bundle.account_adapter.calls == 1
        assert bundle.market_adapter.calls == 1
        assert bundle.chain_adapter.calls == 1
        assert provider.calls == 3
        assert bundle.client.calls == 1

    def test_client_order_id_starts_with_riskcourt(self) -> None:
        bundle = build_test_dependencies()
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.execution is not None
        assert result.execution.client_order_id.startswith("riskcourt-")

    def test_submit_false_yields_approval_ready(self) -> None:
        bundle = build_test_dependencies()
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
            submit=False,
        )
        assert result.status == "approval_ready"
        assert result.reason == "paper_order_preview_ready"
        assert result.order_attempted is False
        assert_zero_network_activity(bundle, expected_orders=0)


# ═══════════════════════════════════════════════════════════════════════
#  3. NO-ENTRY / GUARD DENIAL scenarios
# ═══════════════════════════════════════════════════════════════════════


class TestNoEntry:
    """Verify that every guard condition blocks before order placement."""

    def test_market_closed_blocks(self) -> None:
        bundle = build_test_dependencies(
            account_state=build_fake_account_state(market_open=False),
        )
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.status == "blocked"
        assert result.reason == "market_closed"
        assert_zero_network_activity(bundle, expected_orders=0)

    def test_zero_equity_blocks(self) -> None:
        bundle = build_test_dependencies(
            account_state=build_fake_account_state(equity=Decimal("0")),
        )
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.status == "blocked"
        assert result.reason == "account_equity_unavailable"
        assert_zero_network_activity(bundle, expected_orders=0)

    def test_account_blocked_blocks(self) -> None:
        bundle = build_test_dependencies(
            account_state=build_fake_account_state(account_blocked=True),
        )
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.status == "blocked"
        assert result.reason == "account_blocked"
        assert_zero_network_activity(bundle, expected_orders=0)

    def test_trading_blocked_blocks(self) -> None:
        bundle = build_test_dependencies(
            account_state=build_fake_account_state(trading_blocked=True),
        )
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.status == "blocked"
        assert result.reason == "account_blocked"
        assert_zero_network_activity(bundle, expected_orders=0)

    def test_trade_suspended_by_user_blocks(self) -> None:
        bundle = build_test_dependencies(
            account_state=build_fake_account_state(trade_suspended_by_user=True),
        )
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.status == "blocked"
        assert result.reason == "trade_suspended_by_user"
        assert_zero_network_activity(bundle, expected_orders=0)

    def test_low_options_trading_level_blocks(self) -> None:
        bundle = build_test_dependencies(
            account_state=build_fake_account_state(trading_level=2),
        )
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.status == "blocked"
        assert result.reason == "options_trading_level_unavailable"
        assert_zero_network_activity(bundle, expected_orders=0)

    def test_none_options_trading_level_blocks(self) -> None:
        bundle = build_test_dependencies(
            account_state=build_fake_account_state(trading_level=0),
        )
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.status == "blocked"
        assert_zero_network_activity(bundle, expected_orders=0)

    def test_market_data_unavailable_blocks(self) -> None:
        bundle = build_test_dependencies(
            market_exc=MarketDataUnavailable("test"),
        )
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.status == "blocked"
        assert result.reason == "market_data_unavailable"
        assert_zero_network_activity(bundle, expected_orders=0)

    def test_stale_underlying_quote_blocks(self) -> None:
        bundle = build_test_dependencies(
            market_state=build_fake_market_state(stale=True),
        )
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.status == "blocked"
        assert result.reason == "underlying_quote_stale"
        assert_zero_network_activity(bundle, expected_orders=0)

    def test_option_chain_unavailable_blocks(self) -> None:
        bundle = build_test_dependencies(
            chain_exc=OptionChainUnavailable("test"),
        )
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.status == "blocked"
        assert result.reason == "option_chain_unavailable"
        assert_zero_network_activity(bundle, expected_orders=0)

    def test_empty_chain_no_liquid_spread_blocks(self) -> None:
        bundle = build_test_dependencies(
            chain_state=build_fake_option_chain_state(contracts=()),
        )
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.status == "blocked"
        assert result.reason == "no_liquid_supported_spread"
        assert_zero_network_activity(bundle, expected_orders=0)


# ═══════════════════════════════════════════════════════════════════════
#  4. SAFETY DENIALS — sizing veto, portfolio-risk veto
# ═══════════════════════════════════════════════════════════════════════


class TestSafetyDenials:
    """Verify that risk-limit vetoes prevent order placement."""

    def test_zero_equity_sizing_veto(self) -> None:
        """If equity is very low, sizing rejects the position."""
        bundle = build_test_dependencies(
            account_state=build_fake_account_state(equity=Decimal("1")),
        )
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        # With extremely low equity, sizing or risk limits should veto
        assert result.status in ("vetoed", "blocked")
        assert_zero_network_activity(bundle, expected_orders=0)

    def test_kill_switch_portfolio_risk_veto(self) -> None:
        """A risk store with the kill switch vetoes all orders."""
        bundle = build_test_dependencies(
            risk_store=build_fake_risk_state(kill_switch_enabled=True),
        )
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.status == "vetoed"
        assert_zero_network_activity(bundle, expected_orders=0)

    def test_existing_pending_options_risk_veto(self) -> None:
        """Maximum pending-order count breaches portfolio limits."""
        bundle = build_test_dependencies(
            risk_store=build_fake_risk_state(pending_orders=5),
        )
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.status == "vetoed"
        assert_zero_network_activity(bundle, expected_orders=0)


# ═══════════════════════════════════════════════════════════════════════
#  5. PROVIDER FAILURE
# ═══════════════════════════════════════════════════════════════════════


class TestProviderFailure:
    """Verify fail-closed behavior on model-provider errors."""

    def test_provider_unavailable_abstains(self) -> None:
        bundle = build_test_dependencies(
            juror_provider=ConfigurableJurorProvider(raise_unavailable="timeout"),
        )
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.status == "abstained"
        assert "timeout" in result.reason
        assert_zero_network_activity(bundle, expected_orders=0)

    def test_provider_failure_still_records_evidence(self) -> None:
        """Even on failure the case_opened event is in the log."""
        bundle = build_test_dependencies(
            juror_provider=ConfigurableJurorProvider(raise_unavailable="provider_down"),
        )
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.status == "abstained"
        types = [e.event.event_type for e in bundle.log.events]
        assert DecisionEventType.CASE_OPENED in types

    def test_provider_invalid_evidence_raises(self) -> None:
        """Juror citing rogue evidence outside boundary triggers ProviderUnavailable."""
        bundle = build_test_dependencies(
            juror_provider=ConfigurableJurorProvider(cite_invalid_evidence=True),
        )
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        # Should abstain because the boundary rejects the evidence
        assert result.status == "abstained"
        assert_zero_network_activity(bundle, expected_orders=0)


# ═══════════════════════════════════════════════════════════════════════
#  6. ACCEPTED / REJECTED / PARTIAL / LATE / DUPLICATE RESPONSES
# ═══════════════════════════════════════════════════════════════════════


class TestOrderResponses:
    """Verify PaperCycleResult maps Alpaca response statuses correctly."""

    def test_accepted_status_maps_to_accepted(self) -> None:
        bundle = build_test_dependencies(client_status="accepted")
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.execution is not None
        assert result.execution.status is ExecutionStatus.ACCEPTED

    def test_rejected_status_maps_to_rejected(self) -> None:
        bundle = build_test_dependencies(client_status="rejected")
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.execution is not None
        assert result.execution.status is ExecutionStatus.REJECTED

    def test_partially_filled_status_maps(self) -> None:
        bundle = build_test_dependencies(client_status="partially_filled")
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.execution is not None
        assert result.execution.status is ExecutionStatus.PARTIALLY_FILLED

    def test_filled_without_price_demoted_to_submitted(self) -> None:
        """A filled response that lacks filled_avg_price is demoted to submitted."""
        bundle = build_test_dependencies(client_status="filled")
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.execution is not None
        # The default fake has filled_avg_price=None so it should demote
        assert result.execution.status is ExecutionStatus.SUBMITTED

    def test_filled_with_price_stays_filled(self) -> None:
        filled_resp = build_fake_order_response(
            client_order_id="placeholder",
            status="filled",
            filled_avg_price="1.05",
            filled_at=FIXED_NOW,
        )
        client = FakeTradingClient(responses=[filled_resp])
        bundle = build_test_dependencies(client=client)
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.execution is not None
        assert result.execution.status is ExecutionStatus.FILLED
        assert result.execution.filled_debit == Decimal("1.05")

    def test_canceled_status_maps(self) -> None:
        bundle = build_test_dependencies(client_status="canceled")
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.execution is not None
        assert result.execution.status is ExecutionStatus.CANCELED

    def test_expired_status_maps_to_canceled(self) -> None:
        bundle = build_test_dependencies(client_status="expired")
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.execution is not None
        assert result.execution.status is ExecutionStatus.CANCELED


# ═══════════════════════════════════════════════════════════════════════
#  7. DUPLICATE PENDING ORDER
# ═══════════════════════════════════════════════════════════════════════


class TestDuplicatePendingOrder:
    """Verify that a matching pending order in the account blocks submission."""

    def test_duplicate_pending_order_blocks(self) -> None:
        """If the candidate's proposed client_order_id already appears in
        pending_orders, the cycle blocks with 'duplicate_pending_order'."""
        # First, run a cycle to discover what client_order_id would be proposed
        bundle1 = build_test_dependencies()
        result1 = run_paper_cycle(
            bundle1.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result1.execution is not None
        proposed_id = result1.execution.client_order_id

        # Now set up a pending order with that same client_order_id
        pending = PendingOrderSnapshot(
            client_order_id=proposed_id,
            symbol=None,
            status="accepted",
            order_class="mleg",
            submitted_at=FIXED_NOW,
        )
        bundle2 = build_test_dependencies(
            account_state=build_fake_account_state(pending_orders=(pending,)),
        )
        result2 = run_paper_cycle(
            bundle2.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result2.status == "blocked"
        assert result2.reason == "duplicate_pending_order"
        assert_zero_network_activity(bundle2, expected_orders=0)


# ═══════════════════════════════════════════════════════════════════════
#  8. CANCELLATION / TIMEOUT
# ═══════════════════════════════════════════════════════════════════════


class TestCancellationAndTimeout:
    """Verify cancellation and timeout-related status mapping."""

    def test_pending_cancel_maps_to_canceled(self) -> None:
        bundle = build_test_dependencies(client_status="pending_cancel")
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.execution is not None
        assert result.execution.status is ExecutionStatus.CANCELED

    def test_done_for_day_maps_to_canceled(self) -> None:
        bundle = build_test_dependencies(client_status="done_for_day")
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.execution is not None
        assert result.execution.status is ExecutionStatus.CANCELED

    def test_late_terminal_update_is_rejected_without_state_regression(self) -> None:
        filled = build_fake_order_response(
            client_order_id="riskcourt-late-001",
            status="filled",
            submitted_at=FIXED_NOW,
            updated_at=FIXED_NOW + timedelta(minutes=2),
            filled_qty="1",
            filled_avg_price="1.05",
            filled_at=FIXED_NOW + timedelta(minutes=2),
        )
        late = build_fake_order_response(
            client_order_id="riskcourt-late-001",
            status="accepted",
            submitted_at=FIXED_NOW,
            updated_at=FIXED_NOW + timedelta(seconds=1),
        )
        tracker = OrderLifecycleTracker(filled)

        with pytest.raises(ValueError, match="regressed"):
            tracker.apply(late)

        assert tracker.snapshot.status is ExecutionStatus.FILLED
        assert tracker.snapshot.filled_debit == Decimal("1.05")

    def test_naive_now_raises_valueerror(self) -> None:
        """A naive 'now' timestamp is rejected immediately."""
        bundle = build_test_dependencies()
        with pytest.raises(ValueError, match="timezone-aware"):
            run_paper_cycle(
                bundle.dependencies,
                case_id=FIXED_CASE_ID,
                now=datetime(2026, 8, 30, 15, 0),  # naive
            )


# ═══════════════════════════════════════════════════════════════════════
#  9. EXIT POLICY
# ═══════════════════════════════════════════════════════════════════════


class TestExitPolicy:
    """Verify evaluate_and_submit_exit determinism with fixed states."""

    def _spread_candidate(self) -> SpreadCandidate:
        """Return the spread candidate that the default chain produces."""
        bundle = build_test_dependencies()
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.candidate is not None
        return result.candidate

    def test_exit_on_profit_target(self) -> None:
        candidate = self._spread_candidate()
        state = PositionState(
            has_position=True,
            entry_debit=Decimal("0.20"),
            current_value=Decimal("0.50"),  # 2.5× debit → profit target
            probability_edge=Decimal("0.10"),
            quote_age=timedelta(seconds=5),
            days_to_expiry=10,
            kill_switch_enabled=False,
        )
        adapter = build_test_dependencies().dependencies.orders
        decision, submission = evaluate_and_submit_exit(
            candidate=candidate,
            adapter=adapter,
            state=state,
            client_order_id="riskcourt-exit-profit-001",
            approved=True,
        )
        assert decision.action is PositionAction.EXIT
        assert decision.reason == "profit_target"
        assert submission is not None

    def test_exit_on_expiry_risk(self) -> None:
        candidate = self._spread_candidate()
        state = PositionState(
            has_position=True,
            entry_debit=Decimal("0.20"),
            current_value=Decimal("0.22"),
            probability_edge=Decimal("0.10"),
            quote_age=timedelta(seconds=5),
            days_to_expiry=1,  # within exit_days_before_expiry
            kill_switch_enabled=False,
        )
        adapter = build_test_dependencies().dependencies.orders
        decision, _ = evaluate_and_submit_exit(
            candidate=candidate,
            adapter=adapter,
            state=state,
            client_order_id="riskcourt-exit-expiry-001",
            approved=True,
        )
        assert decision.action is PositionAction.EXIT
        assert decision.reason == "expiry_risk"

    def test_hold_does_not_submit(self) -> None:
        candidate = self._spread_candidate()
        state = PositionState(
            has_position=True,
            entry_debit=Decimal("0.20"),
            current_value=Decimal("0.22"),
            probability_edge=Decimal("0.10"),
            quote_age=timedelta(seconds=5),
            days_to_expiry=10,
            kill_switch_enabled=False,
        )
        adapter = build_test_dependencies().dependencies.orders
        decision, submission = evaluate_and_submit_exit(
            candidate=candidate,
            adapter=adapter,
            state=state,
            client_order_id="riskcourt-exit-hold-001",
            approved=True,
        )
        assert decision.action is PositionAction.HOLD
        assert submission is None

    def test_kill_switch_forces_exit(self) -> None:
        candidate = self._spread_candidate()
        state = PositionState(
            has_position=True,
            entry_debit=Decimal("0.20"),
            current_value=Decimal("0.22"),
            probability_edge=Decimal("0.10"),
            quote_age=timedelta(seconds=5),
            days_to_expiry=10,
            kill_switch_enabled=True,
        )
        adapter = build_test_dependencies().dependencies.orders
        decision, submission = evaluate_and_submit_exit(
            candidate=candidate,
            adapter=adapter,
            state=state,
            client_order_id="riskcourt-exit-kill-001",
            approved=True,
        )
        assert decision.action is PositionAction.EXIT
        assert decision.reason == "kill_switch_enabled"
        assert submission is not None


# ═══════════════════════════════════════════════════════════════════════
#  10. P&L / EVIDENCE BEHAVIOR
# ═══════════════════════════════════════════════════════════════════════


class TestPnLBehavior:
    """Freeze P&L snapshot arithmetic and evidence recording."""

    def test_filled_pnl_snapshot_dollar_based(self) -> None:
        bundle = build_test_dependencies()
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.execution is not None
        filled_exec = result.execution.model_copy(
            update={
                "status": ExecutionStatus.FILLED,
                "filled_at": FIXED_NOW,
                "filled_debit": Decimal("0.10"),
            }
        )
        filled_result = replace(result, execution=filled_exec)
        snapshot = record_filled_pnl(
            filled_result,
            event_log=bundle.log,
            position_value=Decimal("15"),
        )
        # cost_basis = filled_debit * 100 * quantity(1) = 10
        assert snapshot.cost_basis == Decimal("10")
        # unrealized_pnl = position_value - cost_basis = 15 - 10 = 5
        assert snapshot.unrealized_pnl == Decimal("5")
        assert snapshot.realized_pnl == Decimal("0")
        assert snapshot.maximum_loss > 0

    def test_pnl_event_appended_to_log(self) -> None:
        bundle = build_test_dependencies()
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.execution is not None
        filled_exec = result.execution.model_copy(
            update={
                "status": ExecutionStatus.FILLED,
                "filled_at": FIXED_NOW,
                "filled_debit": Decimal("0.10"),
            }
        )
        filled_result = replace(result, execution=filled_exec)
        record_filled_pnl(
            filled_result,
            event_log=bundle.log,
            position_value=Decimal("15"),
        )
        last_event = bundle.log.events[-1].event
        assert last_event.event_type is DecisionEventType.PNL_RECORDED
        bundle.log.verify()

    def test_pnl_rejects_non_filled_execution(self) -> None:
        bundle = build_test_dependencies()
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        with pytest.raises(ValueError, match="filled"):
            record_filled_pnl(
                result,
                event_log=bundle.log,
                position_value=Decimal("15"),
            )


# ═══════════════════════════════════════════════════════════════════════
#  11. EVIDENCE BEHAVIOR — item and hash-chain
# ═══════════════════════════════════════════════════════════════════════


class TestEvidenceBehavior:
    """Freeze evidence item count and types for a submitted cycle."""

    def test_evidence_ids_present_in_execution(self) -> None:
        bundle = build_test_dependencies()
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.execution is not None
        eids = result.execution.evidence_ids
        assert len(eids) == 5
        suffixes = {eid.split("_")[-1] for eid in eids}
        assert suffixes == {"account", "underlying", "long", "short", "policy"}

    def test_evidence_ids_on_approval_match_execution(self) -> None:
        bundle = build_test_dependencies()
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.approval is not None and result.execution is not None
        assert result.approval.evidence_ids == result.execution.evidence_ids


# ═══════════════════════════════════════════════════════════════════════
#  12. ORDERING — event log sequence
# ═══════════════════════════════════════════════════════════════════════


class TestEventOrdering:
    """Freeze the decision-event ordering for a standard submitted cycle."""

    def test_submitted_cycle_event_ordering(self) -> None:
        bundle = build_test_dependencies()
        run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        event_types = [e.event.event_type for e in bundle.log.events]
        assert event_types == [
            DecisionEventType.CASE_OPENED,
            DecisionEventType.FORECAST_RECORDED,
            DecisionEventType.INTENT_PROPOSED,
            DecisionEventType.RISK_EVALUATED,
            DecisionEventType.APPROVAL_ISSUED,
            DecisionEventType.EXECUTION_UPDATED,
        ]

    def test_events_are_hash_chain_verified(self) -> None:
        bundle = build_test_dependencies()
        run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert_events_strictly_ordered(bundle.log)

    def test_provider_failure_event_ordering(self) -> None:
        bundle = build_test_dependencies(
            juror_provider=ConfigurableJurorProvider(raise_unavailable="down"),
        )
        run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        event_types = [e.event.event_type for e in bundle.log.events]
        assert DecisionEventType.CASE_OPENED in event_types
        # No APPROVAL_ISSUED or EXECUTION_UPDATED
        assert DecisionEventType.APPROVAL_ISSUED not in event_types
        assert DecisionEventType.EXECUTION_UPDATED not in event_types

    def test_blocked_cycle_produces_no_events(self) -> None:
        bundle = build_test_dependencies(
            account_state=build_fake_account_state(market_open=False),
        )
        run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert len(bundle.log.events) == 0


# ═══════════════════════════════════════════════════════════════════════
#  13. IDEMPOTENCY / CORRELATION KEYS
# ═══════════════════════════════════════════════════════════════════════


class TestIdempotencyCorrelation:
    """Freeze idempotency key behavior and ID correlation."""

    def test_same_case_same_chain_produces_same_client_order_id(self) -> None:
        """Running the same case_id with the same chain → identical client_order_id."""
        bundle1 = build_test_dependencies()
        r1 = run_paper_cycle(
            bundle1.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        bundle2 = build_test_dependencies()
        r2 = run_paper_cycle(
            bundle2.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert r1.execution is not None and r2.execution is not None
        assert r1.execution.client_order_id == r2.execution.client_order_id

    def test_different_case_ids_produce_different_client_order_ids(self) -> None:
        bundle1 = build_test_dependencies(case_id="case_alpha_001")
        r1 = run_paper_cycle(
            bundle1.dependencies,
            case_id="case_alpha_001",
            now=FIXED_NOW,
        )
        bundle2 = build_test_dependencies(case_id="case_beta_001")
        r2 = run_paper_cycle(
            bundle2.dependencies,
            case_id="case_beta_001",
            now=FIXED_NOW,
        )
        assert r1.execution is not None and r2.execution is not None
        assert r1.execution.client_order_id != r2.execution.client_order_id

    def test_approval_ids_are_deterministic(self) -> None:
        bundle = build_test_dependencies()
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.approval is not None
        assert result.approval.approval_id == f"approval_{FIXED_CASE_ID}"
        assert result.intent is not None
        assert result.intent.intent_id == f"intent_{FIXED_CASE_ID.removeprefix('case_')}"
        assert result.verdict is not None
        assert result.verdict.verdict_id == f"verdict_{FIXED_CASE_ID.removeprefix('case_')}"

    def test_execution_id_is_deterministic(self) -> None:
        bundle = build_test_dependencies()
        result = run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert result.execution is not None
        assert result.execution.execution_id == (f"execution_{FIXED_CASE_ID.removeprefix('case_')}")


# ═══════════════════════════════════════════════════════════════════════
#  14. ZERO NETWORK / LIVE-ORDER ACTIVITY
# ═══════════════════════════════════════════════════════════════════════


class TestZeroNetworkActivity:
    """Globally assert that blocked/abstained cycles never reach the trading client."""

    @pytest.mark.parametrize(
        "account_kwargs",
        [
            {"market_open": False},
            {"equity": Decimal("0")},
            {"account_blocked": True},
            {"trading_blocked": True},
            {"trade_suspended_by_user": True},
            {"trading_level": 1},
        ],
    )
    def test_account_guard_zero_orders(self, account_kwargs: dict[str, Any]) -> None:
        bundle = build_test_dependencies(
            account_state=build_fake_account_state(**account_kwargs),
        )
        run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert_zero_network_activity(bundle, expected_orders=0)

    def test_provider_failure_zero_orders(self) -> None:
        bundle = build_test_dependencies(
            juror_provider=ConfigurableJurorProvider(raise_unavailable="net_fail"),
        )
        run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert_zero_network_activity(bundle, expected_orders=0)

    def test_market_data_failure_zero_orders(self) -> None:
        bundle = build_test_dependencies(
            market_exc=MarketDataUnavailable("test"),
        )
        run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert_zero_network_activity(bundle, expected_orders=0)

    def test_chain_failure_zero_orders(self) -> None:
        bundle = build_test_dependencies(
            chain_exc=OptionChainUnavailable("test"),
        )
        run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert_zero_network_activity(bundle, expected_orders=0)

    def test_submitted_cycle_exactly_one_order(self) -> None:
        bundle = build_test_dependencies()
        run_paper_cycle(
            bundle.dependencies,
            case_id=FIXED_CASE_ID,
            now=FIXED_NOW,
        )
        assert_zero_network_activity(bundle, expected_orders=1)
