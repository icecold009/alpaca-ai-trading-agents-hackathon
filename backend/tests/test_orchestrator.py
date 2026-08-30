from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from riskcourt.domain import ForecastOutcome, OptionRight
from riskcourt.jurors import DeterministicJurorStub
from riskcourt.model_provider import ProviderBoundary, ProviderReply, ProviderRequest
from riskcourt.option_hurdle import VerticalSpreadGeometry
from riskcourt.orchestrator import run_jury

GEOMETRY = VerticalSpreadGeometry(
    underlying_symbol="SPY",
    expiry=date(2026, 9, 11).isoformat(),
    right=OptionRight.CALL,
    long_occ_symbol="SPY260911C00640000",
    short_occ_symbol="SPY260911C00641000",
    net_debit=Decimal("0.10"),
    spread_width=Decimal("1"),
    break_even_underlying=Decimal("640.10"),
    option_implied_hurdle=Decimal("0.10"),
    maximum_loss=Decimal("10"),
)


def test_orchestrator_aggregates_jurors_and_clears_edge() -> None:
    now = datetime(2026, 8, 30, tzinfo=UTC)
    result = run_jury(
        ProviderBoundary(DeterministicJurorStub()),
        GEOMETRY,
        case_id="case_edge_positive",
        outcome=ForecastOutcome.ABOVE_STRIKE,
        produced_at=now,
        horizon_at=now + timedelta(days=7),
        evidence_ids=("quote_spy",),
    )

    assert result.edge is not None
    assert result.edge.decision.value == "pass"
    assert result.aggregate.probability is not None
    assert len(result.forecasts) == 3


def test_orchestrator_abstains_on_partial_provider_failure() -> None:
    class FailingProvider:
        def complete(self, request: ProviderRequest) -> ProviderReply:
            raise RuntimeError("offline")

    now = datetime(2026, 8, 30, tzinfo=UTC)
    result = run_jury(
        ProviderBoundary(FailingProvider()),
        GEOMETRY,
        case_id="case_edge_positive",
        outcome=ForecastOutcome.ABOVE_STRIKE,
        produced_at=now,
        horizon_at=now + timedelta(days=7),
        evidence_ids=("quote_spy",),
    )

    assert result.decision.value == "abstain"
    assert result.reason == "provider request failed"
