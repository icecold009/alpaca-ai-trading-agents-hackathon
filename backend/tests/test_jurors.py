from datetime import UTC, datetime, timedelta

import pytest

from riskcourt.domain import ForecastOutcome
from riskcourt.jurors import JUROR_SPECS, DeterministicJurorStub, run_juror
from riskcourt.model_provider import (
    ProviderBoundary,
    ProviderReply,
    ProviderRequest,
    ProviderUnavailable,
)


def test_three_independent_jurors_return_forecasts_not_orders() -> None:
    now = datetime(2026, 8, 30, tzinfo=UTC)
    boundary = ProviderBoundary(DeterministicJurorStub())
    forecasts = tuple(
        run_juror(
            boundary,
            spec,
            case_id="case_edge_positive",
            outcome=ForecastOutcome.ABOVE_STRIKE,
            produced_at=now,
            horizon_at=now + timedelta(days=7),
            available_evidence_ids=("quote_spy",),
        )
        for spec in JUROR_SPECS
    )

    assert tuple(f.juror_id for f in forecasts) == (
        "juror_market",
        "juror_catalyst",
        "juror_volatility",
    )
    assert all(f.evidence_ids == ("quote_spy",) for f in forecasts)
    assert all(not hasattr(f, "order") for f in forecasts)


def test_juror_evidence_outside_boundary_is_rejected() -> None:
    class BadProvider:
        def complete(self, request: ProviderRequest) -> ProviderReply:
            return ProviderReply(
                {
                    "probability": "0.5",
                    "calibration_score": "0.5",
                    "confidence_stake": "0.5",
                    "evidence_ids": ["unknown_evidence"],
                    "rationale": "bad",
                    "invalidation": "bad",
                }
            )

    now = datetime(2026, 8, 30, tzinfo=UTC)
    with pytest.raises(ProviderUnavailable, match="outside"):
        run_juror(
            ProviderBoundary(BadProvider()),
            JUROR_SPECS[0],
            case_id="case_edge_positive",
            outcome=ForecastOutcome.ABOVE_STRIKE,
            produced_at=now,
            horizon_at=now + timedelta(days=7),
            available_evidence_ids=("quote_spy",),
        )
