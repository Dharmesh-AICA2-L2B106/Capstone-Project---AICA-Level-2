"""Prompt 3.5 API: POST /v1/vat-check, POST /v1/evaluate (stored on the sample)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.services.evaluation import EvalItem, evaluate_mus
from tests.api.test_sampling_api import DUMMY, EDGE, _body, _dataset
from tests.conftest import auth

GOLDEN_ITEMS: list[dict[str, str]] = [
    {"line_ref": "L00159", "audited_value": "214518.17", "remarks": "top"},
    {"line_ref": "L00019", "audited_value": "28613.37"},
    {"line_ref": "L00081", "audited_value": "33206.35", "evidence_ref": "WP-7"},
]


def test_vat_check(client: TestClient, token: Callable[..., str], engagement: str) -> None:
    tok = token()
    did = _dataset(client, tok, engagement, DUMMY)
    r = client.post("/v1/vat-check", headers=auth(tok), json={"dataset_id": did})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["exceptions_count"] == 12 and b["trn"]["invalid_count"] == 5
    assert b["exceptions_by_side"] == {"output": 12, "input": 0}
    o = client.post("/v1/vat-check", headers=auth(tok),
                    json={"dataset_id": did, "sides": ["input"]}).json()
    assert o["exceptions_count"] == 0 and o["sides"] == ["input"]
    assert client.post("/v1/vat-check", headers=auth(tok), json={
        "dataset_id": did, "sides": []}).status_code == 422
    assert client.post("/v1/vat-check", headers=auth(tok), json={
        "dataset_id": did, "sides": ["both"]}).status_code == 422
    edge = _dataset(client, tok, engagement, EDGE)
    assert client.post("/v1/vat-check", headers=auth(tok),
                       json={"dataset_id": edge}).status_code == 409
    assert client.post("/v1/vat-check", headers=auth(token(sub="user-9")),
                       json={"dataset_id": did}).status_code == 403
    assert client.post("/v1/vat-check", headers=auth(tok),
                       json={"dataset_id": "nope"}).status_code == 404


def test_evaluate_mus_end_to_end(client: TestClient, token: Callable[..., str],
                                 engagement: str) -> None:
    tok = token()
    did = _dataset(client, tok, engagement, DUMMY)
    smp = client.post("/v1/sample", headers=auth(tok), json=_body(did)).json()
    by = {i["line_id"]: i for i in smp["items"]}
    # L00159 and L00081 are in the seed-2025 sample; L00019 (golden sheet) is not, so a sampled
    # line is tainted 10% in its place. The result must equal the service called directly.
    assert {"L00159", "L00081"} <= set(by) and "L00019" not in by
    items = [dict(x) for x in GOLDEN_ITEMS]
    other = next(k for k, v in by.items() if not v["top_stratum"] and k != "L00081")
    ob = Decimal(by[other]["value"])
    items[1] = {"line_ref": other, "audited_value": str(ob - (ob / 10).quantize(
        Decimal("0.01")))}
    expected = evaluate_mus(
        [EvalItem(i["line_ref"], Decimal(by[i["line_ref"]]["value"]),
                  Decimal(i["audited_value"])) for i in items],
        interval=Decimal(smp["interval"]), cf=Decimal(smp["cf_value"]),
        tm=Decimal("280000"), confidence="95", on_date=date(2025, 12, 31))
    r = client.post("/v1/evaluate", headers=auth(tok),
                    json={"sample_id": smp["sample_id"], "items": items})
    assert r.status_code == 200, r.text
    e = r.json()
    assert (e["sum_projected"], e["incremental_allowance"], e["uml"]) == (
        str(expected["sum_projected"]), str(expected["incremental_allowance"]),
        str(expected["uml"]))
    assert e["conclusion"] == "Exceeds - further work" and e["method"] == "mus"
    assert e["items_evaluated"] == 3 and e["items_in_sample"] == 149
    g = client.get(f"/v1/samples/{smp['sample_id']}", headers=auth(tok)).json()
    assert g["evaluation"] == e

    from app.core.db import session_factory
    from app.models import SampleItem

    with session_factory()() as s:
        si = s.query(SampleItem).filter_by(sample_id=smp["sample_id"], line_ref="L00081").one()
        assert si.misstatement == Decimal("11068.79") and si.evidence_ref == "WP-7"
        top = s.query(SampleItem).filter_by(sample_id=smp["sample_id"], line_ref="L00159").one()
        assert top.remarks == "top"
        untouched = s.query(SampleItem).filter(SampleItem.sample_id == smp["sample_id"],
                                               SampleItem.misstatement != 0).count()
        assert untouched == 3
    # no misstatements: UML = BP, acceptable
    clean = client.post("/v1/evaluate", headers=auth(tok),
                        json={"sample_id": smp["sample_id"]}).json()
    assert clean["conclusion"] == "Acceptable" and clean["uml"] == clean["basic_precision"]
    # ratio on a MUS sample (D2 option)
    ratio = client.post("/v1/evaluate", headers=auth(tok), json={
        "sample_id": smp["sample_id"], "method": "ratio", "items": items}).json()
    assert ratio["method"] == "ratio" and ratio["actual_misstatement_key_items"] == "12500.00"


def test_evaluate_ratio_and_errors(client: TestClient, token: Callable[..., str],
                                   engagement: str) -> None:
    tok = token()
    did = _dataset(client, tok, engagement, DUMMY)
    st = client.post("/v1/sample", headers=auth(tok), json={
        "dataset_id": did, "account_types": ["Expense"], "method": "stratified",
        "sample_size": 30, "num_strata": 3, "seed": 7}).json()
    item = st["items"][0]
    bad = {"sample_id": st["sample_id"],
           "items": [{"line_ref": item["line_id"], "audited_value": "0"}]}
    r = client.post("/v1/evaluate", headers=auth(tok), json=bad)
    assert r.status_code == 422 and "Tolerable misstatement" in r.json()["detail"]
    r = client.post("/v1/evaluate", headers=auth(tok), json={**bad,
                                                             "tolerable_misstatement": "280000"})
    assert r.status_code == 200, r.text
    e = r.json()
    assert e["method"] == "ratio" and len(e["strata"]) == 3
    assert Decimal(e["projected_misstatement"]) > Decimal(item["value"])
    assert client.post("/v1/evaluate", headers=auth(tok), json={
        **bad, "tolerable_misstatement": "280000", "method": "mus"}).status_code == 422
    unknown = {"sample_id": st["sample_id"], "tolerable_misstatement": "1",
               "items": [{"line_ref": "ZZZ", "audited_value": "1"}]}
    assert client.post("/v1/evaluate", headers=auth(tok), json=unknown).status_code == 422
    dup = {"sample_id": st["sample_id"], "tolerable_misstatement": "1",
           "items": [bad["items"][0], bad["items"][0]]}
    r = client.post("/v1/evaluate", headers=auth(tok), json=dup)
    assert r.status_code == 422 and "twice" in r.json()["detail"]
    assert client.post("/v1/evaluate", headers=auth(tok),
                       json={"sample_id": "nope"}).status_code == 404
    assert client.post("/v1/evaluate", headers=auth(token(sub="user-9")),
                       json={"sample_id": st["sample_id"]}).status_code == 403
