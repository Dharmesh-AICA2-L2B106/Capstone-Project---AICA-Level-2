"""Prompt 3.11 API: job list/cancel, workpaper as a job, row filters, JE flag pages."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from tests.api.test_sampling_api import DUMMY, _dataset
from tests.conftest import auth


class Hold:
    """Backend that queues without running, so a job can be cancelled while queued."""

    name = "hold"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def dispatch(self, job_id: str, name: str, kwargs: dict[str, Any]) -> None:
        self.calls.append((job_id, name, kwargs))

    def run_callable(self, job_id: str, fn: Any) -> None:  # pragma: no cover
        raise AssertionError


def test_list_and_cancel_permissions(client: TestClient, token: Callable[..., str],
                                     engagement: str) -> None:
    from app.services import jobs

    mgr, staff = token(), token(sub="user-2")
    admin, outsider = token(sub="admin-9", roles=["Admin"]), token(sub="user-9")
    did = _dataset(client, mgr, engagement, DUMMY, validate=False)
    client.post(f"/v1/datasets/{did}/validate", headers=auth(mgr))  # as a job
    page = client.get("/v1/jobs", headers=auth(staff)).json()
    assert page["total"] == 2 and {j["type"] for j in page["items"]} == {"parse", "validate"}
    assert all(j["engagement_id"] == engagement for j in page["items"])
    r = client.get(f"/v1/jobs?engagement_id={engagement}&type=parse&status=succeeded",
                   headers=auth(mgr))
    assert r.json()["total"] == 1
    assert client.get("/v1/jobs", headers=auth(outsider)).json()["total"] == 0
    assert client.get(f"/v1/jobs?engagement_id={engagement}",
                      headers=auth(outsider)).status_code == 403
    assert client.get("/v1/jobs?status=bogus", headers=auth(mgr)).status_code == 422
    assert client.get("/v1/jobs?limit=1", headers=auth(mgr)).json()["limit"] == 1

    hold = Hold()
    jobs.set_backend(hold)
    try:
        r = client.post("/v1/je-tests", headers=auth(mgr), json={"dataset_id": did})
        jid = r.json()["job_id"]
        assert client.get(f"/v1/jobs/{jid}", headers=auth(mgr)).json()["status"] == "queued"
        # Staff did not create it and is not Manager/Partner
        assert client.post(f"/v1/jobs/{jid}/cancel", headers=auth(staff)).status_code == 403
        assert client.post(f"/v1/jobs/{jid}/cancel", headers=auth(outsider)).status_code == 403
        r = client.post(f"/v1/jobs/{jid}/cancel", headers=auth(mgr))
        assert r.status_code == 200 and r.json()["status"] == "cancelled"
        assert client.post(f"/v1/jobs/{jid}/cancel", headers=auth(mgr)).status_code == 409
        jobs.run_task(*hold.calls[0])  # worker picks it up later: skipped
        assert r.json()["result_ref"] is None
        run = client.get(f"/v1/je-tests/{hold.calls[0][2]['run_id']}", headers=auth(mgr))
        assert run.json()["status"] == "queued"
        # staff creates its own job and may cancel it; a personal job is hidden from others
        own = jobs.enqueue("validate", {"dataset_id": did}, created_by="user-2")
        assert client.get(f"/v1/jobs/{own}", headers=auth(mgr)).status_code == 404
        assert client.post(f"/v1/jobs/{own}/cancel", headers=auth(staff)).status_code == 200
        eng_job = jobs.enqueue("validate", {"dataset_id": did}, engagement_id=engagement,
                               created_by="user-1")
        assert client.post(f"/v1/jobs/{eng_job}/cancel",
                           headers=auth(admin)).status_code == 403  # Admin is not a member
    finally:
        jobs.set_backend(None)
    assert client.get("/v1/jobs/nope", headers=auth(mgr)).status_code == 404


def test_je_task_cancelled_mid_run(client: TestClient, token: Callable[..., str],
                                   engagement: str, monkeypatch: Any) -> None:
    from app.services import je_tests, jobs

    mgr = token()
    did = _dataset(client, mgr, engagement, DUMMY)
    real = jobs.set_progress

    def cancel_then(job_id: str, p: int) -> None:
        if p >= 40:
            jobs.cancel(job_id)
        real(job_id, p)

    monkeypatch.setattr(je_tests.jobs, "set_progress", cancel_then)
    acc = client.post("/v1/je-tests", headers=auth(mgr), json={"dataset_id": did}).json()
    assert client.get(acc["status_url"], headers=auth(mgr)).json()["status"] == "cancelled"
    assert client.get(acc["result_url"], headers=auth(mgr)).json()["status"] == "cancelled"


def test_workpaper_job_and_flags_pages(client: TestClient, token: Callable[..., str],
                                       engagement: str) -> None:
    mgr = token()
    did = _dataset(client, mgr, engagement, DUMMY)
    acc = client.post("/v1/je-tests", headers=auth(mgr),
                      json={"dataset_id": did, "parameters": {"senior_users": ["FINMGR"]}}).json()
    rid = acc["je_run_id"]
    full = client.get(acc["result_url"], headers=auth(mgr)).json()
    p = client.get(f"/v1/je-tests/{rid}/flags?limit=10", headers=auth(mgr)).json()
    assert p["total"] == full["flagged_lines"] and len(p["items"]) == 10
    scores = [i["risk_score"] for i in p["items"]]
    assert scores == sorted(scores, reverse=True)
    dup = client.get(f"/v1/je-tests/{rid}/flags?flag=duplicate_invoice&limit=1000",
                     headers=auth(mgr)).json()
    want = {f["line_ref"] for f in full["flags"] if "duplicate_invoice" in f["flags"]}
    assert dup["total"] == 10 and {i["line_ref"] for i in dup["items"]} == want
    hi = client.get(f"/v1/je-tests/{rid}/flags?min_score=2&offset=1", headers=auth(mgr)).json()
    assert hi["total"] == sum(1 for f in full["flags"] if f["risk_score"] >= 2)
    assert client.get(f"/v1/je-tests/{rid}/flags?flag=Bad-Flag",
                      headers=auth(mgr)).status_code == 422
    assert client.get("/v1/je-tests/nope/flags", headers=auth(mgr)).status_code == 404
    assert client.get(f"/v1/je-tests/{rid}/flags",
                      headers=auth(token(sub="user-9"))).status_code == 403

    body = {"engagement_id": engagement, "wp_ref": "JE-1", "je_run_id": rid}
    r = client.post("/v1/workpaper/jobs", headers=auth(mgr), json=body)
    assert r.status_code == 202, r.text
    job = client.get(r.json()["status_url"], headers=auth(mgr)).json()
    assert job["status"] == "succeeded" and job["type"] == "workpaper"
    wp_id = job["result_ref"].split(":", 1)[1]
    meta = client.get(f"/v1/workpapers/{wp_id}", headers=auth(mgr)).json()
    assert meta["wp_ref"] == "JE-1" and meta["preparer"] == "user-1"
    bad = client.post("/v1/workpaper/jobs", headers=auth(mgr),
                      json={**body, "je_run_id": "nope"}).json()
    failed = client.get(bad["status_url"], headers=auth(mgr)).json()
    assert failed["status"] == "failed" and "JE run not found" in failed["error"]
    assert client.post("/v1/workpaper/jobs", headers=auth(token(sub="user-9")),
                       json=body).status_code == 403


def test_row_filters(client: TestClient, token: Callable[..., str], engagement: str) -> None:
    import csv
    import io

    mgr = token()
    did = _dataset(client, mgr, engagement, DUMMY)
    src = list(csv.DictReader(io.StringIO(DUMMY.decode("utf-8-sig"))))
    base = f"/v1/datasets/{did}/rows"
    assert client.get(base, headers=auth(mgr)).json()["total"] == len(src)
    user = src[0]["user_id"]
    r = client.get(f"{base}?user_id={user}&limit=1000", headers=auth(mgr)).json()
    assert r["total"] == sum(1 for x in src if x["user_id"] == user)
    assert {x["user_id"] for x in r["rows"]} == {user}
    r = client.get(f"{base}?date_from=2025-12-01&date_to=2025-12-31&limit=1000",
                   headers=auth(mgr)).json()
    assert r["total"] == sum(1 for x in src if x["posting_date"].startswith("2025-12"))
    assert all(x["posting_date"].startswith("2025-12") for x in r["rows"])
    r = client.get(f"{base}?min_amount=100000&limit=1000", headers=auth(mgr)).json()
    big = sum(1 for x in src if max(float(x["debit"] or 0), float(x["credit"] or 0)) >= 100000)
    assert r["total"] == big and big > 0
    acct = src[0]["account_code"]
    r = client.get(f"{base}?account_code={acct}&user_id={user}&min_amount=0",
                   headers=auth(mgr)).json()
    assert r["total"] == sum(1 for x in src if x["user_id"] == user
                             and x["account_code"] == acct)
    assert client.get(f"{base}?date_from=2025-12-31&date_to=2025-01-01",
                      headers=auth(mgr)).status_code == 422
    assert client.get(f"{base}?min_amount=-1", headers=auth(mgr)).status_code == 422
