"""Benford first-digit test (prompt 3.4)."""

from __future__ import annotations

import math
import random
from datetime import date
from decimal import Decimal

import pytest

from app.services import benford as bf


def _benford_amounts(n: int, seed: int = 7) -> list[Decimal]:
    rng = random.Random(seed)
    return [
        Decimal(str(round(math.exp(rng.uniform(math.log(10), math.log(1e6))), 2))) for _ in range(n)
    ]


def test_first_digit() -> None:
    assert bf.first_digit(Decimal("0.0042")) == 4
    assert bf.first_digit(Decimal("-987.1")) == 9
    assert bf.first_digit(Decimal("1E+3")) == 1
    with pytest.raises(bf.BenfordError):
        bf.first_digit(Decimal(0))


def test_conformity_on_log_uniform_amounts() -> None:
    res = bf.run_benford([*_benford_amounts(5000), Decimal("5"), Decimal("0")])
    assert res["n"] == 5000 and res["excluded_below_min"] == 2
    assert res["conclusion"] in ("Close conformity", "Acceptable conformity")
    assert res["mad_thresholds"] == ["0.006", "0.012", "0.015"]
    assert len(res["chart"]) == 9 and res["chart"][0]["expected_pct"] == 30.1
    assert sum(c["count"] for c in res["chart"]) == 5000
    assert res["rule_versions_used"]["benford.mad.first_digit"]["ref"].endswith("@v1")
    assert res["chi_square_critical"] == pytest.approx(15.5073, abs=1e-3)


def test_nonconformity_with_planted_spike() -> None:
    amounts = _benford_amounts(1000) + [Decimal("7500.00")] * 400
    res = bf.run_benford(amounts, on_date=date(2025, 12, 31))
    assert res["conclusion"] == "Nonconformity" and res["chi_square_reject"] is True
    assert 7 in res["significant_digits"] and "targeted JE testing" in res["conclusion_text"]


@pytest.mark.parametrize(
    ("mad", "text"),
    [
        (0.005, "Close conformity"),
        (0.01, "Acceptable conformity"),
        (0.014, "Marginally acceptable conformity"),
        (0.02, "Nonconformity"),
    ],
)
def test_thresholds(mad: float, text: str) -> None:
    assert bf.conclusion_for(mad, (0.006, 0.012, 0.015)) == text


def test_errors() -> None:
    with pytest.raises(bf.BenfordError, match="No amounts"):
        bf.run_benford([Decimal("1")], min_amount=Decimal("10"))
    with pytest.raises(bf.BenfordError, match="Rules Library"):
        bf.run_benford([Decimal("12")], on_date=date(2000, 1, 1))
