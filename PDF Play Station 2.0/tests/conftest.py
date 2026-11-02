"""Shared fixtures. Helpers live in helpers.py (tests\\convert has its own conftest)."""

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
for p in (HERE.parent, HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app.services.common import Job  # noqa: E402
from helpers import make_pdf  # noqa: E402


@pytest.fixture
def job():
    return Job()


@pytest.fixture
def pdf5(tmp_path):
    return make_pdf(tmp_path / "five.pdf", 5)
