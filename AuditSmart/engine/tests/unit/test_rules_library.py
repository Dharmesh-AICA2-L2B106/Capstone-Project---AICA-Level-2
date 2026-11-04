"""Rules Library (prompt 3.8): version by date, exactly-one, overlap, immutability, workflow."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from app.core.db import session_factory
from app.models import AuditLog, RuleVersion
from app.services import rule_proposals as rp
from app.services import rules
from app.services.rules import Rule, RuleConflict, RuleError, RuleNotFound

TP = ("TaxPartner",)
OK = "Verified against the FTA source text"


def _r(v: int, frm: str, to: str | None = None, status: str = "approved", key: str = "x.y",
       value: Any = None) -> Rule:
    return Rule(rule_key=key, version=v, effective_from=date.fromisoformat(frm),
                effective_to=date.fromisoformat(to) if to else None, value=value or v,
                status=status, source_ref="")


def test_resolve_by_date_and_exactly_one() -> None:
    rs = [_r(1, "2018-01-01", "2025-12-31"), _r(2, "2026-01-01")]
    assert rules.resolve("x.y", date(2025, 6, 1), rs).version == 1
    assert rules.resolve("x.y", date(2026, 1, 1), rs).version == 2
    with pytest.raises(RuleNotFound, match="No approved version"):
        rules.resolve("x.y", date(2017, 1, 1), rs)
    with pytest.raises(RuleNotFound, match="not in the Rules Library"):
        rules.resolve("nope.key", date(2025, 1, 1), rs)
    with pytest.raises(RuleConflict, match="2 approved versions"):
        rules.resolve("x.y", date(2026, 2, 1), [*rs, _r(3, "2026-02-01")])


def test_pending_fallback_and_strict_mode() -> None:
    rs = [_r(1, "2018-01-01", status="pending_verification"), _r(2, "2018-01-01",
                                                                  status="proposed")]
    assert rules.resolve("x.y", date(2025, 1, 1), rs, allow_pending=True).version == 1
    with pytest.raises(RuleNotFound, match="awaits Tax Partner approval"):
        rules.resolve("x.y", date(2025, 1, 1), rs, allow_pending=False)
    # approved wins over pending
    both = [*rs, _r(3, "2025-01-01")]
    assert rules.resolve("x.y", date(2025, 6, 1), both, allow_pending=True).version == 3
    with pytest.raises(RuleConflict):
        rules.resolve("x.y", date(2025, 1, 1),
                      [*rs, _r(4, "2019-01-01", status="pending_verification")],
                      allow_pending=True)


def test_seed_file_registry_without_db() -> None:
    rules.use_database(False)
    r = rules.get_rule("input_vat.verification.spend_threshold", date(2026, 10, 1))
    assert r.value == "375000.00" and r.domain == "INPUT_VAT" and r.status == \
        "pending_verification"
    with pytest.raises(RuleNotFound):  # Decision 13 is not effective before 1 Oct 2026
        rules.get_rule("input_vat.verification.spend_threshold", date(2026, 9, 30))
    url = rules.get_rule("legal_ref.input_vat.employee_expenses", date(2026, 10, 1)).source_url
    assert url is not None and url.startswith("https://tax.gov.ae/")
    assert rules.domain_of("zzz.a") == "OTHER"
    assert rules.by_ref("vat.rate.SR@v1") is not None and rules.by_ref("vat.rate.SR@v9") is None


def test_seed_values_have_no_invented_urls() -> None:
    known = Path(__file__).resolve().parents[3] / "prompts" / "stage2_tests"
    text = "".join(p.read_text(encoding="utf-8") for p in known.glob("*.txt"))
    for r in rules.load_rules():
        assert r.status == "pending_verification"
        if r.source_url:
            assert r.source_url in text, r.ref


def _id(key: str, version: int = 1) -> str:
    with session_factory()() as s:
        return s.scalars(select(RuleVersion.id).where(RuleVersion.rule_key == key,
                                                      RuleVersion.version == version)).one()


def test_db_seed_idempotent_and_resolves(env: Path) -> None:
    assert rules.seed_database() == 0
    assert rules.get_rule("vat.rate.SR", date(2025, 1, 1)).id is not None
    with session_factory()() as s:
        assert rules.seed_database(s) == 0
        assert len(rules.list_versions(s, domain="legal_ref")) == 4
        assert rules.list_versions(s, rule_key="vat.rate.SR", status="pending_verification")


def test_propose_validation(env: Path) -> None:
    with session_factory()() as s:
        for kw, msg in (({"rule_key": "Bad Key"}, "Invalid rule key"),
                        ({"effective_to": date(2020, 1, 1)}, "before effective_from"),
                        ({"source_url": "http://x"}, "https://")):
            args: dict[str, Any] = {"rule_key": "vat.rate.SR", "value": "0.05",
                                    "effective_from": date(2026, 1, 1), **kw}
            with pytest.raises(RuleError, match=msg):
                rules.propose(s, **args)
        row = rules.propose(s, rule_key="vat.rate.SR", value="0.05",
                            effective_from=date(2026, 1, 1), proposed_by="u1")
        assert row.version == 2 and row.status == "proposed" and row.domain == "VAT"


def test_approve_roles_comment_and_reject(env: Path) -> None:
    with session_factory()() as s:
        row = rules.propose(s, rule_key="ct.rate.standard", value="0.10",
                            effective_from=date(2027, 1, 1))
        with pytest.raises(RuleError) as e:
            rules.approve(s, row.id, user_id="m", roles=("Manager", "Partner"), comment=OK)
        assert e.value.status_code == 403
        with pytest.raises(RuleError, match="mandatory"):
            rules.approve(s, row.id, user_id="tp", roles=TP, comment="ok")
        with pytest.raises(RuleError) as e:
            rules.approve(s, "missing", user_id="tp", roles=TP, comment=OK)
        assert e.value.status_code == 404
        with pytest.raises(RuleError) as e:
            rules.reject(s, "missing", user_id="tp", roles=TP, comment=OK)
        assert e.value.status_code == 404
        rej = rules.reject(s, row.id, user_id="tp", roles=TP, comment="Not supported by law")
        assert rej.status == "rejected"
        with pytest.raises(RuleError) as e:
            rules.reject(s, row.id, user_id="tp", roles=TP, comment=OK)
        assert e.value.status_code == 409
        with pytest.raises(RuleError) as e:
            rules.approve(s, row.id, user_id="tp", roles=TP, comment=OK)
        assert e.value.status_code == 409


def test_shared_default_approvers_follow_domain_split_no_admin(env: Path) -> None:
    """D47: platform Admin never approves; tax -> TaxPartner, methodology -> Partner."""
    with session_factory()() as s:
        tax = rules.propose(s, rule_key="vat.rate.SR", value="0.06",
                            effective_from=date(2028, 1, 1))
        meth = rules.propose(s, rule_key="sampling.mus.cf.95", value="3.10",
                             effective_from=date(2028, 1, 1))
        for row in (tax, meth):
            for fn in (rules.approve, rules.reject):
                for roles in (["Admin"], ["Admin", "Manager"]):
                    with pytest.raises(RuleError, match="Admin never approves") as e:
                        fn(s, row.id, user_id="adm", roles=roles, comment=OK)
                    assert e.value.status_code == 403
        with pytest.raises(RuleError, match="TaxPartner can approve or reject tax") as e:
            rules.approve(s, tax.id, user_id="p", roles=["Partner"], comment=OK)
        assert e.value.status_code == 403
        with pytest.raises(RuleError, match="Partner can approve or reject methodology") as e:
            rules.approve(s, meth.id, user_id="tp", roles=TP, comment=OK)
        assert e.value.status_code == 403
        with pytest.raises(RuleError, match="mandatory"):
            rules.approve(s, meth.id, user_id="p", roles=["Partner"], comment="ok")
        assert rules.approve(s, meth.id, user_id="p", roles=["Partner"],
                             comment=OK).rule.status == "approved"
        assert rules.approve(s, tax.id, user_id="tp", roles=["TaxPartner", "Admin"],
                             comment=OK).rule.status == "approved"
        rej = rules.propose(s, rule_key="je.round_sum.min", value="20000",
                            effective_from=date(2028, 1, 1))
        assert rules.reject(s, rej.id, user_id="p", roles=["Partner"],
                            comment="Not agreed by the firm").status == "rejected"


def test_approve_seed_then_new_version_closes_prior(env: Path) -> None:
    sid = _id("vat.rate.SR")
    with session_factory()() as s:
        a = rules.approve(s, sid, user_id="tp", roles=TP, comment=OK)
        assert a.rule.status == "approved" and not a.closed and not a.stale
        new = rules.propose(s, rule_key="vat.rate.SR", value="0.06",
                            effective_from=date(2027, 1, 1), source_ref="hypothetical test")
        a2 = rules.approve(s, new.id, user_id="tp", roles=TP, comment=OK)
        assert a2.closed == [{"ref": "vat.rate.SR@v1", "effective_to": date(2026, 12, 31)}]
        assert a2.as_dict()["closed"][0]["effective_to"] == "2026-12-31"
        actions = s.scalars(select(AuditLog.action).where(AuditLog.entity == "rule_version"))
        assert {"rule_approve", "rule_close", "rule_propose"} <= set(actions)
    assert rules.get_rule("vat.rate.SR", date(2026, 12, 31)).version == 1
    assert rules.get_rule("vat.rate.SR", date(2027, 1, 1)).value == "0.06"


def test_overlap_rejected(env: Path) -> None:
    with session_factory()() as s:
        rules.approve(s, _id("vat.rate.ZR"), user_id="tp", roles=TP, comment=OK)
        same = rules.propose(s, rule_key="vat.rate.ZR", value="0.00",
                             effective_from=date(2018, 1, 1))
        with pytest.raises(RuleError, match=r"overlaps approved vat\.rate\.ZR@v1") as e:
            rules.approve(s, same.id, user_id="tp", roles=TP, comment=OK)
        assert e.value.status_code == 409
        # a bounded window inside an open approved version would split it -> rejected
        win = rules.propose(s, rule_key="vat.rate.ZR", value="0.01",
                            effective_from=date(2026, 1, 1), effective_to=date(2026, 6, 30))
        with pytest.raises(RuleError, match="overlaps"):
            rules.approve(s, win.id, user_id="tp", roles=TP, comment=OK)
        # an open-ended later version closes v1
        later = rules.propose(s, rule_key="vat.rate.ZR", value="0.00",
                              effective_from=date(2030, 1, 1))
        assert rules.approve(s, later.id, user_id="tp", roles=TP, comment=OK).closed
        with pytest.raises(RuleError, match=r"overlaps approved vat.rate.ZR@v1 \(2018-01-01 to "
                           "2029-12-31"):
            rules.approve(s, win.id, user_id="tp", roles=TP, comment=OK)


def test_pending_seed_superseded_or_closed(env: Path) -> None:
    with session_factory()() as s:
        same = rules.propose(s, rule_key="vat.rate.EX", value="0.00",
                             effective_from=date(2018, 1, 1))
        a = rules.approve(s, same.id, user_id="tp", roles=TP, comment=OK)
        assert a.superseded == [{"ref": "vat.rate.EX@v1"}]
        later = rules.propose(s, rule_key="vat.tolerance", value="0.10",
                              effective_from=date(2026, 1, 1))
        a = rules.approve(s, later.id, user_id="tp", roles=TP, comment=OK)
        assert a.closed[0]["ref"] == "vat.tolerance@v1"


def test_approved_rows_are_immutable(env: Path) -> None:
    sid = _id("vat.rate.RC")
    with session_factory()() as s:
        rules.approve(s, sid, user_id="tp", roles=TP, comment=OK)
    for change in ({"value": "0.07"}, {"effective_from": date(2019, 1, 1)},
                   {"status": "rejected"}, {"effective_to": None, "_reopen": True}):
        with session_factory()() as s:
            row = s.get(RuleVersion, sid)
            assert row is not None
            if change.pop("_reopen", False):
                row.effective_to = date(2030, 1, 1)
                s.commit()
                row.effective_to = date(2031, 1, 1)
            else:
                for k, v in change.items():
                    setattr(row, k, v)
            with pytest.raises(rules.ImmutableRuleError):
                s.commit()
    with session_factory()() as s:
        row = s.get(RuleVersion, sid)
        s.delete(row)
        with pytest.raises(rules.ImmutableRuleError, match="cannot be deleted"):
            s.commit()
    with session_factory()() as s:  # closing earlier + superseding are allowed
        row = s.get(RuleVersion, sid)
        assert row is not None and row.effective_to == date(2030, 1, 1)
        row.effective_to = date(2029, 1, 1)
        row.status = "superseded"
        s.commit()
    with session_factory()() as s:  # pending rows are freely editable / deletable
        row = s.get(RuleVersion, _id("je.round_sum.min"))
        row.value = 1
        s.commit()
        s.delete(row)
        s.commit()


EXTRACT = ('{"summary":"Employee expenses","changes":['
           '{"rule_key":"input_vat.employee_expense.new_employee_accommodation_max_days",'
           '"current_value":null,"proposed_value":30,"effective_date":"2026-10-01",'
           '"citation":"FTA Decision No. 17 of 2026, Article 2(4)(a)","confidence":"high"},'
           '{"rule_key":"legal_ref.input_vat.employee_expenses","current_value":null,'
           '"proposed_value":"FTA Decision No. 17 of 2026","effective_date":null,'
           '"citation":"FTA Decision No. 17 of 2026, Article 3","confidence":"medium"},'
           '{"rule_key":"sampling.mus.cf.95","current_value":3,"proposed_value":2,'
           '"effective_date":"2026-10-01","citation":"made up","confidence":"low"}]}')


def test_extraction_parser_and_proposals(env: Path) -> None:
    ext, rejected = rp.parse_extraction("```json\n" + EXTRACT + "\n```")
    assert ext.changes[0].rule_key.endswith("max_days")
    assert rejected[0]["change"]["rule_key"] == "sampling.mus.cf.95"
    with session_factory()() as s:
        ids, undated = rp.create_proposals(s, ext, source_url=None, source_doc_hash="ab" * 32)
        assert len(ids) == 1 and undated[0]["rule_key"].startswith("legal_ref")
        row = s.get(RuleVersion, ids[0])
        assert row is not None and row.status == "proposed" and row.version == 2
    none, rej = rp.parse_extraction('{"summary":"No relevant change","changes":[]}')
    assert none.changes == [] and rej == []
    for bad, msg in (("not json", "not JSON"), ('{"summary":"x"}', "'changes' list"),
                     ('{"summary":"x","changes":[]}', "No relevant change"),
                     ('{"summary":"x","changes":[{"rule_key":"vat.codes"}]}', "schema"),
                     ('{"summary":"x","extra":1,"changes":[]}', "schema")):
        with pytest.raises(rp.ExtractionError, match=msg):
            rp.parse_extraction(bad)
    assert rp.PROMPT_PATH.read_text(encoding="utf-8") == (
        Path(__file__).resolve().parents[3] / "prompts" / "rule_extraction_prompt.txt"
    ).read_text(encoding="utf-8")
    assert not rp.key_allowed("input_vat.verification")
