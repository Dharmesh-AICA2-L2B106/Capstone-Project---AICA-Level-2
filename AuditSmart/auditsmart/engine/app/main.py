"""FastAPI application factory for auditsmart-engine."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.db import create_all
from app.core.logging import configure_logging, log_event
from app.version import ENGINE_NAME, ENGINE_VERSION


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        from app.services import rules, rules_monitor

        if settings.environment != "production":
            rules.seed_database()  # production seeds via `alembic upgrade` + CLI (SPEC 3.4)
            rules_monitor.seed_sources_db()
        rules.use_database(True)
        yield
        rules.use_database(False)

    app = FastAPI(
        lifespan=lifespan,
        title="AuditSmart Engine",
        version=ENGINE_VERSION,
        description=(
            "Calculation engine for AuditSmart (CLA Emirates). All numbers are computed "
            "deterministically in Python with Decimal; AI is never used for calculations."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def _access_log(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        log_event(
            "http.request",
            method=request.method,
            path=request.url.path,  # path only: ids, never query strings or bodies
            status_code=response.status_code,
            duration_ms=round((time.perf_counter() - start) * 1000, 1),
        )
        return response

    if settings.environment != "production":
        create_all()  # local SQLite convenience; production runs `alembic upgrade head`
    app.include_router(api_router)
    log_event("engine.started", engine_version=f"{ENGINE_NAME} {ENGINE_VERSION}")
    return app


app = create_app()
