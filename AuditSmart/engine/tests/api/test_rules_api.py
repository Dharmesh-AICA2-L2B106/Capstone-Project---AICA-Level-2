"""Prompt 3.8: /v1/rules + STALE marking of dependent results on approval."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from tests.api.test_workpaper_api import results  # noqa: F401  (fixture)
from tests.conftest import auth

OK = {"comment": "Checked against the FTA source text."}


def _status(model: str, id_: str) -> str:
    from app import models
    from app.core.db import session_factory

    with session_factory()() as s:
        return str(s.get(getattr(models, model), id_).status)


def test_list_resolve_propose(client: TestClient, token: Callable[..., str]) -> None:
    tok = token()
    r = client.get("/v1/rules?domain=input_vat", headers=auth(tok))
    assert r.status_code == 200 and len(r.json()) == 9
    r = client.get("/v1/rules/resolve/vat.rate.SR?on=2025-06-30", headers=auth(tok))
    assert r.json()["ref"] == "vat.rate.SR@v1" and r.json()["value"] == "0.05"
    r = client.get("/v1/rules/resolve/input_vat.verification.spend_threshold?on=2026-09-30",
                   headers=auth(tok))
    assert r.status_code == 404 and "No approved version" in r.json()["detail"]
    assert client.get("/v1/rules/resolve/vat.rate.SR", headers=auth(tok)).status_code == 200
    staff = token(sub="user-2", roles=["Staff"])
    body = {"rule_key": "vat.rate.SR", "value": "0.05", "effective_from": "2027-01-01"}
    assert client.post("/v1/rules/proposals", headers=auth(staff), json=body).status_code == 403
    assert client.post("/v1/rules/proposals", headers=auth(tok),
                       json={**body, "rule_key": "BAD"}).status_code == 422
    r = client.post("/v1/rules/proposals", headers=auth(tok), json=body)
    assert r.status_code == 201 and r.json()["status"] == "proposed"
    vid = r.json()["id"]
    # Manager cannot approve; Tax Partner can; comment mandatory
    assert client.post(f"/v1/rules/{vid}/approve", headers=auth(tok),
                       json=OK).status_code == 403
    tp = token(sub="tp-1", roles=["TaxPartner"])
    assert client.post(f"/v1/rules/{vid}/approve", headers=auth(tp),
                       json={"comment": "short"}).status_code == 422
    assert client.post(f"/v1/rules/{vid}/reject", headers=auth(tp),
                       json=OK).json()["status"] == "rejected"
    assert client.post(f"/v1/rules/{vid}/reject", headers=auth(tp), json=OK).status_code == 409


def test_resolve_conflict_is_409(client: TestClient, token: Callable[..., str]) -> None:
    from app.core.db import session_factory
    from app.models import RuleVersion
    from app.services import rules

    with session_factory()() as s:
        s.add(RuleVersion(rule_key="vat.rate.SR", version=7, value="0.05", status=
                          "pending_verification", effective_from=rules.date(2018, 1, 1)))
        s.commit()
    rules.invalidate()
    r = client.get("/v1/rules/resolve/vat.rate.SR?on=2025-01-01", headers=auth(token()))
    assert r.status_code == 409


def test_approval_marks_overlapping_results_stale(client: TestClient,
                                                 token: Callable[..., str],
                                                 results: dict[str, Any]) -> None:  # noqa: F811
    tok, body = results["tok"], results["body"]
    # D47: methodology keys (je.*, sampling.*) are approved by a Partner, never an Admin
    partner = token(sub="p-1", roles=["Partner"])
    admin = token(sub="adm-1", roles=["Admin"])
    sid, jid = body["sample_id"], body["je_run_id"]

    def approve(key: str, value: Any, frm: str) -> dict[str, Any]:
        p = client.post("/v1/rules/proposals", headers=auth(tok),
                        json={"rule_key": key, "value": value, "effective_from": frm})
        r = client.post(f"/v1/rules/{p.json()['id']}/approve", headers=auth(admin), json=OK)
        assert r.status_code == 403 and "Admin never approves" in r.text
        r = client.post(f"/v1/rules/{p.json()['id']}/reject", headers=auth(admin), json=OK)
        assert r.status_code == 403
        r = client.post(f"/v1/rules/{p.json()['id']}/approve", headers=auth(partner), json=OK)
        assert r.status_code == 200, r.text
        return dict(r.json())

    # a change effective after FY2025 does not touch FY2025 results
    a = approve("je.round_sum.min", "20000", "2027-01-01")
    assert a["closed"] == [{"ref": "je.round_sum.min@v1", "effective_to": "2026-12-31"}]
    assert a["stale"] == [] and _status("JeRun", jid) == "current"
    # a mid-FY2025 change to a sampling factor marks the sample STALE, not the JE run
    a = approve("sampling.mus.cf.95", "3.00", "2025-07-01")
    assert [s["id"] for s in a["stale"]] == [sid] and a["stale"][0]["kind"] == "sample"
    assert _status("Sample", sid) == "STALE" and _status("JeRun", jid) == "current"
    r = client.post("/v1/workpaper", headers=auth(tok), json=body)
    assert r.status_code == 409 and "STALE" in r.json()["detail"]
    # JE: an earlier-dated replacement of a closed seed version touches the JE run
    a = approve("je.period_end.days", 5, "2025-12-01")
    assert {s["kind"] for s in a["stale"]} == {"je_run"} and _status("JeRun", jid) == "STALE"
    # audit trail
    from sqlalchemy import select

    from app.core.db import session_factory
    from app.models import AuditLog

    with session_factory()() as s:
        acts = list(s.scalars(select(AuditLog.action).where(AuditLog.action == "stale")))
    assert len(acts) == 2
