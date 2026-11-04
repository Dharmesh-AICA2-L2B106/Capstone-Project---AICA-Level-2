"""Prompt 3.12 API: supplier register, expense mapping, POST /v1/input-vat-check (job),
answer-key detection (15 unverified / 3 spend threshold / 20 employee expense) and the WP."""

from __future__ import annotations

import io
from collections.abc import Callable
from datetime import date
from typing import Any

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from tests.api.test_sampling_api import DUMMY, _dataset
from tests.conftest import auth
from tests.helpers import DATA, answer_key

MAPPING = [{"account_code": "6050", "category": "transport"},
           {"account_code": "6060", "category": "accommodation_operational"},
           {"account_code": "6070", "category": "mobile_phone_internet"},
           {"account_code": "6080", "category": "parking"},
           {"account_code": "6090", "category": "food_beverages_remote"}]
TEST_EFF = "2025-10-01"


def _key(kind: str) -> set[str]:
    return {a["line_id"] for a in answer_key()
            if a["file"] == "dummy_gl.csv" and a["error_type"] == kind}


def _setup(client: TestClient, tok: str, eng: str) -> str:
    did = _dataset(client, tok, eng, DUMMY)
    r = client.put(f"/v1/engagements/{eng}/supplier-register", headers=auth(tok),
                   files={"file": ("register.csv", (DATA / "supplier_register.csv").read_bytes())})
    assert r.status_code == 200, r.text
    assert r.json()["suppliers"] == 58
    r = client.put(f"/v1/engagements/{eng}/expense-mapping", headers=auth(tok),
                   json={"items": MAPPING})
    assert r.status_code == 200, r.text
    return did


def _run(client: TestClient, tok: str, did: str, **kw: Any) -> dict[str, Any]:
    r = client.post("/v1/input-vat-check", headers=auth(tok), json={"dataset_id": did, **kw})
    assert r.status_code == 202, r.text
    acc = r.json()
    job = client.get(acc["status_url"], headers=auth(tok)).json()
    assert job["status"] == "succeeded", job
    g = client.get(acc["result_url"], headers=auth(tok))
    assert g.status_code == 200, g.text
    return {**g.json(), "_acc": acc}


def test_input_vat_answer_key_job_and_workpaper(client: TestClient, token: Callable[..., str],
                                               engagement: str) -> None:
    tok = token()
    did = _setup(client, tok, engagement)
    b = _run(client, tok, did, effective_date_override=TEST_EFF)
    assert b["status"] == "current" and b["job_id"] == b["_acc"]["job_id"]
    got = {c: {e["line_ref"] for e in b["exceptions"] if e["check"] == c}
           for c in ("unverified_supplier", "spend_threshold", "employee_expense")}
    assert got["unverified_supplier"] == _key("input_vat_unverified_supplier")
    assert got["spend_threshold"] == _key("input_vat_spend_threshold")
    assert got["employee_expense"] == _key("employee_expense")
    assert len(got["unverified_supplier"]) == 15 and len(got["spend_threshold"]) == 3
    assert len(got["employee_expense"]) == 20
    totals = {e["line_ref"]: e["rolling_total"] for e in b["exceptions"]
              if e["check"] == "spend_threshold"}
    assert totals == {"L02434": "380,547.53", "L02768": "393,220.08", "L02936": "397,426.29"}
    assert b["effective_date"] == TEST_EFF and b["rules_pending_verification"] is True
    assert any("TEST-ONLY" in w for w in b["warnings"])
    rid = b["input_vat_run_id"]
    # exceptions endpoint: filter + pagination
    e = client.get(f"/v1/input-vat-check/{rid}/exceptions?check=spend_threshold&limit=2",
                   headers=auth(tok)).json()
    assert e["total"] == 3 and len(e["items"]) == 2
    assert client.get(f"/v1/input-vat-check/{rid}/exceptions?check=bogus",
                      headers=auth(tok)).status_code == 422
    # persistence
    from app.core.db import session_factory
    from app.models import AuditLog, InputVatRun

    with session_factory()() as s:
        run = s.get(InputVatRun, rid)
        assert run is not None and run.created_by == "user-1"
        assert run.rule_versions_used and \
            "input_vat.verification.spend_threshold@v1" in run.rule_versions_used
        acts = {a.action for a in s.query(AuditLog).filter(AuditLog.entity_id == engagement)}
        assert {"supplier_register_replace", "expense_mapping_replace"} <= acts
    # working paper with the Input VAT sheet
    r = client.post("/v1/workpaper", headers=auth(tok), json={
        "engagement_id": engagement, "wp_ref": "C-320", "input_vat_run_id": rid})
    assert r.status_code == 201, r.text
    f = client.get(r.json()["file_url"], headers=auth(tok))
    wb = load_workbook(io.BytesIO(f.content))
    rows = [tuple(c.value for c in row) for row in wb["Input VAT"].iter_rows()]
    assert any(r[0] == "Input VAT run ID" and r[1] == rid for r in rows)
    assert sum(1 for r in rows if r[1] == "unverified_supplier") >= 1
    assert {r[0] for r in rows if r[1] == "spend_threshold"} >= _key("input_vat_spend_threshold")
    # a second run supersedes the first; a run with no override finds no supplier exceptions
    b2 = _run(client, tok, did)
    assert client.get(b["_acc"]["result_url"], headers=auth(tok)).json()["status"] \
        == "superseded"
    assert {s["check"]: s["lines"] for s in b2["summary"]}["unverified_supplier"] == 0
    # rule change over the shifted window marks it STALE
    from app.services.rules import mark_stale

    with session_factory()() as s:
        out = mark_stale(s, [("input_vat.verification.effective_date@v1", date(2025, 1, 1),
                              None)], user_id="t", reason="test")
        s.commit()
    assert b2["input_vat_run_id"] in {o["id"] for o in out}


def test_input_vat_views_and_errors(client: TestClient, token: Callable[..., str],
                                    engagement: str) -> None:
    tok, staff, outsider = token(), token(sub="user-2", roles=["Staff"]), token(sub="zz")
    eng = engagement
    did = _setup(client, tok, eng)
    g = client.get(f"/v1/engagements/{eng}/supplier-register", headers=auth(staff)).json()
    assert g["total"] == 58 and g["items"][0]["supplier_id"] == "S001"
    m = client.get(f"/v1/engagements/{eng}/expense-mapping", headers=auth(staff)).json()
    assert m["mapping"]["6050"] == "transport" and "parking" in m["categories"]
    for path in ("supplier-register", "expense-mapping"):
        assert client.get(f"/v1/engagements/{eng}/{path}",
                          headers=auth(outsider)).status_code == 403
    # register errors: nothing saved
    r = client.put(f"/v1/engagements/{eng}/supplier-register", headers=auth(tok),
                   files={"file": ("r.csv", b"supplier_id,verified_on\nA,2026-13-01\n")})
    assert r.status_code == 422 and r.json()["detail"]["errors"][0]["row"] == 2
    r = client.put(f"/v1/engagements/{eng}/supplier-register", headers=auth(tok),
                   files={"file": ("r.csv", b"name\nA\n")})
    assert r.status_code == 422 and "supplier_id" in r.json()["detail"]
    r = client.put(f"/v1/engagements/{eng}/supplier-register", headers=auth(tok),
                   files={"file": ("r.csv", b"x" * (5 * 1024 * 1024 + 1))})
    assert r.status_code == 413
    assert client.get(f"/v1/engagements/{eng}/supplier-register",
                      headers=auth(tok)).json()["total"] == 58
    # mapping errors
    for items, msg in (([{"account_code": "1", "category": "gym"}], "not one of"),
                       ([{"account_code": " ", "category": "parking"}], "blank"),
                       ([{"account_code": "1", "category": "parking"}] * 2, "twice")):
        r = client.put(f"/v1/engagements/{eng}/expense-mapping", headers=auth(tok),
                       json={"items": items})
        assert r.status_code == 422 and msg in r.json()["detail"], r.text
    # run errors
    assert client.post("/v1/input-vat-check", headers=auth(tok),
                       json={"dataset_id": "nope"}).status_code == 404
    assert client.post("/v1/input-vat-check", headers=auth(outsider),
                       json={"dataset_id": did}).status_code == 403
    assert client.post("/v1/input-vat-check", headers=auth(tok),
                       json={"dataset_id": did, "x": 1}).status_code == 422
    raw = _dataset(client, tok, eng, DUMMY, validate=False)
    r = client.post("/v1/input-vat-check", headers=auth(tok), json={"dataset_id": raw})
    assert r.status_code in (409, 422), r.text
    assert client.get("/v1/input-vat-check/nope", headers=auth(tok)).status_code == 404
    assert client.get("/v1/input-vat-check/nope/exceptions",
                      headers=auth(tok)).status_code == 404
    b = _run(client, tok, did, effective_date_override=TEST_EFF)
    rid = b["input_vat_run_id"]
    assert client.get(f"/v1/input-vat-check/{rid}", headers=auth(outsider)).status_code == 403


def test_input_vat_job_failure_marks_run(client: TestClient, token: Callable[..., str],
                                         engagement: str, monkeypatch: Any) -> None:
    import app.services.input_vat as iv
    from app.core.db import session_factory
    from app.models import InputVatRun

    tok = token()
    did = _setup(client, tok, engagement)

    def boom(*a: Any, **k: Any) -> Any:
        raise iv.InputVatError("Rule missing.")

    monkeypatch.setattr(iv, "run_input_vat", boom)
    r = client.post("/v1/input-vat-check", headers=auth(tok), json={"dataset_id": did})
    acc = r.json()
    job = client.get(acc["status_url"], headers=auth(tok)).json()
    assert job["status"] == "failed" and "Rule missing" in str(job)
    with session_factory()() as s:
        run = s.get(InputVatRun, acc["input_vat_run_id"])
        assert run is not None and run.status == "failed"
