"""Sanitized readiness endpoint for recorded and credentialed paper runtimes."""

from fastapi import APIRouter, Request

from riskcourt.settings import RuntimeMode, Settings

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz(request: Request) -> dict[str, object]:
    """Expose only non-sensitive readiness facts."""

    settings: Settings = request.app.state.settings
    paper_configured = settings.paper_credentials_configured
    ready = settings.riskcourt_mode is RuntimeMode.RECORDED or paper_configured
    return {
        "status": "ok" if ready else "degraded",
        "ready": ready,
        "mode": settings.riskcourt_mode.value,
        "recorded_fallback": True,
        "paper_credentials_configured": paper_configured,
        "live_trading_enabled": False,
    }
