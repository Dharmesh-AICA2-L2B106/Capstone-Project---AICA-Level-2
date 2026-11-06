from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.models import APPENDIX_A_TABLES

ENGINE = Path(__file__).resolve().parents[2]


def test_alembic_upgrade_creates_every_appendix_a_table(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'mig.db'}"
    cfg = Config(str(ENGINE / "alembic.ini"))
    cfg.set_main_option("script_location", str(ENGINE / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    tables = set(inspect(create_engine(url)).get_table_names())
    assert set(APPENDIX_A_TABLES) <= tables
    command.downgrade(cfg, "base")
    assert set(inspect(create_engine(url)).get_table_names()) <= {"alembic_version"}


def test_migrations_match_models(tmp_path: Path) -> None:
    """Every model change ships with a migration (alembic autogenerate finds no diff)."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.models import Base

    url = f"sqlite:///{tmp_path / 'parity.db'}"
    cfg = Config(str(ENGINE / "alembic.ini"))
    cfg.set_main_option("script_location", str(ENGINE / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    with create_engine(url).connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []
