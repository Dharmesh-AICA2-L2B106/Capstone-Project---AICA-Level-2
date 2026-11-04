"""Prompt 3.3 API: POST /v1/sample, GET /v1/samples/{id}, 409 guard, persistence."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import DATA, auth

DUMMY = (DATA / "dummy_gl.csv").read_bytes()
EDGE = (DATA / "edge_cases.csv").read_bytes()


def _dataset(client: TestClient, tok: str, eng: str, data: bytes, validate: bool = True) -> str:
    r = client.post("/v1/datasets", headers=auth(tok), data={"engagement_id": eng},
                    files={"file": ("gl.csv", data)})
    assert r.status_code == 202, r.text
    did = str(r.json()["dataset_id"])
    if validate:
        client.post(f"/v1/datasets/{did}/validate?wait=true", headers=auth(tok))
    return did


def _body(did: str, **kw: Any) -> dict[str, Any]:
    return {"dataset_id": did, "account_types": ["Expense"], "tolerable_misstatement": "280000",
            "seed": 2025, **kw}


def test_sample_golden_95_persisted(client: TestClient, token: Callable[..., str],
                                    engagement: str) -> None:
    tok = token()
    did = _dataset(client, tok, engagement, DUMMY)
    r = client.post("/v1/sample", headers=auth(tok), json=_body(did))
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["n_required"] == 161 and b["cf_value"] == "3.00"
    assert b["cf_rule_version"] == "sampling.mus.cf.95@v1"
    assert abs(Decimal(b["interval"]) - Decimal("77968.969378882")) < Decimal("0.01")
    assert b["top_stratum"]["count"] == 8 and b["credit_lines_excluded"]["count"] == 20
    assert b["random_start"] == "77536.85" and b["sample_size"] == 149
    assert b["dataset_hash"] and len(b["dataset_hash"]) == 64
    assert b["engine_version"].startswith("auditsmart-engine ")
    assert "Monetary unit sampling" in b["rationale"] and b["formula_text"].endswith("77,968.97")
    assert b["rules_pending_verification"] is True
    g = client.get(f"/v1/samples/{b['sample_id']}", headers=auth(tok))
    assert g.status_code == 200 and g.json() == b

    from app.core.db import session_factory
    from app.models import Sample, SampleItem

    with session_factory()() as s:
        smp = s.get(Sample, b["sample_id"])
        assert smp is not None and smp.seed == 2025 and smp.cf_value == Decimal("3")
        assert smp.file_hash == b["dataset_hash"] and smp.method == "mus"
        items = s.query(SampleItem).filter_by(sample_id=smp.id).all()
        assert len(items) == 149 and sum(i.top_stratum for i in items) == 8


def test_sample_90_and_other_methods(client: TestClient, token: Callable[..., str],
                                     engagement: str) -> None:
    tok = token()
    did = _dataset(client, tok, engagement, DUMMY)
    r = client.post("/v1/sample", headers=auth(tok), json=_body(did, confidence="90"))
    assert r.json()["n_required"] == 122
    r = client.post("/v1/sample", headers=auth(tok),
                    json=_body(did, method="stratified", sample_size=30, num_strata=3))
    assert r.status_code == 201 and r.json()["sample_size"] == 30
    r = client.post("/v1/sample", headers=auth(tok),
                    json=_body(did, method="random", sample_size=100_000))
    assert r.status_code == 422 and "larger than the population" in r.json()["detail"]


def test_sample_guard_and_access(client: TestClient, token: Callable[..., str],
                                 engagement: str) -> None:
    tok = token()
    blocked = _dataset(client, tok, engagement, EDGE)
    r = client.post("/v1/sample", headers=auth(tok), json=_body(blocked))
    assert r.status_code == 409 and "critical validation error" in r.json()["detail"]
    unvalidated = _dataset(client, tok, engagement, DUMMY, validate=False)
    r = client.post("/v1/sample", headers=auth(tok), json=_body(unvalidated))
    assert r.status_code == 409
    r = client.post("/v1/sample", headers=auth(tok), json=_body("nope"))
    assert r.status_code == 404
    outsider = token(sub="user-9")
    did = _dataset(client, tok, engagement, DUMMY)
    r = client.post("/v1/sample", headers=auth(outsider), json=_body(did))
    assert r.status_code == 403
    ok = client.post("/v1/sample", headers=auth(tok), json=_body(did)).json()
    assert client.get(f"/v1/samples/{ok['sample_id']}", headers=auth(outsider)).status_code == 403
    assert client.get("/v1/samples/missing", headers=auth(tok)).status_code == 404
    r = client.post("/v1/sample", headers=auth(tok), json=_body(did, bogus=1))
    assert r.status_code == 422
    r = client.post("/v1/sample", headers=auth(tok), json=_body(did, seed=2**31))
    assert r.status_code == 422
    assert client.post("/v1/sample", json=_body(did)).status_code == 401
