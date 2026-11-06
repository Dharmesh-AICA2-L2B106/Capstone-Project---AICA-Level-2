from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.v1.deps import CurrentUser, require_engagement_member, require_roles
from app.core import config
from app.core.security import AuthError, Principal, TokenValidator, normalise_roles
from app.models import EngagementMember
from tests.conftest import AUDIENCE, HS_SECRET, ISSUER, auth, make_token

pytestmark = pytest.mark.security


@pytest.fixture
def app_client(env: Path) -> TestClient:
    app = FastAPI()

    @app.get("/me")
    def me(user: CurrentUser) -> dict[str, Any]:
        return {"user_id": user.user_id, "roles": sorted(user.roles)}

    @app.get("/admin", dependencies=[Depends(require_roles("Admin", "TaxPartner"))])
    def admin() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/engagements/{engagement_id}/manage")
    def manage(m: EngagementMember = Depends(require_engagement_member("Manager", "Partner"))
               ) -> dict[str, str]:
        return {"role": m.role}

    @app.get("/engagements/{engagement_id}/view")
    def view(m: EngagementMember = Depends(require_engagement_member())) -> dict[str, str]:
        return {"role": m.role}

    return TestClient(app)


def test_valid_entra_token(app_client: TestClient, token: Any) -> None:
    r = app_client.get("/me", headers=auth(token(roles=["Manager", "unknown-role"])))
    assert r.status_code == 200
    assert r.json() == {"user_id": "user-1", "roles": ["Manager"]}


@pytest.mark.parametrize(
    "kwargs",
    [{"iss": "https://evil.example/v2.0"}, {"aud": "api://other"}, {"exp_in": -3600},
     {"kid": "unknown-kid"}],
    ids=["wrong-issuer", "wrong-audience", "expired", "unknown-kid"],
)
def test_rejected_tokens(app_client: TestClient, token: Any, kwargs: dict[str, Any]) -> None:
    r = app_client.get("/me", headers=auth(token(**kwargs)))
    assert r.status_code == 401
    assert "not valid" in r.json()["detail"]


def test_missing_and_malformed_token(app_client: TestClient) -> None:
    assert app_client.get("/me").status_code == 401
    assert app_client.get("/me", headers=auth("not-a-jwt")).status_code == 401


def test_bad_signature(app_client: TestClient) -> None:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert app_client.get("/me", headers=auth(make_token(other))).status_code == 401


def test_alg_none_and_hs256_confusion_rejected(app_client: TestClient, jwks_json: str) -> None:
    unsigned = jwt.encode({"sub": "x", "iss": ISSUER, "aud": AUDIENCE}, None, algorithm="none")
    assert app_client.get("/me", headers=auth(unsigned)).status_code == 401
    # HS256 signed with the public key material (classic algorithm confusion attack)
    forged = make_token(HS_SECRET, alg="HS256")
    assert app_client.get("/me", headers=auth(forged)).status_code == 401


def test_role_dependency(app_client: TestClient, token: Any) -> None:
    assert app_client.get("/admin", headers=auth(token(roles=["Manager"]))).status_code == 403
    assert app_client.get("/admin", headers=auth(token(roles=["Tax Partner"]))).status_code == 200


def test_membership_dependency(app_client: TestClient, token: Any, engagement: str) -> None:
    url = f"/engagements/{engagement}"
    assert app_client.get(f"{url}/manage", headers=auth(token(sub="user-1"))).json() == {
        "role": "Manager"
    }
    r = app_client.get(f"{url}/manage", headers=auth(token(sub="user-2")))
    assert r.status_code == 403 and "Staff" in r.json()["detail"]
    assert app_client.get(f"{url}/view", headers=auth(token(sub="user-2"))).status_code == 200
    r = app_client.get(f"{url}/view", headers=auth(token(sub="outsider")))
    assert r.status_code == 403 and "not a member" in r.json()["detail"]


def _settings(**kw: Any) -> config.Settings:
    base: dict[str, Any] = {"auth_issuer": ISSUER, "auth_audience": AUDIENCE,
                            "auth_hs256_secret": HS_SECRET}
    base.update(kw)
    return config.Settings(**base)


def test_supabase_hs256_and_app_metadata_roles(env: Path) -> None:
    v = TokenValidator(_settings(auth_provider="supabase"))
    tok = make_token(HS_SECRET, alg="HS256", sub="sb-user",
                     extra={"app_metadata": {"roles": ["Senior"]}, "email": "a@b.test"})
    p = v.validate(tok)
    assert p == Principal(user_id="sb-user", roles=frozenset({"Senior"}), email="a@b.test",
                          provider="supabase")
    tok2 = make_token(HS_SECRET, alg="HS256", extra={"app_metadata": {"role": "admin"}})
    assert v.validate(tok2).roles == frozenset({"Admin"})


def test_supabase_rs256_via_jwks(env: Path, rsa_key: rsa.RSAPrivateKey, jwks_json: str) -> None:
    v = TokenValidator(_settings(auth_provider="supabase", auth_jwks_json=jwks_json))
    p = v.validate(make_token(rsa_key, extra={"app_metadata": {"roles": ["Partner"]}}))
    assert p.roles == frozenset({"Partner"})
    assert len(p.user_ref) == 12 and p.user_id not in p.user_ref


def test_supabase_hs256_without_secret(env: Path) -> None:
    v = TokenValidator(_settings(auth_provider="supabase", auth_hs256_secret=""))
    with pytest.raises(AuthError):
        v.validate(make_token(HS_SECRET, alg="HS256"))


def test_dev_mode_only_in_development(env: Path) -> None:
    tok = make_token(HS_SECRET, alg="HS256", roles=["Admin"])
    assert TokenValidator(_settings(auth_provider="dev", environment="development")).validate(
        tok
    ).roles == frozenset({"Admin"})
    with pytest.raises(AuthError):
        TokenValidator(_settings(auth_provider="dev", environment="production")).validate(tok)


def test_unconfigured_auth_rejects(env: Path, rsa_key: rsa.RSAPrivateKey) -> None:
    with pytest.raises(AuthError):
        TokenValidator(config.Settings(auth_issuer="", auth_audience="")).validate(
            make_token(rsa_key))


def test_jwks_url_derivation() -> None:
    e = TokenValidator(config.Settings(auth_provider="entra", auth_issuer=ISSUER))
    assert e._jwks_url() == (
        "https://login.microsoftonline.com/00000000-test-tenant/discovery/v2.0/keys")
    s = TokenValidator(config.Settings(auth_provider="supabase",
                                       auth_issuer="https://p.supabase.co/auth/v1"))
    assert s._jwks_url() == "https://p.supabase.co/auth/v1/.well-known/jwks.json"
    o = TokenValidator(config.Settings(auth_jwks_url="https://keys.example/jwks"))
    assert o._jwks_url() == "https://keys.example/jwks"


def test_normalise_roles() -> None:
    assert normalise_roles(None) == frozenset()
    assert normalise_roles("tax_partner") == frozenset({"TaxPartner"})
    assert normalise_roles(["ADMIN", "x"]) == frozenset({"Admin"})


def test_jwks_json_loaded(jwks_json: str) -> None:
    v = TokenValidator(config.Settings(auth_jwks_json=jwks_json))
    assert list(v._static_keys) == [json.loads(jwks_json)["keys"][0]["kid"]]


def test_auth_failures_not_logged_with_token(
    app_client: TestClient, token: Any, caplog: pytest.LogCaptureFixture
) -> None:
    tok = token(exp_in=-10)
    with caplog.at_level(logging.DEBUG):
        app_client.get("/me", headers=auth(tok))
    assert tok not in caplog.text
