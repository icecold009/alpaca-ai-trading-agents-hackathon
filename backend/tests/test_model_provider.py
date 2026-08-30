import time
from decimal import Decimal

import pytest
from pydantic import Field

from riskcourt.domain import ContractModel
from riskcourt.model_provider import (
    ProviderBoundary,
    ProviderReply,
    ProviderRequest,
    ProviderUnavailable,
)


class Output(ContractModel):
    probability: Decimal = Field(ge=0, le=1)


REQUEST = ProviderRequest(
    request_id="model_request_001",
    prompt_version="jury-v1",
    model_version="stub-v1",
    payload={"symbol": "SPY"},
)


class FakeProvider:
    def __init__(self, replies: list[ProviderReply]) -> None:
        self.replies = replies
        self.requests: list[ProviderRequest] = []

    def complete(self, request: ProviderRequest) -> ProviderReply:
        self.requests.append(request)
        return self.replies.pop(0)


def test_structured_output_records_versions_attempts_and_cost() -> None:
    provider = FakeProvider([ProviderReply({"probability": "0.62"}, Decimal("1"))])
    result = ProviderBoundary(provider).call(REQUEST, Output)

    assert result.data.probability == Decimal("0.62")
    assert result.trace.attempts == 1
    assert result.trace.prompt_version == "jury-v1"
    assert result.trace.cost_units == 1


def test_invalid_output_gets_one_repair_attempt() -> None:
    provider = FakeProvider(
        [ProviderReply({"probability": "bad"}), ProviderReply({"probability": "0.55"})]
    )
    result = ProviderBoundary(provider).call(REQUEST, Output)

    assert result.trace.attempts == 2
    assert provider.requests[1].repair is True


def test_timeout_call_cap_and_cost_cap_fail_closed() -> None:
    class SlowProvider:
        def complete(self, request: ProviderRequest) -> ProviderReply:
            time.sleep(0.05)
            return ProviderReply({"probability": "0.5"})

    with pytest.raises(ProviderUnavailable, match="timed out"):
        ProviderBoundary(SlowProvider(), timeout_seconds=0.001).call(REQUEST, Output)

    provider = FakeProvider([ProviderReply({"probability": "0.5"}, Decimal("2"))])
    boundary = ProviderBoundary(provider, max_calls=1, max_cost_units=Decimal("1"))
    with pytest.raises(ProviderUnavailable, match="cost cap"):
        boundary.call(REQUEST, Output)
    with pytest.raises(ProviderUnavailable, match="call cap"):
        boundary.call(REQUEST, Output)
