"""Read-only Alpaca option-chain adapter with explicit missing-data provenance."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol, cast

from alpaca.common.exceptions import APIError
from alpaca.data.enums import OptionsFeed
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import OptionChainRequest
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetStatus
from alpaca.trading.requests import GetOptionContractsRequest
from pydantic import AwareDatetime

from riskcourt.domain import OCC_PATTERN, ContractModel, OccSymbol, OptionRight, Ticker
from riskcourt.settings import RuntimeMode, Settings


class OptionChainUnavailable(RuntimeError):
    """Raised when Alpaca returns no usable option-chain data."""


class ChainContract(ContractModel):
    occ_symbol: OccSymbol
    underlying_symbol: Ticker
    expiry: date
    strike: Decimal
    right: OptionRight
    feed: str
    quoted_at: AwareDatetime | None
    bid: Decimal | None
    ask: Decimal | None
    implied_volatility: Decimal | None
    delta: Decimal | None
    gamma: Decimal | None
    theta: Decimal | None
    vega: Decimal | None
    missing_values: tuple[str, ...]
    active: bool | None = None
    tradable: bool | None = None


class OptionChainState(ContractModel):
    underlying_symbol: Ticker
    feed: str
    expiration_from: date
    expiration_to: date
    strike_from: Decimal
    strike_to: Decimal
    contracts: tuple[ChainContract, ...]

    def sanitized_summary(self) -> dict[str, object]:
        missing_quotes = sum("quote" in item.missing_values for item in self.contracts)
        missing_greeks = sum("greeks" in item.missing_values for item in self.contracts)
        missing_eligibility = sum(
            "contract_eligibility" in item.missing_values for item in self.contracts
        )
        return {
            "underlying_symbol": self.underlying_symbol,
            "feed": self.feed,
            "expiration_from": self.expiration_from.isoformat(),
            "expiration_to": self.expiration_to.isoformat(),
            "strike_from": str(self.strike_from),
            "strike_to": str(self.strike_to),
            "contract_count": len(self.contracts),
            "missing_quote_count": missing_quotes,
            "missing_greeks_count": missing_greeks,
            "missing_eligibility_count": missing_eligibility,
        }


class OptionReadClient(Protocol):
    def get_option_chain(self, request_params: OptionChainRequest) -> Any: ...


class OptionContractReadClient(Protocol):
    def get_option_contracts(self, request: GetOptionContractsRequest) -> Any: ...


class AlpacaOptionChainAdapter:
    def __init__(
        self,
        client: OptionReadClient,
        feed: OptionsFeed = OptionsFeed.INDICATIVE,
        contract_client: OptionContractReadClient | None = None,
    ) -> None:
        self._client = client
        self._feed = feed
        self._contract_client = contract_client

    @classmethod
    def from_settings(cls, settings: Settings) -> AlpacaOptionChainAdapter:
        if settings.riskcourt_mode is not RuntimeMode.PAPER:
            raise ValueError("Alpaca option-chain reads require paper mode")
        assert settings.alpaca_api_key_id is not None
        assert settings.alpaca_api_secret_key is not None
        client = OptionHistoricalDataClient(
            api_key=settings.alpaca_api_key_id.get_secret_value(),
            secret_key=settings.alpaca_api_secret_key.get_secret_value(),
        )
        contract_client = TradingClient(
            api_key=settings.alpaca_api_key_id.get_secret_value(),
            secret_key=settings.alpaca_api_secret_key.get_secret_value(),
            paper=True,
            url_override=str(settings.alpaca_paper_base_url).rstrip("/"),
        )
        return cls(
            cast(OptionReadClient, client),
            feed=OptionsFeed(settings.riskcourt_option_feed),
            contract_client=cast(OptionContractReadClient, contract_client),
        )

    def fetch(
        self,
        underlying_symbol: str,
        *,
        expiration_from: date,
        expiration_to: date,
        strike_from: Decimal,
        strike_to: Decimal,
    ) -> OptionChainState:
        if expiration_to < expiration_from:
            raise ValueError("expiration_to must not precede expiration_from")
        if strike_to < strike_from:
            raise ValueError("strike_to must not be below strike_from")
        try:
            response = self._client.get_option_chain(
                OptionChainRequest(
                    underlying_symbol=underlying_symbol,
                    feed=self._feed,
                    expiration_date_gte=expiration_from,
                    expiration_date_lte=expiration_to,
                    strike_price_gte=float(strike_from),
                    strike_price_lte=float(strike_to),
                )
            )
        except APIError as error:
            message = "Alpaca option chain rate limited" if error.status_code == 429 else (
                "Alpaca option chain request failed"
            )
            raise OptionChainUnavailable(message) from error
        if not isinstance(response, dict) or not response:
            raise OptionChainUnavailable(f"option chain empty for {underlying_symbol}")

        metadata = self._fetch_contract_metadata(
            underlying_symbol,
            expiration_from=expiration_from,
            expiration_to=expiration_to,
            strike_from=strike_from,
            strike_to=strike_to,
        )

        contracts = tuple(
            sorted(
                (
                    _translate(
                        symbol,
                        snapshot,
                        underlying_symbol,
                        self._feed,
                        metadata.get(symbol),
                    )
                    for symbol, snapshot in response.items()
                ),
                key=lambda item: (item.expiry, item.strike, item.right.value, item.occ_symbol),
            )
        )
        return OptionChainState(
            underlying_symbol=underlying_symbol,
            feed=self._feed.value,
            expiration_from=expiration_from,
            expiration_to=expiration_to,
            strike_from=strike_from,
            strike_to=strike_to,
            contracts=contracts,
        )

    def _fetch_contract_metadata(
        self,
        underlying_symbol: str,
        *,
        expiration_from: date,
        expiration_to: date,
        strike_from: Decimal,
        strike_to: Decimal,
    ) -> dict[str, tuple[bool, bool | None]]:
        if self._contract_client is None:
            return {}
        result: dict[str, tuple[bool, bool | None]] = {}
        page_token: str | None = None
        page_count = 0
        while True:
            try:
                response = self._contract_client.get_option_contracts(
                    GetOptionContractsRequest(
                        underlying_symbols=[underlying_symbol],
                        status=AssetStatus.ACTIVE,
                        expiration_date_gte=expiration_from,
                        expiration_date_lte=expiration_to,
                        strike_price_gte=str(strike_from),
                        strike_price_lte=str(strike_to),
                        limit=10_000,
                        page_token=page_token,
                    )
                )
            except Exception as error:
                raise OptionChainUnavailable("option contract eligibility unavailable") from error
            contracts = getattr(response, "option_contracts", None)
            if not isinstance(contracts, list):
                raise OptionChainUnavailable("option contract metadata response is invalid")
            for contract in contracts:
                symbol = getattr(contract, "symbol", None)
                if not isinstance(symbol, str):
                    raise OptionChainUnavailable("option contract metadata omitted a symbol")
                status_value = getattr(contract, "status", None)
                status_text = str(getattr(status_value, "value", status_value)).lower()
                tradable_value = getattr(contract, "tradable", None)
                tradable = tradable_value if isinstance(tradable_value, bool) else None
                result[symbol] = (status_text == AssetStatus.ACTIVE.value, tradable)
            page_token = getattr(response, "next_page_token", None)
            page_count += 1
            if not page_token:
                return result
            if not isinstance(page_token, str) or page_count >= 5:
                raise OptionChainUnavailable(
                    "option contract metadata exceeded the bounded page limit"
                )


def _translate(
    symbol: str,
    snapshot: object,
    underlying: str,
    feed: OptionsFeed,
    eligibility: tuple[bool, bool | None] | None = None,
) -> ChainContract:
    match = OCC_PATTERN.fullmatch(symbol)
    if match is None or match.group("root") != underlying:
        raise OptionChainUnavailable(f"invalid option symbol returned for {underlying}")
    quote = getattr(snapshot, "latest_quote", None)
    greeks = getattr(snapshot, "greeks", None)
    iv = getattr(snapshot, "implied_volatility", None)
    missing: list[str] = []
    if quote is None:
        missing.append("quote")
    if iv is None:
        missing.append("implied_volatility")
    if greeks is None:
        missing.append("greeks")
    active, tradable = eligibility if eligibility is not None else (None, None)
    if active is None or tradable is None:
        missing.append("contract_eligibility")
    return ChainContract(
        occ_symbol=symbol,
        underlying_symbol=underlying,
        expiry=datetime.strptime(match.group("expiry"), "%y%m%d").date(),
        strike=Decimal(match.group("strike")) / Decimal("1000"),
        right=OptionRight.CALL if match.group("right") == "C" else OptionRight.PUT,
        feed=feed.value,
        quoted_at=_optional_time(quote),
        bid=_optional_decimal(quote, "bid_price"),
        ask=_optional_decimal(quote, "ask_price"),
        implied_volatility=None if iv is None else Decimal(str(iv)),
        delta=_optional_decimal(greeks, "delta"),
        gamma=_optional_decimal(greeks, "gamma"),
        theta=_optional_decimal(greeks, "theta"),
        vega=_optional_decimal(greeks, "vega"),
        missing_values=tuple(missing),
        active=active,
        tradable=tradable,
    )


def _optional_decimal(source: object | None, field: str) -> Decimal | None:
    if source is None:
        return None
    value = getattr(source, field, None)
    return None if value is None else Decimal(str(value))


def _optional_time(source: object | None) -> datetime | None:
    if source is None:
        return None
    value = getattr(source, "timestamp", None)
    if not isinstance(value, datetime) or value.tzinfo is None:
        return None
    return value
