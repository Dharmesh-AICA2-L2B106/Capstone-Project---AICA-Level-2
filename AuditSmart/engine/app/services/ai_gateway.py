"""AI gateway (prompt 3.7): anonymised payload -> provider -> validated JSON draft.

AI drafts the wording of an observation only; it never performs or changes a calculation.
Provider adapters are selected by ``AI_PROVIDER`` (``gemini`` | ``azure_openai`` | ``stub``).
API keys are read from the environment at call time, are never logged, stored or returned,
and tests always inject a fake transport (no network, no keys).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

IMPLEMENTED_BY_PROMPT = "3.7"

PROMPT_PATH = Path(__file__).resolve().parents[1] / "ai_prompts" / "observation_v1.txt"
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")
PROMPT_VERSION = "observation@v1+" + hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()[:8]
DRAFT_LABEL = "Draft - generated with AI, subject to auditor review."
TEMPERATURE = 0.2
MAX_WORDS = 220
TIMEOUT_S = 30

Transport = Callable[[str, dict[str, str], bytes], dict[str, Any]]


class AIError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ObservationDraft(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    condition: str = Field(min_length=1)
    criteria: str = Field(min_length=1)
    cause: str = Field(min_length=1)
    effect: str = Field(min_length=1)
    recommendation: str = Field(min_length=1)
    ml_point: str = Field(min_length=1)
    wp_conclusion: str = Field(min_length=1)


class Provider(Protocol):
    name: str
    model: str

    def complete(self, system: str, user: str, temperature: float) -> str: ...


def urllib_transport(url: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
    """Default HTTPS transport (production only; never used by tests)."""
    if not url.startswith("https://"):
        raise AIError("AI endpoint must use HTTPS.", 500)
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")  # noqa: S310
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310  # pragma: no cover
        out: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
        return out


@dataclass
class GeminiProvider:
    model: str
    api_key: str = field(repr=False)
    transport: Transport = urllib_transport
    name: str = "gemini"
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"

    def complete(self, system: str, user: str, temperature: float) -> str:
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": temperature,
                                     "responseMimeType": "application/json"}}
        res = self.transport(f"{self.base_url}/models/{self.model}:generateContent",
                             {"Content-Type": "application/json", "x-goog-api-key": self.api_key},
                             json.dumps(body).encode())
        try:
            return str(res["candidates"][0]["content"]["parts"][0]["text"])
        except (KeyError, IndexError, TypeError):
            raise AIError("Gemini returned no draft text.") from None


@dataclass
class AzureOpenAIProvider:
    endpoint: str
    model: str  # deployment name
    api_key: str = field(repr=False)
    api_version: str = "2024-06-01"
    transport: Transport = urllib_transport
    name: str = "azure_openai"

    def complete(self, system: str, user: str, temperature: float) -> str:
        body = {"messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "temperature": temperature, "response_format": {"type": "json_object"}}
        url = (f"{self.endpoint.rstrip('/')}/openai/deployments/{self.model}/chat/completions"
               f"?api-version={self.api_version}")
        res = self.transport(url, {"Content-Type": "application/json", "api-key": self.api_key},
                             json.dumps(body).encode())
        try:
            return str(res["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError):
            raise AIError("Azure OpenAI returned no draft text.") from None


@dataclass
class StubProvider:
    """Offline, deterministic drafter for development and tests (no AI, no network)."""

    model: str = "stub-deterministic"
    name: str = "stub"
    calls: list[str] = field(default_factory=list)

    def complete(self, system: str, user: str, temperature: float) -> str:
        self.calls.append(user)
        p = json.loads(user.split("\n", 1)[0])
        refs = "; ".join(r["citation"] or r["ref"] for r in p["applicable_references"])
        amt = p["amounts"]
        return json.dumps({
            "condition": f"{p['test']} on {p['item_ref']} ({p['area']}): {p['failed_attribute']}."
                         f" Book value AED {amt['book_value'] or 'Not provided'}, audited value "
                         f"AED {amt['audited_value'] or 'Not provided'}, misstatement AED "
                         f"{amt['misstatement'] or 'Not provided'}.",
            "criteria": refs or "Not provided",
            "cause": "Cause: To be confirmed with management.",
            "effect": "The balance may be misstated by the misstatement noted.",
            "recommendation": "Management should review and correct the item.",
            "ml_point": f"{p['failed_attribute']} - {p['item_ref']}.",
            "wp_conclusion": f"Exception noted; auditor remark: {p['auditor_remark']}.",
        })


def get_provider(*, transport: Transport | None = None) -> Provider:
    from app.core.config import get_settings

    st = get_settings()
    kind = (st.ai_provider or "").strip().lower()
    t = transport or urllib_transport
    if kind == "stub":
        return StubProvider()
    if kind == "gemini":
        key = os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise AIError("AI provider gemini selected but GEMINI_API_KEY is not set.", 503)
        return GeminiProvider(model=st.ai_model or "gemini-1.5-pro", api_key=key, transport=t)
    if kind == "azure_openai":
        key = os.environ.get("AZURE_OPENAI_API_KEY", "")
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        if not key or not endpoint or not st.ai_model:
            raise AIError("AI provider azure_openai needs AZURE_OPENAI_ENDPOINT, "
                          "AZURE_OPENAI_API_KEY and AI_MODEL (deployment).", 503)
        return AzureOpenAIProvider(endpoint=endpoint, model=st.ai_model, api_key=key,
                                   transport=t)
    raise AIError("AI is not configured (AI_PROVIDER is empty or unknown); write the "
                  "observation manually.", 503)


def _parse(text: str) -> ObservationDraft:
    t = text.strip()
    m = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", t, flags=re.DOTALL)
    if m:
        t = m.group(1)
    return ObservationDraft.model_validate(json.loads(t))


def draft_observation(payload: dict[str, Any], provider: Provider) -> dict[str, Any]:
    """Call the provider with the anonymised payload; validate; one retry; append the label."""
    user = json.dumps(payload, ensure_ascii=False, sort_keys=False)
    err = ""
    for attempt in (1, 2):
        msg = user if attempt == 1 else (
            f"{user}\nYour previous reply was invalid ({err}). Reply with JSON only, with "
            "exactly the keys condition, criteria, cause, effect, recommendation, ml_point, "
            "wp_conclusion.")
        try:
            draft = _parse(provider.complete(SYSTEM_PROMPT, msg, TEMPERATURE))
        except (json.JSONDecodeError, PydanticValidationError) as exc:
            err = type(exc).__name__
            continue
        out = draft.model_dump()
        if not out["wp_conclusion"].rstrip().endswith(DRAFT_LABEL):
            out["wp_conclusion"] = f"{out['wp_conclusion'].rstrip()} {DRAFT_LABEL}"
        words = sum(len(str(v).split()) for v in out.values())
        warnings = [f"Draft has {words} words (limit {MAX_WORDS}); shorten on review."] \
            if words > MAX_WORDS else []
        return {"draft": out, "label": DRAFT_LABEL, "provider": provider.name,
                "model": provider.model, "prompt_version": PROMPT_VERSION,
                "temperature": TEMPERATURE, "attempts": attempt, "warnings": warnings}
    raise AIError(f"The AI reply was not valid JSON for the observation schema after one "
                  f"retry ({err}); write the observation manually.")
