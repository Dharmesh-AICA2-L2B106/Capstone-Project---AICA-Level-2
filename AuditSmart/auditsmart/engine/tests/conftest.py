"""Shared fixtures: isolated settings, temporary SQLite DB and storage, signing keys, tokens."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

ENGINE = Path(__file__).resolve().parents[1]
DATA = ENGINE.parent / "data"
ISSUER = "https://login.microsoftonline.com/00000000-test-tenant/v2.0"
AUDIENCE = "api://auditsmart-engine-test"
KID = "test-key-1"
HS_SECRET = "s" * 40


@pytest.fixture(scope="session")
def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def jwks_json(rsa_key: rsa.RSAPrivateKey) -> str:
    jwk = json.loads(RSAAlgorithm.to_jwk(rsa_key.public_key()))
    jwk.update({"kid": KID, "use": "sig", "alg": "RS256"})
    return json.dumps({"keys": [jwk]})


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, jwks_json: str) -> Iterator[Path]:
    from app.core import config, db

    monkeypatch.chdir(tmp_path)  # no stray .env picked up
    values = {
        "ENVIRONMENT": "test",
        "DATABASE_URL": f"sqlite:///{tmp_path / 'test.db'}",
        "REDIS_URL": "",
        "AUTH_PROVIDER": "entra",
        "AUTH_ISSUER": ISSUER,
        "AUTH_AUDIENCE": AUDIENCE,
        "AUTH_JWKS_JSON": jwks_json,
        "AUTH_HS256_SECRET": HS_SECRET,
        "ALLOWED_ORIGINS": "https://auditsmart.example.com",
        "STORAGE_URL": f"file://{tmp_path / 'storage'}",
        "JOB_EAGER": "true",
        "PARSE_CHUNK_ROWS": "1000",
        "UPLOAD_CHUNK_MB": "1",
    }
    for k, v in values.items():
        monkeypatch.setenv(k, v)
    config.reset_settings()
    db.reset_engine()
    db.create_all()
    from app.services import rules

    rules.seed_database()
    rules.use_database(True)
    yield tmp_path
    rules.use_database(False)
    db.reset_engine()
    config.reset_settings()


def make_token(
    key: Any,
    *,
    sub: str = "user-1",
    roles: list[str] | None = None,
    alg: str = "RS256",
    iss: str = ISSUER,
    aud: str = AUDIENCE,
    exp_in: int = 600,
    extra: dict[str, Any] | None = None,
    kid: str = KID,
) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "sub": sub, "oid": sub, "iss": iss, "aud": aud, "iat": now, "nbf": now,
        "exp": now + exp_in, "roles": roles if roles is not None else ["Manager"],
    }
    claims.update(extra or {})
    return jwt.encode(claims, key, algorithm=alg, headers={"kid": kid})


@pytest.fixture
def token(rsa_key: rsa.RSAPrivateKey) -> Any:
    def _make(**kw: Any) -> str:
        return make_token(rsa_key, **kw)

    return _make


@pytest.fixture
def client(env: Path) -> Iterator[TestClient]:
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def engagement(env: Path) -> str:
    """Client + engagement with user-1 (Manager) and user-2 (Staff) as members."""
    from datetime import date

    from app.core.db import session_factory
    from app.models import Client, Engagement, EngagementMember

    with session_factory()() as s:
        c = Client(client_code="DUMMY01", name="Dummy Trading LLC", emirate="Dubai")
        s.add(c)
        s.flush()
        e = Engagement(client_id=c.id, fye=date(2025, 12, 31))
        s.add(e)
        s.flush()
        s.add_all([
            EngagementMember(engagement_id=e.id, user_id="user-1", role="Manager"),
            EngagementMember(engagement_id=e.id, user_id="user-2", role="Staff"),
        ])
        s.commit()
        return e.id


def auth(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}
