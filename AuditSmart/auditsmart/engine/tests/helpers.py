from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Any

import openpyxl

DATA = Path(__file__).resolve().parents[2] / "data"


@lru_cache
def answer_key() -> tuple[dict[str, str], ...]:
    with (DATA / "answer_key.csv").open(newline="", encoding="utf-8") as f:
        return tuple(csv.DictReader(f))


@lru_cache
def golden() -> Any:
    return openpyxl.load_workbook(DATA / "golden_results.xlsx", data_only=True)


def golden_value(sheet: str, ref: str) -> Any:
    return golden()[sheet][ref].value
