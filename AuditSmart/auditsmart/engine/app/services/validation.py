"""Validation of a parsed ledger (prompt 3.2).

Every finding has a severity (critical / warning), the affected data-row numbers (first 50
plus the total count), the field, and a plain-English message with guidance. Row numbers
are 1-based data rows: row 1 is the first row under the header (spreadsheet row = row + 1).

Critical findings block downstream work (sampling, JE tests, VAT) until fixed.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from dataclasses import field as dc_field
from decimal import Decimal
from itertools import pairwise
from pathlib import Path
from typing import Any

from app.services.importer import read_parquet_rows
from app.services.rules import get_rule

IMPLEMENTED_BY_PROMPT = "3.2"

CRITICAL, WARNING = "critical", "warning"
MAX_ROWS = 50
ROW_NOTE = "Row numbers count data rows: row 1 is the first row under the header."

FIELD_LABEL = {
    "entry_date": "entry date", "posting_date": "posting date", "debit": "debit",
    "credit": "credit", "net_amount": "net amount", "vat_amount": "VAT amount",
    "closing_balance": "closing balance", "amount": "amount", "line_id": "line ID",
    "voucher_no": "voucher number", "account_code": "account code",
}


def aed(v: Decimal) -> str:
    return f"AED {v.quantize(Decimal('0.01')):,}"


def _a(label: str) -> str:
    return f"{'an' if label[0] in 'aeiou' else 'a'} {label}"


def fmt_rows(rows: list[int], count: int) -> str:
    shown = ", ".join(str(r) for r in rows[:10])
    more = f" and {count - 10} more" if count > 10 else ""
    return f"row{'s' if count > 1 else ''} {shown}{more}"


@dataclass
class Issue:
    code: str
    severity: str
    field: str | None
    message: str
    guidance: str
    rows: list[int] = dc_field(default_factory=list)
    row_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class _RowSet:
    rows: list[int] = dc_field(default_factory=list)
    count: int = 0
    examples: list[str] = dc_field(default_factory=list)

    def add(self, row: int, example: str | None = None) -> None:
        self.count += 1
        if len(self.rows) < MAX_ROWS:
            self.rows.append(row)
        if example is not None and len(self.examples) < 5 and example not in self.examples:
            self.examples.append(example)


@dataclass
class ValidationReport:
    issues: list[Issue]
    rows: int
    total_dr: Decimal
    total_cr: Decimal

    @property
    def critical(self) -> int:
        return sum(1 for i in self.issues if i.severity == CRITICAL)

    @property
    def warnings(self) -> int:
        return sum(1 for i in self.issues if i.severity == WARNING)

    @property
    def blocked(self) -> bool:
        return self.critical > 0

    def summary(self) -> dict[str, Any]:
        return {
            "rows": self.rows, "total_dr": str(self.total_dr), "total_cr": str(self.total_cr),
            "critical": self.critical, "warnings": self.warnings, "blocked": self.blocked,
        }


_TRAIL_NUM = re.compile(r"^(.*?)(\d+)$")


def _gaps(numbers: Iterable[tuple[str, int, int]]) -> Iterator[tuple[str, list[str]]]:
    """numbers: (prefix, number, width). Yields (prefix, missing voucher numbers)."""
    by_prefix: dict[str, dict[int, int]] = defaultdict(dict)
    for prefix, n, width in numbers:
        by_prefix[prefix][n] = width
    for prefix, nums in sorted(by_prefix.items()):
        if len(nums) < 2:
            continue
        ordered = sorted(nums)
        width = max(nums.values())
        missing = [f"{prefix}{k:0{width}d}"
                   for a, b in pairwise(ordered) for k in range(a + 1, b)]
        if missing:
            yield prefix, missing


def validate_rows(rows: Iterable[dict[str, Any]], *, kind: str = "GL",
                  missing_cols: list[str] | None = None,
                  tb_balances: dict[str, Decimal] | None = None) -> ValidationReport:
    tolerance = Decimal(str(get_rule("validation.balance_tolerance").value))
    trn_re = re.compile(str(get_rule("validation.trn_pattern").value))
    issues: list[Issue] = []

    absent = set(missing_cols or [])
    for col in missing_cols or []:
        issues.append(Issue(
            "missing_mandatory_column", CRITICAL, col,
            f"The file has no column for {col}.",
            "Add the column to the export, or map an existing column to it in the "
            "column-mapping step, then upload again."))

    v_dr: dict[str, Decimal] = defaultdict(Decimal)
    v_cr: dict[str, Decimal] = defaultdict(Decimal)
    v_rows: dict[str, _RowSet] = defaultdict(_RowSet)
    first_seen: dict[str, int] = {}
    dup: dict[str, _RowSet] = {}
    bad_dates: dict[str, _RowSet] = defaultdict(_RowSet)
    parse_probs: dict[tuple[str, str], _RowSet] = defaultdict(_RowSet)
    blank_account = _RowSet()
    blank_fields: dict[str, _RowSet] = defaultdict(_RowSet)
    bad_trn = _RowSet()
    voucher_nums: list[tuple[str, int, int]] = []
    seen_vouchers: set[str] = set()
    gl_by_account: dict[str, Decimal] = defaultdict(Decimal)
    total_dr = total_cr = Decimal("0")
    n = 0
    zero = Decimal("0")

    for r in rows:
        n += 1
        row = int(r["row_no"])
        dr, cr = r["debit"] or zero, r["credit"] or zero
        total_dr += dr
        total_cr += cr
        for item in filter(None, (r.get("parse_issues") or "").split(";")):
            fld, code, raw = item.split("|", 2)
            if code == "unreadable_date":
                bad_dates[fld].add(row, raw)
            else:
                parse_probs[(fld, code)].add(row, raw)
        if kind == "TB":
            if not r["account_code"] and "account_code" not in absent:
                blank_account.add(row)
            continue
        line_id, voucher, account = r["line_id"], r["voucher_no"], r["account_code"]
        if not account:
            if "account_code" not in absent:
                blank_account.add(row)
        else:
            gl_by_account[account] += dr - cr
        for fld in ("line_id", "voucher_no"):
            if not r[fld] and fld not in absent:
                blank_fields[fld].add(row)
        if not r["posting_date_raw"] and "posting_date" not in absent:
            blank_fields["posting_date"].add(row)
        if line_id:
            if line_id in first_seen:
                dup.setdefault(line_id, _RowSet(examples=[str(first_seen[line_id])])).add(row)
            else:
                first_seen[line_id] = row
        if voucher:
            v_dr[voucher] += dr
            v_cr[voucher] += cr
            v_rows[voucher].add(row)
            if voucher not in seen_vouchers:
                seen_vouchers.add(voucher)
                if m := _TRAIL_NUM.match(voucher):
                    voucher_nums.append((m[1], int(m[2]), len(m[2])))
        trn = (r.get("trn") or "").strip()
        if trn and not trn_re.match(trn):
            bad_trn.add(row, trn)

    # --- vouchers out of balance (one finding per voucher, as in the prompt example)
    for voucher in sorted(v_dr.keys() | v_cr.keys(), key=lambda v: v_rows[v].rows[0]):
        diff = v_dr[voucher] - v_cr[voucher]
        if abs(diff) > tolerance:
            rs = v_rows[voucher]
            issues.append(Issue(
                "unbalanced_voucher", CRITICAL, "voucher_no",
                f"Voucher {voucher} is out of balance by {aed(abs(diff))} "
                f"(debits {aed(v_dr[voucher])}, credits {aed(v_cr[voucher])}; "
                f"{fmt_rows(rs.rows, rs.count)}).",
                "Correct the source file or exclude the voucher with a reason.",
                rs.rows, rs.count))
    if abs(total_dr - total_cr) > tolerance:
        issues.append(Issue(
            "total_out_of_balance", CRITICAL, None,
            f"The file does not balance: total debits {aed(total_dr)} and total credits "
            f"{aed(total_cr)} differ by {aed(abs(total_dr - total_cr))}.",
            "Fix the unbalanced vouchers listed above, or re-export the complete ledger "
            "for the period (a partial export will not balance)."))
    for fld, rs in sorted(bad_dates.items()):
        label = FIELD_LABEL.get(fld, fld)
        issues.append(Issue(
            "unreadable_date", CRITICAL, fld,
            f"{rs.count} row{'s have' if rs.count > 1 else ' has'} {_a(label)} that cannot be "
            f"read ({fmt_rows(rs.rows, rs.count)}; e.g. "
            f"{', '.join(repr(e) for e in rs.examples)}).",
            "Use a real calendar date in dd/mm/yyyy or yyyy-mm-dd format (an Excel date "
            "cell is also fine). Correct the rows and upload again.", rs.rows, rs.count))
    if blank_account.count:
        rs = blank_account
        issues.append(Issue(
            "blank_account", CRITICAL, "account_code",
            f"{rs.count} row{'s have' if rs.count > 1 else ' has'} no account code "
            f"({fmt_rows(rs.rows, rs.count)}).",
            "Every line must be posted to an account. Fill in the account code from the "
            "accounting system and upload again.", rs.rows, rs.count))
    for fld, rs in sorted(blank_fields.items()):
        label = FIELD_LABEL.get(fld, fld)
        issues.append(Issue(
            "missing_mandatory_field", CRITICAL, fld,
            f"{rs.count} row{'s are' if rs.count > 1 else ' is'} missing the {label} "
            f"({fmt_rows(rs.rows, rs.count)}).",
            f"The {label} is required on every line. Fill it in and upload again.",
            rs.rows, rs.count))
    for line_id, rs in sorted(dup.items(), key=lambda kv: kv[1].rows[0]):
        issues.append(Issue(
            "duplicate_line_id", CRITICAL, "line_id",
            f"Line ID {line_id} appears more than once (first at row {rs.examples[0]}, "
            f"again at {fmt_rows(rs.rows, rs.count)}).",
            "Each line needs a unique ID. Remove the duplicated line if it was exported twice, "
            "or give it a new ID, then upload again.", rs.rows, rs.count))
    for (fld, code), rs in sorted(parse_probs.items()):
        label = FIELD_LABEL.get(fld, fld)
        eg = ", ".join(repr(e) for e in rs.examples)
        if code == "unreadable_amount":
            issues.append(Issue(
                code, CRITICAL, fld,
                f"{rs.count} {label} value{'s' if rs.count > 1 else ''} cannot be read as a "
                f"number ({fmt_rows(rs.rows, rs.count)}; e.g. {eg}).",
                "Use plain numbers such as 1234.50, 1,234.50, (500.00) or 500.00-. "
                "Correct the rows and upload again.", rs.rows, rs.count))
        elif code == "amount_currency_prefix":
            issues.append(Issue(
                code, WARNING, fld,
                f"{rs.count} {label} value{'s include' if rs.count > 1 else ' includes'} "
                f"the currency text ({fmt_rows(rs.rows, rs.count)}; e.g. {eg}). "
                f"{'They were' if rs.count > 1 else 'It was'} read as AED amounts.",
                "No action needed if the amounts are in AED. Otherwise export amounts without "
                "currency text.", rs.rows, rs.count))
        else:  # amount_precision
            issues.append(Issue(
                code, WARNING, fld,
                f"{rs.count} {label} value{'s have' if rs.count > 1 else ' has'} more than 2 "
                f"decimal places ({fmt_rows(rs.rows, rs.count)}; e.g. {eg}).",
                "Check the export; AED amounts normally have 2 decimals (fils). Values are "
                "kept exactly as given.", rs.rows, rs.count))
    if bad_trn.count:
        rs = bad_trn
        issues.append(Issue(
            "invalid_trn", WARNING, "trn",
            f"{rs.count} TRN{'s are' if rs.count > 1 else ' is'} not in the UAE format of "
            f"15 digits starting with 100 ({fmt_rows(rs.rows, rs.count)}; e.g. "
            f"{', '.join(repr(e) for e in rs.examples)}).",
            "Check the supplier's TRN on its tax invoice or on the FTA TRN verification "
            "service. Format the TRN column as text in Excel so long numbers are not turned "
            "into 1.00456E+14.", rs.rows, rs.count))
    for prefix, missing in _gaps(voucher_nums):
        shown = ", ".join(missing[:10]) + (f" and {len(missing) - 10} more"
                                            if len(missing) > 10 else "")
        issues.append(Issue(
            "voucher_gap", WARNING, "voucher_no",
            f"{len(missing)} voucher number{'s are' if len(missing) > 1 else ' is'} missing "
            f"from the {prefix or '(no prefix)'} sequence: {shown}.",
            "Ask the client whether these vouchers were cancelled or deleted, and keep the "
            "explanation on file. Warnings do not block the next steps.", [], len(missing)))
    if tb_balances is not None:
        diffs = []
        for acct in sorted(gl_by_account.keys() | tb_balances.keys()):
            d = gl_by_account.get(acct, zero) - tb_balances.get(acct, zero)
            if abs(d) > tolerance:
                diffs.append(f"{acct} ({aed(d)})")
        if diffs:
            issues.append(Issue(
                "gl_tb_difference", WARNING, "account_code",
                f"The ledger does not agree to the trial balance for {len(diffs)} account"
                f"{'s' if len(diffs) > 1 else ''}: {', '.join(diffs[:10])}"
                f"{' and more' if len(diffs) > 10 else ''}.",
                "Check that the ledger and the trial balance cover the same period and "
                "entity, and that opening balances are treated the same way.", [], len(diffs)))
    return ValidationReport(issues, n, total_dr, total_cr)


def tb_balances_from_parquet(path: Path) -> dict[str, Decimal]:
    """Net movement per account from a TB dataset (closing_balance, else debit - credit)."""
    out: dict[str, Decimal] = defaultdict(Decimal)
    for r in read_parquet_rows(path):
        if not r["account_code"]:
            continue
        cb = r.get("closing_balance")
        out[r["account_code"]] += cb if cb is not None else (
            (r["debit"] or Decimal("0")) - (r["credit"] or Decimal("0")))
    return dict(out)


def validate_parquet(path: Path, *, kind: str = "GL", missing_cols: list[str] | None = None,
                     tb_path: Path | None = None) -> ValidationReport:
    tb = tb_balances_from_parquet(tb_path) if tb_path is not None else None
    return validate_rows(read_parquet_rows(path), kind=kind, missing_cols=missing_cols,
                         tb_balances=tb)


def render_text(report: ValidationReport) -> str:
    """Plain-English listing (CLI and Workbook Step 3.2 check)."""
    lines = [f"{report.rows} rows checked. Total debits {aed(report.total_dr)}, total credits "
             f"{aed(report.total_cr)}. {report.critical} critical error(s), "
             f"{report.warnings} warning(s).", ROW_NOTE, ""]
    order = {CRITICAL: 0, WARNING: 1}
    for i, iss in enumerate(sorted(report.issues, key=lambda x: order[x.severity]), 1):
        lines.append(f"{i}. [{iss.severity.upper()}] {iss.message}")
        lines.append(f"   How to fix: {iss.guidance}")
    if report.blocked:
        lines += ["", "Sampling, journal-entry tests and VAT checks stay blocked until the "
                  "critical errors are fixed."]
    return "\n".join(lines)
