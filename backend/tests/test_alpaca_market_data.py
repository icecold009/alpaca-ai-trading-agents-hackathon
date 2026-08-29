from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from riskcourt.alpaca_market_data import AlpacaUnderlyingAdapter, MarketDataUnavailable


class FakeClient:
    def __init__(self, now: datetime) -> None:
        self.quote = SimpleNamespace(
            timestamp=now - timedelta(minutes=1),
            bid_price=640.10,
            ask_price=640.12,
            bid_size=4,
            ask_size=6,
        )
        self.bars = SimpleNamespace(
            data={
                "SPY": [
                    SimpleNamespace(
                        timestamp=now - timedelta(minutes=2),
                        open=640,
                        high=641,
                        low=639,
                        close=640.11,
                        volume=1000,
                    )
                ]
            }
        )

    def get_stock_latest_quote(self, request_params: object) -> dict[str, object]:
        return {"SPY": self.quote}

    def get_stock_bars(self, request_params: object) -> object:
        return self.bars


class MissingQuoteClient(FakeClient):
    def get_stock_latest_quote(self, request_params: object) -> dict[str, object]:
        return {}


def test_adapter_records_quote_bar_feed_and_timestamps() -> None:
    now = datetime(2026, 8, 29, 16, 0, tzinfo=UTC)
    state = AlpacaUnderlyingAdapter(FakeClient(now)).fetch(now=now)

    assert state.quote.symbol == "SPY"
    assert state.quote.feed == "iex"
    assert state.quote.bid == Decimal("640.1")
    assert state.quote.stale is False
    assert state.bars[0].close == Decimal("640.11")
    assert state.bars[0].feed == "iex"


def test_adapter_marks_old_quote_stale() -> None:
    now = datetime(2026, 8, 29, 16, 0, tzinfo=UTC)
    client = FakeClient(now)
    client.quote.timestamp = now - timedelta(minutes=6)

    assert AlpacaUnderlyingAdapter(client).fetch(now=now).quote.stale is True


def test_adapter_rejects_missing_quote() -> None:
    now = datetime(2026, 8, 29, 16, 0, tzinfo=UTC)
    with pytest.raises(MarketDataUnavailable, match="quote missing"):
        AlpacaUnderlyingAdapter(MissingQuoteClient(now)).fetch(now=now)


def test_adapter_rejects_missing_bars() -> None:
    now = datetime(2026, 8, 29, 16, 0, tzinfo=UTC)
    client = FakeClient(now)
    client.bars.data["SPY"] = []

    with pytest.raises(MarketDataUnavailable, match="bars missing"):
        AlpacaUnderlyingAdapter(client).fetch(now=now)
