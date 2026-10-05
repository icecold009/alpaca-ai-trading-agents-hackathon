"""Loopback-only fake paper API used by Playwright acceptance tests."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import uvicorn
from fastapi import APIRouter, HTTPException, Request
from pydantic import SecretStr

from riskcourt.alpaca_account import (
    AccountSnapshot,
    AlpacaAccountAdapter,
    MarketClockSnapshot,
    PaperAccountState,
    PendingOrderSnapshot,
    PositionSnapshot,
)
from riskcourt.alpaca_market_data import AlpacaUnderlyingAdapter
from riskcourt.alpaca_option_chain import AlpacaOptionChainAdapter, OptionChainState
from riskcourt.alpaca_order import AlpacaOrderAdapter
from riskcourt.app import create_app
from riskcourt.approval_guard import IdempotencyRegistry
from riskcourt.domain import OptionRight
from riskcourt.personal_store import PersonalStore
from riskcourt.settings import AiMode, RuntimeMode, Settings
from tests.fixtures.paper_fakes import (
    FakeTradingClient,
    build_fake_chain_contract,
    build_fake_market_state,
)


class FakePaperRuntime:
    def __init__(self) -> None:
        self.trading_client = FakeTradingClient(default_status="new")
        self.positions: tuple[PositionSnapshot, ...] = ()

    def reset(self) -> None:
        self.trading_client.calls = 0
        self.trading_client.submitted_requests.clear()
        self.trading_client.orders.clear()
        self.positions = ()

    def account_state(self) -> PaperAccountState:
        observed_at = datetime.now(UTC)
        return PaperAccountState(
            fetched_at=observed_at,
            account=AccountSnapshot(
                observed_at=observed_at,
                status="ACTIVE",
                equity=Decimal("100000"),
                last_equity=Decimal("100000"),
                options_buying_power=Decimal("50000"),
                options_approved_level=3,
                options_trading_level=3,
                trading_blocked=False,
                account_blocked=False,
                trade_suspended_by_user=False,
            ),
            clock=MarketClockSnapshot(
                timestamp=observed_at,
                is_open=True,
                next_open=observed_at + timedelta(hours=1),
                next_close=observed_at + timedelta(hours=6),
            ),
            positions=self.positions,
            pending_orders=tuple(
                PendingOrderSnapshot(
                    client_order_id=client_id,
                    symbol=None,
                    status=str(order.status),
                    order_class="mleg",
                    submitted_at=order.submitted_at,
                )
                for client_id, order in self.trading_client.orders.items()
                if str(order.status) not in {"filled", "rejected", "canceled", "expired"}
            ),
        )

    def market_close(self, on_date: date) -> datetime:
        return datetime.combine(
            on_date,
            time(16, 0),
            tzinfo=ZoneInfo("America/New_York"),
        ).astimezone(UTC)

    def chain(self, symbol: str, **kwargs: object) -> OptionChainState:
        now = datetime.now(UTC) - timedelta(seconds=1)
        today = now.date()
        expiration_from = kwargs.get("expiration_from", today)
        expiration_to = kwargs.get("expiration_to", today + timedelta(days=21))
        if not isinstance(expiration_from, date) or not isinstance(expiration_to, date):
            raise TypeError("fake option chain expects date bounds")
        expiry = expiration_from if expiration_from == expiration_to else today + timedelta(days=10)
        strikes = (Decimal("640"), Decimal("641"))
        contracts = tuple(
            build_fake_chain_contract(
                symbol=symbol,
                expiry=expiry,
                strike=strike,
                right=OptionRight.CALL,
                bid=bid,
                ask=ask,
                quoted_at=now,
                delta=delta,
            ).model_copy(update={"feed": "opra"})
            for strike, bid, ask, delta in (
                (strikes[0], Decimal("1.00"), Decimal("1.10"), Decimal("0.50")),
                (strikes[1], Decimal("0.80"), Decimal("0.90"), Decimal("0.45")),
            )
        )
        return OptionChainState(
            underlying_symbol=symbol,
            feed="opra",
            expiration_from=expiry,
            expiration_to=expiry,
            strike_from=strikes[0],
            strike_to=strikes[1],
            contracts=contracts,
        )

    def fill_latest_order(self) -> dict[str, object]:
        requests = self.trading_client.submitted_requests
        if not requests:
            raise HTTPException(status_code=409, detail="no fake order is available to fill")
        request = requests[-1]
        client_order_id = str(request.client_order_id)
        order = self.trading_client.orders[client_order_id]
        now = datetime.now(UTC)
        order.status = "filled"
        order.filled_qty = str(request.qty)
        order.filled_at = now
        order.updated_at = now

        if self.positions:
            order.filled_avg_price = "-0.15"
            self.positions = ()
            return {"status": "filled", "kind": "exit", "price": order.filled_avg_price}

        order.filled_avg_price = "0.30"
        raw_legs = request.legs or []
        self.positions = tuple(
            PositionSnapshot(
                symbol=str(leg.symbol),
                asset_class="us_option",
                quantity=Decimal(str(request.qty)),
                side=(
                    "long"
                    if "buy" in str(getattr(leg.position_intent, "value", leg.position_intent))
                    else "short"
                ),
                market_value=None,
                unrealized_pl=Decimal("0"),
            )
            for leg in raw_legs
        )
        return {"status": "filled", "kind": "entry", "price": order.filled_avg_price}


runtime = FakePaperRuntime()
state_dir = Path(os.environ.get("RISKCOURT_E2E_STATE_DIR", Path.cwd() / ".e2e-state"))
settings = Settings(
    riskcourt_mode=RuntimeMode.PAPER,
    riskcourt_state_dir=state_dir,
    riskcourt_option_feed="opra",
    riskcourt_ai_mode=AiMode.DETERMINISTIC,
    riskcourt_provider_spec=None,
    riskcourt_allowed_origins="http://127.0.0.1:5206",
    riskcourt_live_trading=False,
    alpaca_live_trading=False,
    alpaca_api_key_id=SecretStr("test-only-paper-key"),
    alpaca_api_secret_key=SecretStr("test-only-paper-secret"),
)


setattr(  # noqa: B010 - test server injects fake adapters without changing production code
    AlpacaAccountAdapter,
    "from_settings",
    classmethod(
        lambda _cls, _settings: SimpleNamespace(
            fetch=runtime.account_state,
            market_close=runtime.market_close,
        )
    ),
)
setattr(  # noqa: B010 - test server injects fake adapters without changing production code
    AlpacaUnderlyingAdapter,
    "from_settings",
    classmethod(
        lambda _cls, _settings: SimpleNamespace(
            fetch=lambda *, symbol, now: build_fake_market_state(symbol=symbol, observed_at=now)
        )
    ),
)
setattr(  # noqa: B010 - test server injects fake adapters without changing production code
    AlpacaOptionChainAdapter,
    "from_settings",
    classmethod(lambda _cls, _settings: SimpleNamespace(fetch=runtime.chain)),
)
setattr(  # noqa: B010 - test server injects fake adapters without changing production code
    AlpacaOrderAdapter,
    "from_settings",
    classmethod(
        lambda _cls, _settings: AlpacaOrderAdapter(
            runtime.trading_client,
            registry=IdempotencyRegistry(),
        )
    ),
)

app = create_app(settings)
test_router = APIRouter(prefix="/__test", tags=["test-only acceptance API"])


@test_router.post("/reset")
def reset_test_runtime(request: Request) -> dict[str, bool]:
    """Clear only the ephemeral test database and fake broker state."""

    store = request.app.state.personal_store
    database_path = store.path
    store.close()
    for suffix in ("", "-wal", "-shm"):
        Path(f"{database_path}{suffix}").unlink(missing_ok=True)
    request.app.state.personal_store = PersonalStore(database_path)
    request.app.state.personal_store.replace_watchlist(["SPY"])
    runtime.reset()
    return {"reset": True}


@test_router.post("/fill-latest-order")
def fill_latest_order() -> dict[str, object]:
    return runtime.fill_latest_order()


app.include_router(test_router)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
