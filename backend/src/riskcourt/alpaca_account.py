"""Read-only, paper-only Alpaca account state adapter."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Protocol, cast

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest
from pydantic import AwareDatetime, Field

from riskcourt.domain import ContractModel
from riskcourt.settings import RuntimeMode, Settings


class AccountSnapshot(ContractModel):
    """Account fields needed by the options risk and eligibility gates."""

    observed_at: AwareDatetime
    status: str
    equity: Decimal | None
    options_buying_power: Decimal | None
    options_approved_level: int | None = Field(default=None, ge=0, le=3)
    options_trading_level: int | None = Field(default=None, ge=0, le=3)
    trading_blocked: bool
    account_blocked: bool
    trade_suspended_by_user: bool


class MarketClockSnapshot(ContractModel):
    timestamp: AwareDatetime
    is_open: bool
    next_open: AwareDatetime
    next_close: AwareDatetime


class PositionSnapshot(ContractModel):
    symbol: str
    asset_class: str
    quantity: Decimal
    side: str
    market_value: Decimal | None
    unrealized_pl: Decimal | None


class PendingOrderSnapshot(ContractModel):
    client_order_id: str
    symbol: str | None
    status: str
    order_class: str
    submitted_at: AwareDatetime


class PaperAccountState(ContractModel):
    """One internally complete but externally sanitizable paper-account read."""

    fetched_at: AwareDatetime
    account: AccountSnapshot
    clock: MarketClockSnapshot
    positions: tuple[PositionSnapshot, ...]
    pending_orders: tuple[PendingOrderSnapshot, ...]

    def sanitized_summary(self) -> dict[str, object]:
        """Return proof fields without credentials, account ID, balances, or order IDs."""

        return {
            "paper": True,
            "account_status": self.account.status,
            "equity_present": self.account.equity is not None,
            "options_buying_power_present": self.account.options_buying_power is not None,
            "options_approved_level": self.account.options_approved_level,
            "options_trading_level": self.account.options_trading_level,
            "trading_blocked": self.account.trading_blocked,
            "market_open": self.clock.is_open,
            "clock_timestamp": self.clock.timestamp.isoformat(),
            "position_count": len(self.positions),
            "pending_order_count": len(self.pending_orders),
        }


class TradingReadClient(Protocol):
    def get_account(self) -> Any: ...

    def get_clock(self) -> Any: ...

    def get_all_positions(self) -> Any: ...

    def get_orders(self, filter: GetOrdersRequest | None = None) -> Any: ...


class AlpacaAccountAdapter:
    """Translate Alpaca SDK objects into stable RiskCourt contracts."""

    def __init__(self, client: TradingReadClient) -> None:
        self._client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> AlpacaAccountAdapter:
        if settings.riskcourt_mode is not RuntimeMode.PAPER:
            raise ValueError("Alpaca account reads require paper mode")
        assert settings.alpaca_api_key_id is not None
        assert settings.alpaca_api_secret_key is not None
        client = TradingClient(
            api_key=settings.alpaca_api_key_id.get_secret_value(),
            secret_key=settings.alpaca_api_secret_key.get_secret_value(),
            paper=True,
            url_override=str(settings.alpaca_paper_base_url).rstrip("/"),
        )
        return cls(cast(TradingReadClient, client))

    def fetch(self) -> PaperAccountState:
        account = self._client.get_account()
        clock = self._client.get_clock()
        positions = self._client.get_all_positions()
        orders = self._client.get_orders(
            filter=GetOrdersRequest(status=QueryOrderStatus.OPEN, nested=True)
        )

        if not isinstance(positions, list) or not isinstance(orders, list):
            raise TypeError("Alpaca read client must return typed position and order lists")

        return PaperAccountState(
            fetched_at=_aware_datetime(clock, "timestamp"),
            account=AccountSnapshot(
                observed_at=_aware_datetime(clock, "timestamp"),
                status=_text(account, "status"),
                equity=_optional_decimal(account, "equity"),
                options_buying_power=_optional_decimal(account, "options_buying_power"),
                options_approved_level=getattr(account, "options_approved_level", None),
                options_trading_level=getattr(account, "options_trading_level", None),
                trading_blocked=bool(getattr(account, "trading_blocked", False)),
                account_blocked=bool(getattr(account, "account_blocked", False)),
                trade_suspended_by_user=bool(
                    getattr(account, "trade_suspended_by_user", False)
                ),
            ),
            clock=MarketClockSnapshot(
                timestamp=_aware_datetime(clock, "timestamp"),
                is_open=bool(clock.is_open),
                next_open=_aware_datetime(clock, "next_open"),
                next_close=_aware_datetime(clock, "next_close"),
            ),
            positions=tuple(
                PositionSnapshot(
                    symbol=_text(position, "symbol"),
                    asset_class=_text(position, "asset_class"),
                    quantity=_decimal(position, "qty"),
                    side=_text(position, "side"),
                    market_value=_optional_decimal(position, "market_value"),
                    unrealized_pl=_optional_decimal(position, "unrealized_pl"),
                )
                for position in positions
            ),
            pending_orders=tuple(
                PendingOrderSnapshot(
                    client_order_id=_text(order, "client_order_id"),
                    symbol=getattr(order, "symbol", None),
                    status=_text(order, "status"),
                    order_class=_text(order, "order_class"),
                    submitted_at=_aware_datetime(order, "submitted_at"),
                )
                for order in orders
            ),
        )


def _text(source: object, field: str) -> str:
    value = getattr(source, field)
    if isinstance(value, Enum):
        value = value.value
    text = str(value).strip()
    if not text:
        raise ValueError(f"Alpaca response field {field} is empty")
    return text


def _decimal(source: object, field: str) -> Decimal:
    return Decimal(_text(source, field))


def _optional_decimal(source: object, field: str) -> Decimal | None:
    value = getattr(source, field, None)
    return None if value is None else Decimal(str(value))


def _aware_datetime(source: object, field: str) -> datetime:
    value = getattr(source, field)
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"Alpaca response field {field} must be timezone-aware")
    return value
