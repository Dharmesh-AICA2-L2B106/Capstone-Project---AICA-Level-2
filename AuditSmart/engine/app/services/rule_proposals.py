"""Validation of the AI rule-extraction output (prompts/rule_extraction_prompt.txt, 3.8/3.9).

The AI only *proposes*; this module never calls a model. It parses the JSON the extractor
returned, enforces the exact schema and the allowed rule-key families, and turns valid
changes into ``proposed`` rule versions for Tax Partner approval (rules.approve).
A change with no stated effective date is kept for the Tax Partner but not proposed
(the prompt forbids guessing dates).
"""

from __future__ import annotations

import fnmatch
import json
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app.services import rules

PROMPT_PATH = Path(__file__).resolve().parents[1] / "ai_prompts" / "rule_extraction_v1.txt"
ALLOWED_KEYS = ("vat.rate.*", "vat.codes", "trn.pattern", "input_vat.verification.*",
                "input_vat.employee_expense.*", "ct.rate.*", "ct.threshold.*", "legal_ref.*")
NO_CHANGE = "No relevant change"


class ExtractionError(ValueError):
    pass


class Change(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_key: str = Field(min_length=3, max_length=128)
    current_value: Any = None
    proposed_value: Any
    effective_date: date | None
    citation: str = Field(min_length=3, max_length=500)
    confidence: Literal["high", "medium", "low"]


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(max_length=2000)
    changes: list[Change] = Field(max_length=50)


def key_allowed(rule_key: str) -> bool:
    return any(fnmatch.fnmatchcase(rule_key, p) for p in ALLOWED_KEYS) \
        and bool(rules.KEY_RE.match(rule_key))


def parse_extraction(text: str) -> tuple[Extraction, list[dict[str, Any]]]:
    """Strictly parse extractor JSON. Returns (valid extraction, rejected changes)."""
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"Extractor output is not JSON: {exc.msg}") from None
    if not isinstance(data, dict) or not isinstance(data.get("changes"), list):
        raise ExtractionError("Extractor output must be an object with a 'changes' list")
    kept: list[Any] = []
    rejected: list[dict[str, Any]] = []
    for ch in data["changes"]:
        key = ch.get("rule_key") if isinstance(ch, dict) else None
        if not isinstance(key, str) or not key_allowed(key):
            rejected.append({"change": ch, "reason": "rule key not in the allowed families"})
        else:
            kept.append(ch)
    try:
        ext = Extraction.model_validate({**data, "changes": kept})
    except ValidationError as exc:
        raise ExtractionError(f"Extractor output does not match the schema: "
                              f"{exc.errors()[0]['msg']}") from None
    if not ext.changes and ext.summary.strip() != NO_CHANGE and not rejected:
        raise ExtractionError(f"An empty change list must have summary '{NO_CHANGE}'")
    return ext, rejected


def create_proposals(s: Session, ext: Extraction, *, source_url: str | None,
                     source_doc_hash: str | None, proposed_by: str = "fta-monitor"
                     ) -> tuple[list[str], list[dict[str, Any]]]:
    """``proposed`` rule versions for dated changes; undated ones are returned for review."""
    ids: list[str] = []
    undated: list[dict[str, Any]] = []
    for ch in ext.changes:
        if ch.effective_date is None:
            undated.append(ch.model_dump(mode="json"))
            continue
        row = rules.propose(s, rule_key=ch.rule_key, value=ch.proposed_value,
                            effective_from=ch.effective_date, source_url=source_url,
                            source_ref=ch.citation, proposed_by=proposed_by,
                            source_doc_hash=source_doc_hash,
                            comment=f"AI extraction ({ch.confidence} confidence); "
                                    "subject to Tax Partner review")
        ids.append(row.id)
    return ids, undated
