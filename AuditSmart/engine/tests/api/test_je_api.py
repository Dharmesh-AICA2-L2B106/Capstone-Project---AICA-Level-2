"""Prompt 3.4 API: POST /v1/je-tests (background job), GET result, POST /v1/benford."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.api.test_sampling_api import DUMMY, EDGE, _dataset
from tests.conftest import auth
from tests.helpers import answer_key


def test_je_run_job_and_persistence(
    client: TestClient, token: Callable[..., str], engagement: str
) -> None:
    tok = token()
    did = _dataset(client, tok, engagement, DUMMY)
    r = client.post(
        "/v1/je-tests",
        headers=auth(tok),
        json={"dataset_id": did, "parameters": {"senior_users": ["FINMGR"]}},
    )
    assert r.status_code == 202, r.text
    acc = r.json()
    job = client.get(acc["status_url"], headers=auth(tok)).json()
    assert job["status"] == "succeeded" and job["type"] == "je_tests"
    g = client.get(acc["result_url"], headers=auth(tok))
    assert g.status_code == 200, g.text
    b = g.json()
    assert b["status"] == "current" and b["job_id"] == acc["job_id"]
    assert len(b["calendar_hash"]) == 64 and b["calendar"]["emirate"] == "Dubai"
    assert b["dataset_hash"] and b["benford"]["n"] > 2000
    summ = {s["test"]: s["lines"] for s in b["summary"]}
    assert summ["non_working_day"] == 40 and summ["after_half_day_cutoff"] == 10
    assert summ["round_sum"] == 20 and summ["period_end"] == 15
    assert summ["vague_narration"] == 10 and summ["duplicate_invoice"] == 10
    planted = {
        a["line_id"]
        for a in answer_key()
        if a["file"] == "dummy_gl.csv" and a["error_type"] == "duplicate_invoice"
    }
    assert {f["line_ref"] for f in b["flags"] if "duplicate_invoice" in f["flags"]} == planted
    assert b["parameters"]["period_end_days"] == 5 and b["parameters"]["round_min"] == "10000"

    from app.core.db import session_factory
    from app.models import JeFlag, JeRun

    with session_factory()() as s:
        run = s.get(JeRun, acc["je_run_id"])
        assert run is not None and run.calendar_hash == b["calendar_hash"]
        assert run.rule_versions_used and "je.round_sum.min" in run.rule_versions_used
        assert run.created_by == "user-1"
        assert s.query(JeFlag).filter_by(je_run_id=run.id).count() == b["flagged_lines"]
    # a second run supersedes the first
    r2 = client.post("/v1/je-tests", headers=auth(tok), json={"dataset_id": did})
    assert client.get(acc["result_url"], headers=auth(tok)).json()["status"] == "superseded"
    assert client.get(r2.json()["result_url"], headers=auth(tok)).json()["status"] == "current"


def test_je_guards(client: TestClient, token: Callable[..., str], engagement: str) -> None:
    tok = token()
    edge = _dataset(client, tok, engagement, EDGE)
    assert (
        client.post("/v1/je-tests", headers=auth(tok), json={"dataset_id": edge}).status_code == 409
    )
    assert (
        client.post("/v1/benford", headers=auth(tok), json={"dataset_id": edge}).status_code == 409
    )
    assert (
        client.post("/v1/je-tests", headers=auth(tok), json={"dataset_id": "nope"}).status_code
        == 404
    )
    did = _dataset(client, tok, engagement, DUMMY)
    bad = client.post(
        "/v1/je-tests",
        headers=auth(tok),
        json={"dataset_id": did, "parameters": {"tests": ["nope"]}},
    )
    assert bad.status_code == 422 and "Unknown JE test" in bad.json()["detail"]
    assert (
        client.post(
            "/v1/je-tests",
            headers=auth(tok),
            json={"dataset_id": did, "parameters": {"colour": "red"}},
        ).status_code
        == 422
    )
    outsider = token(sub="user-9")
    assert (
        client.post("/v1/je-tests", headers=auth(outsider), json={"dataset_id": did}).status_code
        == 403
    )
    r = client.post("/v1/je-tests", headers=auth(tok), json={"dataset_id": did})
    assert client.get(r.json()["result_url"], headers=auth(outsider)).status_code == 403
    assert client.get("/v1/je-tests/nope", headers=auth(tok)).status_code == 404


def test_benford_endpoint(client: TestClient, token: Callable[..., str], engagement: str) -> None:
    tok = token()
    did = _dataset(client, tok, engagement, DUMMY)
    r = client.post("/v1/benford", headers=auth(tok), json={"dataset_id": did})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["n"] > 2000 and len(b["chart"]) == 9 and b["conclusion"]
    assert b["mad_thresholds"] == ["0.006", "0.012", "0.015"]
    e = client.post(
        "/v1/benford", headers=auth(tok), json={"dataset_id": did, "account_types": ["Expense"]}
    ).json()
    assert e["n"] < b["n"] and e["account_types"] == ["expense"]
    bad = client.post(
        "/v1/benford", headers=auth(tok), json={"dataset_id": did, "min_amount": "100000000"}
    )
    assert bad.status_code == 422
    assert (
        client.post("/v1/benford", headers=auth(tok), json={"dataset_id": "nope"}).status_code
        == 404
    )
