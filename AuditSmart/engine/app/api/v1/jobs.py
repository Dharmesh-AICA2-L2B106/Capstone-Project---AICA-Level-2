"""Job endpoints (prompts 3.2 and 3.11).

GET  /v1/jobs                 -> paginated list (filters engagement_id, status, type)
GET  /v1/jobs/{id}            -> status and progress
POST /v1/jobs/{id}/cancel     -> co-operative cancel (creator, engagement Manager/Partner, Admin)
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.api.v1.deps import CurrentUser, DbSession, check_membership
from app.models import EngagementMember, Job
from app.schemas.datasets import JobOut
from app.services import jobs

router = APIRouter(tags=["jobs"])
CANCEL_ROLES = ("Manager", "Partner")


class JobsPage(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[JobOut]


def _visible(job: Job | None, user: CurrentUser, db: DbSession) -> Job:
    if job is None:
        raise HTTPException(404, "Job not found.")
    if job.engagement_id:
        check_membership(db, user, job.engagement_id)
    elif job.created_by != user.user_id:
        raise HTTPException(404, "Job not found.")
    return job


@router.get("/jobs", response_model=JobsPage, summary="List jobs you can see")
def list_jobs(user: CurrentUser, db: DbSession, engagement_id: str | None = None,
              status: Literal["queued", "running", "succeeded", "failed",
                              "cancelled"] | None = None,
              type: Annotated[str | None, Query(max_length=32)] = None,
              offset: Annotated[int, Query(ge=0)] = 0,
              limit: Annotated[int, Query(ge=1, le=200)] = 50) -> JobsPage:
    if engagement_id:
        check_membership(db, user, engagement_id)
    mine = list(db.execute(select(EngagementMember.engagement_id).where(
        EngagementMember.user_id == user.user_id)).scalars())
    total, items = jobs.list_jobs(engagement_ids=mine, created_by=user.user_id,
                                  engagement_id=engagement_id, status=status, job_type=type,
                                  offset=offset, limit=limit)
    return JobsPage(total=total, offset=offset, limit=limit,
                    items=[JobOut.model_validate(j) for j in items])


@router.get("/jobs/{job_id}", response_model=JobOut, summary="Status and progress of a job")
def get_job(job_id: str, user: CurrentUser, db: DbSession) -> JobOut:
    return JobOut.model_validate(_visible(jobs.get_job(job_id), user, db))


@router.post("/jobs/{job_id}/cancel", response_model=JobOut, summary="Cancel a job")
def cancel_job(job_id: str, user: CurrentUser, db: DbSession) -> JobOut:
    job = _visible(jobs.get_job(job_id), user, db)
    if job.created_by != user.user_id and not user.has_any("Admin"):
        assert job.engagement_id is not None  # _visible: other users' jobs are engagement jobs
        check_membership(db, user, job.engagement_id, CANCEL_ROLES)
    try:
        return JobOut.model_validate(jobs.cancel(job_id))
    except jobs.JobError as exc:
        raise HTTPException(exc.status_code, exc.message) from None
