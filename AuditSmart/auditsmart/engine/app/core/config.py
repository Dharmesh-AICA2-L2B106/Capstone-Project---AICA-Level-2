"""Runtime configuration (12-factor: everything comes from environment variables / .env)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENGINE_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"

    # Required by prompt 3.1 (.env.example)
    database_url: str = ""  # empty -> local SQLite file (Workbook Stage 3 caution)
    redis_url: str = ""  # empty -> in-process job runner
    auth_issuer: str = ""
    auth_audience: str = ""
    allowed_origins: str = ""  # comma separated whitelist
    ai_provider: str = ""  # used from prompt 3.7 only; never for calculations
    ai_model: str = ""
    storage_url: str = ""  # empty -> file://<engine>/storage

    # Authentication details
    auth_provider: Literal["entra", "supabase", "dev"] = "entra"
    auth_jwks_url: str = ""  # default derived from issuer
    auth_jwks_json: str = ""  # static JWKS (tests / air-gapped)
    auth_hs256_secret: str = ""  # Supabase legacy JWT secret or dev secret
    auth_leeway_seconds: int = 30
    # D42 multi-firm: token claim naming the user's firm (top level, or Supabase app_metadata).
    # A token without it is a platform / single-firm user (shared defaults only).
    auth_firm_claim: str = "firm_id"

    # Upload limits (SPEC 3.6)
    max_upload_mb: int = 500
    upload_chunk_mb: int = 8
    parse_chunk_rows: int = 50_000
    job_eager: bool = False  # run jobs synchronously (tests / CLI)
    # D24: resolve pending_verification rules until the Tax Partner approves the seed (3.8).
    # D42/D44: stays true by default so a new firm can start at once; a firm can tighten it
    # for itself (firms.require_approved_rules) but never loosen a false value here.
    rules_allow_pending: bool = True

    log_level: str = "INFO"

    @field_validator("auth_hs256_secret")
    @classmethod
    def _no_short_secret(cls, v: str) -> str:
        if v and len(v) < 32:
            raise ValueError("AUTH_HS256_SECRET must be at least 32 characters")
        return v

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{ENGINE_ROOT / 'auditsmart_dev.db'}"

    @property
    def storage_path(self) -> Path:
        url = self.storage_url or f"file://{ENGINE_ROOT / 'storage'}"
        if not url.startswith("file://"):
            raise ValueError("Only file:// storage is implemented; Azure Blob arrives in Stage 7")
        return Path(url.removeprefix("file://"))

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def upload_chunk_bytes(self) -> int:
        return self.upload_chunk_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings() -> None:
    get_settings.cache_clear()


ROLE_NAMES = ("Admin", "Partner", "Manager", "Senior", "Staff", "TaxPartner")
