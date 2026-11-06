"""Prompt 3.2 API: uploads (chunked + multipart), async parse/validate jobs, errors, rows, guard."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.api.v1.datasets import ValidatedDataset
from tests.conftest import DATA, auth

EDGE = (DATA / "edge_cases.csv").read_bytes()
DUMMY = (DATA / "dummy_gl.csv").read_bytes()


def _multipart(client: TestClient, tok: str, eng: str, data: bytes, name: str = "gl.csv",
               **form: str) -> Any:
    return client.post("/v1/datasets", headers=auth(tok),
                       data={"engagement_id": eng, **form}, files={"file": (name, data)})


def _chunked(client: TestClient, tok: str, eng: str, data: bytes, chunk: int,
             sha: str | None = None) -> Any:
    r = client.post("/v1/uploads", headers=auth(tok),
                    json={"engagement_id": eng, "file_name": "dummy_gl.csv",
                          "size_bytes": len(data)})
    assert r.status_code == 201, r.text
    sid = r.json()["dataset_id"]
    assert r.json()["chunk_size_bytes"] == 1024 * 1024
    for i in range(0, len(data), chunk):
        a = client.put(f"/v1/uploads/{sid}/chunks/{i // chunk}", headers=auth(tok),
                       content=data[i:i + chunk])
        assert a.status_code == 200, a.text
    return client.post(f"/v1/uploads/{sid}/complete", headers=auth(tok),
                       json={"sha256": sha} if sha else {})


def test_multipart_edge_upload_blocks(client: TestClient, token: Callable[..., str],
                                      engagement: str) -> None:
    tok = token()
    r = _multipart(client, tok, engagement, EDGE)
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["sha256"] == hashlib.sha256(EDGE).hexdigest()
    assert body["mapping_suggestion"]["posting_date"] == "posting_date"
    assert body["status"] == "parsed" and body["profile"]["rows"] == 60
    did = body["dataset_id"]
    job = client.get(f"/v1/jobs/{body['job_id']}", headers=auth(tok)).json()
    assert job["status"] == "succeeded" and job["progress"] == 100

    v = client.post(f"/v1/datasets/{did}/validate?wait=true", headers=auth(tok))
    assert v.status_code == 202
    res = v.json()
    assert res["blocked"] and res["critical"] == 8 and res["warnings"] == 3
    assert res["status"] == "blocked"
    first = res["errors"][0]
    assert first["code"] == "unbalanced_voucher" and first["rows"] == [1, 2]
    assert "Voucher EV-001 is out of balance by AED 0.05" in first["message"]

    e = client.get(f"/v1/datasets/{did}/errors", headers=auth(tok)).json()
    assert e == res
    ds = client.get(f"/v1/datasets/{did}", headers=auth(tok)).json()
    assert ds["status"] == "blocked" and ds["profile"]["validation"]["critical"] == 8
    assert ds["total_dr"] != ds["total_cr"]


def test_chunked_dummy_upload_validates(client: TestClient, token: Callable[..., str],
                                        engagement: str) -> None:
    tok = token()
    r = _chunked(client, tok, engagement, DUMMY, 100_000, hashlib.sha256(DUMMY).hexdigest())
    assert r.status_code == 202, r.text
    did = r.json()["dataset_id"]
    ds = client.get(f"/v1/datasets/{did}", headers=auth(tok)).json()
    assert ds["rows"] == 3000 and ds["profile"]["chunks"] == 3
    assert ds["total_dr"].startswith("35728611.45")
    v = client.post(f"/v1/datasets/{did}/validate", headers=auth(tok))
    assert v.status_code == 202 and "job_id" in v.json()
    job = client.get(f"/v1/jobs/{v.json()['job_id']}", headers=auth(tok)).json()
    assert job["status"] == "succeeded"
    res = client.get(f"/v1/datasets/{did}/errors", headers=auth(tok)).json()
    assert res["status"] == "validated" and res["critical"] == 0
    assert [x["code"] for x in res["errors"]] == ["invalid_trn"]

    page = client.get(f"/v1/datasets/{did}/rows?offset=10&limit=5", headers=auth(tok)).json()
    assert page["total"] == 3000 and len(page["rows"]) == 5 and page["rows"][0]["row_no"] == 11
    assert isinstance(page["rows"][0]["debit"], str)
    voucher = page["rows"][0]["voucher_no"]
    f = client.get(f"/v1/datasets/{did}/rows", params={"voucher_no": voucher},
                   headers=auth(tok)).json()
    assert f["total"] >= 2 and {x["voucher_no"] for x in f["rows"]} == {voucher}
    a = client.get(f"/v1/datasets/{did}/rows", params={"account_code": "nope"},
                   headers=auth(tok)).json()
    assert a["total"] == 0
    assert client.get(f"/v1/datasets/{did}/rows?limit=5000", headers=auth(tok)).status_code == 422


def test_chunk_protocol_errors(client: TestClient, token: Callable[..., str],
                               engagement: str) -> None:
    tok = token()
    bad = _chunked(client, tok, engagement, EDGE, 1000, "0" * 64)
    assert bad.status_code == 409 and "SHA-256" in bad.json()["detail"]

    r = client.post("/v1/uploads", headers=auth(tok), json={
        "engagement_id": engagement, "file_name": "x.csv", "size_bytes": 10})
    sid = r.json()["dataset_id"]
    assert client.put(f"/v1/uploads/{sid}/chunks/0", headers=auth(tok),
                      content=b"x" * 11).status_code == 413
    assert client.put(f"/v1/uploads/{sid}/chunks/1", headers=auth(tok),
                      content=b"x" * 5).status_code == 200
    missing = client.post(f"/v1/uploads/{sid}/complete", headers=auth(tok), json={})
    assert missing.status_code == 409 and "missing" in missing.json()["detail"]
    assert client.put(f"/v1/uploads/{sid}/chunks/0", headers=auth(tok),
                      content=b"y" * 4).status_code == 200
    short = client.post(f"/v1/uploads/{sid}/complete", headers=auth(tok), json={})
    assert short.status_code == 409 and "declared" in short.json()["detail"]
    assert client.put(f"/v1/uploads/{sid}/chunks/-1", headers=auth(tok),
                      content=b"y").status_code == 400

    too_big = client.post("/v1/uploads", headers=auth(tok), json={
        "engagement_id": engagement, "file_name": "x.csv", "size_bytes": 501 * 1024 * 1024})
    assert too_big.status_code == 413
    pdf = client.post("/v1/uploads", headers=auth(tok), json={
        "engagement_id": engagement, "file_name": "x.pdf", "size_bytes": 10})
    assert pdf.status_code == 415
    big = client.put(f"/v1/uploads/{sid}/chunks/2", headers=auth(tok),
                     content=b"z" * (1024 * 1024 + 1))
    assert big.status_code == 413


def test_upload_done_twice_and_size_cap(client: TestClient, token: Callable[..., str],
                                        engagement: str, monkeypatch: pytest.MonkeyPatch) -> None:
    tok = token()
    r = _chunked(client, tok, engagement, EDGE, 4096)
    sid = r.json()["dataset_id"]
    assert client.post(f"/v1/uploads/{sid}/complete", headers=auth(tok),
                       json={}).status_code == 409
    assert client.put(f"/v1/uploads/{sid}/chunks/0", headers=auth(tok),
                      content=b"a").status_code == 409
    monkeypatch.setenv("MAX_UPLOAD_MB", "0")
    from app.core.config import reset_settings

    reset_settings()
    over = _multipart(client, tok, engagement, b"line_id\n1\n")
    assert over.status_code == 413 and "larger" in over.json()["detail"]


def test_mapping_override_and_reparse(client: TestClient, token: Callable[..., str],
                                      engagement: str) -> None:
    tok = token()
    csv = b"Ref,When,Jv,Acc,Dr,Cr\n1,2025-01-05,J1,6100,10,0\n2,2025-01-05,J1,2010,0,10\n"
    r = _multipart(client, tok, engagement, csv)
    did = r.json()["dataset_id"]
    v = client.post(f"/v1/datasets/{did}/validate?wait=true", headers=auth(tok)).json()
    assert v["blocked"] and {e["code"] for e in v["errors"]} == {"missing_mandatory_column"}
    m = client.put(f"/v1/datasets/{did}/mapping", headers=auth(tok), json={"mapping_override": {
        "line_id": "Ref", "posting_date": "When", "voucher_no": "Jv", "account_code": "Acc"}})
    assert m.status_code == 202
    assert client.get(f"/v1/datasets/{did}/errors", headers=auth(tok)).json()["errors"] == []
    v2 = client.post(f"/v1/datasets/{did}/validate?wait=true", headers=auth(tok)).json()
    assert v2["status"] == "validated" and v2["errors"] == []

    form = _multipart(client, tok, engagement, csv, mapping_override=json.dumps(
        {"line_id": "Ref", "posting_date": "When", "voucher_no": "Jv", "account_code": "Acc"}))
    assert form.json()["mapping_suggestion"]["line_id"] == "Ref"
    assert _multipart(client, tok, engagement, csv, mapping_override="[1]").status_code == 422
    bad = _multipart(client, tok, engagement, csv, mapping_override='{"zzz": "Ref"}')
    assert bad.status_code == 422  # D56: was 400; a bad mapping is now a 422 with a reason
    assert "Unknown field 'zzz'" in bad.json()["detail"]


def test_tb_comparison(client: TestClient, token: Callable[..., str], engagement: str) -> None:
    tok = token()
    gl = _multipart(client, tok, engagement,
                    b"line_id,posting_date,voucher_no,account_code,debit,credit\n"
                    b"1,2025-01-05,J1,6100,10,0\n2,2025-01-05,J1,2010,0,10\n").json()["dataset_id"]
    tb = _multipart(client, tok, engagement, b"Account,Balance\n6100,10\n2010,-9\n",
                    name="tb.csv", kind="TB").json()["dataset_id"]
    res = client.post(f"/v1/datasets/{gl}/validate?wait=true", headers=auth(tok),
                      json={"tb_dataset_id": tb}).json()
    assert [e["code"] for e in res["errors"]] == ["gl_tb_difference"]
    assert res["status"] == "validated"
    wrong = client.post(f"/v1/datasets/{gl}/validate?wait=true", headers=auth(tok),
                        json={"tb_dataset_id": gl})
    assert wrong.status_code == 400


def test_membership_and_roles(client: TestClient, token: Callable[..., str],
                              engagement: str) -> None:
    did = _multipart(client, token(), engagement, EDGE).json()["dataset_id"]
    outsider = token(sub="user-9")
    for path in (f"/v1/datasets/{did}", f"/v1/datasets/{did}/errors", f"/v1/datasets/{did}/rows"):
        assert client.get(path, headers=auth(outsider)).status_code == 403
    assert _multipart(client, outsider, engagement, EDGE).status_code == 403
    assert client.get("/v1/datasets/nope", headers=auth(token())).status_code == 404
    assert client.get("/v1/jobs/nope", headers=auth(token())).status_code == 404
    assert client.get(f"/v1/datasets/{did}").status_code == 401
    staff = token(sub="user-2", roles=["Staff"])
    assert client.get(f"/v1/datasets/{did}", headers=auth(staff)).status_code == 200


def test_job_without_engagement_visible_to_creator_only(client: TestClient,
                                                        token: Callable[..., str]) -> None:
    from app.services import jobs

    jid = jobs.submit("misc", lambda _j: "ok", engagement_id=None, created_by="user-1")
    assert client.get(f"/v1/jobs/{jid}", headers=auth(token())).json()["result_ref"] == "ok"
    assert client.get(f"/v1/jobs/{jid}", headers=auth(token(sub="user-2"))).status_code == 404

    def boom(_j: str) -> str:
        raise RuntimeError("secret detail")

    jid2 = jobs.submit("misc", boom, engagement_id=None, created_by="user-1")
    j = client.get(f"/v1/jobs/{jid2}", headers=auth(token())).json()
    assert j["status"] == "failed" and "secret" not in (j["error"] or "")


def test_downstream_guard(env: Path, token: Callable[..., str], engagement: str) -> None:
    from app.main import create_app

    app: FastAPI = create_app()
    r = APIRouter()

    @r.get("/v1/_guarded/{dataset_id}")
    def guarded(ds: ValidatedDataset) -> dict[str, str]:
        return {"id": ds.id}

    app.include_router(r)
    with TestClient(app) as c:
        tok = token()
        edge = _multipart(c, tok, engagement, EDGE).json()["dataset_id"]
        assert "Validate" in c.get(f"/v1/_guarded/{edge}", headers=auth(tok)).json()["detail"]
        c.post(f"/v1/datasets/{edge}/validate?wait=true", headers=auth(tok))
        blocked = c.get(f"/v1/_guarded/{edge}", headers=auth(tok))
        assert blocked.status_code == 409 and "8 critical" in blocked.json()["detail"]
        clean = _multipart(c, tok, engagement, (DATA / "fy2021_2022.csv").read_bytes())
        cid = clean.json()["dataset_id"]
        c.post(f"/v1/datasets/{cid}/validate?wait=true", headers=auth(tok))
        assert c.get(f"/v1/_guarded/{cid}", headers=auth(tok)).json() == {"id": cid}


def test_async_executor_mode(client: TestClient, token: Callable[..., str], engagement: str,
                             monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import reset_settings
    from app.services import jobs

    monkeypatch.setenv("JOB_EAGER", "false")
    reset_settings()
    tok = token()
    r = _multipart(client, tok, engagement, EDGE)
    assert r.status_code == 202
    jobs.wait_all(timeout=30)
    did = r.json()["dataset_id"]
    assert client.get(f"/v1/datasets/{did}", headers=auth(tok)).json()["status"] == "parsed"
    done = client.get(f"/v1/jobs/{r.json()['job_id']}", headers=auth(tok)).json()
    assert done["status"] == "succeeded"


def test_xlsx_and_logs_scrubbed(client: TestClient, token: Callable[..., str], engagement: str,
                                tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["line_id", "posting_date", "voucher_no", "account_code", "debit", "credit",
               "party_name"])
    ws.append(["1", "2025-01-05", "J1", "6100", 10, 0, "Secret Vendor LLC"])
    ws.append(["2", "2025-01-05", "J1", "2010", 0, 10, "Secret Vendor LLC"])
    p = tmp_path / "g.xlsx"
    wb.save(p)
    r = _multipart(client, token(), engagement, p.read_bytes(), name="g.xlsx")
    assert r.status_code == 202 and r.json()["profile"]["rows"] == 2
    out = capsys.readouterr()
    assert "Secret Vendor" not in out.out + out.err
