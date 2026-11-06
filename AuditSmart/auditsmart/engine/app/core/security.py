"""JWT validation for Microsoft Entra ID and Supabase (selected by AUTH_PROVIDER).

* entra    – RS256 tokens, keys from the tenant JWKS; roles from the ``roles`` claim (app roles).
* supabase – RS256/ES256 via the project JWKS, or HS256 with the legacy JWT secret;
             roles from ``app_metadata.roles`` (list) or ``app_metadata.role``.
* dev      – HS256 with AUTH_HS256_SECRET; refused unless ENVIRONMENT=development.

Issuer, audience, exp and iat are always required. ``alg=none`` and algorithm confusion
(HS256 token against an RSA key) are rejected because the accepted algorithms are fixed
per provider.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

import jwt
from jwt import PyJWK, PyJWKClient

from app.core.config import ROLE_NAMES, Settings

_ROLE_LOOKUP = {r.lower(): r for r in ROLE_NAMES} | {
    "tax_partner": "TaxPartner",
    "taxpartner": "TaxPartner",
}


class AuthError(Exception):
    """Raised for any token problem; the API maps it to 401 without details."""


@dataclass(frozen=True)
class Principal:
    user_id: str
    roles: frozenset[str] = field(default_factory=frozenset)
    email: str | None = None
    provider: str = ""
    firm_id: str | None = None  # D42: the audit firm (tenant); None = platform / single-firm

    @property
    def user_ref(self) -> str:
        """Pseudonymous id safe for logs."""
        return hashlib.sha256(self.user_id.encode()).hexdigest()[:12]

    def has_any(self, *roles: str) -> bool:
        return bool(self.roles.intersection(roles))


def normalise_roles(raw: Any) -> frozenset[str]:
    if raw is None:
        return frozenset()
    items = [raw] if isinstance(raw, str) else list(raw)
    out = set()
    for item in items:
        key = str(item).strip().lower().replace(" ", "")
        if key in _ROLE_LOOKUP:
            out.add(_ROLE_LOOKUP[key])
    return frozenset(out)


class TokenValidator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._jwks_client: PyJWKClient | None = None
        self._static_keys: dict[str, PyJWK] = {}
        if settings.auth_jwks_json:
            data = json.loads(settings.auth_jwks_json)
            for k in data.get("keys", []):
                self._static_keys[k.get("kid", "")] = PyJWK(k)

    # -- key resolution -------------------------------------------------------
    def _jwks_url(self) -> str:
        s = self.settings
        if s.auth_jwks_url:
            return s.auth_jwks_url
        iss = s.auth_issuer.rstrip("/")
        if s.auth_provider == "entra":
            # https://login.microsoftonline.com/{tenant}/v2.0 -> .../discovery/v2.0/keys
            return iss.removesuffix("/v2.0") + "/discovery/v2.0/keys"
        return iss + "/.well-known/jwks.json"

    def _asymmetric_key(self, token: str) -> Any:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid", "")
        if self._static_keys:
            if kid not in self._static_keys:
                raise AuthError("unknown signing key")
            return self._static_keys[kid].key
        if self._jwks_client is None:  # pragma: no cover - network path
            self._jwks_client = PyJWKClient(self._jwks_url(), cache_keys=True, timeout=5)
        return self._jwks_client.get_signing_key_from_jwt(token).key  # pragma: no cover

    # -- validation -------------------------------------------------------------
    def validate(self, token: str) -> Principal:
        s = self.settings
        if not s.auth_issuer or not s.auth_audience:
            raise AuthError("authentication is not configured")
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise AuthError("malformed token") from exc
        alg = header.get("alg", "")
        if s.auth_provider == "dev":
            if s.environment != "development" or not s.auth_hs256_secret:
                raise AuthError("dev authentication is disabled")
            algorithms, key = ["HS256"], s.auth_hs256_secret
        elif s.auth_provider == "supabase" and alg == "HS256":
            if not s.auth_hs256_secret:
                raise AuthError("HS256 not configured")
            algorithms, key = ["HS256"], s.auth_hs256_secret
        else:
            algorithms = ["RS256"] if s.auth_provider == "entra" else ["RS256", "ES256"]
            if alg not in algorithms:
                raise AuthError("algorithm not allowed")
            key = self._asymmetric_key(token)
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key,
                algorithms=algorithms,
                audience=s.auth_audience,
                issuer=s.auth_issuer,
                leeway=s.auth_leeway_seconds,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthError(type(exc).__name__) from exc
        return self._principal(claims)

    def _principal(self, claims: dict[str, Any]) -> Principal:
        provider = self.settings.auth_provider
        claim = self.settings.auth_firm_claim
        meta = claims.get("app_metadata") or {}
        raw_firm = claims.get(claim) if provider == "entra" else meta.get(claim, claims.get(claim))
        firm_id = str(raw_firm).strip()[:64] if raw_firm not in (None, "") else None
        if provider == "entra":
            user_id = str(claims.get("oid") or claims["sub"])
            roles = normalise_roles(claims.get("roles"))
            email = claims.get("preferred_username") or claims.get("email")
        else:
            user_id = str(claims["sub"])
            roles = normalise_roles(meta.get("roles", meta.get("role")))
            if provider == "dev" and not roles:
                roles = normalise_roles(claims.get("roles"))
            email = claims.get("email")
        return Principal(user_id=user_id, roles=roles, email=email, provider=provider,
                         firm_id=firm_id or None)
