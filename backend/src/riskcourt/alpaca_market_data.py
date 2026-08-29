"""Read-only Alpaca underlying quote and bar adapter with provenance."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol, cast

from alpaca.common.enums import Sort
from alpaca.common.exceptions import APIError
from alpaca.data.enums import DataFeed
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame
from pydantic import AwareDatetime, Field

from riskcourt.domain import ContractModel, NonNegativeMoney, PositiveMoney, Ticker
from riskcourt.settings import RuntimeMode, Settings


class MarketDataUnavailable(RuntimeError):
    """A safe, credential-free market-data failure."""


class UnderlyingQuote(ContractModel):
    symbol: Ticker
    feed: str
    quoted_at: AwareDatetime
    bid: NonNegativeMoney
    ask: PositiveMoney
    bid_size: Decimal = Field(ge=0)
    ask_size: Decimal = Field(ge=0)
    stale: bool


class UnderlyingBar(ContractModel):
    symbol: Ticker
    feed: str
    started_at: AwareDatetime
    open: PositiveMoney
    high: PositiveMoney
    low: PositiveMoney
    close: PositiveMoney
    volume: Decimal = Field(ge=0)


class UnderlyingMarketState(ContractModel):
    fetched_at: AwareDatetime
    quote: UnderlyingQuote
    bars: tuple[UnderlyingBar, ...]

    def sanitized_summary(self) -> dict[str, object]:
        return {
            "symbol": self.quote.symbol,
            "feed": self.quote.feed,
            "quote_timestamp": self.quote.quoted_at.isoformat(),
            "quote_stale": self.quote.stale,
            "bar_count": len(self.bars),
            "latest_bar_timestamp": (
                self.bars[-1].started_at.isoformat() if self.bars else None
            ),
        }


class StockReadClient(Protocol):
    def get_stock_latest_quote(self, request_params: StockLatestQuoteRequest) -> Any: ...

    def get_stock_bars(self, request_params: StockBarsRequest) -> Any: ...


class AlpacaUnderlyingAdapter:
    def __init__(self, client: StockReadClient, feed: DataFeed = DataFeed.IEX) -> None:
        self._client = client
        self._feed = feed

    @classmethod
    def from_settings(cls, settings: Settings) -> AlpacaUnderlyingAdapter:
        if settings.riskcourt_mode is not RuntimeMode.PAPER:
            raise ValueError("Alpaca market-data reads require paper mode")
        assert settings.alpaca_api_key_id is not None
        assert settings.alpaca_api_secret_key is not None
        client = StockHistoricalDataClient(
            api_key=settings.alpaca_api_key_id.get_secret_value(),
            secret_key=settings.alpaca_api_secret_key.get_secret_value(),
        )
        return cls(cast(StockReadClient, client))

    def fetch(
        self,
        symbol: str = "SPY",
        *,
        now: datetime | None = None,
        maximum_quote_age: timedelta = timedelta(minutes=5),
        bar_limit: int = 20,
    ) -> UnderlyingMarketState:
        fetched_at = now or datetime.now(UTC)
        try:
            quote_response = self._client.get_stock_latest_quote(
                StockLatestQuoteRequest(symbol_or_symbols=symbol, feed=self._feed)
            )
            bar_response = self._client.get_stock_bars(
                StockBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=TimeFrame.Minute,
                    start=fetched_at - timedelta(days=7),
                    end=fetched_at,
                    limit=bar_limit,
                    feed=self._feed,
                    sort=Sort.DESC,
                )
            )
        except APIError as error:
            if error.status_code == 429:
                raise MarketDataUnavailable("Alpaca market data rate limited") from error
            raise MarketDataUnavailable("Alpaca market data request failed") from error

        if not isinstance(quote_response, dict) or symbol not in quote_response:
            raise MarketDataUnavailable(f"latest quote missing for {symbol}")
        quote = quote_response[symbol]
        quote_time = _aware_datetime(quote, "timestamp")
        if fetched_at.tzinfo is None:
            raise ValueError("now must be timezone-aware")

        raw_bars = getattr(bar_response, "data", {}).get(symbol, [])
        if not raw_bars:
            raise MarketDataUnavailable(f"bars missing for {symbol}")
        ordered_bars = sorted(raw_bars, key=lambda bar: _aware_datetime(bar, "timestamp"))

        return UnderlyingMarketState(
            fetched_at=fetched_at,
            quote=UnderlyingQuote(
                symbol=symbol,
                feed=self._feed.value,
                quoted_at=quote_time,
                bid=_decimal(quote, "bid_price"),
                ask=_decimal(quote, "ask_price"),
                bid_size=_decimal(quote, "bid_size"),
                ask_size=_decimal(quote, "ask_size"),
                stale=fetched_at - quote_time > maximum_quote_age,
            ),
            bars=tuple(
                UnderlyingBar(
                    symbol=symbol,
                    feed=self._feed.value,
                    started_at=_aware_datetime(bar, "timestamp"),
                    open=_decimal(bar, "open"),
                    high=_decimal(bar, "high"),
                    low=_decimal(bar, "low"),
                    close=_decimal(bar, "close"),
                    volume=_decimal(bar, "volume"),
                )
                for bar in ordered_bars
            ),
        )


def _decimal(source: object, field: str) -> Decimal:
    return Decimal(str(getattr(source, field)))


def _aware_datetime(source: object, field: str) -> datetime:
    value = getattr(source, field)
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"Alpaca response field {field} must be timezone-aware")
    return value
