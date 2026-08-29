import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import create_engine, text

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
    with TestClient(app) as client:
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
    with TestClient(app) as client:
        response = client.get("/api/recorded-cases/not-a-case")

    assert response.status_code == 404
    assert response.json() == {"detail": "Recorded case not found"}
