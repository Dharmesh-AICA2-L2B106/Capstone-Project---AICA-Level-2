"""Scaffold contract: every service module from SPEC 3.2 exists and says which prompt builds it."""

from __future__ import annotations

import importlib

import pytest

PLACEHOLDERS = {
    "sampling": "3.3", "je_tests": "3.4", "benford": "3.4", "vat": "3.5", "evaluation": "3.5",
    "workpaper": "3.6", "anonymiser": "3.7", "rules_monitor": "3.9", "calendar": "3.10",
    "input_vat": "3.12",
}


@pytest.mark.parametrize(("module", "prompt"), sorted(PLACEHOLDERS.items()))
def test_placeholder_services(module: str, prompt: str) -> None:
    mod = importlib.import_module(f"app.services.{module}")
    assert prompt == mod.IMPLEMENTED_BY_PROMPT
