"""Separate process liveness from sanitized local-runtime readiness checks."""

from typing import Any, cast

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from riskcourt.alpaca_account import AlpacaAccountAdapter
from riskcourt.personal_store import PersonalStore
from riskcourt.settings import AiMode, RuntimeMode, Settings

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz(request: Request) -> dict[str, object]:
    """Return process liveness without depending on external services."""

    settings: Settings = request.app.state.settings
    return {"status": "ok", "live": True, "mode": settings.riskcourt_mode.value}


@router.get("/readyz")
def readyz(request: Request) -> Response:
    """Check local storage and configured paper runtime using read-only broker calls."""

    settings = cast(Settings, request.app.state.settings)
    store = cast(PersonalStore, request.app.state.personal_store)
    try:
        database = store.health_check()
    except Exception:
        database = {"ok": False, "schema_version": -1}

    provider_configured = (
        settings.riskcourt_mode is RuntimeMode.RECORDED
        or settings.riskcourt_ai_mode is not AiMode.TYPESAFE
        or settings.typesafe_credentials_configured
    )
    broker_status = "not_required"
    if settings.riskcourt_mode is RuntimeMode.PAPER:
        try:
            account_state = AlpacaAccountAdapter.from_settings(settings).fetch()
            broker_status = (
                "reachable"
                if account_state.account.status.strip().upper() == "ACTIVE"
                else "account_not_active"
            )
        except Exception:
            broker_status = "unavailable"

    ready = (
        bool(database["ok"])
        and provider_configured
        and broker_status
        in {
            "not_required",
            "reachable",
        }
    )
    paper = settings.riskcourt_mode is RuntimeMode.PAPER
    entry_ready = ready and (not paper or settings.riskcourt_option_feed == "opra")
    payload: dict[str, Any] = {
        "status": "ready" if ready else "degraded",
        "ready": ready,
        "entry_ready": entry_ready,
        "mode": settings.riskcourt_mode.value,
        "checks": {
            "database": database,
            "provider_configured": provider_configured,
            "paper_broker": broker_status,
            "option_feed": (settings.riskcourt_option_feed if paper else "not_required"),
        },
        "live_trading_enabled": False,
    }
    return JSONResponse(status_code=200 if ready else 503, content=payload)
