"""Deterministic fakes, constants, and dependency builders for characterization tests.

All components in this module are completely offline, sealed, and deterministic.
They generate reproducible IDs, timestamps, quotes, accounts, and order responses
without performing any network calls or live trading.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

from alpaca.trading.requests import LimitOrderRequest
from pydantic import JsonValue

from riskcourt.alpaca_account import (
    AccountSnapshot,
    AlpacaAccountAdapter,
    MarketClockSnapshot,
    PaperAccountState,
    PendingOrderSnapshot,
    PositionSnapshot,
)
from riskcourt.alpaca_market_data import (
    AlpacaUnderlyingAdapter,
    UnderlyingMarketState,
    UnderlyingQuote,
)
from riskcourt.alpaca_option_chain import (
    AlpacaOptionChainAdapter,
    ChainContract,
    OptionChainState,
)
from riskcourt.alpaca_order import AlpacaOrderAdapter
from riskcourt.approval_guard import IdempotencyRegistry
from riskcourt.domain import (
    OptionRight,
)
from riskcourt.event_store import AppendOnlyDecisionLog
from riskcourt.jurors import DeterministicJurorStub
from riskcourt.model_provider import (
    ProviderBoundary,
    ProviderReply,
    ProviderRequest,
    ProviderUnavailable,
)
from riskcourt.paper_loop import PaperCycleDependencies, PaperCycleResult
from riskcourt.risk_limits import PortfolioRiskSnapshot, RiskStateStore

FIXED_NOW: datetime = datetime(2026, 8, 30, 15, 0, 0, tzinfo=UTC)
FIXED_CASE_ID: str = "case_characterization_001"
FIXED_SYMBOL: str = "SPY"
FIXED_EXPIRY: date = date(2026, 9, 11)
FIXED_POLICY_VERSION: str = "risk-v1"
FIXED_MINIMUM_EDGE: Decimal = Decimal("0.08")

FIXED_UNDERLYING_BID: Decimal = Decimal("640.00")
FIXED_UNDERLYING_ASK: Decimal = Decimal("640.01")

FIXED_CALL_LONG_STRIKE: Decimal = Decimal("640.00")
FIXED_CALL_LONG_BID: Decimal = Decimal("1.00")
FIXED_CALL_LONG_ASK: Decimal = Decimal("1.10")

FIXED_CALL_SHORT_STRIKE: Decimal = Decimal("641.00")
FIXED_CALL_SHORT_BID: Decimal = Decimal("0.80")
FIXED_CALL_SHORT_ASK: Decimal = Decimal("0.90")

FIXED_PUT_LONG_STRIKE: Decimal = Decimal("641.00")
FIXED_PUT_LONG_BID: Decimal = Decimal("1.00")
FIXED_PUT_LONG_ASK: Decimal = Decimal("1.10")

FIXED_PUT_SHORT_STRIKE: Decimal = Decimal("640.00")
FIXED_PUT_SHORT_BID: Decimal = Decimal("0.80")
FIXED_PUT_SHORT_ASK: Decimal = Decimal("0.90")


def build_fake_account_state(
    *,
    observed_at: datetime = FIXED_NOW,
    market_open: bool = True,
    equity: Decimal = Decimal("100000.00"),
    options_buying_power: Decimal = Decimal("50000.00"),
    trading_level: int = 3,
    approved_level: int = 3,
    trading_blocked: bool = False,
    account_blocked: bool = False,
    trade_suspended_by_user: bool = False,
    positions: tuple[PositionSnapshot, ...] = (),
    pending_orders: tuple[PendingOrderSnapshot, ...] = (),
) -> PaperAccountState:
    """Build a deterministic paper account state for testing."""
    return PaperAccountState(
        fetched_at=observed_at,
        account=AccountSnapshot(
            observed_at=observed_at,
            status="ACTIVE",
            equity=equity,
            options_buying_power=options_buying_power,
            options_approved_level=approved_level,
            options_trading_level=trading_level,
            trading_blocked=trading_blocked,
            account_blocked=account_blocked,
            trade_suspended_by_user=trade_suspended_by_user,
        ),
        clock=MarketClockSnapshot(
            timestamp=observed_at,
            is_open=market_open,
            next_open=observed_at + timedelta(hours=1),
            next_close=observed_at + timedelta(hours=6),
        ),
        positions=positions,
        pending_orders=pending_orders,
    )


def build_fake_market_state(
    *,
    symbol: str = FIXED_SYMBOL,
    observed_at: datetime = FIXED_NOW,
    bid: Decimal = FIXED_UNDERLYING_BID,
    ask: Decimal = FIXED_UNDERLYING_ASK,
    stale: bool = False,
) -> UnderlyingMarketState:
    """Build a deterministic underlying market quote state."""
    return UnderlyingMarketState(
        fetched_at=observed_at,
        quote=UnderlyingQuote(
            symbol=symbol,
            feed="iex",
            quoted_at=observed_at,
            bid=bid,
            ask=ask,
            bid_size=Decimal("100"),
            ask_size=Decimal("100"),
            stale=stale,
        ),
        bars=(),
    )


def build_fake_chain_contract(
    *,
    symbol: str = FIXED_SYMBOL,
    expiry: date = FIXED_EXPIRY,
    strike: Decimal = FIXED_CALL_LONG_STRIKE,
    right: OptionRight = OptionRight.CALL,
    bid: Decimal = FIXED_CALL_LONG_BID,
    ask: Decimal = FIXED_CALL_LONG_ASK,
    quoted_at: datetime = FIXED_NOW,
    delta: Decimal = Decimal("0.50"),
) -> ChainContract:
    """Build a single deterministic chain contract."""
    right_code = "C" if right is OptionRight.CALL else "P"
    strike_int = int(strike * 1000)
    expiry_str = expiry.strftime("%y%m%d")
    occ = f"{symbol}{expiry_str}{right_code}{strike_int:08d}"
    return ChainContract(
        occ_symbol=occ,
        underlying_symbol=symbol,
        expiry=expiry,
        strike=strike,
        right=right,
        feed="indicative",
        quoted_at=quoted_at,
        bid=bid,
        ask=ask,
        implied_volatility=Decimal("0.20"),
        delta=delta,
        gamma=Decimal("0.10"),
        theta=Decimal("-0.10"),
        vega=Decimal("0.20"),
        missing_values=(),
    )


def build_fake_option_chain_state(
    *,
    symbol: str = FIXED_SYMBOL,
    contracts: tuple[ChainContract, ...] | None = None,
    expiry_from: date | None = None,
    expiry_to: date | None = None,
    strike_from: Decimal = Decimal("630.00"),
    strike_to: Decimal = Decimal("650.00"),
) -> OptionChainState:
    """Build an option chain state populated with deterministic contracts."""
    if contracts is None:
        contracts = (
            build_fake_chain_contract(
                strike=FIXED_CALL_LONG_STRIKE,
                right=OptionRight.CALL,
                bid=FIXED_CALL_LONG_BID,
                ask=FIXED_CALL_LONG_ASK,
                delta=Decimal("0.50"),
            ),
            build_fake_chain_contract(
                strike=FIXED_CALL_SHORT_STRIKE,
                right=OptionRight.CALL,
                bid=FIXED_CALL_SHORT_BID,
                ask=FIXED_CALL_SHORT_ASK,
                delta=Decimal("0.45"),
            ),
        )
    return OptionChainState(
        underlying_symbol=symbol,
        feed="indicative",
        expiration_from=expiry_from or FIXED_NOW.date(),
        expiration_to=expiry_to or (FIXED_NOW.date() + timedelta(days=21)),
        strike_from=strike_from,
        strike_to=strike_to,
        contracts=contracts,
    )


def build_fake_put_chain_state(
    *,
    symbol: str = FIXED_SYMBOL,
) -> OptionChainState:
    """Build an option chain state with deterministic put contracts."""
    contracts = (
        build_fake_chain_contract(
            strike=FIXED_PUT_LONG_STRIKE,
            right=OptionRight.PUT,
            bid=FIXED_PUT_LONG_BID,
            ask=FIXED_PUT_LONG_ASK,
            delta=Decimal("-0.50"),
        ),
        build_fake_chain_contract(
            strike=FIXED_PUT_SHORT_STRIKE,
            right=OptionRight.PUT,
            bid=FIXED_PUT_SHORT_BID,
            ask=FIXED_PUT_SHORT_ASK,
            delta=Decimal("-0.45"),
        ),
    )
    return build_fake_option_chain_state(symbol=symbol, contracts=contracts)


def build_fake_risk_state(
    *,
    equity: Decimal = Decimal("100000.00"),
    open_risk: Decimal = Decimal("0.00"),
    open_positions: int = 0,
    pending_orders: int = 0,
    daily_pnl: Decimal = Decimal("0.00"),
    kill_switch_enabled: bool = False,
) -> RiskStateStore:
    """Build a deterministic portfolio risk store."""
    return RiskStateStore(
        PortfolioRiskSnapshot(
            account_equity=equity,
            open_options_risk=open_risk,
            open_option_positions=open_positions,
            pending_option_orders=pending_orders,
            daily_pnl=daily_pnl,
            kill_switch_enabled=kill_switch_enabled,
            revision=0,
        )
    )


def build_fake_order_response(
    *,
    client_order_id: str,
    status: str = "new",
    submitted_at: datetime = FIXED_NOW,
    updated_at: datetime = FIXED_NOW,
    filled_qty: str = "0",
    filled_avg_price: str | None = None,
    filled_at: datetime | None = None,
    replaced_by: str | None = None,
) -> SimpleNamespace:
    """Build a fake Alpaca Order response payload."""
    return SimpleNamespace(
        client_order_id=client_order_id,
        status=status,
        submitted_at=submitted_at,
        updated_at=updated_at,
        filled_qty=filled_qty,
        filled_avg_price=filled_avg_price,
        filled_at=filled_at,
        replaced_by=replaced_by,
    )


class FakeAccountAdapter:
    """Deterministic fake account adapter."""

    def __init__(self, state: PaperAccountState) -> None:
        self.state = state
        self.calls: int = 0

    def fetch(self) -> PaperAccountState:
        self.calls += 1
        return self.state


class FakeMarketAdapter:
    """Deterministic fake underlying market adapter."""

    def __init__(
        self,
        state: UnderlyingMarketState | None = None,
        *,
        exc: Exception | None = None,
    ) -> None:
        self.state = state or build_fake_market_state()
        self.exc = exc
        self.calls: int = 0

    def fetch(self, *, symbol: str, now: datetime) -> UnderlyingMarketState:
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return self.state


class FakeOptionChainAdapter:
    """Deterministic fake option chain adapter."""

    def __init__(
        self,
        state: OptionChainState | None = None,
        *,
        exc: Exception | None = None,
    ) -> None:
        self.state = state or build_fake_option_chain_state()
        self.exc = exc
        self.calls: int = 0

    def fetch(self, underlying_symbol: str, **_: object) -> OptionChainState:
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return self.state


class FakeTradingClient:
    """Zero-network fake trading client with exact call and submission tracking."""

    def __init__(
        self,
        *,
        default_status: str = "new",
        responses: list[Any] | None = None,
        exc: Exception | None = None,
    ) -> None:
        self.calls: int = 0
        self.default_status = default_status
        self.responses = list(responses) if responses else []
        self.exc = exc
        self.submitted_requests: list[LimitOrderRequest] = []

    def submit_order(self, order_data: LimitOrderRequest) -> Any:
        self.calls += 1
        self.submitted_requests.append(order_data)
        if self.exc is not None:
            raise self.exc
        if self.responses:
            return self.responses.pop(0)
        return build_fake_order_response(
            client_order_id=str(order_data.client_order_id),
            status=self.default_status,
        )


class ConfigurableJurorProvider:
    """Deterministic juror provider with configurable probabilities or errors."""

    def __init__(
        self,
        *,
        probabilities: dict[str, str] | None = None,
        raise_unavailable: str | None = None,
        cite_invalid_evidence: bool = False,
    ) -> None:
        self.calls: int = 0
        self.probabilities = probabilities or {
            "juror_market": "0.62",
            "juror_catalyst": "0.58",
            "juror_volatility": "0.60",
        }
        self.raise_unavailable = raise_unavailable
        self.cite_invalid_evidence = cite_invalid_evidence

    def complete(self, request: ProviderRequest) -> ProviderReply:
        self.calls += 1
        if self.raise_unavailable is not None:
            raise ProviderUnavailable(self.raise_unavailable)

        juror_id = str(request.payload["juror_id"])
        prob = self.probabilities.get(juror_id, "0.60")
        available_evidence = request.payload["available_evidence_ids"]
        if not isinstance(available_evidence, list):
            raise AssertionError("available evidence must be a list")
        evidence: list[JsonValue] = (
            ["ev_invalid_rogue_id"] if self.cite_invalid_evidence else available_evidence
        )
        return ProviderReply(
            output={
                "probability": prob,
                "calibration_score": "0.85",
                "confidence_stake": "0.75",
                "evidence_ids": evidence,
                "rationale": f"Deterministic rationale for {juror_id}",
                "invalidation": "Invalidate if underlying quote changes significantly.",
            }
        )


class DependenciesBundle:
    """Container for dependencies and inspection handles."""

    __slots__ = (
        "dependencies",
        "log",
        "client",
        "account_adapter",
        "market_adapter",
        "chain_adapter",
        "risk_store",
        "juror_provider",
    )

    def __init__(
        self,
        dependencies: PaperCycleDependencies,
        log: AppendOnlyDecisionLog,
        client: FakeTradingClient,
        account_adapter: FakeAccountAdapter,
        market_adapter: FakeMarketAdapter,
        chain_adapter: FakeOptionChainAdapter,
        risk_store: RiskStateStore,
        juror_provider: ConfigurableJurorProvider | DeterministicJurorStub,
    ) -> None:
        self.dependencies = dependencies
        self.log = log
        self.client = client
        self.account_adapter = account_adapter
        self.market_adapter = market_adapter
        self.chain_adapter = chain_adapter
        self.risk_store = risk_store
        self.juror_provider = juror_provider


def build_test_dependencies(
    *,
    case_id: str = FIXED_CASE_ID,
    account_state: PaperAccountState | None = None,
    market_state: UnderlyingMarketState | None = None,
    market_exc: Exception | None = None,
    chain_state: OptionChainState | None = None,
    chain_exc: Exception | None = None,
    client: FakeTradingClient | None = None,
    client_status: str = "new",
    juror_provider: ConfigurableJurorProvider | DeterministicJurorStub | None = None,
    risk_store: RiskStateStore | None = None,
    idempotency_registry: IdempotencyRegistry | None = None,
) -> DependenciesBundle:
    """Assemble an isolated, zero-network dependencies bundle."""
    log = AppendOnlyDecisionLog(case_id)
    resolved_client = client or FakeTradingClient(default_status=client_status)
    resolved_account_adapter = FakeAccountAdapter(account_state or build_fake_account_state())
    resolved_market_adapter = FakeMarketAdapter(market_state, exc=market_exc)
    resolved_chain_adapter = FakeOptionChainAdapter(chain_state, exc=chain_exc)
    resolved_risk = risk_store or build_fake_risk_state()
    resolved_provider = juror_provider or DeterministicJurorStub()
    order_adapter = AlpacaOrderAdapter(
        resolved_client,
        registry=idempotency_registry or IdempotencyRegistry(),
    )

    deps = PaperCycleDependencies(
        account=cast(AlpacaAccountAdapter, resolved_account_adapter),
        market=cast(AlpacaUnderlyingAdapter, resolved_market_adapter),
        chain=cast(AlpacaOptionChainAdapter, resolved_chain_adapter),
        orders=order_adapter,
        provider=ProviderBoundary(resolved_provider),
        risk=resolved_risk,
        event_log=log,
    )
    return DependenciesBundle(
        dependencies=deps,
        log=log,
        client=resolved_client,
        account_adapter=resolved_account_adapter,
        market_adapter=resolved_market_adapter,
        chain_adapter=resolved_chain_adapter,
        risk_store=resolved_risk,
        juror_provider=resolved_provider,
    )


# --- Shape verification helpers ---

EXPECTED_PAPER_CYCLE_RESULT_FIELDS: tuple[str, ...] = (
    "case_id",
    "status",
    "reason",
    "account",
    "market",
    "chain",
    "candidate",
    "jury",
    "intent",
    "verdict",
    "approval",
    "submission",
    "execution",
    "lifecycle",
    "pnl_snapshot",
)


def assert_paper_cycle_result_shape(result: PaperCycleResult) -> None:
    """Assert that a PaperCycleResult strictly adheres to the frozen dataclass schema."""
    assert is_dataclass(result), "Result must be a dataclass instance"
    result_fields = tuple(f.name for f in fields(result))
    assert result_fields == EXPECTED_PAPER_CYCLE_RESULT_FIELDS, (
        f"Result fields {result_fields} do not match expected {EXPECTED_PAPER_CYCLE_RESULT_FIELDS}"
    )
    # Check slots existence
    assert hasattr(result, "__slots__"), "Result must use slots"
    # Check order_attempted property
    assert isinstance(result.order_attempted, bool), "order_attempted must be a boolean"
    assert result.order_attempted == (result.submission is not None), (
        "order_attempted must strictly mirror (submission is not None)"
    )


def assert_events_strictly_ordered(log: AppendOnlyDecisionLog) -> None:
    """Assert that decision events strictly follow sequence ordering and hash invariants."""
    events = log.events
    assert len(events) > 0, "Log must contain at least one event"
    for i, event in enumerate(events):
        assert event.event.sequence == i, f"Event sequence {event.event.sequence} != index {i}"
        if i > 0:
            assert event.previous_hash == events[i - 1].event_hash, (
                f"Event hash chain broken at index {i}"
            )
    # Verify cryptographic integrity
    log.verify()


def assert_zero_network_activity(
    bundle: DependenciesBundle,
    *,
    expected_orders: int = 0,
) -> None:
    """Assert expected client calls and the absence of unexpected live trading."""
    assert bundle.client.calls == expected_orders, (
        f"Expected {expected_orders} order calls, but client recorded {bundle.client.calls}"
    )
