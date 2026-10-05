"""FastAPI application entry point."""

import ipaddress
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from riskcourt import __version__
from riskcourt.case_repository import RecordedCaseRepository
from riskcourt.health import router as health_router
from riskcourt.personal_api import router as personal_router
from riskcourt.personal_store import PersonalStore
from riskcourt.routes import router as recorded_cases_router
from riskcourt.settings import Settings


def create_app(
    settings: Settings | None = None,
    recorded_case_repository: RecordedCaseRepository | None = None,
) -> FastAPI:
    """Construct the API only after its fail-closed configuration validates."""

    resolved_settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            application.state.personal_store.close()

    application = FastAPI(
        title="RiskCourt API",
        version=__version__,
        description="Recorded and Alpaca paper-only options decision service.",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.recorded_case_repository = (
        recorded_case_repository or RecordedCaseRepository()
    )
    application.state.personal_store = PersonalStore(
        resolved_settings.riskcourt_state_dir / "riskcourt.sqlite3"
    )
    if resolved_settings.allowed_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(resolved_settings.allowed_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Accept", "Content-Type"],
        )

    @application.middleware("http")
    async def guard_local_mutations(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path.startswith(
            "/api/"
        ):
            host_header = request.headers.get("host", "")
            host = urlsplit(f"//{host_header}").hostname
            peer = request.client.host if request.client is not None else ""
            test_peer = peer == "testclient"
            if host not in {"localhost", "127.0.0.1", "::1"} and not (
                test_peer and host == "testserver"
            ):
                return JSONResponse({"detail": "local API host required"}, status_code=403)
            if not test_peer:
                try:
                    if not ipaddress.ip_address(peer).is_loopback:
                        return JSONResponse(
                            {"detail": "local API client required"}, status_code=403
                        )
                except ValueError:
                    return JSONResponse(
                        {"detail": "local API client required"}, status_code=403
                    )
            origin = request.headers.get("origin")
            if origin:
                allowed = origin.rstrip("/") in resolved_settings.allowed_origins
                if not allowed:
                    origin_parts = urlsplit(origin)
                    request_netloc = host_header.lower()
                    if (
                        origin_parts.scheme not in {"http", "https"}
                        or origin_parts.netloc.lower() != request_netloc
                    ):
                        return JSONResponse(
                            {"detail": "cross-origin API mutation blocked"}, status_code=403
                        )
        return await call_next(request)

    application.include_router(health_router)
    application.include_router(recorded_cases_router)
    application.include_router(personal_router)
    return application


app = create_app()
