"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from riskcourt import __version__
from riskcourt.case_repository import RecordedCaseRepository
from riskcourt.health import router as health_router
from riskcourt.routes import router as recorded_cases_router
from riskcourt.settings import Settings


def create_app(
    settings: Settings | None = None,
    recorded_case_repository: RecordedCaseRepository | None = None,
) -> FastAPI:
    """Construct the API only after its fail-closed configuration validates."""

    resolved_settings = settings or Settings()
    application = FastAPI(
        title="RiskCourt API",
        version=__version__,
        description="Recorded and Alpaca paper-only options decision service.",
    )
    application.state.settings = resolved_settings
    application.state.recorded_case_repository = (
        recorded_case_repository or RecordedCaseRepository()
    )
    if resolved_settings.allowed_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(resolved_settings.allowed_origins),
            allow_credentials=False,
            allow_methods=["GET"],
            allow_headers=["Accept", "Content-Type"],
        )
    application.include_router(health_router)
    application.include_router(recorded_cases_router)
    return application


app = create_app()
