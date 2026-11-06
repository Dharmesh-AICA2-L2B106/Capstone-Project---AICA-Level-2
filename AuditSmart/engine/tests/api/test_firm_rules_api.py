"""D42 multi-firm rules: /v1/firm/rules/* review / approve / override / reject, firm scoping
of resolution and STALE marking, and no leakage between firms."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.api.test_sampling_api import DUMMY, _body, _dataset
from tests.conftest import auth

OK = {"comment": "Reviewed against our firm methodology."}
TAX_KEY = "vat.rate.SR"
METHOD_KEY = "sampling.mus.cf.95"


def _db() -> Any:
    from app.core.db import session_factory

    return session_factory()()


@pytest.fixture
def firms(client: TestClient, token: Callable[..., str], engagement: str) -> dict[str, Any]:
    """firm-a owns the DUMMY01 engagement (user-1 Manager); firm-b owns a second one."""
    from app.models import Client, Engagement, EngagementMember

    admin = token(sub="platform", roles=["Admin"])
    for fid in ("firm-a", "firm-b"):
        r = client.post("/v1/firms", headers=auth(admin), json={"id": fid, "name": fid.upper()})
        assert r.status_code == 201, r.text
    with _db() as s:
        c = Client(client_code="OTHER01", name="Other LLC", emirate="Sharjah")
        s.add(c)
        s.flush()
        e = Engagement(client_id=c.id, fye=date(2025, 12, 31))
        s.add(e)
        s.flush()
        s.add(EngagementMember(engagement_id=e.id, user_id="b-mgr", role="Manager"))
        s.commit()
        eng_b, client_b = e.id, c.id
        client_a = s.get(Engagement, engagement).client_id
    assert client.put(f"/v1/firms/firm-a/clients/{client_a}",
                      headers=auth(admin)).status_code == 200
    assert client.put(f"/v1/firms/firm-b/clients/{client_b}",
                      headers=auth(admin)).status_code == 200

    def tok(firm: str, sub: str, *roles: str) -> str:
        return token(sub=sub, roles=list(roles), extra={"firm_id": firm})

    return {"eng_a": engagement, "eng_b": eng_b, "client_a": client_a, "admin": admin,
            "a_mgr": tok("firm-a", "user-1", "Manager"),
            "a_tp": tok("firm-a", "a-tp", "TaxPartner"),
            "a_p": tok("firm-a", "a-p", "Partner"),
            "a_staff": tok("firm-a", "user-2", "Staff"),
            "a_admin": tok("firm-a", "a-admin", "Admin"),
            "b_mgr": tok("firm-b", "b-mgr", "Manager"),
            "b_tp": tok("firm-b", "b-tp", "TaxPartner"),
            "b_p": tok("firm-b", "b-p", "Partner")}


def _resolve(client: TestClient, tok: str, key: str, **q: str) -> Any:
    qs = "&".join(f"{k}={v}" for k, v in {"on": "2025-06-30", **q}.items())
    return client.get(f"/v1/rules/resolve/{key}?{qs}", headers=auth(tok))


def _item(client: TestClient, tok: str, key: str, **q: str) -> dict[str, Any]:
    qs = "&".join(f"{k}={v}" for k, v in {"on": "2025-06-30", **q}.items())
    r = client.get(f"/v1/firm/rules/review?{qs}", headers=auth(tok))
    assert r.status_code == 200, r.text
    return next(i for i in r.json()["items"] if i["rule_key"] == key)


def _audit(action: str) -> list[Any]:
    from app.models import AuditLog

    with _db() as s:
        return list(s.scalars(select(AuditLog).where(AuditLog.action == action)))


def test_platform_firm_management(client: TestClient, token: Callable[..., str],
                                  firms: dict[str, Any]) -> None:
    admin = firms["admin"]
    body = {"id": "firm-a", "name": "Dup"}
    assert client.post("/v1/firms", headers=auth(admin), json=body).status_code == 409
    assert client.post("/v1/firms", headers=auth(firms["a_admin"]),
                       json={"id": "x1", "name": "X1"}).status_code == 403
    assert client.post("/v1/firms", headers=auth(token()),
                       json={"id": "x1", "name": "X1"}).status_code == 403
    ca = firms["client_a"]
    assert client.put(f"/v1/firms/firm-a/clients/{ca}", headers=auth(admin)).json() == {
        "client_id": ca, "firm_id": "firm-a"}  # idempotent
    assert client.put(f"/v1/firms/firm-b/clients/{ca}", headers=auth(admin)).status_code == 409
    assert client.put("/v1/firms/firm-b/clients/nope", headers=auth(admin)).status_code == 404
    assert client.put(f"/v1/firms/nope/clients/{ca}", headers=auth(admin)).status_code == 404
    assert client.put(f"/v1/firms/firm-a/clients/{ca}",
                      headers=auth(firms["a_admin"])).status_code == 403
    assert len(_audit("firm_create")) == 2 and len(_audit("client_firm")) == 2


def test_my_firm_requires_registered_firm(client: TestClient, token: Callable[..., str],
                                          firms: dict[str, Any]) -> None:
    assert client.get("/v1/firm", headers=auth(token())).status_code == 403
    ghost = token(extra={"firm_id": "ghost"})
    r = client.get("/v1/firm/rules/review", headers=auth(ghost))
    assert r.status_code == 403 and "not registered" in r.json()["detail"]
    me = client.get("/v1/firm", headers=auth(firms["a_mgr"])).json()
    assert me == {"id": "firm-a", "name": "FIRM-A", "require_approved_rules": False,
                  "rules_allow_pending": True, "pending_rules_resolve": True}


def test_review_lists_defaults_pending_for_every_firm(client: TestClient,
                                                      firms: dict[str, Any]) -> None:
    r = client.get("/v1/firm/rules/review?on=2025-06-30", headers=auth(firms["a_staff"]))
    assert r.status_code == 200
    body = r.json()
    assert body["firm"]["id"] == "firm-a" and body["summary"]["total"] == len(body["items"]) > 40
    assert body["summary"]["approved_by_firm"] == 0 and body["summary"]["overridden"] == 0
    item = next(i for i in body["items"] if i["rule_key"] == TAX_KEY)
    assert item["review_status"] == "awaiting_firm_approval"
    assert item["default"]["ref"] == "vat.rate.SR@v1"
    assert item["effective"]["status"] == "pending_verification"
    assert item["approver_roles"] == ["TaxPartner"]
    assert _item(client, firms["a_mgr"], METHOD_KEY)["approver_roles"] == ["Partner"]
    r = client.get("/v1/firm/rules/review?domain=input_vat", headers=auth(firms["a_mgr"]))
    assert {i["domain"] for i in r.json()["items"]} == {"INPUT_VAT"}
    r = client.get("/v1/firm/rules/review?status=approved_by_firm", headers=auth(firms["a_mgr"]))
    assert r.json()["items"] == []
    r = client.get("/v1/firm/rules/review?on=1990-01-01&domain=vat",
                   headers=auth(firms["a_mgr"]))
    assert {i["review_status"] for i in r.json()["items"]} == {"not_effective"}
    assert client.get("/v1/firm/rules/review?status=bogus",
                      headers=auth(firms["a_mgr"])).status_code == 422
    # engagement view: must be the firm's engagement and a member
    eb = firms["eng_b"]
    assert client.get(f"/v1/firm/rules/review?engagement_id={eb}",
                      headers=auth(firms["a_mgr"])).status_code == 404
    assert client.get(f"/v1/firm/rules/review?engagement_id={firms['eng_a']}",
                      headers=auth(firms["a_tp"])).status_code == 403
    assert client.get(f"/v1/firm/rules/review?engagement_id={firms['eng_a']}",
                      headers=auth(firms["a_mgr"])).status_code == 200


def test_partner_approves_default_for_own_firm_only(client: TestClient,
                                                    firms: dict[str, Any]) -> None:
    url = f"/v1/firm/rules/{TAX_KEY}/approve"
    assert client.post(url, headers=auth(firms["a_mgr"]), json=OK).status_code == 403
    assert client.post(url, headers=auth(firms["a_p"]), json=OK).status_code == 403  # tax rule
    assert client.post(url, headers=auth(firms["a_admin"]), json=OK).status_code == 403
    assert client.post(url, headers=auth(firms["a_tp"]),
                       json={"comment": "short"}).status_code == 422
    r = client.post(url, headers=auth(firms["a_tp"]), json={**OK, "on": "2025-06-30"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["action"] == "default_approved" and out["stale"] == []
    assert out["rule"]["ref"] == "vat.rate.SR@v1" and out["rule"]["status"] == "approved"
    assert out["rule"]["firm_approved"] is True and out["rule"]["layer"] == "default"
    assert client.post(url, headers=auth(firms["a_tp"]), json=OK).status_code == 409
    # firm A now resolves it as approved; firm B and platform users still see pending
    ra = _resolve(client, firms["a_mgr"], TAX_KEY).json()
    assert ra["status"] == "approved" and ra["ref"] == "vat.rate.SR@v1"
    assert _resolve(client, firms["b_mgr"], TAX_KEY).json()["status"] == "pending_verification"
    assert _item(client, firms["b_mgr"], TAX_KEY)["review_status"] == "awaiting_firm_approval"
    item = _item(client, firms["a_mgr"], TAX_KEY)
    assert item["review_status"] == "approved_by_firm"
    assert item["firm_approval"]["approved_by"] == "a-tp"
    # the shared row itself is untouched
    from app.models import RuleVersion

    with _db() as s:
        row = s.scalars(select(RuleVersion).where(RuleVersion.rule_key == TAX_KEY)).one()
        assert row.status == "pending_verification" and row.approved_by is None
    logs = _audit("firm_rule_approve")
    assert len(logs) == 1 and logs[0].user_id == "a-tp" and logs[0].new["firm_id"] == "firm-a"
    # methodology rule: the Partner approves, the Tax Partner cannot
    murl = f"/v1/firm/rules/{METHOD_KEY}/approve"
    assert client.post(murl, headers=auth(firms["a_tp"]), json=OK).status_code == 403
    assert client.post(murl, headers=auth(firms["a_p"]), json=OK).status_code == 200
    # nothing effective on that date / unknown version
    assert client.post(url, headers=auth(firms["b_tp"]),
                       json={**OK, "on": "1990-01-01"}).status_code == 404
    assert client.post(url, headers=auth(firms["b_tp"]),
                       json={**OK, "version_id": "nope"}).status_code == 404
    # a specific default version by id
    vid = item["default"]["id"]
    r = client.post(url, headers=auth(firms["b_tp"]), json={**OK, "version_id": vid})
    assert r.status_code == 200 and r.json()["firm_id"] == "firm-b"


def test_approving_a_closed_default_is_refused(client: TestClient,
                                               firms: dict[str, Any]) -> None:
    from app.models import RuleVersion

    with _db() as s:
        row = s.scalars(select(RuleVersion).where(RuleVersion.rule_key == TAX_KEY)).one()
        row.status = "superseded"
        s.commit()
        vid = row.id
    r = client.post(f"/v1/firm/rules/{TAX_KEY}/approve", headers=auth(firms["a_tp"]),
                    json={**OK, "version_id": vid})
    assert r.status_code == 409


def test_require_approved_rules_tightens_one_firm(client: TestClient,
                                                  firms: dict[str, Any]) -> None:
    body = {"require_approved_rules": True, **OK}
    assert client.patch("/v1/firm/settings", headers=auth(firms["a_staff"]),
                        json=body).status_code == 403
    assert client.patch("/v1/firm/settings", headers=auth(firms["a_p"]),
                        json={**body, "comment": "x"}).status_code == 422
    r = client.patch("/v1/firm/settings", headers=auth(firms["a_p"]), json=body)
    assert r.status_code == 200 and r.json()["pending_rules_resolve"] is False
    r = _resolve(client, firms["a_mgr"], TAX_KEY)
    assert r.status_code == 404 and "awaits approval by the firm's audit partner" in r.text
    assert _resolve(client, firms["b_mgr"], TAX_KEY).status_code == 200  # firm B unaffected
    item = _item(client, firms["a_mgr"], TAX_KEY)
    assert item["effective"] is None and "awaits approval" in item["effective_error"]
    client.post(f"/v1/firm/rules/{TAX_KEY}/approve", headers=auth(firms["a_tp"]), json=OK)
    assert _resolve(client, firms["a_mgr"], TAX_KEY).json()["status"] == "approved"
    assert len(_audit("firm_settings")) == 1


def test_override_lifecycle_and_isolation(client: TestClient, token: Callable[..., str],
                                          firms: dict[str, Any]) -> None:
    key = "sampling.min_n"
    url = f"/v1/firm/rules/{key}/override"
    body = {"value": 30, "effective_from": "2025-01-01", **OK}
    assert client.post(url, headers=auth(firms["a_staff"]), json=body).status_code == 403
    assert client.post(url, headers=auth(firms["a_mgr"]),
                       json={**body, "comment": "x"}).status_code == 422
    assert client.post("/v1/firm/rules/no.such.rule/override", headers=auth(firms["a_mgr"]),
                       json=body).status_code == 404
    assert client.post(url, headers=auth(firms["a_mgr"]),
                       json={**body, "engagement_id": firms["eng_b"]}).status_code == 404
    r = client.post(url, headers=auth(firms["a_mgr"]), json=body)
    assert r.status_code == 201, r.text
    prop = r.json()
    assert prop["status"] == "proposed" and prop["firm_id"] == "firm-a"
    assert prop["layer"] == "firm" and prop["unit"] == _item(
        client, firms["a_mgr"], key)["default"]["unit"]
    vid = prop["id"]
    assert len(_audit("firm_rule_override")) == 1
    # visible only to firm A
    assert len(_item(client, firms["a_mgr"], key)["open_proposals"]) == 1
    assert _item(client, firms["b_mgr"], key)["open_proposals"] == []
    listed = client.get(f"/v1/rules?rule_key={key}", headers=auth(firms["a_mgr"])).json()
    assert vid in {v["id"] for v in listed}
    for other in (firms["b_mgr"], token()):
        listed = client.get(f"/v1/rules?rule_key={key}", headers=auth(other)).json()
        assert vid not in {v["id"] for v in listed}
    # other firm cannot act on it, through either API
    assert client.post(f"/v1/firm/rules/{key}/approve", headers=auth(firms["b_p"]),
                       json={**OK, "version_id": vid}).status_code == 404
    assert client.post(f"/v1/rules/{vid}/approve", headers=auth(firms["b_p"]),
                       json=OK).status_code == 404
    assert client.post(f"/v1/firm/rules/{key}/reject", headers=auth(firms["b_p"]),
                       json={**OK, "version_id": vid}).status_code == 404
    # the platform approver cannot approve a firm row either (it is not a default)
    tp = token(sub="tp-1", roles=["TaxPartner"])
    assert client.post(f"/v1/rules/{vid}/approve", headers=auth(tp), json=OK).status_code == 404
    # wrong role in firm A (methodology rule -> Partner)
    assert client.post(f"/v1/firm/rules/{key}/approve", headers=auth(firms["a_tp"]),
                       json={**OK, "version_id": vid}).status_code == 403
    r = client.post(f"/v1/firm/rules/{key}/approve", headers=auth(firms["a_p"]),
                    json={**OK, "version_id": vid})
    assert r.status_code == 200, r.text
    assert r.json()["action"] == "override_approved" and r.json()["closed"] == []
    ref = f"{key}@v{prop['version']}"
    assert _resolve(client, firms["a_mgr"], key).json()["ref"] == ref
    assert _resolve(client, firms["b_mgr"], key).json()["ref"] == f"{key}@v1"
    assert _resolve(client, token(), key).json()["ref"] == f"{key}@v1"
    item = _item(client, firms["a_mgr"], key)
    assert item["review_status"] == "overridden" and item["firm_override"]["ref"] == ref
    assert item["effective"]["layer"] == "firm"
    # a second firm proposal, rejected
    r = client.post(url, headers=auth(firms["a_mgr"]),
                    json={**body, "value": 40, "effective_from": "2027-01-01"})
    v2 = r.json()["id"]
    assert client.post(f"/v1/firm/rules/{key}/reject", headers=auth(firms["a_p"]),
                       json={**OK, "version_id": v2}).json()["status"] == "rejected"
    assert client.post(f"/v1/firm/rules/{TAX_KEY}/reject", headers=auth(firms["a_p"]),
                       json={**OK, "version_id": v2}).status_code == 404


def test_firm_users_cannot_change_shared_defaults(client: TestClient,
                                                  firms: dict[str, Any]) -> None:
    body = {"rule_key": TAX_KEY, "value": "0.05", "effective_from": "2027-01-01"}
    r = client.post("/v1/rules/proposals", headers=auth(firms["a_tp"]), json=body)
    assert r.status_code == 403 and "/v1/firm/rules/" in r.json()["detail"]
    vid = _item(client, firms["a_tp"], TAX_KEY)["default"]["id"]
    for path in ("approve", "reject"):
        r = client.post(f"/v1/rules/{vid}/{path}", headers=auth(firms["a_tp"]), json=OK)
        assert r.status_code == 403


def test_engagement_override_and_membership(client: TestClient,
                                            firms: dict[str, Any]) -> None:
    key = "je.round_sum.min"
    ea = firms["eng_a"]
    body = {"value": "50000", "effective_from": "2025-01-01", "engagement_id": ea, **OK}
    assert client.post(f"/v1/firm/rules/{key}/override", headers=auth(firms["a_tp"]),
                       json=body).status_code == 403  # not a member of the engagement
    r = client.post(f"/v1/firm/rules/{key}/override", headers=auth(firms["a_mgr"]), json=body)
    assert r.status_code == 201 and r.json()["layer"] == "engagement"
    vid = r.json()["id"]
    # the approving Partner must also be on the engagement
    assert client.post(f"/v1/firm/rules/{key}/approve", headers=auth(firms["a_p"]),
                       json={**OK, "version_id": vid}).status_code == 403
    from app.models import EngagementMember

    with _db() as s:
        s.add(EngagementMember(engagement_id=ea, user_id="a-p", role="Partner"))
        s.commit()
    r = client.post(f"/v1/firm/rules/{key}/approve", headers=auth(firms["a_p"]),
                    json={**OK, "version_id": vid})
    assert r.status_code == 200, r.text
    ref = r.json()["rule"]["ref"]
    assert _resolve(client, firms["a_mgr"], key, engagement_id=ea).json()["ref"] == ref
    assert _resolve(client, firms["a_mgr"], key).json()["ref"] == f"{key}@v1"
    assert _resolve(client, firms["b_mgr"], key,
                    engagement_id=firms["eng_b"]).json()["ref"] == f"{key}@v1"
    item = _item(client, firms["a_mgr"], key, engagement_id=ea)
    assert item["engagement_override"]["ref"] == ref and item["review_status"] == "overridden"
    # firm B cannot resolve in firm A's engagement
    assert _resolve(client, firms["b_mgr"], key, engagement_id=ea).status_code == 403


def test_member_row_cannot_cross_firms(client: TestClient, firms: dict[str, Any]) -> None:
    from app.models import EngagementMember

    with _db() as s:  # a stray membership of a firm-B user on a firm-A engagement
        s.add(EngagementMember(engagement_id=firms["eng_a"], user_id="b-mgr", role="Manager"))
        s.commit()
    r = _resolve(client, firms["b_mgr"], TAX_KEY, engagement_id=firms["eng_a"])
    assert r.status_code == 403 and "another firm" in r.json()["detail"]


def test_firm_override_stales_only_that_firms_results(client: TestClient,
                                                      firms: dict[str, Any]) -> None:
    from app.models import Sample

    sa = client.post("/v1/sample", headers=auth(firms["a_mgr"]), json=_body(
        _dataset(client, firms["a_mgr"], firms["eng_a"], DUMMY))).json()
    sb = client.post("/v1/sample", headers=auth(firms["b_mgr"]), json=_body(
        _dataset(client, firms["b_mgr"], firms["eng_b"], DUMMY))).json()
    assert sa["cf_rule_version"] == sb["cf_rule_version"] == f"{METHOD_KEY}@v1"
    assert sa["rules_pending_verification"] is True
    r = client.post(f"/v1/firm/rules/{METHOD_KEY}/override", headers=auth(firms["a_mgr"]),
                    json={"value": "3.10", "effective_from": "2025-01-01", **OK})
    vid = r.json()["id"]
    r = client.post(f"/v1/firm/rules/{METHOD_KEY}/approve", headers=auth(firms["a_p"]),
                    json={**OK, "version_id": vid})
    assert r.status_code == 200
    assert [x["id"] for x in r.json()["stale"]] == [sa["sample_id"]]
    with _db() as s:
        assert s.get(Sample, sa["sample_id"]).status == "STALE"
        assert s.get(Sample, sb["sample_id"]).status != "STALE"
    # a new firm-A sample uses the firm's value; firm B keeps the default
    sa2 = client.post("/v1/sample", headers=auth(firms["a_mgr"]), json=_body(
        _dataset(client, firms["a_mgr"], firms["eng_a"], DUMMY))).json()
    assert sa2["cf_rule_version"] == r.json()["rule"]["ref"] and sa2["cf_value"] == "3.10"
    sb2 = client.post("/v1/sample", headers=auth(firms["b_mgr"]), json=_body(
        _dataset(client, firms["b_mgr"], firms["eng_b"], DUMMY))).json()
    assert sb2["cf_value"] == "3.00" and sb2["n_required"] == 161  # golden unchanged


def test_jobs_run_in_the_engagement_firm_scope(client: TestClient,
                                               firms: dict[str, Any]) -> None:
    from app.services import jobs, rules

    seen: list[rules.RuleScope] = []

    def fn(job_id: str) -> str:
        seen.append(rules.current_scope())
        return "ok"

    jobs.submit("probe", fn, engagement_id=firms["eng_a"])
    jobs.submit("probe", fn)
    assert seen[0] == rules.RuleScope(firm_id="firm-a", engagement_id=firms["eng_a"])
    assert seen[1] == rules.NO_SCOPE
    assert rules.current_scope() == rules.NO_SCOPE
    # a JE run (background job) records firm A's override, firm B the default
    key = "je.round_sum.min"
    r = client.post(f"/v1/firm/rules/{key}/override", headers=auth(firms["a_mgr"]),
                    json={"value": "20000", "effective_from": "2025-01-01", **OK})
    client.post(f"/v1/firm/rules/{key}/approve", headers=auth(firms["a_p"]),
                json={**OK, "version_id": r.json()["id"]})

    def je(tok: str, eng: str) -> dict[str, Any]:
        did = _dataset(client, tok, eng, DUMMY)
        j = client.post("/v1/je-tests", headers=auth(tok), json={"dataset_id": did}).json()
        return dict(client.get(j["result_url"], headers=auth(tok)).json())

    used_a = je(firms["a_mgr"], firms["eng_a"])["rule_versions_used"]
    used_b = je(firms["b_mgr"], firms["eng_b"])["rule_versions_used"]
    assert used_a[key]["version"] == r.json()["version"] and used_a[key]["value"] == "20000"
    assert used_b[key]["version"] == 1
