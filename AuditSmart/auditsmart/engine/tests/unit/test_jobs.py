"""Prompt 3.11: job backends, task registry and co-operative cancellation."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from app.services import jobs


@pytest.fixture
def reg(env: Path) -> Iterator[dict[str, Any]]:
    seen: dict[str, Any] = {}

    @jobs.task("t_ok")
    def ok(job_id: str, *, x: int) -> str:
        jobs.set_progress(job_id, 40)
        jobs.set_progress(job_id, 20)  # progress never goes back
        seen["progress"] = jobs.get_job(job_id).progress  # type: ignore[union-attr]
        return f"ok:{x}"

    @jobs.task("t_boom")
    def boom(job_id: str) -> str:
        raise ValueError("secret detail 123")

    class Friendly(Exception):
        message = "The trial balance is not parsed yet."

    @jobs.task("t_friendly")
    def friendly(job_id: str) -> str:
        raise Friendly()

    yield seen
    for n in ("t_ok", "t_boom", "t_friendly", "t_wait"):
        jobs.TASKS.pop(n, None)
    jobs.set_backend(None)


def test_eager_task_lifecycle(reg: dict[str, Any]) -> None:
    jid = jobs.enqueue("t_ok", {"x": 7}, engagement_id=None, created_by="u1")
    job = jobs.get_job(jid)
    assert job is not None and job.status == "succeeded" and job.result_ref == "ok:7"
    assert job.progress == 100 and job.started_at and job.finished_at and job.type == "t_ok"
    assert reg["progress"] == 40
    bad = jobs.get_job(jobs.enqueue("t_boom", job_type="custom"))
    assert bad is not None and bad.status == "failed" and bad.type == "custom"
    assert bad.error is not None and "secret" not in bad.error and "ValueError" in bad.error
    fr = jobs.get_job(jobs.enqueue("t_friendly"))
    assert fr is not None and fr.error == "The trial balance is not parsed yet."
    with pytest.raises(jobs.JobError) as e:
        jobs.enqueue("nope")
    assert e.value.status_code == 500
    jid = jobs.create_job("x", None, None)
    jobs.run_task(jid, "nope", {})
    assert jobs.get_job(jid).error == "Unknown task 'nope'."  # type: ignore[union-attr]
    jobs.set_progress("missing-id", 50)  # no row: ignored


def test_cancel_queued_running_and_finished(reg: dict[str, Any]) -> None:
    class Hold:
        name = "hold"

        def __init__(self) -> None:
            self.calls: list[tuple[str, str, dict[str, Any]]] = []

        def dispatch(self, job_id: str, name: str, kwargs: dict[str, Any]) -> None:
            self.calls.append((job_id, name, kwargs))

        def run_callable(self, job_id: str, fn: jobs.JobFn) -> None:  # pragma: no cover
            raise AssertionError

    hold = Hold()
    jobs.set_backend(hold)
    jid = jobs.enqueue("t_ok", {"x": 1})
    assert jobs.get_job(jid).status == "queued"  # type: ignore[union-attr]
    c = jobs.cancel(jid)
    assert c.status == "cancelled" and c.finished_at is not None
    jobs.run_task(*hold.calls[0])  # the worker picks it up later: skipped
    assert jobs.get_job(jid).result_ref is None  # type: ignore[union-attr]
    with pytest.raises(jobs.JobError) as e:
        jobs.cancel(jid)
    assert e.value.status_code == 409
    with pytest.raises(jobs.JobError) as e:
        jobs.cancel("missing")
    assert e.value.status_code == 404

    # running job stops at its next progress update
    started, release = threading.Event(), threading.Event()

    @jobs.task("t_wait")
    def wait_task(job_id: str) -> str:
        started.set()
        release.wait(10)
        jobs.set_progress(job_id, 50)
        return "never"

    jobs.set_backend(jobs.ThreadBackend(workers=1))
    jid = jobs.enqueue("t_wait")
    assert started.wait(10)
    assert jobs.get_job(jid).status == "running"  # type: ignore[union-attr]
    assert jobs.cancel(jid).finished_at is None
    release.set()
    jobs.wait_all(timeout=10)
    done = jobs.get_job(jid)
    assert done is not None and done.status == "cancelled" and done.finished_at is not None
    assert done.result_ref is None


def test_late_finish_does_not_override_cancel(reg: dict[str, Any]) -> None:
    def fn(job_id: str) -> str:
        jobs.cancel(job_id)  # cancelled while running, task never checks
        return "late"

    jid = jobs.submit("closure", fn)
    j = jobs.get_job(jid)
    assert j is not None and j.status == "cancelled" and j.result_ref is None


def test_rq_backend_with_fake_queue(reg: dict[str, Any]) -> None:
    class FakeQueue:
        def __init__(self) -> None:
            self.items: list[tuple[Any, ...]] = []
            self.kw: list[dict[str, Any]] = []

        def enqueue(self, fn: str, *args: Any, **kw: Any) -> None:
            self.items.append((fn, *args))
            self.kw.append(kw)

    q = FakeQueue()
    backend = jobs.RQBackend(q, timeout=99)
    jobs.set_backend(backend)
    jid = jobs.enqueue("t_ok", {"x": 3}, engagement_id=None, created_by="u")
    assert q.items == [("app.services.jobs.run_task", jid, "t_ok", {"x": 3})]
    assert q.kw == [{"job_id": jid, "job_timeout": 99}]
    # the worker process side: resolve the dotted path and run it
    import importlib

    mod, _, attr = q.items[0][0].rpartition(".")
    getattr(importlib.import_module(mod), attr)(*q.items[0][1:])
    assert jobs.get_job(jid).result_ref == "ok:3"  # type: ignore[union-attr]
    # closures never cross to the worker: they run in-process
    cid = jobs.submit("closure", lambda j: "local")
    jobs.wait_all(timeout=10)
    assert jobs.get_job(cid).result_ref == "local"  # type: ignore[union-attr]
    assert len(q.items) == 1


def test_task_modules_lazy_loaded(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    saved = dict(jobs.TASKS)
    monkeypatch.setattr(jobs, "TASKS", {})
    jobs.load_tasks()  # modules already imported: registration happened at import time
    jid = jobs.create_job("validate", None, None)
    jobs.run_task(jid, "parse", {"dataset_id": "missing"})  # loads, then fails cleanly
    assert jobs.get_job(jid).status == "failed"  # type: ignore[union-attr]
    assert {"parse", "validate", "je_tests", "workpaper"} <= set(saved)


def test_default_backends(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import reset_settings

    assert isinstance(jobs.get_backend(), jobs.EagerBackend)
    monkeypatch.setenv("JOB_EAGER", "false")
    reset_settings()
    b = jobs.get_backend()
    assert isinstance(b, jobs.ThreadBackend) and jobs.get_backend() is b
    assert jobs.queue_status() == "in-process"


def test_list_jobs_visibility_and_filters(reg: dict[str, Any], engagement: str) -> None:
    a = jobs.enqueue("t_ok", {"x": 1}, engagement_id=engagement, created_by="u1")
    b = jobs.enqueue("t_boom", engagement_id=engagement, created_by="u2")
    mine = jobs.enqueue("t_ok", {"x": 2}, created_by="u3")
    other = jobs.enqueue("t_ok", {"x": 3}, created_by="u4")
    total, items = jobs.list_jobs(engagement_ids=[engagement], created_by="u3")
    assert total == 3 and {j.id for j in items} == {a, b, mine}
    total, items = jobs.list_jobs(engagement_ids=[], created_by="u3")
    assert [j.id for j in items] == [mine]
    total, items = jobs.list_jobs(engagement_ids=None, created_by=None)
    assert total == 4 and other in {j.id for j in items}
    total, items = jobs.list_jobs(engagement_ids=None, created_by=None, status="failed")
    assert [j.id for j in items] == [b]
    total, items = jobs.list_jobs(engagement_ids=None, created_by=None, job_type="t_ok",
                                  engagement_id=engagement)
    assert [j.id for j in items] == [a]
    total, items = jobs.list_jobs(engagement_ids=None, created_by=None, offset=1, limit=2)
    assert total == 4 and len(items) == 2
