from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from alpaca.common.exceptions import APIError
from alpaca.trading.requests import LimitOrderRequest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from riskcourt.alpaca_account import AlpacaAccountAdapter, PositionSnapshot
from riskcourt.alpaca_market_data import AlpacaUnderlyingAdapter
from riskcourt.alpaca_option_chain import AlpacaOptionChainAdapter
from riskcourt.alpaca_order import AlpacaOrderAdapter
from riskcourt.app import create_app
from riskcourt.approval_guard import IdempotencyRegistry
from riskcourt.case_repository import RecordedCaseRepository
from riskcourt.personal_store import PersonalStore
from riskcourt.settings import RuntimeMode, Settings
from riskcourt.spread_selector import select_vertical_spreads
from tests.fixtures.paper_fakes import (
    build_fake_account_state,
    build_fake_chain_contract,
    build_fake_market_state,
    build_fake_option_chain_state,
)


def client_for(tmp_path: Path) -> TestClient:
    settings = Settings(
        riskcourt_mode=RuntimeMode.RECORDED,
        riskcourt_state_dir=tmp_path / ".riskcourt",
    )
    return TestClient(create_app(settings))


def store_for_client(client: TestClient) -> PersonalStore:
    return cast(PersonalStore, cast(Any, client.app).state.personal_store)


class TimeoutAfterAcceptanceClient:
    def __init__(self) -> None:
        self.submit_calls = 0
        self.lookup_calls = 0
        self.lookup_failures = 1
        self.order: Any | None = None
        self.orders: dict[str, Any] = {}
        self.account_positions: tuple[PositionSnapshot, ...] = ()
        self.timeout_on_submit = True

    def submit_order(self, order_data: LimitOrderRequest) -> object:
        self.submit_calls += 1
        client_order_id = order_data.client_order_id
        assert client_order_id is not None
        self.order = SimpleNamespace(
            client_order_id=client_order_id,
            status="new",
            submitted_at=datetime.now(UTC),
            filled_at=None,
            filled_avg_price=None,
        )
        self.orders[client_order_id] = self.order
        if self.timeout_on_submit:
            raise TimeoutError("broker accepted the order but the response was lost")
        return self.order

    def get_order_by_client_id(self, client_id: str) -> object:
        self.lookup_calls += 1
        if self.lookup_failures:
            self.lookup_failures -= 1
            raise TimeoutError("order lookup temporarily unavailable")
        if client_id in self.orders:
            return self.orders[client_id]
        raise APIError(  # type: ignore[no-untyped-call]
            "order not found",
            SimpleNamespace(response=SimpleNamespace(status_code=404)),
        )


def paper_client_for(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    broker: TimeoutAfterAcceptanceClient,
) -> TestClient:
    now = datetime.now(UTC)
    chain = paper_chain(now)
    settings = Settings(
        riskcourt_mode=RuntimeMode.PAPER,
        riskcourt_state_dir=tmp_path / ".riskcourt",
        alpaca_api_key_id=SecretStr("test-paper-key"),
        alpaca_api_secret_key=SecretStr("test-paper-secret"),
        riskcourt_option_feed="opra",
    )
    adapter = AlpacaOrderAdapter(broker, registry=IdempotencyRegistry())
    monkeypatch.setattr(
        AlpacaOrderAdapter,
        "from_settings",
        classmethod(lambda _cls, _settings: adapter),
    )
    monkeypatch.setattr(
        AlpacaAccountAdapter,
        "from_settings",
        classmethod(
            lambda _cls, _settings: SimpleNamespace(
                fetch=lambda: build_fake_account_state(
                    observed_at=datetime.now(UTC),
                    positions=broker.account_positions,
                )
            )
        ),
    )
    monkeypatch.setattr(
        AlpacaUnderlyingAdapter,
        "from_settings",
        classmethod(
            lambda _cls, _settings: SimpleNamespace(
                fetch=lambda symbol, now: build_fake_market_state(symbol=symbol, observed_at=now)
            )
        ),
    )
    monkeypatch.setattr(
        AlpacaOptionChainAdapter,
        "from_settings",
        classmethod(lambda _cls, _settings: SimpleNamespace(fetch=lambda *args, **kwargs: chain)),
    )
    return TestClient(create_app(settings))


def paper_chain(now: datetime) -> Any:
    expiry = now.date() + timedelta(days=10)
    contracts = (
        build_fake_chain_contract(
            expiry=expiry,
            quoted_at=now,
            strike=Decimal("640"),
            bid=Decimal("1.00"),
            ask=Decimal("1.10"),
        ).model_copy(update={"feed": "opra"}),
        build_fake_chain_contract(
            expiry=expiry,
            quoted_at=now,
            strike=Decimal("641"),
            bid=Decimal("0.80"),
            ask=Decimal("0.90"),
        ).model_copy(update={"feed": "opra"}),
    )
    return build_fake_option_chain_state(
        contracts=contracts,
        expiry_from=expiry,
        expiry_to=expiry,
    ).model_copy(update={"feed": "opra"})


def create_approved_paper_decision(client: TestClient) -> tuple[str, str]:
    store = store_for_client(client)
    now = datetime.now(UTC)
    chain = paper_chain(now)
    candidate = select_vertical_spreads(chain, as_of=now)[0]
    scan_id = store.create_scan("paper", ["SPY"])
    decision_id = store.save_decision(
        scan_id=scan_id,
        mode="paper",
        payload={
            "case_id": "case_fake_paper",
            "underlying_symbol": "SPY",
            "as_of": now.isoformat(),
            "candidate": {
                "long_contract": candidate.long_contract.model_dump(mode="json"),
                "short_contract": candidate.short_contract.model_dump(mode="json"),
            },
            "account": {
                "account": {
                    "equity": "100000",
                    "last_equity": "100000",
                    "options_buying_power": "50000",
                    "status": "ACTIVE",
                    "options_trading_level": 3,
                    "trading_blocked": False,
                    "account_blocked": False,
                    "trade_suspended_by_user": False,
                },
            },
            "verdict": {
                "decision": "approve",
                "approved_quantity": 1,
                "maximum_loss": str(candidate.geometry.net_debit * Decimal("100")),
            },
            "intent": {"direction": "bullish"},
        },
    )
    response = client.post(f"/api/decisions/{decision_id}/approve")
    assert response.status_code == 200
    return decision_id, response.json()["approval"]["approval_id"]


def test_personal_recorded_workspace_scan_and_approval(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        account = client.get("/api/account/summary")
        assert account.status_code == 200
        assert account.json()["mode"] == "recorded"

        scan = client.post("/api/scans", json={"symbols": ["SPY", "QQQ"]})
        assert scan.status_code == 200
        payload = scan.json()
        assert payload["status"] == "completed"
        assert payload["decisions"][0]["symbol"] == "SPY"
        assert payload["failures"] == [{"symbol": "QQQ", "reason": "recorded_case_unavailable"}]

        decision_id = payload["decisions"][0]["decision_id"]
        approval = client.post(f"/api/decisions/{decision_id}/approve")
        assert approval.status_code == 200
        approval_id = approval.json()["approval"]["approval_id"]

        blocked = client.post(
            f"/api/approvals/{approval_id}/submit",
            json={"confirm": True},
        )
        assert blocked.status_code == 409
        assert "recorded mode" in blocked.json()["detail"]


def test_paper_api_cannot_mutate_a_recorded_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    broker = TimeoutAfterAcceptanceClient()
    with paper_client_for(tmp_path, monkeypatch, broker) as client:
        store = store_for_client(client)
        recorded_case = RecordedCaseRepository().get("case_edge_positive")
        assert recorded_case is not None
        scan_id = store.create_scan("recorded", ["SPY"])
        decision_id = store.save_decision(
            scan_id=scan_id,
            mode="recorded",
            payload=recorded_case.model_dump(mode="json"),
        )

        veto = client.post(f"/api/decisions/{decision_id}/veto")
        approval = client.post(f"/api/decisions/{decision_id}/approve")

        assert veto.status_code == 404
        assert approval.status_code == 404
        saved = store.get_decision(decision_id)
        assert saved is not None
        assert saved["status"] == "ready"
        assert store.orders(mode="recorded") == []


def test_personal_workspace_veto_and_journal(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        scan = client.post("/api/scans", json={"symbols": ["SPY"]})
        decision_id = scan.json()["decisions"][0]["decision_id"]
        veto = client.post(f"/api/decisions/{decision_id}/veto")
        assert veto.status_code == 200
        assert veto.json()["status"] == "vetoed"

        journal = client.post(
            "/api/journal",
            json={"body": "Keep the edge threshold conservative.", "decision_id": decision_id},
        )
        assert journal.status_code == 200
        assert client.get("/api/journal").json()["entries"][0]["body"].startswith("Keep")
        audit = client.get("/api/audit")
        assert audit.status_code == 200
        assert any(item["event_type"] == "journal.created" for item in audit.json()["events"])


def test_veto_revokes_approval_and_api_rejects_reapproval(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        scan = client.post("/api/scans", json={"symbols": ["SPY"]})
        decision_id = scan.json()["decisions"][0]["decision_id"]
        approval = client.post(f"/api/decisions/{decision_id}/approve")
        approval_id = approval.json()["approval"]["approval_id"]

        veto = client.post(f"/api/decisions/{decision_id}/veto")

        assert veto.status_code == 200
        assert veto.json()["status"] == "vetoed"
        revoked = store_for_client(client).get_approval(approval_id)
        assert revoked is not None
        assert revoked["status"] == "revoked"
        reapproval = client.post(f"/api/decisions/{decision_id}/approve")
        assert reapproval.status_code == 409


def test_ambiguous_submission_retries_by_server_order_id_without_duplicate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = TimeoutAfterAcceptanceClient()
    with paper_client_for(tmp_path, monkeypatch, broker) as client:
        decision_id, approval_id = create_approved_paper_decision(client)

        first = client.post(
            f"/api/approvals/{approval_id}/submit",
            json={"confirm": True},
        )

        assert first.status_code == 503
        assert first.json()["detail"].startswith("paper order outcome is unknown")
        store = store_for_client(client)
        assert store.orders()[0]["status"] == "unknown"
        decision = store.get_decision(decision_id)
        assert decision is not None
        assert decision["status"] == "unknown"

        recovered = client.post(
            f"/api/approvals/{approval_id}/submit",
            json={"confirm": True},
        )

        assert recovered.status_code == 200
        assert recovered.json()["replayed"] is True
        order = recovered.json()["order"]
        assert order["status"] == "new"
        assert len(order["client_order_id"]) <= 48
        assert order["client_order_id"].startswith("rc_")
        assert len(store.orders()) == 1
        assert broker.submit_calls == 1
        assert broker.lookup_calls == 2


def test_changed_account_equity_blocks_entry_before_broker_submission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = TimeoutAfterAcceptanceClient()
    with paper_client_for(tmp_path, monkeypatch, broker) as client:
        _, approval_id = create_approved_paper_decision(client)
        monkeypatch.setattr(
            AlpacaAccountAdapter,
            "from_settings",
            classmethod(
                lambda _cls, _settings: SimpleNamespace(
                    fetch=lambda: build_fake_account_state(
                        observed_at=datetime.now(UTC), equity=Decimal("100001")
                    )
                )
            ),
        )

        response = client.post(
            f"/api/approvals/{approval_id}/submit", json={"confirm": True}
        )

        assert response.status_code == 409
        assert "equity changed" in response.json()["detail"]
        assert broker.submit_calls == 0


def test_reconcile_creates_position_from_a_later_fill_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = TimeoutAfterAcceptanceClient()
    with paper_client_for(tmp_path, monkeypatch, broker) as client:
        _, approval_id = create_approved_paper_decision(client)
        first = client.post(
            f"/api/approvals/{approval_id}/submit", json={"confirm": True}
        )
        assert first.status_code == 503
        recovered = client.post(
            f"/api/approvals/{approval_id}/submit", json={"confirm": True}
        )
        assert recovered.status_code == 200

        assert broker.order is not None
        broker.order.status = "filled"
        broker.order.filled_qty = "1"
        broker.order.filled_avg_price = "0.30"
        broker.order.filled_at = datetime.now(UTC)
        reconciled = client.post("/api/reconcile")

        assert reconciled.status_code == 200
        assert reconciled.json()["updated_orders"] == 1
        position = store_for_client(client).positions()[0]
        assert position["quantity"] == "1"
        assert position["cost_basis"] == "30.00"
        assert position["reconciliation_status"] == "discrepancy"

        again = client.post("/api/reconcile")
        assert again.status_code == 200
        assert len(store_for_client(client).positions()) == 1
        assert store_for_client(client).positions()[0]["cost_basis"] == "30.00"


def test_exit_preview_submit_and_later_fill_use_realized_fill_pnl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = TimeoutAfterAcceptanceClient()
    with paper_client_for(tmp_path, monkeypatch, broker) as client:
        _, approval_id = create_approved_paper_decision(client)
        assert client.post(
            f"/api/approvals/{approval_id}/submit", json={"confirm": True}
        ).status_code == 503
        assert client.post(
            f"/api/approvals/{approval_id}/submit", json={"confirm": True}
        ).status_code == 200

        assert broker.order is not None
        broker.order.status = "filled"
        broker.order.filled_qty = "1"
        broker.order.filled_avg_price = "0.30"
        broker.order.filled_at = datetime.now(UTC)
        candidate = select_vertical_spreads(
            paper_chain(datetime.now(UTC)), as_of=datetime.now(UTC)
        )[0]
        broker.account_positions = (
            PositionSnapshot(
                symbol=candidate.long_contract.occ_symbol,
                asset_class="us_option",
                quantity=Decimal("1"),
                side="long",
                market_value=Decimal("100"),
                unrealized_pl=Decimal("0"),
            ),
            PositionSnapshot(
                symbol=candidate.short_contract.occ_symbol,
                asset_class="us_option",
                quantity=Decimal("1"),
                side="short",
                market_value=Decimal("-90"),
                unrealized_pl=Decimal("0"),
            ),
        )
        assert client.post("/api/reconcile").status_code == 200
        position = store_for_client(client).positions()[0]
        assert position["reconciliation_status"] == "matched"

        preview = client.post(f"/api/positions/{position['position_id']}/exit-preview")
        assert preview.status_code == 200
        exit_approval_id = preview.json()["approval"]["approval_id"]
        broker.timeout_on_submit = False
        submitted = client.post(
            f"/api/positions/{position['position_id']}/exit-submit",
            json={"confirm": True},
        )

        assert submitted.status_code == 200
        assert broker.order is not None
        assert broker.order.client_order_id.startswith("rc_")
        broker.order.status = "filled"
        broker.order.filled_qty = "1"
        broker.order.filled_avg_price = "-0.15"
        broker.order.filled_at = datetime.now(UTC)
        broker.account_positions = ()
        assert client.post("/api/reconcile").status_code == 200

        closed = store_for_client(client).positions()[0]
        assert closed["status"] == "closed"
        assert closed["realized_pnl"] == "-15.00"
        exit_approval = store_for_client(client).get_approval(exit_approval_id)
        assert exit_approval is not None
        assert exit_approval["status"] == "filled"


def test_personal_workspace_read_models_and_guardrails(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        assert client.get("/api/watchlist").json()["symbols"]
        updated = client.post("/api/watchlist", json={"symbols": ["QQQ"]})
        assert updated.status_code == 200
        scan = client.post("/api/scans", json={"symbols": ["SPY"]}).json()
        scan_id = scan["scan_id"]
        decision_id = scan["decisions"][0]["decision_id"]

        assert client.get(f"/api/scans/{scan_id}").status_code == 200
        assert client.get("/api/decisions").json()["decisions"]
        assert client.get(f"/api/decisions/{decision_id}").status_code == 200
        assert client.get("/api/orders").json()["orders"] == []
        assert client.get("/api/positions").json()["positions"] == []

        kill = client.post("/api/kill-switch", json={"enabled": True, "reason": "pause"})
        assert kill.status_code == 200
        assert kill.json()["kill_switch"]["enabled"] is True
        assert (
            client.post("/api/kill-switch", json={"enabled": False, "reason": "resume"}).status_code
            == 200
        )

        assert client.post("/api/positions/missing/exit-preview").status_code == 404
        assert (
            client.post(
                "/api/positions/missing/exit-submit",
                json={"confirm": True},
            ).status_code
            == 404
        )
