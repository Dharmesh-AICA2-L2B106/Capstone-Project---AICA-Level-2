from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core import config
from app.version import ENGINE_VERSION


def test_health_reports_version_db_and_queue(client: TestClient) -> None:
    r = client.get("/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "status": "ok", "service": "auditsmart-engine", "version": ENGINE_VERSION,
        "environment": "test", "db": "ok", "queue": "in-process",
    }


def test_openapi_lists_health(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/v1/health" in paths
    assert client.get("/docs").status_code == 200


def test_health_degraded_when_redis_unreachable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    config.reset_settings()
    body = client.get("/v1/health").json()
    assert body["queue"].startswith("error")
    assert body["status"] == "degraded"


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    for k in ("DATABASE_URL", "STORAGE_URL", "ALLOWED_ORIGINS", "AUTH_HS256_SECRET"):
        monkeypatch.delenv(k, raising=False)
    s = config.Settings()
    assert s.effective_database_url.startswith("sqlite:///")
    assert s.storage_path.name == "storage"
    assert s.origins == []
    assert s.max_upload_bytes == 500 * 1024 * 1024


def test_settings_validation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://a.example, https://b.example ,")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/db")
    s = config.Settings()
    assert s.origins == ["https://a.example", "https://b.example"]
    assert s.effective_database_url.startswith("postgresql")
    with pytest.raises(ValueError):
        config.Settings(auth_hs256_secret="short")
    with pytest.raises(ValueError):
        _ = config.Settings(storage_url="s3://bucket").storage_path


def test_render_style_database_urls_use_psycopg3(monkeypatch: pytest.MonkeyPatch) -> None:
    """D46: Render/Supabase give postgres:// or postgresql://; psycopg2 is not installed."""
    n = config.normalise_database_url
    assert n("postgres://u:p@h:5432/db") == "postgresql+psycopg://u:p@h:5432/db"
    assert n(" postgresql://u:p@h/db ") == "postgresql+psycopg://u:p@h/db"
    for kept in ("postgresql+psycopg://u:p@h/db", "sqlite:///x.db", "sqlite://"):
        assert n(kept) == kept
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h/db")
    assert config.Settings().effective_database_url == "postgresql+psycopg://u:p@h/db"
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://a.lovable.app/,https://b.example//, /")
    assert config.Settings().origins == ["https://a.lovable.app", "https://b.example"]
    from sqlalchemy import create_engine
    eng = create_engine(config.Settings().effective_database_url)
    assert eng.dialect.driver == "psycopg"


def test_cors_whitelist(client: TestClient) -> None:
    ok = client.get("/v1/health", headers={"Origin": "https://auditsmart.example.com"})
    assert ok.headers.get("access-control-allow-origin") == "https://auditsmart.example.com"
    bad = client.get("/v1/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in bad.headers
