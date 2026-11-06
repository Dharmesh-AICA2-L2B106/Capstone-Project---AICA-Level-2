"""Prompt 3.3 unit + property tests for app.services.sampling."""

from __future__ import annotations

import itertools
from datetime import date
from decimal import Decimal
from typing import Any

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services import sampling as s
from app.services.sampling import PopItem, SampleRequest, SamplingError, run_sampling

FYE = date(2025, 12, 31)
D = Decimal


def rows(values: list[str], **extra: Any) -> list[dict[str, Any]]:
    out = []
    for i, v in enumerate(values, 1):
        d = D(v)
        out.append({"row_no": i, "line_id": f"L{i:05d}", "account_code": "6100",
                    "account_type": extra.get("account_type", "Expense"),
                    "debit": d if d > 0 else D(0), "credit": -d if d < 0 else D(0)})
    return out


def run(values: list[str], **kw: Any) -> dict[str, Any]:
    return run_sampling(rows(values), SampleRequest(**kw), period_end=FYE, dataset_hash="h")


def rules() -> s.RuleSet:
    return s.RuleSet(FYE)


# ---------------------------------------------------------------- size formulas
def test_guide_example_from_prompt() -> None:
    size = s.mus_size(D("12500000"), D("450000"), "95", rules(), formula="guide")
    assert size.n == 84
    assert size.formula_text == "n = ceil(12,500,000.00 x 3.00 / 450,000.00) = 84; J = 148,809.52"


def test_firm_worked_example_from_digest() -> None:
    size = s.mus_size(D("12500000"), D("280000"), "95", rules())
    assert size.n == 160 and size.interval == D("78125")
    assert size.basic_precision == D("234375")


def test_zero_expected_misstatement_omits_ef() -> None:
    size = s.mus_size(D("1000000"), D("100000"), "95", rules(), expected_pct=D("0"))
    assert size.ef is None and size.n == 30
    assert size.formula_text == ("n = ROUNDUP(1,000,000.00 x 3.00 / 100,000.00, 0) = 30; "
                                 "J = 33,333.33")


@pytest.mark.parametrize(("pct", "msg"), [(D("0.51"), "above the 50% limit"),
                                          (D("-0.1"), "cannot be negative")])
def test_expected_misstatement_limits(pct: Decimal, msg: str) -> None:
    with pytest.raises(SamplingError, match=msg):
        s.mus_size(D("1000000"), D("100000"), "95", rules(), expected_pct=pct)


def test_80_percent_uses_rules_and_99_refuses_without_ef() -> None:
    size = s.mus_size(D("1000000"), D("100000"), "80", rules())
    assert size.cf == D("1.61") and size.ef == D("1.3")
    with pytest.raises(SamplingError, match=r"sampling\.mus\.ef\.99"):
        s.mus_size(D("1000000"), D("100000"), "99", rules())


@pytest.mark.parametrize(("pop", "tm", "level", "msg"), [
    (D("100"), D("0"), "95", "greater than zero"),
    (D("0"), D("10"), "95", "no value"),
    (D("100"), D("10"), "97", "80, 90, 95 or 99"),
])
def test_size_input_errors(pop: Decimal, tm: Decimal, level: str, msg: str) -> None:
    with pytest.raises(SamplingError, match=msg):
        s.mus_size(pop, tm, level, rules())


def test_rules_missing_for_old_period() -> None:
    with pytest.raises(SamplingError, match="Rules Library has no value"):
        s.mus_size(D("100"), D("10"), "95", s.RuleSet(date(2000, 1, 1)))


# ---------------------------------------------------------------- population
def test_population_bases_and_filters() -> None:
    data = rows(["100", "-40", "0", "60"])
    data[3]["account_code"] = "7200"
    data.append({"row_no": 5, "line_id": "L5", "account_code": "1100", "account_type": "Asset",
                 "debit": D(5), "credit": D(0)})
    deb = s.build_population(data, basis="debit", account_types=["expense"])
    assert [i.row_no for i in deb.items] == [1, 4] and [i.row_no for i in deb.excluded] == [2]
    assert deb.zero_lines == 1 and deb.value == D(160)
    assert deb.filter_text == "account_type in (expense) and debit > 0"
    cr = s.build_population(data, basis="credit", account_types=["Expense"])
    assert [i.row_no for i in cr.items] == [2] and [i.row_no for i in cr.excluded] == [1, 4]
    sg = s.build_population(data, basis="signed")
    assert [i.row_no for i in sg.items] == [1, 4, 5] and sg.excluded[0].value == D(40)
    ab = s.build_population(data, basis="absolute")
    assert ab.value == D(205) and not ab.excluded
    codes = s.build_population(data, account_codes=["72*", "1100"])
    assert [i.row_no for i in codes.items] == [4, 5]
    assert "account_code in (72*, 1100)" in codes.filter_text


def test_empty_population_refused() -> None:
    with pytest.raises(SamplingError, match="No lines match"):
        run(["100"], account_types=["Revenue"], tolerable_misstatement=D(10))


# ---------------------------------------------------------------- MUS run
def test_mus_requires_tm_and_reports_no_sampling() -> None:
    with pytest.raises(SamplingError, match="Tolerable misstatement is required"):
        run(["100"])
    r = run(["100", "200", "300"], tolerable_misstatement=D("1000"), seed=1)
    assert r["n_required"] == 3 and r["status"] == "no_sampling" and r["items"] == []
    assert "below the minimum of 5" in r["warnings"][0]
    assert "below the firm minimum of 5" in r["rationale"]


def test_mus_warning_when_distinct_lines_far_below_n() -> None:
    r = run(["1000000", "10", "10", "10", "10", "10"], tolerable_misstatement=D("100000"),
            seed=5)
    assert r["n_required"] == 36 and r["sample_size"] < r["n_required"]
    assert any("distinct lines will be tested" in w for w in r["warnings"])
    assert r["items"][0]["hits"] >= 30 and r["items"][0]["top_stratum"]


def test_rationale_mentions_excluded_credits_and_seed() -> None:
    r = run(["5000"] * 30 + ["-25"], tolerable_misstatement=D("20000"), seed=9)
    assert "1 credit/negative line(s) totalling AED 25.00" in r["rationale"]
    assert "seed 9" in r["rationale"] and r["rules_pending_verification"]
    assert set(r["rule_versions_used"]) >= {"sampling.mus.cf.95", "sampling.min_n"}


def test_seed_generated_when_missing_and_bounds() -> None:
    r = run(["5000"] * 30, tolerable_misstatement=D("20000"))
    assert 0 <= r["seed"] <= s.MAX_SEED
    with pytest.raises(SamplingError, match="Seed must be"):
        run(["5000"] * 30, tolerable_misstatement=D("20000"), seed=-1)


def test_key_items_mus() -> None:
    vals = ["90000", "80000"] + ["1000"] * 200
    r = run(vals, method="key_items_mus", key_item_threshold=D("50000"),
            tolerable_misstatement=D("20000"), seed=3)
    assert r["key_items"]["count"] == 2 and r["key_items"]["value"] == D("170000.00")
    picked = {i["row_no"] for i in r["items"]}
    assert {1, 2} <= picked
    assert r["formula_text"].startswith("n = ROUNDUP(200,000.00 x 3.00")
    assert "2 key item(s) at or above AED 50,000.00" in r["rationale"]
    with pytest.raises(SamplingError, match="Key item threshold"):
        run(vals, method="key_items_mus", tolerable_misstatement=D("20000"))


def test_key_items_cover_everything() -> None:
    r = run(["90000", "80000"], method="key_items_mus", key_item_threshold=D("1"),
            tolerable_misstatement=D("20000"), seed=3)
    assert r["sample_size"] == 2 and r["n_required"] is None and r["status"] == "selected"


def test_key_items_remainder_below_min_n() -> None:
    r = run(["90000", "10", "10"], method="key_items_mus", key_item_threshold=D("50000"),
            tolerable_misstatement=D("20000"), seed=3)
    assert r["status"] == "selected" and r["sample_size"] == 1
    assert "below the minimum" in r["warnings"][0]


# ---------------------------------------------------------------- other methods
def test_random_and_systematic() -> None:
    vals = [str(i) for i in range(1, 101)]
    r = run(vals, method="random", sample_size=10, seed=4)
    assert r["sample_size"] == 10 and len({i["row_no"] for i in r["items"]}) == 10
    assert r["items"] == run(vals, method="random", sample_size=10, seed=4)["items"]
    y = run(vals, method="systematic", sample_size=10, seed=4)
    rows_ = [i["row_no"] for i in y["items"]]
    assert len(rows_) == 10 and all(b - a == 10 for a, b in itertools.pairwise(rows_))
    assert y["interval"] == D(10) and "interval = 100 lines / 10" in y["formula_text"]
    assert "Systematic sampling" in y["rationale"]
    for m in ("random", "systematic"):
        with pytest.raises(SamplingError, match="larger than the population"):
            run(vals, method=m, sample_size=101, seed=1)
    with pytest.raises(SamplingError, match="Sample size is required"):
        run(vals, method="random")


def test_stratified_with_boundaries() -> None:
    vals = ["10"] * 50 + ["1000"] * 10 + ["50000"] * 2
    r = run(vals, method="stratified", sample_size=12, strata_boundaries=[D("100"), D("10000")],
            seed=8)
    st_ = r["strata"]
    assert [x["count"] for x in st_] == [50, 10, 2]
    assert sum(x["sample_size"] for x in st_) == 12 and st_[2]["sample_size"] == 2
    assert st_[0]["sample_size"] >= 1
    assert r["sample_size"] == 12 and "Stratified sampling" in r["rationale"]


def test_stratified_warns_when_allocation_differs() -> None:
    r = run(["10", "20", "30", "40"], method="stratified", sample_size=1, num_strata=4, seed=1)
    assert r["sample_size"] == 4
    assert "Allocation gives 4 items" in r["warnings"][0]


def test_make_strata_value_on_boundary_goes_up() -> None:
    items = [PopItem(i, f"L{i}", D(v)) for i, v in enumerate(["5", "10", "15"], 1)]
    strata = s.make_strata(items, boundaries=[D("10")])
    assert [[i.row_no for i in x.items] for x in strata] == [[1], [2, 3]]
    with pytest.raises(SamplingError, match="at least 1"):
        s.make_strata(items, num_strata=0)
    assert s.make_strata([], num_strata=3) == []


amounts = st.lists(st.decimals(min_value=D("0.01"), max_value=D("1000000"), places=2),
                   min_size=1, max_size=120)


@settings(max_examples=60, deadline=None)
@given(amounts, st.integers(1, 6), st.integers(1, 80), st.integers(0, 2**31 - 1))
def test_property_strata_sum_to_population(vals: list[Decimal], k: int, n: int,
                                           seed: int) -> None:
    items = [PopItem(i, f"L{i}", v) for i, v in enumerate(vals, 1)]
    strata = s.make_strata(items, num_strata=k)
    assert sum(len(x.items) for x in strata) == len(items)
    assert sum((x.value for x in strata), D(0)) == sum(vals, D(0))
    s.allocate(strata, n)
    total = sum(x.allocated for x in strata)
    assert total == min(max(n, len(strata)), len(items))
    assert all(1 <= x.allocated <= len(x.items) for x in strata)
    picked, _ = s.stratified_select(items, n, np.random.default_rng(seed), boundaries=None,
                                    num_strata=k)
    assert len({p.item.row_no for p in picked}) == len(picked) == total


@settings(max_examples=60, deadline=None)
@given(amounts, st.integers(0, 2**31 - 1))
def test_property_mus_subset_top_stratum_and_determinism(vals: list[Decimal], seed: int) -> None:
    data = rows([str(v) for v in vals])
    tm = max(sum(vals, D(0)) / 10, D("0.01"))
    try:
        a = run_sampling(data, SampleRequest(tolerable_misstatement=tm, seed=seed),
                         period_end=FYE, dataset_hash=None)
    except SamplingError:  # pragma: no cover - not expected for positive populations
        raise
    b = run_sampling(data, SampleRequest(tolerable_misstatement=tm, seed=seed),
                     period_end=FYE, dataset_hash=None)
    assert a["items"] == b["items"]
    if a["status"] == "selected":
        assert sum(i["hits"] for i in a["items"]) == a["n_required"]
        picked = {i["row_no"] for i in a["items"]}
        assert picked <= {r["row_no"] for r in data}
        assert {r["row_no"] for r in data if r["debit"] >= a["interval"]} <= picked


def test_jsonable_and_money() -> None:
    assert s.jsonable({"a": [D("1.5"), (D("2"),)], "b": 1}) == {"a": ["1.5", ["2"]], "b": 1}
    assert s.money(D("1234.565")) == "1,234.57"
