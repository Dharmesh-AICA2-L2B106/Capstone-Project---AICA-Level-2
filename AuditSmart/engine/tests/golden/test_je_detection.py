"""Prompt 3.4 detection test: planted (answer_key.csv) vs detected per test, 100% required.

Mapping answer-key error types to engine criteria:
- weekend_posting / public_holiday_posting / non_working_day: non_working_day (reason
  weekend / holiday) from calendar.resolve.
- friday_after_cutoff: after_half_day_cutoff.
- round_sum, vague_narration and duplicate_invoice map to the criteria of the same name.
- period_end_finmgr: period_end AND senior_user (senior_users = ["FINMGR"]).

Precision is checked too: no line outside the answer key may carry these flags.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.services import calendar as c
from app.services import je_tests as je
from app.services.importer import parse_to_parquet, read_parquet_rows
from tests.conftest import DATA
from tests.helpers import answer_key

TYPES = {
    "dummy_gl.csv": [
        "weekend_posting",
        "public_holiday_posting",
        "friday_after_cutoff",
        "round_sum",
        "period_end_finmgr",
        "vague_narration",
        "duplicate_invoice",
    ],
    "fy2021_2022.csv": ["non_working_day"],
}
FYE = {"dummy_gl.csv": date(2025, 12, 31), "fy2021_2022.csv": date(2021, 12, 31)}


def detected(res: dict[str, Any]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for f in res["flags"]:
        ref, codes = f["line_ref"], set(f["flags"])
        if "non_working_day" in codes:
            out["non_working_day"].add(ref)
            out[
                {"weekend": "weekend_posting", "holiday": "public_holiday_posting"}.get(
                    f["non_working_reason"], "company_closure"
                )
            ].add(ref)
        if "after_half_day_cutoff" in codes:
            out["friday_after_cutoff"].add(ref)
        if {"period_end", "senior_user"} <= codes:
            out["period_end_finmgr"].add(ref)
        for code in ("round_sum", "vague_narration", "duplicate_invoice", "period_end"):
            if code in codes:
                out[code].add(ref)
    return out


def _rows(name: str, tmp: Path) -> list[dict[str, Any]]:
    parse_to_parquet(DATA / name, tmp / "gl.parquet")
    return list(read_parquet_rows(tmp / "gl.parquet"))


def _profile() -> c.CalendarProfile:
    return c.CalendarProfile(emirate="Dubai", weeks=c.seed_weeks(), holidays=c.seed_holidays())


@pytest.mark.parametrize(
    "overrides",
    [{}, {"period_end_days": 3, "round_multiple": "10000"}],
    ids=["methodology_defaults", "prompt_values"],
)
@pytest.mark.parametrize("name", sorted(TYPES))
def test_detection_100_percent(
    name: str, overrides: dict[str, Any], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    res = je.run_je_tests(
        _rows(name, tmp_path),
        je.JeParams.build(FYE[name], {"senior_users": ["FINMGR"], **overrides}),
        _profile(),
    )
    det = detected(res)
    planted: dict[str, set[str]] = defaultdict(set)
    for a in answer_key():
        if a["file"] == name:
            planted[a["error_type"]].add(a["line_id"])
    lines = [
        f"{name} ({', '.join(f'{k}={v}' for k, v in overrides.items()) or 'defaults'})",
        f"{'test':<24}{'planted':>8}{'detected':>9}{'extra':>6}{'rate':>8}",
    ]
    for t in TYPES[name]:
        p, d = planted[t], det[t]
        lines.append(
            f"{t:<24}{len(p):>8}{len(p & d):>9}{len(d - p):>6}{100 * len(p & d) / len(p):>7.0f}%"
        )
    with capsys.disabled():
        print("\n" + "\n".join(lines))
    for t in TYPES[name]:
        assert det[t] == planted[t], t
    assert res["calendar_errors"] == []


def test_fy_controls_not_flagged(tmp_path: Path) -> None:
    """Sunday Dec-2021 and Friday-morning Jan-2022 controls (feature_key) stay clean."""
    import csv

    with (DATA / "feature_key.csv").open(newline="", encoding="utf-8") as fh:
        controls = {
            r["line_id"] for r in csv.DictReader(fh) if r["feature"] == "working_day_control"
        }
    res = je.run_je_tests(
        _rows("fy2021_2022.csv", tmp_path), je.JeParams.build(FYE["fy2021_2022.csv"]), _profile()
    )
    flagged = {
        f["line_ref"]
        for f in res["flags"]
        if {"non_working_day", "after_half_day_cutoff"} & set(f["flags"])
    }
    assert len(controls) == 60 and not controls & flagged


def test_calendar_hash_stable_and_weekend_sensitive(tmp_path: Path) -> None:
    rows = _rows("fy2021_2022.csv", tmp_path)
    p = je.JeParams.build(FYE["fy2021_2022.csv"])
    h1 = je.run_je_tests(rows, p, _profile())["calendar_hash"]
    assert h1 == je.run_je_tests(rows, p, _profile())["calendar_hash"]
    flat = c.CalendarProfile(weeks=(c.WorkWeek(frozenset({6, 7}), date(2018, 1, 1)),))
    res = je.run_je_tests(rows, p, flat)
    assert res["calendar_hash"] != h1  # a hard-coded Sat/Sun weekend would miss Dec Fridays
    nw = {f["line_ref"] for f in res["flags"] if "non_working_day" in f["flags"]}
    planted = {a["line_id"] for a in answer_key() if a["file"] == "fy2021_2022.csv"}
    assert nw != planted  # Dec-2021 Sundays wrongly flagged, Fridays missed
