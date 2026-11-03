"""
audit_engine.py - calculation, validation and findings engine for
"Analytical review for Audit by Prabhdeep".

Standard library only, so it can be tested without PyQt6.
Fictional—For Demonstration Only. All amounts are AED, unscaled.

Sign conventions follow the workbook's Data_Dictionary:
  * Trial balance Debit / Credit are both >= 0; one of them is 0.
  * Debit-normal categories (assets, cost of sales, expenses): balance = Debit - Credit.
  * Credit-normal categories (liabilities, equity, revenue):   balance = Credit - Debit.
  * Budget_Amount is in reporting sign (positive in the account's normal direction).
  * Receivable (debtor) days = closing account 1100 / annual Credit_Sales x 365.
    Receivables include 5% VAT, credit sales exclude it. The basis is the same in
    both years, so the trend is comparable. The basis is retained, not adjusted.
"""

import csv
import datetime
import inspect
import json
import os
from pathlib import Path

DEMO_LABEL = "Fictional—For Demonstration Only"
AI_LABEL = "Draft—Subject to Auditor Review"
UNVERIFIED_LABEL = "Possible explanations — UNVERIFIED. Auditor must corroborate before use."

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

SCHEMAS = {
    "Trial_Balance": ["Year", "Account_Code", "Account_Name", "Category", "Debit", "Credit"],
    "Monthly_Sales": ["Year", "Month", "Sales", "Credit_Sales"],
    "Budget": ["Year", "Account_Code", "Budget_Amount"],
    "Thresholds": ["Rule_ID", "Metric", "Comparison", "Threshold", "Unit", "Rationale"],
}

DEBIT_NORMAL = {"Current Assets", "Non-Current Assets", "Cost of Sales",
                "Operating Expenses", "Finance Costs", "Tax Expense"}
CREDIT_NORMAL = {"Current Liabilities", "Non-Current Liabilities", "Equity", "Revenue"}
CATEGORIES = DEBIT_NORMAL | CREDIT_NORMAL
PL_CATEGORIES = ["Revenue", "Cost of Sales", "Operating Expenses", "Finance Costs", "Tax Expense"]
TRADE_RECEIVABLES_CODE = "1100"
TOLERANCE = 0.01

VAT_BASIS_NOTE = ("Receivable days = closing trade receivables (1100) / annual credit sales x 365. "
                  "Receivables include 5% VAT; credit sales exclude VAT. The workbook basis is "
                  "retained and is the same in both years, so the trend is comparable.")

DEFAULT_THRESHOLDS = {
    "R01": {"Metric": "Same-month sales growth vs prior year", "Comparison": ">", "Threshold": 30.0, "Unit": "%"},
    "R02": {"Metric": "Debtor days change vs prior year", "Comparison": ">", "Threshold": 10.0, "Unit": "days"},
    "R03": {"Metric": "Operating expense account change vs prior year", "Comparison": ">", "Threshold": 50.0, "Unit": "%"},
    "R04": {"Metric": "Operating expense account variance vs budget", "Comparison": ">", "Threshold": 25.0, "Unit": "%"},
}

OPERATORS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
}

STAGES = ["Preliminary", "Substantive/Interim", "Final"]
STATUSES = ["Open", "Awaiting management response", "Awaiting evidence",
            "Explained - evidence obtained", "Escalated to engagement lead", "Resolved"]
RESOLVED_STATUSES = {"Resolved"}

# Non-AI prompts shown when AI is unavailable. Generic inquiry ideas only.
STANDARD_PROCEDURES = {
    "R01": ["Obtain the sales listing for the month and trace large invoices to delivery notes.",
            "Check invoices either side of the period end / month end for cut-off.",
            "Inquire about new customers, promotions or one-off orders in the month.",
            "Review credit notes issued in the following months."],
    "R02": ["Obtain the aged receivables listing and agree it to account 1100.",
            "Review receipts after the year end for the largest balances.",
            "Inquire about changes in credit terms or customer disputes.",
            "Consider confirmations for material or overdue balances."],
    "R03": ["Obtain the account ledger and review the largest entries.",
            "Vouch a sample of entries to invoices and approvals.",
            "Consider whether any amounts are capital in nature.",
            "Inquire about one-off events (e.g. major repairs, new contracts)."],
    "R04": ["Compare the budget assumptions with actual activity.",
            "Obtain management's explanation for the overspend and corroborate it.",
            "Vouch the largest entries to supporting documents.",
            "Check whether costs were misclassified from other accounts."],
}


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------
def fmt_aed(value, decimals=0):
    if value is None:
        return "n/a"
    return f"{value:,.{decimals}f}"


def fmt_pct(value, decimals=1, signed=True):
    if value is None:
        return "n/a"
    return f"{value:+.{decimals}f}%" if signed else f"{value:.{decimals}f}%"


def fmt_num(value, decimals=2):
    if value is None:
        return "n/a"
    return f"{value:,.{decimals}f}"


def now_text():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


# --------------------------------------------------------------------------
# CSV reading and parsing
# --------------------------------------------------------------------------
def read_csv(path):
    """Read a CSV into {"path", "columns", "rows"}. Tries UTF-8 then Windows-1252."""
    last_error = None
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            with open(path, newline="", encoding=encoding) as handle:
                reader = csv.DictReader(handle)
                columns = [c.strip() for c in (reader.fieldnames or [])]
                rows = []
                for raw in reader:
                    row = {}
                    for key, value in raw.items():
                        if key is None:          # extra cells beyond the header
                            continue
                        row[key.strip()] = (value or "").strip() if isinstance(value, str) else ""
                    if any(v for v in row.values()):
                        rows.append(row)
            return {"path": str(path), "columns": columns, "rows": rows}
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(f"Could not decode {path}: {last_error}")


def parse_number(text):
    """Return (value, error). Accepts 1,234.50 and (1,234) for negatives."""
    if text is None or str(text).strip() == "":
        return None, "blank"
    cleaned = str(text).strip().replace(",", "").replace("AED", "").strip()
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    if negative:
        cleaned = cleaned[1:-1]
    try:
        value = float(cleaned)
    except ValueError:
        return None, f"not a number ('{text}')"
    if value != value or value in (float("inf"), float("-inf")):
        return None, f"not a finite number ('{text}')"
    return (-value if negative else value), None


def parse_int(text):
    value, error = parse_number(text)
    if error or value is None or value != int(value):
        return None
    return int(value)


def normalise_code(text):
    value = parse_int(text)
    return str(value) if value is not None else (text or "").strip()


# --------------------------------------------------------------------------
# Validation and data model
# --------------------------------------------------------------------------
class AuditData:
    def __init__(self):
        self.tb = {}            # (year, code) -> record
        self.sales = {}         # (year, month) -> {"sales", "credit"}
        self.budget = {}        # code -> amount (current year)
        self.budget_year = None
        self.thresholds = {}    # rule -> dict
        self.years = []
        self.py = None
        self.cy = None
        self.checks = []

    @property
    def has_failures(self):
        return any(c["result"] == "FAIL" for c in self.checks)

    def account_names(self):
        names = {}
        for (year, code), rec in sorted(self.tb.items()):
            names[code] = (rec["name"], rec["category"])
        return names


def _add(checks, area, check, ok, detail="", warn_only=False):
    result = "PASS" if ok else ("WARN" if warn_only else "FAIL")
    checks.append({"area": area, "check": check, "result": result, "detail": detail})


def _short(items, limit=6):
    items = list(items)
    text = "; ".join(str(i) for i in items[:limit])
    if len(items) > limit:
        text += f"; ... (+{len(items) - limit} more)"
    return text


def build_data(tables):
    """tables: {"Trial_Balance": table-or-None, ...} as returned by read_csv.
    Returns AuditData with .checks populated. Never raises on bad data."""
    data = AuditData()
    checks = data.checks
    usable = {}

    for name, required in SCHEMAS.items():
        table = tables.get(name)
        if table is None:
            _add(checks, name, "File uploaded", False, "Not uploaded yet")
            continue
        missing = [c for c in required if c not in table["columns"]]
        _add(checks, name, "Required columns present", not missing,
             ("Missing: " + ", ".join(missing)) if missing else
             f"{len(table['rows'])} data rows")
        if not missing:
            usable[name] = table

    if "Trial_Balance" in usable:
        _validate_tb(data, usable["Trial_Balance"]["rows"])
    if "Monthly_Sales" in usable:
        _validate_sales(data, usable["Monthly_Sales"]["rows"])
    if "Budget" in usable:
        _validate_budget(data, usable["Budget"]["rows"])
    _validate_thresholds(data, usable.get("Thresholds"))
    _cross_checks(data)
    return data


def _validate_tb(data, rows):
    checks = data.checks
    invalid, negative, both, dupes, bad_cat, bad_key = [], [], [], [], [], []
    for line, row in enumerate(rows, start=2):
        year = parse_int(row.get("Year"))
        code = normalise_code(row.get("Account_Code"))
        if year is None or not code:
            bad_key.append(f"line {line}")
            continue
        debit, d_err = parse_number(row.get("Debit"))
        credit, c_err = parse_number(row.get("Credit"))
        if d_err:
            invalid.append(f"line {line} {code}/{year} Debit {d_err}")
        if c_err:
            invalid.append(f"line {line} {code}/{year} Credit {c_err}")
        if (debit or 0) < 0 or (credit or 0) < 0:
            negative.append(f"line {line} {code}/{year}")
        if (debit or 0) > 0 and (credit or 0) > 0:
            both.append(f"line {line} {code}/{year}")
        category = (row.get("Category") or "").strip()
        if category not in CATEGORIES:
            bad_cat.append(f"line {line} {code} '{category}'")
        key = (year, code)
        if key in data.tb:
            dupes.append(f"line {line} {code}/{year}")
            continue
        data.tb[key] = {"year": year, "code": code, "name": (row.get("Account_Name") or "").strip(),
                        "category": category, "debit": debit, "credit": credit}

    _add(checks, "Trial_Balance", "Year and account code readable", not bad_key, _short(bad_key) or "All rows")
    _add(checks, "Trial_Balance", "Debit/Credit amounts present and numeric", not invalid, _short(invalid) or "All amounts valid")
    _add(checks, "Trial_Balance", "No negative amounts", not negative, _short(negative) or "None")
    _add(checks, "Trial_Balance", "No rows with both debit and credit", not both, _short(both) or "None")
    _add(checks, "Trial_Balance", "No duplicate account-year rows", not dupes,
         (_short(dupes) + " (first occurrence kept)") if dupes else "None")
    _add(checks, "Trial_Balance", "Categories recognised", not bad_cat, _short(bad_cat) or "All recognised")

    cat_by_code = {}
    inconsistent = set()
    for (year, code), rec in data.tb.items():
        if code in cat_by_code and cat_by_code[code] != rec["category"]:
            inconsistent.add(code)
        cat_by_code.setdefault(code, rec["category"])
    _add(checks, "Trial_Balance", "One category per account code", not inconsistent,
         _short(sorted(inconsistent)) or "Consistent")

    data.years = sorted({y for (y, _c) in data.tb})
    if data.years:
        data.cy = data.years[-1]
        data.py = data.cy - 1
    has_both = data.py in data.years and data.cy in data.years
    _add(checks, "Trial_Balance", "Prior and current year present", has_both,
         f"Years found: {', '.join(map(str, data.years)) or 'none'}"
         + (f" (PY {data.py}, CY {data.cy})" if has_both else ""))

    for year in data.years:
        recs = [r for (y, _c), r in data.tb.items() if y == year]
        if any(r["debit"] is None or r["credit"] is None for r in recs):
            _add(checks, "Trial_Balance", f"FY{year} trial balance balances", False,
                 "Cannot confirm: blank or invalid amounts")
            continue
        dr = sum(r["debit"] for r in recs)
        cr = sum(r["credit"] for r in recs)
        diff = round(dr - cr, 2)
        _add(checks, "Trial_Balance", f"FY{year} trial balance balances", abs(diff) < TOLERANCE,
             f"Debits {fmt_aed(dr, 2)} | Credits {fmt_aed(cr, 2)} | Difference {fmt_aed(diff, 2)}")


def _validate_sales(data, rows):
    checks = data.checks
    invalid, negative, dupes, bad_month, over = [], [], [], [], []
    for line, row in enumerate(rows, start=2):
        year = parse_int(row.get("Year"))
        month = (row.get("Month") or "").strip()[:3].title()
        if month not in MONTHS or year is None:
            bad_month.append(f"line {line} '{row.get('Year')}/{row.get('Month')}'")
            continue
        sales, s_err = parse_number(row.get("Sales"))
        credit, c_err = parse_number(row.get("Credit_Sales"))
        if s_err:
            invalid.append(f"line {line} {month}-{year} Sales {s_err}")
        if c_err:
            invalid.append(f"line {line} {month}-{year} Credit_Sales {c_err}")
        if (sales or 0) < 0 or (credit or 0) < 0:
            negative.append(f"line {line} {month}-{year}")
        if sales is not None and credit is not None and credit - sales > TOLERANCE:
            over.append(f"{month}-{year}")
        key = (year, month)
        if key in data.sales:
            dupes.append(f"line {line} {month}-{year}")
            continue
        data.sales[key] = {"sales": sales, "credit": credit}

    _add(checks, "Monthly_Sales", "Valid year and month labels", not bad_month, _short(bad_month) or "All valid")
    _add(checks, "Monthly_Sales", "Sales amounts present and numeric", not invalid, _short(invalid) or "All amounts valid")
    _add(checks, "Monthly_Sales", "No negative amounts", not negative, _short(negative) or "None")
    _add(checks, "Monthly_Sales", "No duplicate year-month rows", not dupes,
         (_short(dupes) + " (first occurrence kept)") if dupes else "None")
    _add(checks, "Monthly_Sales", "Credit sales do not exceed sales", not over, _short(over) or "None")
    for year in sorted({y for (y, _m) in data.sales}):
        count = sum(1 for (y, _m) in data.sales if y == year)
        missing = [m for m in MONTHS if (year, m) not in data.sales]
        _add(checks, "Monthly_Sales", f"FY{year} has 12 months", count == 12,
             f"{count} months" + (f"; missing {', '.join(missing)}" if missing else ""))


def _validate_budget(data, rows):
    checks = data.checks
    invalid, negative, dupes = [], [], []
    years = set()
    for line, row in enumerate(rows, start=2):
        year = parse_int(row.get("Year"))
        code = normalise_code(row.get("Account_Code"))
        amount, err = parse_number(row.get("Budget_Amount"))
        years.add(year)
        if err:
            invalid.append(f"line {line} {code} {err}")
        elif amount < 0:
            negative.append(f"line {line} {code}")
        if code in data.budget:
            dupes.append(f"line {line} {code}")
            continue
        data.budget[code] = amount
    data.budget_year = max((y for y in years if y is not None), default=None)
    _add(checks, "Budget", "Budget amounts present and numeric", not invalid, _short(invalid) or "All valid")
    _add(checks, "Budget", "No negative budget amounts", not negative, _short(negative) or "None")
    _add(checks, "Budget", "No duplicate budget rows", not dupes,
         (_short(dupes) + " (first occurrence kept)") if dupes else "None")
    _add(checks, "Budget", "Single budget year", len({y for y in years if y is not None}) == 1,
         f"Years: {', '.join(str(y) for y in sorted(y for y in years if y is not None))}")


def _validate_thresholds(data, table):
    checks = data.checks
    data.thresholds = {k: dict(v) for k, v in DEFAULT_THRESHOLDS.items()}
    if table is None:
        _add(checks, "Thresholds", "Thresholds read from CSV", False,
             "Using built-in illustrative defaults (30% / 10 days / 50% / 25%)", warn_only=True)
        return
    problems, seen = [], set()
    for line, row in enumerate(table["rows"], start=2):
        rule = (row.get("Rule_ID") or "").strip().upper()
        if rule not in DEFAULT_THRESHOLDS:
            problems.append(f"line {line} unknown rule '{rule}'")
            continue
        value, err = parse_number(row.get("Threshold"))
        comparison = (row.get("Comparison") or "").strip()
        if err or value is None or value <= 0:
            problems.append(f"{rule} threshold {err or 'must be > 0'} (default kept)")
            continue
        if comparison not in OPERATORS:
            problems.append(f"{rule} comparison '{comparison}' invalid (default kept)")
            continue
        seen.add(rule)
        data.thresholds[rule].update({
            "Metric": row.get("Metric") or data.thresholds[rule]["Metric"],
            "Comparison": comparison, "Threshold": value,
            "Unit": row.get("Unit") or data.thresholds[rule]["Unit"],
            "Rationale": row.get("Rationale", ""),
        })
    missing = sorted(set(DEFAULT_THRESHOLDS) - seen)
    if missing:
        problems.append("missing rules " + ", ".join(missing) + " (defaults used)")
    _add(checks, "Thresholds", "Rules R01-R04 valid", not problems, _short(problems) or "4 rules read",
         warn_only=True)


def _cross_checks(data):
    checks = data.checks
    if data.tb and data.sales:
        for year in data.years:
            revenue = category_total(data, year, "Revenue")
            months = [data.sales.get((year, m), {}).get("sales") for m in MONTHS]
            if revenue is None or any(v is None for v in months):
                _add(checks, "Reconciliation", f"FY{year} monthly sales = TB revenue", False,
                     "Cannot reconcile: missing or invalid amounts")
                continue
            diff = round(sum(months) - revenue, 2)
            _add(checks, "Reconciliation", f"FY{year} monthly sales = TB revenue", abs(diff) < TOLERANCE,
                 f"Monthly total {fmt_aed(sum(months), 2)} | TB revenue {fmt_aed(revenue, 2)} | Difference {fmt_aed(diff, 2)}")
    if data.tb and data.budget:
        cy = data.budget_year or data.cy
        tb_codes = {c for (y, c) in data.tb if y == cy}
        no_tb = sorted(c for c in data.budget if c not in tb_codes)
        _add(checks, "Reconciliation", "Every budget account exists in the TB", not no_tb,
             _short(no_tb) or f"All {len(data.budget)} budget accounts found in FY{cy}")
        unbudgeted = sorted(c for (y, c), r in data.tb.items()
                            if y == cy and r["category"] in PL_CATEGORIES and c not in data.budget)
        _add(checks, "Reconciliation", "Every P&L account has a budget", not unbudgeted,
             _short(unbudgeted) or "All P&L accounts budgeted")
        _add(checks, "Reconciliation", "Budget year is the current year", cy == data.cy,
             f"Budget FY{cy} | TB current year FY{data.cy}")


# --------------------------------------------------------------------------
# Calculations
# --------------------------------------------------------------------------
def signed_balance(rec):
    if rec is None or rec["debit"] is None or rec["credit"] is None:
        return None
    if rec["category"] in CREDIT_NORMAL:
        return rec["credit"] - rec["debit"]
    return rec["debit"] - rec["credit"]


def category_total(data, year, category):
    recs = [r for (y, _c), r in data.tb.items() if y == year and r["category"] == category]
    if not recs:
        return None
    values = [signed_balance(r) for r in recs]
    if any(v is None for v in values):
        return None
    return sum(values)


def safe_div(numerator, denominator):
    """Return (value, note). Never raises."""
    if numerator is None or denominator is None:
        return None, "n/a - missing data"
    if abs(denominator) < 1e-9:
        return None, "n/a - zero denominator"
    return numerator / denominator, ""


def pct_change(current, prior):
    value, note = safe_div(None if current is None or prior is None else current - prior,
                           None if prior is None else abs(prior))
    return (value * 100 if value is not None else None), note


def compute_ratios(data, year):
    revenue = category_total(data, year, "Revenue")
    cos = category_total(data, year, "Cost of Sales")
    gp = revenue - cos if revenue is not None and cos is not None else None
    ca = category_total(data, year, "Current Assets")
    cl = category_total(data, year, "Current Liabilities")
    receivables = signed_balance(data.tb.get((year, TRADE_RECEIVABLES_CODE)))
    credits = [data.sales.get((year, m), {}).get("credit") for m in MONTHS]
    credit_sales = None if any(c is None for c in credits) else sum(credits)
    gpm, gpm_note = safe_div(gp, revenue)
    cr, cr_note = safe_div(ca, cl)
    rd, rd_note = safe_div(receivables, credit_sales)
    return {
        "year": year,
        "revenue": revenue, "cost_of_sales": cos, "gross_profit": gp,
        "gross_margin_pct": gpm * 100 if gpm is not None else None, "gross_margin_note": gpm_note,
        "current_assets": ca, "current_liabilities": cl,
        "current_ratio": cr, "current_ratio_note": cr_note,
        "trade_receivables": receivables, "credit_sales": credit_sales,
        "receivable_days": rd * 365 if rd is not None else None, "receivable_days_note": rd_note,
    }


def compare(rule, value, thresholds):
    rule_def = thresholds[rule]
    if value is None:
        return False
    return OPERATORS[rule_def["Comparison"]](value, rule_def["Threshold"])


def run_analysis(data, thresholds):
    """Return dict with ratios, annual and budget variances, monthly sales and flags."""
    py, cy = data.py, data.cy
    result = {"py": py, "cy": cy, "ratios": {}, "annual": [], "budget": [], "monthly": [], "flags": []}
    if cy is None:
        return result
    for year in (py, cy):
        result["ratios"][year] = compute_ratios(data, year)

    # Annual variances, every account in either year
    codes = sorted({c for (y, c) in data.tb if y in (py, cy)}, key=lambda c: (len(c), c))
    for code in codes:
        cur_rec, pri_rec = data.tb.get((cy, code)), data.tb.get((py, code))
        rec = cur_rec or pri_rec
        cur = signed_balance(cur_rec) if cur_rec else None
        pri = signed_balance(pri_rec) if pri_rec else None
        change = cur - pri if cur is not None and pri is not None else None
        pct, note = pct_change(cur, pri)
        if cur_rec is None or pri_rec is None:
            note = "n/a - account missing in " + (f"FY{cy}" if cur_rec is None else f"FY{py}")
        result["annual"].append({"code": code, "name": rec["name"], "category": rec["category"],
                                 "py": pri, "cy": cur, "change": change, "pct": pct, "note": note})

    # Budget variances (current year)
    for code, budget in sorted(data.budget.items()):
        rec = data.tb.get((cy, code))
        actual = signed_balance(rec) if rec else None
        variance = actual - budget if actual is not None and budget is not None else None
        pct, note = pct_change(actual, budget)
        if rec is None:
            note = "n/a - no TB account"
        category = rec["category"] if rec else ""
        if variance is None or abs(variance) < TOLERANCE:
            direction = "-"
        elif category == "Revenue":
            direction = "Favourable" if variance > 0 else "Adverse"
        else:
            direction = "Adverse" if variance > 0 else "Favourable"
        result["budget"].append({"code": code, "name": rec["name"] if rec else "(not in TB)",
                                 "category": category, "actual": actual, "budget": budget,
                                 "variance": variance, "pct": pct, "note": note, "direction": direction})

    # Monthly sales
    for month in MONTHS:
        cur = data.sales.get((cy, month), {}).get("sales")
        pri = data.sales.get((py, month), {}).get("sales")
        pct, note = pct_change(cur, pri)
        flagged = compare("R01", pct, thresholds)
        result["monthly"].append({"month": month, "py": pri, "cy": cur,
                                  "change": cur - pri if cur is not None and pri is not None else None,
                                  "pct": pct, "note": note, "flag": flagged})
    result["flags"] = build_flags(data, result, thresholds)
    return result


def _threshold_text(rule, thresholds):
    t = thresholds[rule]
    unit = "%" if t["Unit"] == "%" else f" {t['Unit']}"
    return f"{t['Comparison']} {t['Threshold']:g}{unit}"


def build_flags(data, analysis, thresholds):
    py, cy = analysis["py"], analysis["cy"]
    flags = []

    for row in analysis["monthly"]:
        if row["flag"]:
            flags.append({
                "id": f"R01-{cy}-{row['month']}", "rule": "R01", "area": "Revenue - monthly sales",
                "title": f"{row['month']} {cy} sales up {fmt_pct(row['pct'])} on {row['month']} {py}",
                "description": (f"{row['month']} {cy} sales AED {fmt_aed(row['cy'])} vs {row['month']} {py} "
                                f"AED {fmt_aed(row['py'])}: change AED {fmt_aed(row['change'])} "
                                f"({fmt_pct(row['pct'])}). Threshold {_threshold_text('R01', thresholds)}."),
                "figures": {"Month": row["month"], f"Sales FY{cy} (AED)": row["cy"],
                            f"Sales FY{py} (AED)": row["py"], "Change (AED)": row["change"],
                            "Change (%)": round(row["pct"], 2),
                            f"Annual sales FY{cy} (AED)": analysis["ratios"][cy]["revenue"],
                            f"Annual sales FY{py} (AED)": analysis["ratios"][py]["revenue"]},
            })

    rp, rc = analysis["ratios"][py], analysis["ratios"][cy]
    if rp["receivable_days"] is not None and rc["receivable_days"] is not None:
        delta = rc["receivable_days"] - rp["receivable_days"]
        if compare("R02", delta, thresholds):
            flags.append({
                "id": f"R02-{cy}", "rule": "R02", "area": "Trade receivables",
                "title": f"Receivable days up {delta:+.1f} days",
                "description": (f"Receivable days FY{cy} {rc['receivable_days']:.1f} vs FY{py} "
                                f"{rp['receivable_days']:.1f}: change {delta:+.1f} days. "
                                f"Threshold {_threshold_text('R02', thresholds)}. {VAT_BASIS_NOTE}"),
                "figures": {f"Trade receivables FY{cy} (AED)": rc["trade_receivables"],
                            f"Trade receivables FY{py} (AED)": rp["trade_receivables"],
                            f"Credit sales FY{cy} (AED)": rc["credit_sales"],
                            f"Credit sales FY{py} (AED)": rp["credit_sales"],
                            f"Receivable days FY{cy}": round(rc["receivable_days"], 1),
                            f"Receivable days FY{py}": round(rp["receivable_days"], 1),
                            "Change (days)": round(delta, 1),
                            "VAT basis": "Receivables include 5% VAT; credit sales exclude VAT (same basis both years)"},
            })

    for row in analysis["annual"]:
        if row["category"] == "Operating Expenses" and compare("R03", row["pct"], thresholds):
            flags.append({
                "id": f"R03-{cy}-{row['code']}", "rule": "R03", "area": f"{row['code']} {row['name']}",
                "title": f"{row['name']} up {fmt_pct(row['pct'])} on FY{py}",
                "description": (f"{row['code']} {row['name']} FY{cy} AED {fmt_aed(row['cy'])} vs FY{py} "
                                f"AED {fmt_aed(row['py'])}: change AED {fmt_aed(row['change'])} "
                                f"({fmt_pct(row['pct'])}). Threshold {_threshold_text('R03', thresholds)}."),
                "figures": {"Account": f"{row['code']} {row['name']}", f"FY{cy} (AED)": row["cy"],
                            f"FY{py} (AED)": row["py"], "Change (AED)": row["change"],
                            "Change (%)": round(row["pct"], 2)},
            })

    for row in analysis["budget"]:
        if row["category"] == "Operating Expenses" and compare("R04", row["pct"], thresholds):
            flags.append({
                "id": f"R04-{cy}-{row['code']}", "rule": "R04", "area": f"{row['code']} {row['name']}",
                "title": f"{row['name']} {fmt_pct(row['pct'])} over FY{cy} budget",
                "description": (f"{row['code']} {row['name']} FY{cy} actual AED {fmt_aed(row['actual'])} vs "
                                f"budget AED {fmt_aed(row['budget'])}: variance AED {fmt_aed(row['variance'])} "
                                f"({fmt_pct(row['pct'])}). Threshold {_threshold_text('R04', thresholds)}."),
                "figures": {"Account": f"{row['code']} {row['name']}", f"Actual FY{cy} (AED)": row["actual"],
                            f"Budget FY{cy} (AED)": row["budget"], "Variance (AED)": row["variance"],
                            "Variance (%)": round(row["pct"], 2)},
            })
    return flags


# --------------------------------------------------------------------------
# Findings register (saved locally as JSON)
# --------------------------------------------------------------------------
def new_workspace():
    return {"label": DEMO_LABEL, "version": 1, "threshold_overrides": {},
            "files": {}, "findings": {}, "final_notes": ""}


def load_workspace(path):
    path = Path(path)
    if not path.exists():
        return new_workspace()
    with open(path, encoding="utf-8") as handle:
        ws = json.load(handle)
    base = new_workspace()
    base.update(ws)
    return base


def save_workspace(path, workspace):
    """Atomic write: a crash mid-save cannot corrupt the existing file."""
    path = Path(path)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(workspace, handle, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def blank_finding(fid, rule, area, title, description, figures=None, auto=True):
    return {"id": fid, "rule": rule, "area": area, "title": title, "description": description,
            "figures": figures or {}, "auto": auto, "flag_active": True,
            "stage": "Preliminary", "carried_from": "", "status": "Open",
            "management_response": "", "evidence_ref": "", "reviewer_notes": "",
            "ai_draft": "", "ai_reviewed": False,
            "created": now_text(), "updated": now_text(), "history": [f"{now_text()} Created at Preliminary"]}


def merge_flags(findings, flags):
    """Add new flags, refresh figures on existing ones, and mark flags that no
    longer trigger. Auditor-entered fields are never overwritten."""
    active = set()
    for flag in flags:
        active.add(flag["id"])
        if flag["id"] in findings:
            f = findings[flag["id"]]
            if not f.get("flag_active", True):
                f["history"].append(f"{now_text()} Flag triggered again")
            f.update({k: flag[k] for k in ("rule", "area", "title", "description", "figures")})
            f["flag_active"] = True
        else:
            findings[flag["id"]] = blank_finding(flag["id"], flag["rule"], flag["area"], flag["title"],
                                                 flag["description"], flag["figures"])
    for fid, f in findings.items():
        if f.get("auto") and fid not in active and f.get("flag_active", True):
            f["flag_active"] = False
            f["history"].append(f"{now_text()} No longer flagged at current thresholds")
    return findings


def is_unresolved(finding):
    return finding.get("status") not in RESOLVED_STATUSES


def carry_forward_unresolved(findings):
    moved = 0
    for f in findings.values():
        if is_unresolved(f) and f["stage"] != "Final":
            f["carried_from"] = f["stage"]
            f["history"].append(f"{now_text()} Carried forward from {f['stage']} to Final (unresolved)")
            f["stage"] = "Final"
            f["updated"] = now_text()
            moved += 1
    return moved


EXPORT_COLUMNS = ["Data_Label", "Finding_ID", "Rule", "Area", "Title", "Description", "Stage",
                  "Carried_From", "Status", "Unresolved", "Flag_Active_At_Current_Thresholds",
                  "Management_Response", "Evidence_Reference", "Reviewer_Notes",
                  "AI_Draft_Label", "AI_Draft", "AI_Draft_Reviewed_By_Auditor", "Created", "Updated", "History"]


def export_findings_csv(path, findings):
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(EXPORT_COLUMNS)
        for f in sorted(findings.values(), key=lambda x: x["id"]):
            writer.writerow([
                DEMO_LABEL, f["id"], f["rule"], f["area"], f["title"], f["description"], f["stage"],
                f.get("carried_from", ""), f["status"], "Yes" if is_unresolved(f) else "No",
                "Yes" if f.get("flag_active", True) else "No",
                f["management_response"], f["evidence_ref"], f["reviewer_notes"],
                AI_LABEL if f.get("ai_draft") else "", f.get("ai_draft", ""),
                "Yes" if f.get("ai_reviewed") else "No", f["created"], f["updated"],
                " | ".join(f.get("history", [])),
            ])


# --------------------------------------------------------------------------
# Optional AI draft explanations (Claude API). Never required to run the app.
# --------------------------------------------------------------------------
CONFIG_DIR = Path.home() / ".analytical_review_prabhdeep"
AI_SETTINGS_FILE = CONFIG_DIR / "ai_settings.json"
API_KEY_FILE = CONFIG_DIR / "anthropic_api_key.txt"
DEFAULT_MODEL = "claude-opus-5-5"

AI_SYSTEM_PROMPT = (
    "You assist a financial statement auditor performing analytical review on FICTIONAL "
    "demonstration data. You receive one analytical-review flag with verified figures. "
    "Write possible business explanations for the movement and the audit evidence that "
    "would corroborate or contradict each one.\n"
    "Rules:\n"
    "- Use only the figures provided. Do not invent, estimate or recalculate other numbers.\n"
    "- Every explanation is a hypothesis. Label the section 'Possible explanations (UNVERIFIED)'.\n"
    "- Do not give an audit opinion, a conclusion on misstatement, or any conclusion about "
    "fraud or intent. Do not say the matter is resolved.\n"
    "- Be concise: 3-5 possible explanations, then 3-5 suggested corroborating procedures or "
    "inquiries of management. Plain text, short bullet points."
)


class AIUnavailable(Exception):
    pass


def load_ai_settings():
    settings = {"enabled": True, "model": DEFAULT_MODEL}
    try:
        settings.update(json.loads(AI_SETTINGS_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return settings


def save_ai_settings(settings, api_key=None):
    """Settings and key are stored in the user's profile folder, never in source code."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    AI_SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    if api_key is not None:
        if api_key.strip():
            API_KEY_FILE.write_text(api_key.strip(), encoding="utf-8")
        elif API_KEY_FILE.exists():
            API_KEY_FILE.unlink()


def get_api_key():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    try:
        return API_KEY_FILE.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def build_ai_prompt(finding):
    lines = [f"Flag: {finding['title']}", f"Rule: {finding['rule']}", f"Area: {finding['area']}",
             "Verified figures (AED unless stated):"]
    for key, value in finding.get("figures", {}).items():
        if isinstance(value, float):
            value = f"{value:,.2f}"
        elif isinstance(value, int):
            value = f"{value:,}"
        lines.append(f"- {key}: {value}")
    lines.append("Company context: fictional UAE general trader, calendar financial year, "
                 "all invoices on 45-day credit terms.")
    return "\n".join(lines)


def draft_ai_explanation(finding, data_verified, model=None):
    """Return labelled draft text, or raise AIUnavailable with a readable reason."""
    if not data_verified:
        raise AIUnavailable("Validation has failures, so figures are not verified. "
                            "Fix the data before requesting AI drafts.")
    if not finding.get("figures"):
        raise AIUnavailable("This finding has no verified figures (e.g. a manual finding).")
    try:
        import anthropic
    except ImportError:
        raise AIUnavailable("The optional 'anthropic' package is not installed.")
    key = get_api_key()
    try:
        client = anthropic.Anthropic(api_key=key, timeout=90.0) if key else anthropic.Anthropic(timeout=90.0)
    except Exception as exc:  # no credentials configured
        raise AIUnavailable(f"No API key configured ({exc}). Use AI Settings or set ANTHROPIC_API_KEY.")
    request = dict(model=model or DEFAULT_MODEL, max_tokens=4000,
                   system=AI_SYSTEM_PROMPT, output_config={"effort": "low"},
                   messages=[{"role": "user", "content": build_ai_prompt(finding)}])
    # Server-side fallback lets another model answer if the first declines (newer SDKs only).
    supports_fallbacks = "fallbacks" in inspect.signature(client.beta.messages.create).parameters
    try:
        if supports_fallbacks:
            response = client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **request)
        else:
            response = client.messages.create(**request)
    except TypeError:  # the SDK raises this when no credentials can be found
        raise AIUnavailable("No API key configured. Use AI Settings or set ANTHROPIC_API_KEY.")
    except anthropic.AuthenticationError:
        raise AIUnavailable("The API key was rejected. Check it in AI Settings.")
    except anthropic.PermissionDeniedError:
        raise AIUnavailable("The API key does not have permission for this model.")
    except anthropic.NotFoundError:
        raise AIUnavailable(f"Model '{request['model']}' was not found. Check AI Settings.")
    except anthropic.RateLimitError:
        raise AIUnavailable("Rate limited by the AI service. Try again shortly.")
    except anthropic.APIStatusError as exc:
        raise AIUnavailable(f"AI service error ({exc.status_code}): {exc.message}")
    except anthropic.APIConnectionError:
        raise AIUnavailable("Could not reach the AI service. Check the internet connection.")
    if response.stop_reason == "refusal":
        raise AIUnavailable("The AI declined this request. Draft the explanation manually.")
    text = "\n".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        raise AIUnavailable("The AI returned an empty response.")
    return (f"[{AI_LABEL}]\n[{UNVERIFIED_LABEL}]\n[Generated {now_text()} by {response.model} "
            f"from verified figures only]\n\n{text}")


def standard_procedures_text(finding):
    steps = STANDARD_PROCEDURES.get(finding.get("rule"), [])
    if not steps:
        return ""
    return ("[Standard inquiry prompts - not AI generated. Auditor judgement required.]\n"
            + "\n".join(f"- {s}" for s in steps))
