from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import create_engine, text

from riskcourt.alpaca_account import AlpacaAccountAdapter
from riskcourt.app import app, create_app
from riskcourt.settings import RuntimeMode, Settings


def test_application_imports() -> None:
    assert isinstance(app, FastAPI)
    assert app.title == "RiskCourt API"


def test_recorded_mode_starts_without_credentials() -> None:
    settings = Settings(
        riskcourt_mode=RuntimeMode.RECORDED,
        alpaca_api_key_id=None,
        alpaca_api_secret_key=None,
    )

    recorded_app = create_app(settings)

    assert recorded_app.state.settings.riskcourt_mode is RuntimeMode.RECORDED
    assert not hasattr(recorded_app.state, "alpaca_trading_client")


def test_liveness_does_not_depend_on_credentials() -> None:
    settings = Settings(
        riskcourt_mode=RuntimeMode.RECORDED,
        alpaca_api_key_id=SecretStr("  "),
        alpaca_api_secret_key=SecretStr(""),
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/healthz")

    assert response.json()["live"] is True


def test_paper_mode_rejects_missing_credentials() -> None:
    with pytest.raises(ValidationError, match="paper mode requires"):
        Settings(
            riskcourt_mode=RuntimeMode.PAPER,
            alpaca_api_key_id=None,
            alpaca_api_secret_key=None,
        )


def test_paper_mode_starts_with_paper_credentials() -> None:
    settings = Settings(
        riskcourt_mode=RuntimeMode.PAPER,
        alpaca_api_key_id=SecretStr("test-paper-key"),
        alpaca_api_secret_key=SecretStr("test-paper-secret"),
    )

    paper_app = create_app(settings)

    assert paper_app.state.settings.riskcourt_mode is RuntimeMode.PAPER
    assert not hasattr(paper_app.state, "alpaca_trading_client")


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"riskcourt_mode": "live"}, "recorded.*paper"),
        (
            {"alpaca_paper_base_url": "https://api.alpaca.markets"},
            "paper-trading endpoint",
        ),
        ({"riskcourt_live_trading": True}, "live trading is permanently disabled"),
        ({"alpaca_live_trading": True}, "live trading is permanently disabled"),
    ],
)
def test_live_configuration_is_rejected(override: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(**override)  # type: ignore[arg-type]


def test_sqlite_runtime_is_available() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    with engine.connect() as connection:
        assert connection.scalar(text("select 1")) == 1

    engine.dispose()


def test_recorded_case_api_lists_and_loads_both_cases() -> None:
    with TestClient(create_app(Settings(riskcourt_mode=RuntimeMode.RECORDED))) as client:
        response = client.get("/api/recorded-cases")
        assert response.status_code == 200
        assert {item["case_id"] for item in response.json()} == {
            "case_edge_positive",
            "case_insufficient_edge",
        }

        case_response = client.get("/api/recorded-cases/case_edge_positive")
        assert case_response.status_code == 200
        assert case_response.json()["recorded"] is True
        assert case_response.json()["verdict"]["decision"] == "resize"


def test_recorded_case_api_returns_404_for_unknown_case() -> None:
    with TestClient(create_app(Settings(riskcourt_mode=RuntimeMode.RECORDED))) as client:
        response = client.get("/api/recorded-cases/not-a-case")

    assert response.status_code == 404
    assert response.json() == {"detail": "Recorded case not found"}


def test_healthz_is_sanitized_and_reports_recorded_fallback() -> None:
    settings = Settings(
        riskcourt_mode=RuntimeMode.RECORDED,
        alpaca_api_key_id=None,
        alpaca_api_secret_key=None,
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "live": True, "mode": "recorded"}
    assert "secret" not in response.text.lower()


def test_readyz_reports_recorded_storage_and_no_broker_dependency(tmp_path: Path) -> None:
    settings = Settings(
        riskcourt_mode=RuntimeMode.RECORDED,
        riskcourt_state_dir=tmp_path,
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["entry_ready"] is True
    assert payload["checks"]["paper_broker"] == "not_required"
    assert payload["checks"]["database"]["ok"] is True


def test_readyz_checks_paper_broker_read_and_surfaces_feed_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(
        riskcourt_mode=RuntimeMode.PAPER,
        riskcourt_state_dir=tmp_path,
        alpaca_api_key_id=SecretStr("paper-key"),
        alpaca_api_secret_key=SecretStr("paper-secret"),
        riskcourt_option_feed="indicative",
    )
    monkeypatch.setattr(
        AlpacaAccountAdapter,
        "from_settings",
        classmethod(
            lambda _cls, _settings: SimpleNamespace(
                fetch=lambda: SimpleNamespace(account=SimpleNamespace(status="ACTIVE"))
            )
        ),
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert response.json()["entry_ready"] is False
    assert response.json()["checks"]["paper_broker"] == "reachable"
    assert response.json()["checks"]["option_feed"] == "indicative"


def test_readyz_degrades_when_read_only_paper_broker_probe_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(
        riskcourt_mode=RuntimeMode.PAPER,
        riskcourt_state_dir=tmp_path,
        alpaca_api_key_id=SecretStr("paper-key"),
        alpaca_api_secret_key=SecretStr("paper-secret"),
        riskcourt_option_feed="opra",
    )

    def fail_from_settings(_cls: type[AlpacaAccountAdapter], _settings: Settings) -> object:
        raise RuntimeError("private broker response must not escape")

    monkeypatch.setattr(AlpacaAccountAdapter, "from_settings", fail_from_settings)
    with TestClient(create_app(settings)) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["ready"] is False
    assert response.json()["entry_ready"] is False
    assert response.json()["checks"]["paper_broker"] == "unavailable"
    assert "private broker" not in response.text


def test_cors_uses_exact_allowlist_for_safe_workstation_mutations() -> None:
    settings = Settings(
        riskcourt_mode=RuntimeMode.RECORDED,
        riskcourt_allowed_origins="https://demo.example, https://demo.example/",
    )
    with TestClient(create_app(settings)) as client:
        response = client.options(
            "/api/kill-switch",
            headers={
                "Origin": "https://demo.example",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://demo.example"
    assert "POST" in response.headers["access-control-allow-methods"]


def test_public_app_has_no_order_mutation_routes() -> None:
    with TestClient(create_app(Settings(riskcourt_mode=RuntimeMode.RECORDED))) as client:
        assert client.post("/api/orders").status_code == 404
        assert client.delete("/api/orders/example").status_code == 404


def test_personal_mutations_reject_untrusted_origin_and_host(tmp_path: Path) -> None:
    settings = Settings(
        riskcourt_mode=RuntimeMode.RECORDED,
        riskcourt_state_dir=tmp_path,
    )
    with TestClient(create_app(settings)) as client:
        cross_origin = client.post(
            "/api/kill-switch",
            json={"enabled": True, "reason": "hostile origin"},
            headers={"Origin": "https://attacker.example"},
        )
        hostile_host = client.post(
            "/api/kill-switch",
            json={"enabled": True, "reason": "hostile host"},
            headers={"Host": "attacker.example"},
        )

    assert cross_origin.status_code == 403
    assert hostile_host.status_code == 403
