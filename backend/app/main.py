"""FastAPI application entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import __version__, ai
from app.api import ai_routes, analytics, auth, issues, reports_routes, scans, websites
from app.config import get_settings
from app.db import get_engine

log = logging.getLogger("accessiscan")
MAX_BODY_BYTES = 1_000_000


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log.info(
        "AccessiScan AI %s starting (environment=%s, ai=%s)",
        __version__,
        settings.environment,
        settings.ai_provider if settings.ai_enabled else "disabled",
    )
    if settings.run_embedded_worker and settings.environment != "test":
        from app.worker import start_embedded_worker

        start_embedded_worker()
    yield
    if settings.run_embedded_worker and settings.environment != "test":
        from app.worker import stop_embedded_worker

        stop_embedded_worker()


def create_app() -> FastAPI:
    settings = get_settings()
    docs = settings.docs_enabled
    app = FastAPI(
        title="AccessiScan AI API",
        version=__version__,
        description=(
            "Automated web accessibility auditing (axe-core in a real Chromium browser) with optional AI "
            "explanations. Results are automated assessments, not legal certification or proof of WCAG conformance."
        ),
        docs_url="/api/docs" if docs else None,
        redoc_url="/api/redoc" if docs else None,
        openapi_url="/api/openapi.json" if docs else None,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,  # bearer tokens, no cookies
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Content-Disposition"],
        max_age=600,
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Any:
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > MAX_BODY_BYTES:
            return JSONResponse({"detail": "Request body too large"}, status_code=413)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if not request.url.path.startswith("/api/docs") and not request.url.path.startswith("/api/redoc"):
            response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        if settings.environment == "production":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.url.path.startswith("/api/v1"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = []
        for e in exc.errors():
            loc = ".".join(str(p) for p in e.get("loc", []) if p not in ("body", "query", "path"))
            msg = str(e.get("msg", "Invalid value")).removeprefix("Value error, ")
            errors.append({"field": loc, "message": msg})
        detail = "; ".join(f"{e['field']}: {e['message']}" if e["field"] else e["message"] for e in errors)
        return JSONResponse({"detail": detail or "Invalid request", "errors": errors}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", exc_info=exc)
        return JSONResponse({"detail": "Internal server error"}, status_code=500)

    api = APIRouter(prefix="/api/v1")
    for r in (
        auth.router,
        auth.me_router,
        websites.router,
        scans.router,
        scans.meta_router,
        issues.router,
        ai_routes.router,
        reports_routes.router,
        analytics.router,
    ):
        api.include_router(r)
    app.include_router(api)

    @app.get("/health/live", tags=["health"])
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    def ready() -> JSONResponse:
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            db_ok = True
        except Exception:  # noqa: BLE001
            db_ok = False
        body = {
            "status": "ok" if db_ok else "degraded",
            "database": "ok" if db_ok else "unavailable",
            "version": __version__,
            "ai": ai.status()["enabled"],
            "embedded_worker": settings.run_embedded_worker,
        }
        return JSONResponse(body, status_code=200 if db_ok else 503)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"name": "AccessiScan AI API", "docs": "/api/docs" if docs else "disabled", "health": "/health/ready"}

    return app


app = create_app()
