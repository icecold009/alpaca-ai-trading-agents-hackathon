"""FastAPI application entry point."""

from fastapi import FastAPI

from riskcourt import __version__
from riskcourt.case_repository import RecordedCaseRepository
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
    application.include_router(recorded_cases_router)
    return application


app = create_app()
