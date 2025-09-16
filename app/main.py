"""Application entrypoint for the personal contact management service."""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import router as api_v1_router
from app.core.config import Settings, get_settings
from app.core.db import engine
from app.core.logging import configure_logging
from app.models import Base
from app.web import router as web_router

logger = logging.getLogger(__name__)

ERROR_CODE_MAP: dict[int, str] = {
    404: "RESOURCE_NOT_FOUND",
    422: "VALIDATION_ERROR",
}


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    settings = get_settings()
    configure_logging(settings)

    application = FastAPI(title="Personal Contacts Manager", version=settings.version)

    _configure_cors(application, settings)
    _configure_exception_handlers(application)

    static_dir = Path(__file__).resolve().parent / "web" / "static"
    application.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    application.include_router(web_router)
    application.include_router(api_v1_router, prefix="/api/v1")

    @application.on_event("startup")
    async def _on_startup() -> None:  # pragma: no cover - exercised via tests
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    return application


def _configure_cors(application: FastAPI, settings: Settings) -> None:
    if not settings.cors_origins:
        return

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _configure_exception_handlers(application: FastAPI) -> None:
    application.add_exception_handler(HTTPException, _http_exception_handler)
    application.add_exception_handler(RequestValidationError, _validation_exception_handler)
    application.add_exception_handler(Exception, _unhandled_exception_handler)


async def _http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, HTTPException)
    if isinstance(exc.detail, dict):
        message = str(exc.detail.get("message", "")) or str(exc.detail)
        code = exc.detail.get(
            "code", ERROR_CODE_MAP.get(exc.status_code, f"HTTP_{exc.status_code}")
        )
    else:
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        code = ERROR_CODE_MAP.get(exc.status_code, f"HTTP_{exc.status_code}")
    return _error_response(code, message, exc.status_code)


async def _validation_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    logger.info("Validation error", extra={"errors": exc.errors()})
    return _error_response("VALIDATION_ERROR", "Validation error", status_code=422)


async def _unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled application error")
    return _error_response("INTERNAL_SERVER_ERROR", "Internal server error", status_code=500)


def _error_response(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


app = create_app()
