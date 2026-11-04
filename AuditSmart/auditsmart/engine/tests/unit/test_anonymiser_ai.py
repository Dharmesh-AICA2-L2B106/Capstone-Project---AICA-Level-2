"""Prompt 3.7 unit tests: scrubbing, whitelist, provider adapters (fake transport), retry,
draft label and provider selection. No network, no API keys."""

from __future__ import annotations

import json
import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from app.core import config
from app.services import ai_gateway, anonymiser
from app.services.ai_gateway import AIError, draft_observation

REPO = Path(__file__).resolve().parents[3]
GOOD = {"condition": "c", "criteria": "r", "cause": "Cause: To be confirmed with management.",
        "effect": "e", "recommendation": "m", "ml_point": "p", "wp_conclusion": "w"}
FAKE_KEY = "fake-key-for-tests-only"


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def _blocked(*a: Any, **k: Any) -> None:
        raise AssertionError("network access attempted in a test")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    yield


class Scripted:
    name, model = "fake", "fake-1"

    def __init__(self, *replies: str) -> None:
        self.replies, self.seen = list(replies), []  # type: list[str], list[tuple[str, str, float]]

    def complete(self, system: str, user: str, temperature: float) -> str:
        self.seen.append((system, user, temperature))
        return self.replies.pop(0)


def _payload() -> dict[str, Any]:
    return anonymiser.build_payload(
        area="Expense / Rent", test="Vouching", item_ref="L00081",
        amounts={"book_value": "1000", "audited_value": "900", "misstatement": "100"},
        failed_attribute="Agreed to evidence", applicable_references=[
            {"ref": "vat.rate.SR@v1", "citation": "Decree-Law"}],
        auditor_remark=None, names=["Some Party Name"])


def test_prompt_copy_matches_repo_prompt() -> None:
    assert (REPO / "prompts/observation_system_prompt.txt").read_text() == ai_gateway.SYSTEM_PROMPT
    assert ai_gateway.PROMPT_VERSION.startswith("observation@v1+")
    assert ai_gateway.DRAFT_LABEL in ai_gateway.SYSTEM_PROMPT


def test_scrub_each_pattern_and_names() -> None:
    s = anonymiser.scrub
    assert s("mail a.b+c@firm.co.ae now") == "mail [EMAIL] now"
    assert s("TRN 100286583490896.") == "TRN [TRN]."
    assert s("EID 784198512345671") == "EID [EMIRATES_ID]"
    assert s("call 04 123 4567 / 0501234567 / 00971-4-123-4567") == \
        "call [PHONE] / [PHONE] / [PHONE]"
    assert s("IBAN AE07 0331 2345 6789 0123 456") == "IBAN [IBAN]"
    assert s("from Gulf Star Trading and Ms Fatima") == "from [PARTY] and [NAME]"
    assert s("approved by jsmith1", ["JSMITH1", "AB"]) == "approved by [REDACTED]"
    assert s("AB stays") == "AB stays" and s(None) == "" and s("") == ""
    assert s("AED 1,234,567.89 on 2025-12-31 ref TI-2700579") == \
        "AED 1,234,567.89 on 2025-12-31 ref TI-2700579"


def test_payload_whitelist_and_amounts() -> None:
    p = _payload()
    assert tuple(p) == anonymiser.WHITELIST
    assert p["amounts"] == {"book_value": "1000.00", "audited_value": "900.00",
                            "misstatement": "100.00"}
    assert p["auditor_remark"] == "Not provided"
    names = anonymiser.forbidden_terms(client_name="Dummy Trading LLC", client_code=None,
                                       rows=[{"party_name": "X Y Z", "trn": "", "user_id": "AP1"}])
    assert names == ["Dummy Trading LLC", "X Y Z"]


def test_draft_ok_label_and_metadata() -> None:
    prov = Scripted(json.dumps(GOOD))
    res = draft_observation(_payload(), prov)
    assert res["attempts"] == 1 and res["model"] == "fake-1" and res["provider"] == "fake"
    assert res["draft"]["wp_conclusion"] == f"w {ai_gateway.DRAFT_LABEL}"
    assert res["prompt_version"] == ai_gateway.PROMPT_VERSION and res["warnings"] == []
    system, user, temp = prov.seen[0]
    assert system == ai_gateway.SYSTEM_PROMPT and temp == 0.2
    assert json.loads(user) == _payload()


def test_fenced_json_label_not_duplicated_and_word_warning() -> None:
    body = dict(GOOD, wp_conclusion=f"Done. {ai_gateway.DRAFT_LABEL}",
                effect=" ".join(["word"] * 230))
    res = draft_observation(_payload(), Scripted(f"```json\n{json.dumps(body)}\n```"))
    assert res["draft"]["wp_conclusion"].count(ai_gateway.DRAFT_LABEL) == 1
    assert "limit 220" in res["warnings"][0]


def test_one_retry_then_fail() -> None:
    prov = Scripted("not json", json.dumps(GOOD))
    res = draft_observation(_payload(), prov)
    assert res["attempts"] == 2 and "previous reply was invalid" in prov.seen[1][1]
    bad = dict(GOOD, extra="x")
    with pytest.raises(AIError) as e:
        draft_observation(_payload(), Scripted(json.dumps(bad), json.dumps({"condition": ""})))
    assert e.value.status_code == 502 and "after one retry" in e.value.message


class FakeTransport:
    def __init__(self, reply: dict[str, Any]) -> None:
        self.reply, self.calls = reply, []  # type: dict[str, Any], list[Any]

    def __call__(self, url: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        self.calls.append((url, headers, json.loads(body)))
        return self.reply


def test_gemini_adapter_request_and_parse() -> None:
    t = FakeTransport({"candidates": [{"content": {"parts": [{"text": json.dumps(GOOD)}]}}]})
    g = ai_gateway.GeminiProvider(model="gemini-x", api_key=FAKE_KEY, transport=t)
    res = draft_observation(_payload(), g)
    url, headers, body = t.calls[0]
    assert url.endswith("/models/gemini-x:generateContent") and url.startswith("https://")
    assert headers["x-goog-api-key"] == FAKE_KEY and FAKE_KEY not in repr(g)
    assert body["generationConfig"] == {"temperature": 0.2,
                                        "responseMimeType": "application/json"}
    assert body["systemInstruction"]["parts"][0]["text"] == ai_gateway.SYSTEM_PROMPT
    assert res["model"] == "gemini-x" and res["provider"] == "gemini"
    with pytest.raises(AIError, match="Gemini"):
        ai_gateway.GeminiProvider(model="m", api_key="k", transport=FakeTransport({})).complete(
            "s", "u", 0.2)


def test_azure_adapter_request_and_parse() -> None:
    t = FakeTransport({"choices": [{"message": {"content": json.dumps(GOOD)}}]})
    a = ai_gateway.AzureOpenAIProvider(endpoint="https://x.openai.azure.com/", model="dep1",
                                       api_key=FAKE_KEY, transport=t)
    res = draft_observation(_payload(), a)
    url, headers, body = t.calls[0]
    assert url == ("https://x.openai.azure.com/openai/deployments/dep1/chat/completions"
                   "?api-version=2024-06-01")
    assert headers["api-key"] == FAKE_KEY and FAKE_KEY not in repr(a)
    assert body["temperature"] == 0.2 and body["response_format"] == {"type": "json_object"}
    assert body["messages"][0] == {"role": "system", "content": ai_gateway.SYSTEM_PROMPT}
    assert res["provider"] == "azure_openai"
    with pytest.raises(AIError, match="Azure"):
        ai_gateway.AzureOpenAIProvider(endpoint="https://e", model="d", api_key="k",
                                       transport=FakeTransport({"choices": []})).complete(
            "s", "u", 0.2)


def test_https_only_transport() -> None:
    with pytest.raises(AIError, match="HTTPS"):
        ai_gateway.urllib_transport("http://insecure", {}, b"")


@pytest.mark.parametrize(("env", "expect"), [
    ({}, 503), ({"AI_PROVIDER": "other"}, 503), ({"AI_PROVIDER": "stub"}, "stub"),
    ({"AI_PROVIDER": "gemini"}, 503),
    ({"AI_PROVIDER": "gemini", "GEMINI_API_KEY": FAKE_KEY, "AI_MODEL": "g1"}, "gemini"),
    ({"AI_PROVIDER": "azure_openai", "AZURE_OPENAI_API_KEY": FAKE_KEY}, 503),
    ({"AI_PROVIDER": "azure_openai", "AZURE_OPENAI_API_KEY": FAKE_KEY, "AI_MODEL": "d",
      "AZURE_OPENAI_ENDPOINT": "https://e"}, "azure_openai"),
])
def test_provider_selection(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                            env: dict[str, str], expect: Any) -> None:
    monkeypatch.chdir(tmp_path)
    for k in ("AI_PROVIDER", "AI_MODEL", "GEMINI_API_KEY", "AZURE_OPENAI_API_KEY",
              "AZURE_OPENAI_ENDPOINT"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    config.reset_settings()
    try:
        if isinstance(expect, int):
            with pytest.raises(AIError) as e:
                ai_gateway.get_provider()
            assert e.value.status_code == expect and FAKE_KEY not in e.value.message
        else:
            p = ai_gateway.get_provider(transport=FakeTransport({}))
            assert p.name == expect
    finally:
        config.reset_settings()
