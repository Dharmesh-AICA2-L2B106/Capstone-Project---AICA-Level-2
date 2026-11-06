"""Background jobs (prompts 3.2 and 3.11).

Every job has a row in ``jobs`` (id, type, engagement_id, status queued/running/succeeded/
failed/cancelled, progress, started_at, finished_at, error, result_ref).

Work is dispatched through a :class:`JobBackend` so the queue can be swapped (D36):

* ``EagerBackend``  - JOB_EAGER=true; runs the task at once (tests, CLI).
* ``ThreadBackend`` - REDIS_URL empty; a small thread pool inside the API process.
* ``RQBackend``     - REDIS_URL set; RQ (Redis) queue ``auditsmart``. ``python -m app.cli
  worker`` starts a worker. An Azure Storage Queue / Service Bus backend only has to
  implement ``dispatch``.

Tasks are registered by name (``@task("je_tests")``) and receive ``(job_id, **kwargs)``
with JSON-able kwargs, so they can cross a process boundary. ``submit`` with a closure is
kept for in-process work that needs live dependencies (the FTA monitor check, D37).

Cancellation (D38) is co-operative: ``cancel`` marks the row ``cancelled``; a queued job is
skipped when it starts, and a running job stops at its next ``set_progress`` call.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import session_factory
from app.core.logging import log_event
from app.models import Job
from app.services import rules

IMPLEMENTED_BY_PROMPT = "3.11"

QUEUE_NAME = "auditsmart"
STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")
FINAL = ("succeeded", "failed", "cancelled")

JobFn = Callable[[str], str | None]  # receives job_id, returns result_ref
TaskFn = Callable[..., str | None]  # (job_id, **kwargs) -> result_ref

TASKS: dict[str, TaskFn] = {}
# Modules that register tasks; imported on demand so a bare worker process finds them.
TASK_MODULES = ("app.services.datasets", "app.services.je_tests", "app.services.workpaper",
                "app.services.input_vat")


def load_tasks() -> None:
    import importlib

    for mod in TASK_MODULES:
        importlib.import_module(mod)


class JobCancelled(Exception):
    """Raised inside a task when its job was cancelled."""


class JobError(Exception):
    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.message, self.status_code = message, status_code


def task(name: str) -> Callable[[TaskFn], TaskFn]:
    def deco(fn: TaskFn) -> TaskFn:
        TASKS[name] = fn
        return fn
    return deco


# ------------------------------------------------------------------ job rows
def queue_status() -> str:
    """Report "in-process" when REDIS_URL is empty; otherwise ping Redis."""
    url = get_settings().redis_url
    if not url:
        return "in-process"
    try:
        import redis

        client = redis.Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
        client.ping()
        return "ok"
    except Exception as exc:
        return f"error: {type(exc).__name__}"


def create_job(job_type: str, engagement_id: str | None, created_by: str | None) -> str:
    with session_factory()() as s:
        job = Job(type=job_type, engagement_id=engagement_id, created_by=created_by)
        s.add(job)
        s.commit()
        return job.id


def _status(job_id: str) -> str | None:
    with session_factory()() as s:
        job = s.get(Job, job_id)
        return None if job is None else job.status


def set_progress(job_id: str, progress: int) -> None:
    """Record progress (0-100). Raises JobCancelled when the job was cancelled."""
    with session_factory()() as s:
        job = s.get(Job, job_id)
        if job is None:
            return
        if job.status == "cancelled":
            raise JobCancelled(job_id)
        job.progress = max(job.progress, max(0, min(100, progress)))
        s.commit()


def _finish(job_id: str, status: str, *, ref: str | None = None,
            error: str | None = None) -> None:
    with session_factory()() as s:
        job = s.get(Job, job_id)
        assert job is not None
        if job.status == "cancelled":  # a cancel wins over a late finish
            job.finished_at = job.finished_at or datetime.now(UTC)
            s.commit()
            return
        job.status, job.finished_at = status, datetime.now(UTC)
        if status == "succeeded":
            job.progress, job.result_ref = 100, ref
        job.error = error
        s.commit()


def job_error_text(exc: BaseException) -> str:
    """The error stored on a failed job (D56). Our own errors carry a plain-English
    ``.message`` (DatasetError, JobError, MappingError ...) or set ``user_facing = True``;
    anything else gets a generic text so no internal detail or stack trace is shown."""
    msg = getattr(exc, "message", None)
    if isinstance(msg, str) and msg:
        return msg
    if getattr(exc, "user_facing", False) is True and str(exc):
        return str(exc)
    return f"{type(exc).__name__}: the job failed. Check the file and try again."


def _run(job_id: str, fn: JobFn) -> None:
    with session_factory()() as s:
        job = s.get(Job, job_id)
        assert job is not None
        if job.status != "queued":  # cancelled before it started
            log_event("job.skipped", job_id=job_id, status=job.status)
            return
        job.status, job.started_at = "running", datetime.now(UTC)
        s.commit()
        # D42: every backend passes here, so jobs resolve rules for their engagement's firm.
        scope = rules.scope_for_engagement(s, job.engagement_id)
    try:
        with rules.rule_scope(scope):
            ref = fn(job_id)
    except JobCancelled:
        _finish(job_id, "cancelled")
        log_event("job.cancelled", job_id=job_id)
        return
    except Exception as exc:
        _finish(job_id, "failed", error=job_error_text(exc))
        log_event("job.failed", job_id=job_id, error_type=type(exc).__name__)
        return
    _finish(job_id, "succeeded", ref=ref)
    log_event("job.succeeded", job_id=job_id)


def run_task(job_id: str, name: str, kwargs: dict[str, Any]) -> None:
    """Entry point used by every backend, including the RQ worker process."""
    if name not in TASKS:
        load_tasks()
    fn = TASKS.get(name)
    if fn is None:
        _finish(job_id, "failed", error=f"Unknown task {name!r}.")
        return
    _run(job_id, lambda jid: fn(jid, **kwargs))


# ------------------------------------------------------------------ backends
class JobBackend(Protocol):
    name: str

    def dispatch(self, job_id: str, name: str, kwargs: dict[str, Any]) -> None: ...

    def run_callable(self, job_id: str, fn: JobFn) -> None: ...


_pending: set[Future[None]] = set()


class EagerBackend:
    name = "eager"

    def dispatch(self, job_id: str, name: str, kwargs: dict[str, Any]) -> None:
        run_task(job_id, name, kwargs)

    def run_callable(self, job_id: str, fn: JobFn) -> None:
        _run(job_id, fn)


class ThreadBackend:
    name = "thread"

    def __init__(self, workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=workers,
                                            thread_name_prefix="auditsmart-job")

    def _track(self, fut: Future[None]) -> None:
        _pending.add(fut)
        fut.add_done_callback(_pending.discard)

    def dispatch(self, job_id: str, name: str, kwargs: dict[str, Any]) -> None:
        self._track(self._executor.submit(run_task, job_id, name, kwargs))

    def run_callable(self, job_id: str, fn: JobFn) -> None:
        self._track(self._executor.submit(_run, job_id, fn))


class RQBackend:
    """RQ (Redis) queue. ``queue`` is injectable so tests need no Redis server."""

    name = "rq"

    def __init__(self, queue: Any = None, *, timeout: int = 3600) -> None:
        if queue is None:  # pragma: no cover - needs a Redis server
            import redis
            from rq import Queue

            queue = Queue(QUEUE_NAME, connection=redis.Redis.from_url(get_settings().redis_url))
        self.queue, self.timeout = queue, timeout
        self._local = ThreadBackend(workers=1)

    def dispatch(self, job_id: str, name: str, kwargs: dict[str, Any]) -> None:
        self.queue.enqueue("app.services.jobs.run_task", job_id, name, kwargs,
                           job_id=job_id, job_timeout=self.timeout)

    def run_callable(self, job_id: str, fn: JobFn) -> None:
        # Closures cannot cross to a worker process; they stay in-process (D37).
        self._local.run_callable(job_id, fn)


_backend: JobBackend | None = None
_thread_backend: ThreadBackend | None = None


def get_backend() -> JobBackend:
    global _thread_backend
    if _backend is not None:
        return _backend
    settings = get_settings()
    if settings.job_eager:
        return EagerBackend()
    if settings.redis_url:  # pragma: no cover - needs a Redis server
        return RQBackend()
    if _thread_backend is None:
        _thread_backend = ThreadBackend()
    return _thread_backend


def set_backend(backend: JobBackend | None) -> None:
    """Install a backend (tests, or an Azure adapter at start-up). None restores the default."""
    global _backend
    _backend = backend


def enqueue(name: str, kwargs: dict[str, Any] | None = None, *, job_type: str | None = None,
            engagement_id: str | None = None, created_by: str | None = None) -> str:
    """Create a job row and dispatch registered task ``name`` with JSON-able ``kwargs``."""
    if name not in TASKS:
        load_tasks()
    if name not in TASKS:
        raise JobError(f"Unknown task {name!r}.", 500)
    job_id = create_job(job_type or name, engagement_id, created_by)
    get_backend().dispatch(job_id, name, dict(kwargs or {}))
    return job_id


def submit(job_type: str, fn: JobFn, *, engagement_id: str | None = None,
           created_by: str | None = None) -> str:
    """Run an in-process closure as a job (live dependencies; never sent to a worker)."""
    job_id = create_job(job_type, engagement_id, created_by)
    get_backend().run_callable(job_id, fn)
    return job_id


# ------------------------------------------------------------------ queries and control
def get_job(job_id: str) -> Job | None:
    with session_factory()() as s:
        return s.get(Job, job_id)


def cancel(job_id: str) -> Job:
    with session_factory()() as s:
        job = s.get(Job, job_id)
        if job is None:
            raise JobError("Job not found.", 404)
        if job.status in FINAL:
            raise JobError(f"The job has already finished ({job.status}).", 409)
        was = job.status
        job.status = "cancelled"
        if was == "queued":
            job.finished_at = datetime.now(UTC)
        s.commit()
        s.refresh(job)
    log_event("job.cancel_requested", job_id=job_id, was=was)
    return job


def list_jobs(*, engagement_ids: list[str] | None, created_by: str | None,
              engagement_id: str | None = None, status: str | None = None,
              job_type: str | None = None, offset: int = 0,
              limit: int = 50) -> tuple[int, list[Job]]:
    """Jobs visible to a caller: in ``engagement_ids`` or created by ``created_by``.

    ``engagement_ids=None`` means no restriction (Admin).
    """
    q = select(Job)
    if engagement_ids is not None:
        own = (Job.engagement_id.is_(None)) & (Job.created_by == (created_by or ""))
        q = q.where(Job.engagement_id.in_(engagement_ids) | own)
    if engagement_id:
        q = q.where(Job.engagement_id == engagement_id)
    if status:
        q = q.where(Job.status == status)
    if job_type:
        q = q.where(Job.type == job_type)
    with session_factory()() as s:
        total = s.execute(select(func.count()).select_from(q.subquery())).scalar_one()
        items = list(s.execute(q.order_by(Job.created_at.desc(), Job.id).offset(offset)
                               .limit(limit)).scalars())
    return int(total), items


def wait_all(timeout: float | None = None) -> None:
    """Block until in-process background jobs finish (tests and graceful shutdown)."""
    wait(list(_pending), timeout=timeout)
