"""/v1/rules-monitor endpoints (prompt 3.9).  Fakes injected; no network."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.api.v1 import rules_monitor as api
from app.services import rules_monitor as mon
from tests.conftest import auth
from tests.unit.test_rules_monitor import D17_OUT, D17_PDF, D17_URL, FakeFetcher, fixed, pdf


def _tp(token: Any) -> dict[str, str]:
    return auth(token(sub="tp-1", roles=["TaxPartner"]))


def test_roles(client: TestClient, token: Any) -> None:
    for roles in (["Manager"], ["Partner"], ["Staff"]):
        h = auth(token(sub="u", roles=roles))
        assert client.get("/v1/rules-monitor/sources", headers=h).status_code == 403
    assert client.get("/v1/rules-monitor/sources",
                      headers=auth(token(sub="a", roles=["Admin"]))).status_code == 200


def test_sources_seeded_and_editable(client: TestClient, token: Any) -> None:
    h = _tp(token)
    srcs = client.get("/v1/rules-monitor/sources", headers=h).json()
    assert len(srcs) == 9
    ph = next(s for s in srcs if s["url"] == "urn:auditsmart:pending:vatp046")
    assert ph["active"] is False and ph["due"] is False
    r = client.patch(f"/v1/rules-monitor/sources/{ph['id']}", headers=h, json={"active": True})
    assert r.status_code == 422
    url = "https://tax.gov.ae/en/taxes/Vat/guides.references.aspx"
    assert client.patch(f"/v1/rules-monitor/sources/{ph['id']}", headers=h,
                        json={"url": url}).status_code == 409
    new_url = "https://tax.gov.ae/en/vatp046-recorded-by-tax-partner.pdf"
    r = client.patch(f"/v1/rules-monitor/sources/{ph['id']}", headers=h,
                     json={"url": new_url, "active": True})
    assert r.status_code == 200 and r.json()["active"] and r.json()["last_hash"] is None
    assert client.patch("/v1/rules-monitor/sources/nope", headers=h,
                        json={"active": False}).status_code == 404
    body = {"url": "https://tax.gov.ae/en/announcements.aspx", "name": "FTA announcements",
            "type": "html"}
    assert client.post("/v1/rules-monitor/sources", headers=h, json=body).status_code == 201
    assert client.post("/v1/rules-monitor/sources", headers=h, json=body).status_code == 409
    bad = {**body, "url": "http://tax.gov.ae/x"}
    assert client.post("/v1/rules-monitor/sources", headers=h, json=bad).status_code == 422


def test_check_now_upload_and_alerts(client: TestClient, token: Any) -> None:
    h = _tp(token)
    srcs = client.get("/v1/rules-monitor/sources", headers=h).json()
    pages: dict[str, mon.Response | Exception] = {
        s["url"]: mon.MonitorError("offline fixture") for s in srcs}
    pages[D17_URL] = pdf()
    client.app.dependency_overrides[api.get_fetcher] = lambda: FakeFetcher(pages)  # type: ignore[attr-defined]
    client.app.dependency_overrides[api.get_extractor] = lambda: fixed(D17_OUT)  # type: ignore[attr-defined]
    try:
        r = client.post("/v1/rules-monitor/check", headers=h)
        assert r.status_code == 202
        job = client.get(f"/v1/jobs/{r.json()['job_id']}", headers=h).json()
        assert job["status"] == "succeeded" and "checked=6" in job["result_ref"]
        alerts = client.get("/v1/rules-monitor/alerts", headers=h).json()
        assert sorted(a["kind"] for a in alerts) == ["change"] + ["failure"] * 5
        change = next(a for a in alerts if a["kind"] == "change")
        assert len(change["proposal_ids"]) == 4
        proposed = client.get("/v1/rules", headers=h, params={"status": "proposed"}).json()
        assert {p["id"] for p in proposed} >= set(change["proposal_ids"])
        files = {"file": ("decision17.pdf", D17_PDF, "application/pdf")}
        r = client.post("/v1/rules-monitor/upload", headers=h, files=files,
                        data={"source_url": D17_URL})
        assert r.status_code == 201 and r.json()["kind"] == "upload"
        r = client.post("/v1/rules-monitor/upload", headers=h,
                        files={"file": ("e.txt", b"", "text/plain")})
        assert r.status_code == 422
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]
    assert len(client.get("/v1/rules-monitor/alerts", headers=h,
                          params={"kind": "upload"}).json()) == 1
    r = client.post(f"/v1/rules-monitor/alerts/{change['id']}/close", headers=h)
    assert r.json()["status"] == "closed"
    assert len(client.get("/v1/rules-monitor/alerts", headers=h,
                          params={"status": "open"}).json()) == 6
    assert client.post("/v1/rules-monitor/alerts/x/close", headers=h).status_code == 404


def test_default_dependencies() -> None:
    assert isinstance(api.get_fetcher(), mon.PoliteFetcher)
    assert api.get_extractor() is None and api.get_notifier() is mon.log_notifier
