from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.db import ping
from app.schemas.health import Health
from app.services import jobs
from app.version import ENGINE_NAME, ENGINE_VERSION

router = APIRouter(tags=["health"])


@router.get("/health", response_model=Health, summary="Engine version, database and queue status")
async def health() -> Health:
    s = get_settings()
    db = ping()
    queue = jobs.queue_status()
    ok = db == "ok" and not queue.startswith("error")
    return Health(
        status="ok" if ok else "degraded",
        service=ENGINE_NAME,
        version=ENGINE_VERSION,
        environment=s.environment,
        db=db,
        queue=queue,
    )
