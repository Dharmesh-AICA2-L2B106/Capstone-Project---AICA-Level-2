"""Anonymiser (prompt 3.7, SPEC 4 "AI payload").

The AI payload is built **only** from whitelisted fields; the auditor remark is scrubbed of
names, TRNs, e-mails, phones, IBANs and Emirates ID numbers; and the finished payload is
re-checked (``assert_clean``) before any provider is called. Nothing here calculates.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

IMPLEMENTED_BY_PROMPT = "3.7"

WHITELIST = ("area", "test", "item_ref", "amounts", "failed_attribute",
             "applicable_references", "auditor_remark")
AMOUNT_KEYS = ("book_value", "audited_value", "misstatement")
MIN_TERM = 4  # shorter deny-list terms would over-scrub ordinary words

# Order matters: Emirates ID (15 digits starting 784) before TRN (15 digits).
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("[EMAIL]", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("[IBAN]", re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){3,7}(?:[ ]?[A-Z0-9]{1,4})?\b")),
    ("[EMIRATES_ID]", re.compile(r"\b784[- ]?\d{4}[- ]?\d{7}[- ]?\d\b")),
    ("[TRN]", re.compile(r"(?<!\d)\d{15}(?!\d)")),
    ("[PHONE]", re.compile(r"(?:\+|\b00)971[ -]?\d{1,2}[ -]?\d{3}[ -]?\d{4}\b"
                           r"|\b0(?:5\d|[234679])[ -]?\d{3}[ -]?\d{4}\b")),
    ("[PARTY]", re.compile(
        r"\b(?:[A-Z][\w&'.-]*\s+){1,6}"
        r"(?:L\.?L\.?C\.?|FZ-?LLC|FZCO|FZE|PJSC|PSC|LTD|Ltd\.?|Est\.?|Establishment|Trading)"
        r"(?![\w])")),
    ("[PARTY]", re.compile(r"\b(?:Al|El|Bin|Bu)[ -][A-Z][\w&'-]*(?:\s+[A-Z][\w&'.-]*)*")),
    ("[NAME]", re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Dr|Sheikh)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?")),
)


class AnonymisationError(ValueError):
    """Raised when a payload still carries an identifying term; the AI call must not run."""


def _terms(names: Iterable[str | None]) -> list[str]:
    out = {str(n).strip() for n in names if n and len(str(n).strip()) >= MIN_TERM}
    return sorted(out, key=len, reverse=True)


def scrub(text: str | None, names: Iterable[str | None] = ()) -> str:
    """Remove known names and identifying patterns from free text."""
    if not text:
        return ""
    out = str(text)
    for term in _terms(names):
        out = re.sub(re.escape(term), "[REDACTED]", out, flags=re.IGNORECASE)
    for label, pat in PATTERNS:
        out = pat.sub(label, out)
    return re.sub(r"\s+", " ", out).strip()


def _money(v: Any) -> str | None:
    if v is None or v == "":
        return None
    return f"{Decimal(str(v)):.2f}"


def build_payload(*, area: str, test: str, item_ref: str, amounts: dict[str, Any],
                  failed_attribute: str, applicable_references: list[dict[str, str]],
                  auditor_remark: str | None, names: Iterable[str | None]) -> dict[str, Any]:
    """Whitelisted, scrubbed payload. ``names`` is the engagement deny list."""
    names = list(names)
    payload = {
        "area": scrub(area, names),
        "test": scrub(test, names),
        "item_ref": scrub(item_ref, names),
        "amounts": {k: _money(amounts.get(k)) for k in AMOUNT_KEYS},
        "failed_attribute": scrub(failed_attribute, names),
        "applicable_references": [{"ref": scrub(r.get("ref"), names),
                                   "citation": scrub(r.get("citation"), names)}
                                  for r in applicable_references],
        "auditor_remark": scrub(auditor_remark, names) or "Not provided",
    }
    assert tuple(payload) == WHITELIST
    assert_clean(payload, names)
    return payload


def assert_clean(payload: dict[str, Any], forbidden: Iterable[str | None]) -> None:
    extra = set(payload) - set(WHITELIST)
    if extra:
        raise AnonymisationError(f"Non-whitelisted fields in AI payload: {sorted(extra)}")
    blob = json.dumps(payload, ensure_ascii=False)
    low = blob.lower()
    hits = [t for t in _terms(forbidden) if t.lower() in low]
    hits += [label for label, pat in PATTERNS if pat.search(blob)]
    if hits:
        raise AnonymisationError(f"AI payload still carries identifying data ({len(hits)} hit(s)); "
                                 "the AI call was not made.")


def forbidden_terms(*, client_name: str | None, client_code: str | None,
                    rows: Iterable[dict[str, Any]],
                    register: Iterable[dict[str, Any]] = ()) -> list[str]:
    """Deny list: client name/code, party names/ids, TRNs and user ids from the ledger and
    the supplier register."""
    terms: set[str] = {t for t in (client_name, client_code) if t}
    for r in [*rows, *register]:
        for k in ("party_name", "trn", "user_id"):
            v = r.get(k)
            if v not in (None, ""):
                terms.add(str(v))
    return _terms(terms)
