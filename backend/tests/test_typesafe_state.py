from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from riskcourt.domain import EvidenceItem, EvidenceType, ForecastOutcome
from riskcourt.typesafe_state import TypeSafeState, build_typesafe_state

NOW = datetime(2026, 8, 30, 15, tzinfo=UTC)


def evidence(evidence_id: str, kind: EvidenceType, *, observed_at: datetime = NOW) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        evidence_type=kind,
        source="test-source",
        symbol="SPY",
        observed_at=observed_at,
        payload_sha256="0" * 64,
        summary="Current test evidence summary.",
        raw_reference="test-only-reference",
    )


def state_with_all_evidence() -> TypeSafeState:
    return build_typesafe_state(
        symbol="SPY",
        outcome=ForecastOutcome.ABOVE_STRIKE,
        horizon_at=NOW + timedelta(days=7),
        as_of=NOW,
        evidence=(
            evidence("ev_market", EvidenceType.UNDERLYING_QUOTE),
            evidence("ev_option", EvidenceType.OPTION_QUOTE),
            evidence("ev_news", EvidenceType.NEWS),
        ),
        market={
            "bid": "640.10",
            "ask": "640.20",
            "forecast_reference": {
                "kind": "deterministic_break_even_underlying",
                "value": "640.15",
            },
        },
        options={"spread_width": "1"},
    )


def test_state_hash_is_stable_and_role_partitions_are_explicit() -> None:
    state = state_with_all_evidence()

    assert state.state_hash == state_with_all_evidence().state_hash
    assert state.for_juror("juror_market").evidence_ids == ("ev_market",)
    assert state.for_juror("juror_volatility").evidence_ids == ("ev_option",)
    assert state.for_juror("juror_catalyst").evidence_ids == ("ev_news",)
    assert state.for_juror("juror_market").market == {
        "bid": "640.10",
        "ask": "640.20",
        "forecast_reference": {
            "kind": "deterministic_break_even_underlying",
            "value": "640.15",
        },
    }
    assert state.for_juror("juror_market").options == {}
    assert state.for_juror("juror_volatility").options == {"spread_width": "1"}
    assert state.for_juror("juror_volatility").market == {
        "bid": "640.10",
        "ask": "640.20",
    }
    assert state.for_juror("juror_catalyst").market == {}
    assert state.for_juror("juror_catalyst").options == {}
    assert "raw_reference" not in state.model_dump(mode="json")


def test_state_rejects_sensitive_market_or_option_keys() -> None:
    with pytest.raises(ValueError, match="sensitive provider state key"):
        build_typesafe_state(
            symbol="SPY",
            outcome=ForecastOutcome.ABOVE_STRIKE,
            horizon_at=NOW + timedelta(days=7),
            as_of=NOW,
            evidence=(evidence("ev_market", EvidenceType.UNDERLYING_QUOTE),),
            market={"account_id": "should-not-cross-boundary"},
        )

    with pytest.raises(ValueError, match="sensitive provider state key"):
        build_typesafe_state(
            symbol="SPY",
            outcome=ForecastOutcome.ABOVE_STRIKE,
            horizon_at=NOW + timedelta(days=7),
            as_of=NOW,
            evidence=(evidence("ev_market", EvidenceType.UNDERLYING_QUOTE),),
            market={"accountId": "should-not-cross-boundary"},
        )


def test_state_rejects_duplicate_or_stale_evidence() -> None:
    with pytest.raises(ValueError, match="duplicate evidence"):
        build_typesafe_state(
            symbol="SPY",
            outcome=ForecastOutcome.ABOVE_STRIKE,
            horizon_at=NOW + timedelta(days=7),
            as_of=NOW,
            evidence=(
                evidence("ev_market", EvidenceType.UNDERLYING_QUOTE),
                evidence("ev_market", EvidenceType.UNDERLYING_QUOTE),
            ),
        )

    stale = state_with_all_evidence().model_copy(
        update={
            "evidence": (
                evidence(
                    "ev_old",
                    EvidenceType.UNDERLYING_QUOTE,
                    observed_at=NOW - timedelta(days=2),
                ),
            )
        },
    )
    with pytest.raises(ValueError, match="stale"):
        stale.validate_freshness()


def test_state_rejects_unknown_juror_and_malformed_summary() -> None:
    with pytest.raises(ValueError, match="unknown juror"):
        state_with_all_evidence().for_juror("juror_unknown")

    with pytest.raises(ValidationError):
        build_typesafe_state(
            symbol="SPY",
            outcome=ForecastOutcome.ABOVE_STRIKE,
            horizon_at=NOW + timedelta(days=7),
            as_of=NOW,
            evidence=(
                evidence("ev_market", EvidenceType.UNDERLYING_QUOTE).model_copy(
                    update={"summary": "x" * 401}
                ),
            ),
        )
