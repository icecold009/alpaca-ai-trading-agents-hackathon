from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from alpaca.common.exceptions import APIError
from alpaca.trading.enums import PositionIntent
from alpaca.trading.requests import LimitOrderRequest

from riskcourt.alpaca_option_chain import ChainContract, OptionChainState
from riskcourt.alpaca_order import (
    AlpacaOrderAdapter,
    SubmissionOutcomeUnknown,
    SubmissionRejected,
    client_order_id_for_approval,
    request_fingerprint,
)
from riskcourt.domain import OptionRight
from riskcourt.spread_selector import SpreadCandidate, select_vertical_spreads

NOW = datetime(2026, 8, 30, 15, 0, tzinfo=UTC)


def candidate() -> SpreadCandidate:
    def c(strike: str) -> ChainContract:
        return ChainContract(
            occ_symbol=f"SPY260911C{int(Decimal(strike) * 1000):08d}",
            underlying_symbol="SPY",
            expiry=date(2026, 9, 11),
            strike=Decimal(strike),
            right=OptionRight.CALL,
            feed="indicative",
            quoted_at=NOW,
            bid=Decimal("1.00"),
            ask=Decimal("1.10"),
            implied_volatility=Decimal(".2"),
            delta=Decimal(".5"),
            gamma=Decimal(".1"),
            theta=Decimal("-.1"),
            vega=Decimal(".2"),
            missing_values=(),
            active=True,
            tradable=True,
        )

    state = OptionChainState(
        underlying_symbol="SPY",
        feed="indicative",
        expiration_from=date(2026, 9, 4),
        expiration_to=date(2026, 9, 18),
        strike_from=Decimal("630"),
        strike_to=Decimal("650"),
        contracts=(c("640"), c("641")),
    )
    return select_vertical_spreads(state, as_of=NOW)[0]


class FakeClient:
    def __init__(
        self,
        *,
        exc: Exception | None = None,
        accept_before_error: bool = False,
        lookup_exc: Exception | None = None,
    ) -> None:
        self.calls = 0
        self.lookup_calls = 0
        self.exc = exc
        self.accept_before_error = accept_before_error
        self.lookup_exc = lookup_exc
        self.orders: dict[str, object] = {}

    def submit_order(self, order_data: LimitOrderRequest) -> object:
        self.calls += 1
        client_order_id = str(order_data.client_order_id)
        response = SimpleNamespace(id="paper-order", client_order_id=client_order_id)
        if self.exc is not None and not self.accept_before_error:
            raise self.exc
        self.orders[client_order_id] = response
        if self.exc is not None:
            raise self.exc
        return response

    def get_order_by_client_id(self, client_id: str) -> object:
        self.lookup_calls += 1
        if self.lookup_exc is not None:
            raise self.lookup_exc
        order = self.orders.get(client_id)
        if order is not None:
            return order
        http_error = SimpleNamespace(response=SimpleNamespace(status_code=404))
        raise APIError("order not found", http_error)  # type: ignore[no-untyped-call]


def test_build_maps_one_contract_day_mleg_with_position_intents() -> None:
    request = AlpacaOrderAdapter.build_vertical_order(candidate(), client_order_id="riskcourt-001")
    fields = request.to_request_fields()

    assert fields["qty"] == 1
    assert fields["order_class"] == "mleg"
    assert fields["time_in_force"] == "day"
    assert fields["limit_price"] == pytest.approx(0.1)
    assert [leg["position_intent"] for leg in fields["legs"]] == [
        PositionIntent.BUY_TO_OPEN.value,
        PositionIntent.SELL_TO_OPEN.value,
    ]


def test_rejects_unsafe_price_and_requires_approval() -> None:
    with pytest.raises(ValueError, match="no greater"):
        AlpacaOrderAdapter.build_vertical_order(
            candidate(), client_order_id="riskcourt-001", limit_price=Decimal("2")
        )
    adapter = AlpacaOrderAdapter(FakeClient())
    request = adapter.build_vertical_order(candidate(), client_order_id="riskcourt-001")
    with pytest.raises(PermissionError, match="explicit approval"):
        adapter.submit(request)


def test_approval_order_identity_is_stable_bounded_and_request_bound() -> None:
    first_id = client_order_id_for_approval("approval_123")
    second_id = client_order_id_for_approval("approval_123")
    default_request = AlpacaOrderAdapter.build_vertical_order(
        candidate(), client_order_id=first_id
    )
    changed_request = AlpacaOrderAdapter.build_vertical_order(
        candidate(), client_order_id=first_id, limit_price=Decimal("0.20")
    )

    assert first_id == second_id
    assert len(first_id) <= 48
    assert request_fingerprint(default_request) == request_fingerprint(default_request)
    assert request_fingerprint(default_request) != request_fingerprint(changed_request)


def test_duplicate_request_is_replayed_without_second_submission() -> None:
    client = FakeClient()
    adapter = AlpacaOrderAdapter(client)
    request = adapter.build_vertical_order(candidate(), client_order_id="riskcourt-001")

    first = adapter.submit(request, approved=True)
    second = adapter.submit(request, approved=True)

    assert first.action.value == "submit"
    assert second.action.value == "replay"
    assert second.response is first.response
    assert client.calls == 1


def test_accepted_then_timeout_is_recovered_by_stable_client_id() -> None:
    client = FakeClient(exc=TimeoutError("response lost"), accept_before_error=True)
    adapter = AlpacaOrderAdapter(client)
    request = adapter.build_vertical_order(candidate(), client_order_id="riskcourt-accepted-001")

    result = adapter.submit(request, approved=True)

    assert result.action.value == "replay"
    assert result.response is client.orders["riskcourt-accepted-001"]
    assert client.calls == 1
    assert client.lookup_calls == 1


def test_transport_timeout_without_lookup_confirmation_stays_unknown() -> None:
    client = FakeClient(
        exc=TimeoutError("response lost"),
        lookup_exc=TimeoutError("lookup unavailable"),
    )
    adapter = AlpacaOrderAdapter(client)
    request = adapter.build_vertical_order(candidate(), client_order_id="riskcourt-unknown-001")

    with pytest.raises(SubmissionOutcomeUnknown, match="outcome remains unknown"):
        adapter.submit(request, approved=True)
    assert client.calls == 1


def test_confirmed_client_id_not_found_is_the_only_empty_lookup_result() -> None:
    client = FakeClient()
    adapter = AlpacaOrderAdapter(client)

    assert adapter.lookup_order_by_client_id("riskcourt-missing-001") is None


def test_definitive_api_rejection_is_distinct_from_unknown_transport() -> None:
    error = APIError(  # type: ignore[no-untyped-call]
        "forbidden", SimpleNamespace(response=SimpleNamespace(status_code=403))
    )
    client = FakeClient(exc=error)
    adapter = AlpacaOrderAdapter(client)
    request = adapter.build_vertical_order(candidate(), client_order_id="riskcourt-rejected-001")

    with pytest.raises(SubmissionRejected, match="Alpaca rejected"):
        adapter.submit(request, approved=True)
    assert client.calls == 1
    assert client.lookup_calls == 1


def test_exit_maps_close_intents_to_a_credit_order() -> None:
    request = AlpacaOrderAdapter.build_vertical_exit_order(
        candidate(), client_order_id="riskcourt-exit-001", credit_price=Decimal("0.50")
    )
    fields = request.to_request_fields()

    assert fields["limit_price"] == pytest.approx(-0.5)
    assert [leg["position_intent"] for leg in fields["legs"]] == [
        "sell_to_close",
        "buy_to_close",
    ]
