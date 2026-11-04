"""Observations (prompt 3.7): AI-drafted audit observations and their human review.

Flow: sample item -> anonymised payload (whitelist + scrub + assert_clean) -> provider ->
validated draft -> ``observations`` row (ai_generated, prompt_version, model). A reviewer
(Senior/Manager/Partner) must accept or edit it before the working paper can be generated.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services import ai_gateway, anonymiser

REVIEW_ROLES = ("Senior", "Manager", "Partner")


class ObservationError(Exception):
    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _references(rule_keys: list[str], on: Any) -> list[dict[str, str]]:
    from app.services.rules import RuleNotFound, get_rule

    refs = []
    for key in rule_keys:
        try:
            r = get_rule(key, on)
        except RuleNotFound:
            raise ObservationError(f"Rule '{key}' is not in the Rules Library; cite only "
                                   "rules from the library.") from None
        refs.append({"ref": r.ref, "citation": r.source_ref})
    return refs


def _describe(ob: Any, line_ref: str, engagement_id: str) -> dict[str, Any]:
    return {"observation_id": ob.id, "sample_item_id": ob.sample_item_id, "line_ref": line_ref,
            "engagement_id": engagement_id, "text": ob.text, "ai_generated": ob.ai_generated,
            "prompt_version": ob.prompt_version, "model": ob.model,
            "reviewed_by": ob.reviewed_by,
            "reviewed_at": (ob.reviewed_at if ob.reviewed_at.tzinfo else
                            ob.reviewed_at.replace(tzinfo=UTC)).isoformat()
            if ob.reviewed_at else None}


def item_engagement(sample_item_id: str) -> str:
    from app.core.db import session_factory
    from app.models import Sample, SampleItem

    with session_factory()() as s:
        si = s.get(SampleItem, sample_item_id)
        smp = s.get(Sample, si.sample_id) if si else None
        if smp is None:
            raise ObservationError("Sample item not found.", 404)
        return smp.engagement_id


def draft(*, sample_item_id: str, user_id: str, failed_attribute: str, test: str,
          remark: str | None, rule_keys: list[str],
          provider: ai_gateway.Provider | None = None) -> dict[str, Any]:
    from app.core.db import session_factory
    from app.models import (
        AuditLog,
        Client,
        Dataset,
        Engagement,
        Observation,
        Sample,
        SampleItem,
        SupplierRegister,
    )
    from app.services.importer import read_parquet_rows

    with session_factory()() as s:
        si = s.get(SampleItem, sample_item_id)
        smp = s.get(Sample, si.sample_id) if si else None
        if si is None or smp is None:
            raise ObservationError("Sample item not found.", 404)
        eng = s.get(Engagement, smp.engagement_id)
        cl = s.get(Client, eng.client_id) if eng else None
        ds = s.get(Dataset, smp.dataset_id)
        rows = list(read_parquet_rows(Path(ds.parquet_ref))) if ds and ds.parquet_ref else []
        reg = [{"party_name": r.supplier_name, "trn": r.trn, "user_id": r.supplier_id}
               for r in s.query(SupplierRegister).filter_by(engagement_id=smp.engagement_id)]
        names = anonymiser.forbidden_terms(client_name=cl.name if cl else None,
                                           client_code=cl.client_code if cl else None,
                                           rows=rows, register=reg)
        line = next((r for r in rows if str(r.get("line_id")) == si.line_ref), {})
        area = " / ".join(str(x) for x in (line.get("account_type"), line.get("account_name"))
                          if x) or "Not provided"
        try:
            payload = anonymiser.build_payload(
                area=area, test=test, item_ref=si.line_ref,
                amounts={"book_value": si.book_value, "audited_value": si.audited_value,
                         "misstatement": si.misstatement},
                failed_attribute=failed_attribute,
                applicable_references=_references(rule_keys, eng.fye if eng else None),
                auditor_remark=remark if remark is not None else si.remarks, names=names)
        except anonymiser.AnonymisationError as exc:  # pragma: no cover - defence in depth
            raise ObservationError(str(exc), 422) from None
        try:
            res = ai_gateway.draft_observation(payload, provider or ai_gateway.get_provider())
        except ai_gateway.AIError as exc:
            raise ObservationError(exc.message, exc.status_code) from None
        ob = Observation(sample_item_id=si.id, text=res["draft"], ai_generated=True,
                         prompt_version=res["prompt_version"], model=res["model"])
        s.add(ob)
        s.flush()
        s.add(AuditLog(user_id=user_id, action="ai_draft", entity="observation", entity_id=ob.id,
                       new={"sample_item_id": si.id, "prompt_version": res["prompt_version"],
                            "provider": res["provider"], "model": res["model"],
                            "attempts": res["attempts"]}))
        s.commit()
        out = _describe(ob, si.line_ref, smp.engagement_id)
        out.update(payload=payload, label=res["label"], provider=res["provider"],
                   attempts=res["attempts"], temperature=res["temperature"],
                   warnings=res["warnings"])
        return out


def get(observation_id: str) -> dict[str, Any]:
    from app.core.db import session_factory
    from app.models import Observation, Sample, SampleItem

    with session_factory()() as s:
        ob = s.get(Observation, observation_id)
        si = s.get(SampleItem, ob.sample_item_id) if ob else None
        smp = s.get(Sample, si.sample_id) if si else None
        if ob is None or si is None or smp is None:
            raise ObservationError("Observation not found.", 404)
        return _describe(ob, si.line_ref, smp.engagement_id)


def review(observation_id: str, *, user_id: str, text: dict[str, str] | None) -> dict[str, Any]:
    from app.core.db import session_factory
    from app.models import AuditLog, Observation

    with session_factory()() as s:
        ob = s.get(Observation, observation_id)
        if ob is None:  # pragma: no cover - checked by get() in the API first
            raise ObservationError("Observation not found.", 404)
        old = {"text": ob.text, "reviewed_by": ob.reviewed_by}
        if text is not None:
            ob.text = text
        ob.reviewed_by, ob.reviewed_at = user_id, datetime.now(UTC)
        s.add(AuditLog(user_id=user_id, action="review", entity="observation", entity_id=ob.id,
                       old=old, new={"text": ob.text, "reviewed_by": user_id,
                                     "edited": text is not None}))
        s.commit()
    return get(observation_id)
