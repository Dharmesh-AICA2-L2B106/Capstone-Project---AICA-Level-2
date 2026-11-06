"""D42 unit tests: layered resolution, firm claim extraction, scope helpers."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.core import config
from app.core.security import TokenValidator
from app.services import rules as R
from tests.conftest import AUDIENCE, HS_SECRET, ISSUER, make_token

D = date(2025, 6, 30)


def _r(version: int, status: str, firm: str | None = None, eng: str | None = None,
       frm: date = date(2018, 1, 1), to: date | None = None) -> R.Rule:
    return R.Rule(rule_key="vat.rate.SR", version=version, value=str(version), status=status,
                  source_ref="t",
                  effective_from=frm, effective_to=to, id=f"id{version}", firm_id=firm,
                  engagement_id=eng)


def test_layers_and_isolation() -> None:
    pool = [_r(1, "pending_verification"), _r(2, "approved", "A"), _r(3, "approved", "A", "E"),
            _r(4, "approved", "B"), _r(5, "proposed", "A", "E2")]
    fa = R.RuleScope(firm_id="A")
    assert R.resolve("vat.rate.SR", D, pool, scope=fa, adopted=()).version == 2
    assert R.resolve("vat.rate.SR", D, pool, scope=R.RuleScope("A", "E"),
                     adopted=()).layer == "engagement"
    assert R.resolve("vat.rate.SR", D, pool, scope=R.RuleScope("A", "E2"),
                     adopted=()).version == 2
    assert R.resolve("vat.rate.SR", D, pool, scope=R.RuleScope("C"),
                     adopted=()).version == 1
    assert R.resolve("vat.rate.SR", D, pool, scope=R.NO_SCOPE).version == 1  # no firm rows
    adopted = R.resolve("vat.rate.SR", D, pool, scope=R.RuleScope("C"), adopted={("C", "id1")})
    assert adopted.status == "approved" and adopted.firm_approved and adopted.version == 1
    assert R.rule_dict(adopted)["layer"] == "default"


def test_firm_errors() -> None:
    pool = [_r(1, "pending_verification"), _r(2, "approved", "A"), _r(3, "approved", "A")]
    with pytest.raises(R.RuleConflict):
        R.resolve("vat.rate.SR", D, pool, scope=R.RuleScope("A"), adopted=())
    with pytest.raises(R.RuleNotFound, match="awaits approval"):
        R.resolve("vat.rate.SR", D, pool, scope=R.RuleScope("C", require_approved=True),
                  adopted=())
    with pytest.raises(R.RuleNotFound, match="awaits approval"):
        R.resolve("vat.rate.SR", D, pool, scope=R.RuleScope("C"), allow_pending=False,
                  adopted=())
    with pytest.raises(R.RuleNotFound, match="No approved version"):
        R.resolve("vat.rate.SR", date(2010, 1, 1), pool, scope=R.RuleScope("A"), adopted=())
    with pytest.raises(R.RuleNotFound, match="not in the Rules Library"):
        R.resolve("vat.rate.SR", D, [_r(4, "approved", "B")], scope=R.RuleScope("A"),
                  adopted=())


def test_seed_mode_has_no_adoptions() -> None:
    R.use_database(False)
    assert R.firm_adoptions() == frozenset()
    r = R.resolve("vat.rate.SR", D, scope=R.RuleScope("A"))
    assert r.status == "pending_verification"
    with R.engagement_scope(None) as sc:
        assert sc == R.NO_SCOPE


def test_scope_helpers_with_unknown_rows(env: Path) -> None:
    from app.core.db import session_factory

    with session_factory()() as s:
        assert R.firm_of_engagement(s, None) is None
        assert R.firm_of_engagement(s, "nope") is None
        assert R.scope_for_engagement(s, "nope") == R.NO_SCOPE
        assert R.scope_for_firm(s, None) == R.NO_SCOPE
        assert R.scope_for_firm(s, "unregistered") == R.RuleScope(firm_id="unregistered")
        assert R.mark_stale(s, [("x@v1", D, None)], user_id=None, reason="t",
                            engagement_ids=[]) == []
    with R.engagement_scope("nope") as sc:
        assert sc == R.NO_SCOPE


def _settings(**kw: Any) -> config.Settings:
    return config.Settings(auth_issuer=ISSUER, auth_audience=AUDIENCE,
                           auth_hs256_secret=HS_SECRET, **kw)


def test_firm_claim_extraction(env: Path, rsa_key: Any) -> None:
    sb = TokenValidator(_settings(auth_provider="supabase"))
    tok = make_token(HS_SECRET, alg="HS256",
                     extra={"app_metadata": {"roles": ["Partner"], "firm_id": "firm-x"}})
    assert sb.validate(tok).firm_id == "firm-x"
    tok = make_token(HS_SECRET, alg="HS256", extra={"firm_id": "  "})
    assert sb.validate(tok).firm_id is None
    custom = TokenValidator(_settings(auth_provider="supabase", auth_firm_claim="tenant"))
    tok = make_token(HS_SECRET, alg="HS256", extra={"app_metadata": {"tenant": "t-1"}})
    assert custom.validate(tok).firm_id == "t-1"
    # D48: Supabase reads app_metadata only - a top-level or user_metadata firm is ignored
    for extra in ({"firm_id": "firm-top"}, {"user_metadata": {"firm_id": "firm-um"}},
                  {"app_metadata": "not-a-dict", "firm_id": "firm-top"}):
        assert sb.validate(make_token(HS_SECRET, alg="HS256", extra=extra)).firm_id is None
    tok = make_token(HS_SECRET, alg="HS256",
                     extra={"firm_id": "firm-top", "app_metadata": {"firm_id": "firm-am"}})
    assert sb.validate(tok).firm_id == "firm-am"
    # dev (local only) mirrors Supabase but still accepts a top-level claim
    dev = TokenValidator(_settings(auth_provider="dev", environment="development"))
    assert dev.validate(make_token(HS_SECRET, alg="HS256",
                                   extra={"firm_id": "firm-top"})).firm_id == "firm-top"
    assert dev.validate(make_token(HS_SECRET, alg="HS256", extra={
        "firm_id": "firm-top", "app_metadata": {"firm_id": "firm-am"}})).firm_id == "firm-am"
    assert sb.validate(make_token(HS_SECRET, alg="HS256")).firm_id is None
    # Entra: top-level claim only (app_metadata is not an Entra concept)
    entra = TokenValidator(_settings(auth_provider="entra"))
    assert entra._principal({"sub": "u", "firm_id": "firm-e"}).firm_id == "firm-e"
    assert entra._principal({"sub": "u", "app_metadata": {"firm_id": "x"}}).firm_id is None
