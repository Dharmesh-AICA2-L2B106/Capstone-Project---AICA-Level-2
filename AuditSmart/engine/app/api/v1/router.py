from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    calendar,
    datasets,
    engagements,
    evaluation,
    firm_rules,
    health,
    input_vat,
    je,
    jobs,
    observations,
    rules,
    rules_monitor,
    sampling,
    workpaper,
)

api_router = APIRouter(prefix="/v1")
api_router.include_router(health.router)
api_router.include_router(datasets.router)
api_router.include_router(engagements.router)
api_router.include_router(jobs.router)
api_router.include_router(sampling.router)
api_router.include_router(je.router)
api_router.include_router(evaluation.router)
api_router.include_router(workpaper.router)
api_router.include_router(observations.router)
api_router.include_router(rules.router)
api_router.include_router(firm_rules.router)
api_router.include_router(rules_monitor.router)
api_router.include_router(calendar.router)
api_router.include_router(input_vat.router)
