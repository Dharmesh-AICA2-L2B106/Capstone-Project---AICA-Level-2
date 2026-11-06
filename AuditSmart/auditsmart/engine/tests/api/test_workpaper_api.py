"""Prompt 3.6: POST /v1/workpaper – opens the file and checks every sheet and key cell."""

from __future__ import annotations

import io
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from app.services.workpaper import SHEETS
from tests.api.test_evaluation_api import GOLDEN_ITEMS
from tests.api.test_sampling_api import DUMMY, _body, _dataset
from tests.conftest import auth


def _find(ws: Worksheet, label: str) -> Any:
    for row in ws.iter_rows():
        if row[0].value == label:
            return row[1].value
    raise AssertionError(f"{label} not on {ws.title}")


def _rows(ws: Worksheet) -> list[tuple[Any, ...]]:
    return [tuple(c.value for c in r) for r in ws.iter_rows()]


@pytest.fixture
def results(client: TestClient, token: Callable[..., str], engagement: str) -> dict[str, Any]:
    tok = token()
    did = _dataset(client, tok, engagement, DUMMY)
    smp = client.post("/v1/sample", headers=auth(tok), json=_body(did)).json()
    items = [GOLDEN_ITEMS[0], GOLDEN_ITEMS[2]]
    ev = client.post("/v1/evaluate", headers=auth(tok),
                     json={"sample_id": smp["sample_id"], "items": items}).json()
    je = client.post("/v1/je-tests", headers=auth(tok), json={
        "dataset_id": did, "parameters": {"senior_users": ["FINMGR"]}}).json()
    jr = client.get(je["result_url"], headers=auth(tok)).json()
    return {"tok": tok, "did": did, "sample": smp, "ev": ev, "je": jr,
            "body": {"engagement_id": engagement, "wp_ref": "C-310", "sample_id":
                     smp["sample_id"], "je_run_id": jr["je_run_id"]}}


def test_workpaper_every_sheet(client: TestClient, results: dict[str, Any]) -> None:
    tok, smp, ev, jr = results["tok"], results["sample"], results["ev"], results["je"]
    r = client.post("/v1/workpaper", headers=auth(tok), json=results["body"])
    assert r.status_code == 201, r.text
    meta = r.json()
    assert meta["status"] == "prepared" and meta["preparer"] == "user-1"
    assert meta["manifest"]["sheets"] == list(SHEETS) and len(meta["sha256"]) == 64
    assert client.get(f"/v1/workpapers/{meta['workpaper_id']}", headers=auth(tok)).json() == meta
    f = client.get(meta["file_url"], headers=auth(tok))
    assert f.status_code == 200 and f.headers["content-type"].startswith(
        "application/vnd.openxmlformats")
    wb = load_workbook(io.BytesIO(f.content))
    assert wb.sheetnames == list(SHEETS)
    for ws in wb.worksheets:
        assert ws["A1"].value == f"Dummy Trading LLC – {ws.title}"
        assert "C-310" in ws["A2"].value and ws.freeze_panes is not None
        assert ws.oddFooter.left.text == "WP C-310"
        assert ws.oddFooter.center.text == "Page &P of &N"
        assert ws.oddFooter.right.text.startswith("auditsmart-engine ")
        assert ws.page_setup.orientation == "landscape" and ws.print_title_rows

    lead = wb["Lead"]
    assert _find(lead, "Working paper ref") == "C-310"
    assert _find(lead, "Evaluation").startswith(f"UML {ev['uml']}")
    ev_row = next(r for r in _rows(lead) if r[0] == "Evaluation")
    assert ev_row[2] == ev["conclusion"]

    pop = wb["Population"]
    assert _find(pop, "SHA-256") == smp["dataset_hash"]
    assert abs(_find(pop, "Sampling population value") - float(smp["population"]["value"])) < 0.01
    assert pop.cell(row=next(i for i, r in enumerate(_rows(pop), 1)
                             if r[0] == "Total debits"), column=2).number_format.startswith(
        "#,##0.00")

    sp = wb["Sampling"]
    assert _find(sp, "Confidence factor (CF)") == smp["cf_value"] == "3.00"
    assert _find(sp, "Seed") == 2025 and _find(sp, "Formula") == smp["formula_text"]
    assert abs(_find(sp, "Sampling interval (J)") - 77968.97) < 0.01

    st = wb["Sample & Testing"]
    rows = _rows(st)
    hdr = next(i for i, r in enumerate(rows) if r[0] == "#")
    data = [r for r in rows[hdr + 1:] if r[0] is not None]
    assert len(data) == smp["sample_size"] == 149
    assert rows[hdr][7:10] == ("Exists", "Agreed to evidence", "Correctly recorded")
    l81 = next(r for r in data if r[1] == "L00081")
    assert l81[10] == 33206.35 and l81[11] == 11068.79 and l81[12] == "WP-7"
    dv = st.data_validations.dataValidation
    assert len(dv) == 1 and dv[0].formula1 == '"Yes,No,N/A"'
    assert str(dv[0].sqref) == f"H{hdr + 2}:J{hdr + 1 + len(data)}"
    assert st.freeze_panes == f"A{hdr + 2}"

    je = wb["JE Risk"]
    assert _find(je, "Calendar hash") == jr["calendar_hash"]
    assert _find(je, "Lines flagged") == jr["flagged_lines"]
    jrows = _rows(je)
    assert next(r for r in jrows if r[0] == "non_working_day")[:1] == ("non_working_day",)
    sel = [r for r in jrows if r[8] in ("test", "test_topup")]
    assert len(sel) == jr["selected_for_testing"]

    bf = wb["Benford"]
    assert len(bf._charts) == 1 and _find(bf, "Conclusion") == jr["benford"]["conclusion"]
    digits = [r for r in _rows(bf) if isinstance(r[0], int) and 1 <= r[0] <= 9]
    assert [r[0] for r in digits] == list(range(1, 10))

    evs = wb["Evaluation"]
    assert abs(_find(evs, "Upper misstatement limit") - float(ev["uml"])) < 0.005
    assert _find(evs, "Conclusion") == ev["conclusion"]

    assert "No input VAT run" in wb["Input VAT"]["A4"].value
    assert "No AI drafts" in wb["AI Drafts"]["A4"].value

    rc = _rows(wb["Rules & Calendar"])
    refs = {r[0] for r in rc}
    assert {"sampling.mus.cf.95", "sampling.mus.if.95", "benford.min_amount",
            "je.round_sum.multiple", "je.score.test"} <= refs
    cf_row = next(r for r in rc if r[0] == "sampling.mus.cf.95")
    assert cf_row[3] == "pending_verification" and "firm_methodology_v0.2" in cf_row[5]
    assert cf_row[6] == "(not recorded – Rules Library 3.8)"
    assert next(r for r in rc if r[0] == "Calendar hash")[1] == jr["calendar_hash"]

    so = _rows(wb["Sign-offs"])
    assert next(r for r in so if r[0] == "Preparer")[1] == "user-1"
    assert next(r for r in so if r[0] == "Tool version")[1].startswith("auditsmart-engine ")

    from app.core.db import session_factory
    from app.models import AuditLog

    with session_factory()() as s:
        log = s.query(AuditLog).filter_by(entity="workpaper").one()
        assert log.entity_id == meta["workpaper_id"] and log.new["sha256"] == meta["sha256"]


def _set(model: str, id_: str, **values: Any) -> None:
    from app import models
    from app.core.db import session_factory

    with session_factory()() as s:
        obj = s.get(getattr(models, model), id_)
        for k, v in values.items():
            setattr(obj, k, v)
        s.commit()


def test_stale_refused_and_override(client: TestClient, token: Callable[..., str],
                                    results: dict[str, Any]) -> None:
    tok, body = results["tok"], results["body"]
    _set("JeRun", body["je_run_id"], status="stale")
    r = client.post("/v1/workpaper", headers=auth(tok), json=body)
    assert r.status_code == 409 and "STALE" in r.json()["detail"]
    ov = {"kind": "je_run", "id": body["je_run_id"], "justification": "too short"}
    r = client.post("/v1/workpaper", headers=auth(tok), json={**body, "stale_overrides": [ov]})
    assert r.status_code == 422
    r = client.post("/v1/workpaper", headers=auth(token(sub="user-2")),
                    json={**body, "stale_overrides": [ov]})
    assert r.status_code == 403
    ov["justification"] = "Calendar change affects 2026 only; FY2025 days unchanged."
    r = client.post("/v1/workpaper", headers=auth(tok), json={**body, "stale_overrides": [ov]})
    assert r.status_code == 201, r.text
    assert r.json()["manifest"]["overrides"][0]["by"] == "user-1"
    wb = load_workbook(io.BytesIO(client.get(r.json()["file_url"], headers=auth(tok)).content))
    so = _rows(wb["Sign-offs"])
    assert any(row[0] == "je_run" and row[2] == ov["justification"] for row in so)


def test_unreviewed_ai_draft_refused(client: TestClient, results: dict[str, Any]) -> None:
    from app.core.db import session_factory
    from app.models import Observation, SampleItem

    tok, body = results["tok"], results["body"]
    with session_factory()() as s:
        si = s.query(SampleItem).filter_by(sample_id=body["sample_id"], line_ref="L00081").one()
        ob = Observation(sample_item_id=si.id, text={"finding": "Invoice understated"},
                         ai_generated=True, prompt_version="obs-v1", model="stub")
        s.add(ob)
        s.commit()
        oid = ob.id
    r = client.post("/v1/workpaper", headers=auth(tok), json=body)
    assert r.status_code == 409 and "L00081" in r.json()["detail"]
    _set("Observation", oid, reviewed_by="user-1", reviewed_at=datetime(2026, 1, 5, tzinfo=UTC))
    r = client.post("/v1/workpaper", headers=auth(tok), json=body)
    assert r.status_code == 201, r.text
    wb = load_workbook(io.BytesIO(client.get(r.json()["file_url"], headers=auth(tok)).content))
    d = next(row for row in _rows(wb["AI Drafts"]) if row[0] == "L00081")
    assert d[1] == "DRAFT – AI generated" and d[5] == "✓" and d[6] == "user-1"
    assert "Invoice understated" in d[2]


def test_workpaper_guards(client: TestClient, token: Callable[..., str],
                          results: dict[str, Any], engagement: str) -> None:
    tok, body = results["tok"], results["body"]
    assert client.post("/v1/workpaper", headers=auth(tok), json={
        "engagement_id": engagement, "wp_ref": "X"}).status_code == 422
    assert client.post("/v1/workpaper", headers=auth(tok), json={
        **body, "wp_ref": "bad<ref>"}).status_code == 422
    assert client.post("/v1/workpaper", headers=auth(tok), json={
        **body, "sample_id": "nope"}).status_code == 404
    assert client.post("/v1/workpaper", headers=auth(tok), json={
        **body, "je_run_id": "nope"}).status_code == 404
    assert client.post("/v1/workpaper", headers=auth(tok), json={
        **body, "input_vat_run_id": "nope"}).status_code == 404
    assert client.post("/v1/workpaper", headers=auth(token(sub="user-9")),
                       json=body).status_code == 403
    assert client.get("/v1/workpapers/nope", headers=auth(tok)).status_code == 404
    r = client.post("/v1/workpaper", headers=auth(tok), json=body).json()
    assert client.get(r["file_url"], headers=auth(token(sub="user-9"))).status_code == 403
