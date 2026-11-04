"""Prompt 3.7 API: POST /v1/ai/observation (stub provider, no network), review, WP gate."""

from __future__ import annotations

import json
import socket
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.services.ai_gateway import DRAFT_LABEL, PROMPT_VERSION
from tests.api.test_sampling_api import DUMMY, _body, _dataset
from tests.conftest import auth

GOOD = {"condition": "c", "criteria": "r", "cause": "Cause: To be confirmed with management.",
        "effect": "e", "recommendation": "m", "ml_point": "p", "wp_conclusion": "Reviewed."}


@pytest.fixture
def ai(monkeypatch: pytest.MonkeyPatch, env: Any) -> Iterator[None]:
    from app.core import config

    def _blocked(*a: Any, **k: Any) -> None:
        raise AssertionError("network access attempted in a test")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setenv("AI_PROVIDER", "stub")
    config.reset_settings()
    yield
    config.reset_settings()


@pytest.fixture
def item(client: TestClient, token: Callable[..., str], engagement: str) -> dict[str, Any]:
    from app.core.db import session_factory
    from app.models import SampleItem

    tok = token()
    did = _dataset(client, tok, engagement, DUMMY)
    smp = client.post("/v1/sample", headers=auth(tok), json=_body(did)).json()
    with session_factory()() as s:
        si = s.query(SampleItem).filter_by(sample_id=smp["sample_id"], line_ref="L00081").one()
        return {"tok": tok, "id": si.id, "sample_id": smp["sample_id"], "eng": engagement}


def test_ai_observation_stub_flow(ai: None, client: TestClient, token: Callable[..., str],
                                  item: dict[str, Any]) -> None:
    from app.core.db import session_factory
    from app.models import AuditLog, Observation

    tok = item["tok"]
    remark = ("Invoice from Al Wasl Wholesale LLC, TRN 100286583490896, client Dummy Trading LLC "
              "(DUMMY01); contact finance@dummy.ae / +971 4 123 4567")
    r = client.post("/v1/ai/observation", headers=auth(tok), json={
        "sample_item_id": item["id"], "failed_attribute": "Agreed to evidence",
        "remark": remark, "rule_keys": ["vat.rate.SR"]})
    assert r.status_code == 201, r.text
    b = r.json()
    blob = json.dumps(b["payload"])
    for secret in ("Al Wasl", "100286583490896", "Dummy Trading", "DUMMY01", "finance@",
                   "123 4567"):
        assert secret not in blob
    assert b["payload"]["item_ref"] == "L00081"
    assert b["payload"]["applicable_references"][0]["ref"] == "vat.rate.SR@v1"
    assert b["ai_generated"] is True and b["model"] == "stub-deterministic"
    assert b["prompt_version"] == PROMPT_VERSION and b["temperature"] == 0.2
    assert b["text"]["wp_conclusion"].endswith(DRAFT_LABEL) and b["reviewed_by"] is None
    assert b["text"]["cause"] == "Cause: To be confirmed with management."
    with session_factory()() as s:
        ob = s.get(Observation, b["observation_id"])
        assert ob is not None and ob.ai_generated and ob.prompt_version == PROMPT_VERSION
        log = s.query(AuditLog).filter_by(action="ai_draft", entity_id=ob.id).one()
        assert "payload" not in (log.new or {}) and "Al Wasl" not in json.dumps(log.new)

    # Unreviewed AI draft blocks the WP (3.6 gate); Staff cannot review; Manager can.
    wp = {"engagement_id": item["eng"], "wp_ref": "C-320", "sample_id": item["sample_id"]}
    assert client.post("/v1/workpaper", headers=auth(tok), json=wp).status_code == 409
    url = f"/v1/observations/{b['observation_id']}/review"
    assert client.post(url, headers=auth(token(sub="user-2")), json={}).status_code == 403
    rv = client.post(url, headers=auth(tok), json={"text": GOOD})
    assert rv.status_code == 200, rv.text
    assert rv.json()["reviewed_by"] == "user-1" and rv.json()["text"] == GOOD
    assert rv.json()["reviewed_at"]
    g = client.get(f"/v1/observations/{b['observation_id']}", headers=auth(tok))
    assert g.status_code == 200 and g.json() == rv.json()
    assert client.post("/v1/workpaper", headers=auth(tok), json=wp).status_code == 201


def test_ai_observation_guards(ai: None, client: TestClient, token: Callable[..., str],
                               item: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import config

    tok = item["tok"]
    body = {"sample_item_id": item["id"], "failed_attribute": "Exists"}
    assert client.post("/v1/ai/observation", headers=auth(tok),
                       json={**body, "sample_item_id": "nope"}).status_code == 404
    r = client.post("/v1/ai/observation", headers=auth(tok),
                    json={**body, "rule_keys": ["made.up.rule"]})
    assert r.status_code == 422 and "Rules Library" in r.json()["detail"]
    assert client.post("/v1/ai/observation", headers=auth(token(sub="user-9")),
                       json=body).status_code == 403
    assert client.post("/v1/ai/observation", headers=auth(tok),
                       json={**body, "narration": "x"}).status_code == 422
    r = client.post("/v1/ai/observation", headers=auth(tok), json=body)
    assert r.status_code == 201 and r.json()["payload"]["auditor_remark"] == "Not provided"
    rv = client.post(f"/v1/observations/{r.json()['observation_id']}/review", headers=auth(tok),
                     json={})
    assert rv.status_code == 200 and rv.json()["text"] == r.json()["text"]
    monkeypatch.setenv("AI_PROVIDER", "")
    config.reset_settings()
    r = client.post("/v1/ai/observation", headers=auth(tok), json=body)
    assert r.status_code == 503 and "manually" in r.json()["detail"]
    assert client.get("/v1/observations/nope", headers=auth(tok)).status_code == 404
    assert client.post("/v1/observations/nope/review", headers=auth(tok),
                       json={}).status_code == 404
