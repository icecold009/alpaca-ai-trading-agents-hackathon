import sys
import types
from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import JsonValue

from riskcourt.domain import EvidenceType, ForecastOutcome
from riskcourt.jurors import JUROR_SPECS, run_juror
from riskcourt.model_provider import (
    ProviderBoundary,
    ProviderReply,
    ProviderRequest,
    ProviderUnavailable,
)
from riskcourt.typesafe_provider import (
    ShadowProviderClient,
    TypeSafeProviderClient,
    TypeSafeProviderConfig,
    create_typesafe_sdk_client,
)
from riskcourt.typesafe_state import NO_SUPPORTED_EVIDENCE, TypeSafeState, build_typesafe_state
from tests.test_typesafe_state import NOW, evidence


class FakeQuestion:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


class FakeSdkResponse:
    def __init__(self, probability: str = "0.62", anchor: str = "ev_market") -> None:
        self.model = "jev-test"
        self.nouls = {"outcome_probability": SimpleNamespace(noul=float(probability))}
        self.choices = {
            "evidence_anchor": SimpleNamespace(choice=anchor, confidence=0.8)
        }
        self.scores = {
            "evidence_quality": SimpleNamespace(score=1.5, confidence=0.9)
        }
        self.usage = SimpleNamespace(input_tokens=120, output_tokens=12)


class FakeSdkClient:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def system_one(
        self,
        *,
        state: dict[str, JsonValue],
        questions: Mapping[str, object],
        model: str,
    ) -> object:
        self.calls.append({"state": state, "questions": questions, "model": model})
        return self.response


def install_fake_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("typesafe_sdk")
    module.__dict__["Noul"] = FakeQuestion
    module.__dict__["Choice"] = FakeQuestion
    module.__dict__["Score"] = FakeQuestion
    monkeypatch.setitem(sys.modules, "typesafe_sdk", module)


def request(state: TypeSafeState, juror_id: str = "juror_market") -> ProviderRequest:
    return ProviderRequest(
        request_id="request_typesafe",
        prompt_version="riskcourt-typesafe-jury-v1",
        model_version="jev-latest",
        payload={
            "juror_id": juror_id,
            "available_evidence_ids": ["ev_market", "ev_option", "ev_news"],
            "typesafe_state": state.model_dump(mode="json"),
        },
    )


def complete_state() -> TypeSafeState:
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
    )


def test_valid_typed_judgment_maps_to_existing_provider_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_sdk(monkeypatch)
    client = FakeSdkClient(FakeSdkResponse())
    provider = TypeSafeProviderClient(
        client, config=TypeSafeProviderConfig(model="jev-test")
    )

    reply = provider.complete(request(complete_state()))

    assert reply.output["probability"] == "0.62"
    assert reply.output["evidence_ids"] == ["ev_market"]
    assert reply.metadata["provider"] == "typesafe"
    assert reply.metadata["input_tokens"] == 120
    assert reply.metadata["state_hash"]
    assert "api_key" not in str(reply.metadata).lower()
    assert client.calls[0]["model"] == "jev-test"


@pytest.mark.parametrize("probability", ["0", "1"])
def test_probability_boundaries_are_accepted(
    monkeypatch: pytest.MonkeyPatch, probability: str
) -> None:
    install_fake_sdk(monkeypatch)
    provider = TypeSafeProviderClient(FakeSdkClient(FakeSdkResponse(probability)))

    reply = provider.complete(request(complete_state()))

    assert reply.output["probability"] == probability


def test_no_supported_evidence_unknown_anchor_and_stale_evidence_abstain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_sdk(monkeypatch)
    provider = TypeSafeProviderClient(FakeSdkClient(FakeSdkResponse(anchor="ev_news")))
    with pytest.raises(ProviderUnavailable, match="unknown evidence"):
        provider.complete(request(complete_state()))

    catalyst_state = build_typesafe_state(
        symbol="SPY",
        outcome=ForecastOutcome.ABOVE_STRIKE,
        horizon_at=NOW + timedelta(days=7),
        as_of=NOW,
        evidence=(evidence("ev_market", EvidenceType.UNDERLYING_QUOTE),),
    )
    with pytest.raises(ProviderUnavailable, match=NO_SUPPORTED_EVIDENCE):
        provider.complete(request(catalyst_state, "juror_catalyst"))

    stale_state = build_typesafe_state(
        symbol="SPY",
        outcome=ForecastOutcome.ABOVE_STRIKE,
        horizon_at=NOW + timedelta(days=7),
        as_of=NOW,
        evidence=(
            evidence(
                "ev_market",
                EvidenceType.UNDERLYING_QUOTE,
                observed_at=NOW - timedelta(days=2),
            ),
        ),
    )
    with pytest.raises(ProviderUnavailable, match="invalid"):
        provider.complete(request(stale_state))


def test_juror_mapping_keeps_calibration_code_owned(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_sdk(monkeypatch)
    state = complete_state()
    forecast = run_juror(
        ProviderBoundary(TypeSafeProviderClient(FakeSdkClient(FakeSdkResponse()))),
        JUROR_SPECS[0],
        case_id="case_typesafe",
        outcome=ForecastOutcome.ABOVE_STRIKE,
        produced_at=NOW,
        horizon_at=NOW + timedelta(days=7),
        available_evidence_ids=state.evidence_ids,
        state=state,
    )

    assert forecast.calibration_score == Decimal("0.80")
    assert forecast.confidence_stake > 0
    assert forecast.provider_metadata["validation"] == "passed"


def test_shadow_mode_keeps_primary_output_when_typesafe_disagrees(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_sdk(monkeypatch)

    class Primary:
        def complete(self, _: ProviderRequest) -> ProviderReply:
            return ProviderReply(
                output={
                    "probability": "0.50",
                    "calibration_score": "0.80",
                    "confidence_stake": "0.70",
                    "evidence_ids": ["ev_market"],
                    "rationale": "deterministic",
                    "invalidation": "test",
                }
            )

    primary = Primary()
    shadow = TypeSafeProviderClient(FakeSdkClient(FakeSdkResponse("1")))
    reply = ShadowProviderClient(primary, shadow).complete(request(complete_state()))

    assert reply.output["probability"] == "0.50"
    assert reply.metadata["shadow_typesafe"] == {
        "status": "completed",
        "probability": "1",
        "evidence_ids": ["ev_market"],
        "confidence_stake": "0.825",
    }


def test_sdk_factory_requires_key_and_does_not_leak_it(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ProviderUnavailable, match="api key"):
        create_typesafe_sdk_client(api_key=" ", model="jev-latest", timeout_seconds=1)

    module = types.ModuleType("typesafe_sdk")
    class SafeClient:
        def __init__(self, **kwargs: object) -> None:
            self.model = kwargs["model"]

        def __repr__(self) -> str:
            return "SafeClient()"

    module.__dict__["TypeSafeClient"] = SafeClient
    monkeypatch.setitem(sys.modules, "typesafe_sdk", module)
    client = create_typesafe_sdk_client(
        api_key="ts_secret_value", model="jev-test", timeout_seconds=2
    )
    assert type(client).__name__ == "SafeClient"
    assert "ts_secret_value" not in repr(client)
