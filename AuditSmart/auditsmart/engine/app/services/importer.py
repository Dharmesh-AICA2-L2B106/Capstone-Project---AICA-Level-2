"""Importer: header mapping, value parsing and chunked conversion to Parquet (prompt 3.2).

* Header synonyms are matched after normalising (lower case, letters and digits only);
  the user can override any mapping.
* Dates: ISO (yyyy-mm-dd, optional time), dd/mm/yyyy (UAE convention, also - and .),
  dd-Mon-yyyy and Excel serial numbers (1900 system, epoch 1899-12-30).
* Amounts: thousands commas, (brackets) and trailing/leading minus for negatives; an
  "AED" prefix/suffix is accepted with a warning. Values are exact ``Decimal``.
* The file is parsed ``parse_chunk_rows`` rows at a time and written to one Parquet file
  per dataset; nothing is held in memory beyond a chunk. Parse problems are carried per
  row in the ``parse_issues`` column for the validation service.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, BinaryIO

import pyarrow as pa
import pyarrow.parquet as pq

IMPLEMENTED_BY_PROMPT = "3.2"

AMOUNT_TYPE = pa.decimal128(24, 6)

TEXT_FIELDS = (
    "line_id", "posting_time", "voucher_no", "account_code", "account_name", "account_type",
    "currency", "narration", "user_id", "party_id", "party_name", "trn", "invoice_no",
    "vat_code", "expense_category",
)
DATE_FIELDS = ("entry_date", "posting_date")
AMOUNT_FIELDS = ("debit", "credit", "net_amount", "vat_amount")

SYNONYMS: dict[str, tuple[str, ...]] = {
    "line_id": ("line_id", "lineid", "line_no", "line", "entry_line_id", "row_id", "id",
                "transaction_line_id"),
    "entry_date": ("entry_date", "created_date", "date_entered", "input_date", "creation_date",
                   "system_date"),
    "posting_date": ("posting_date", "post_date", "gl_date", "date", "transaction_date",
                     "document_date", "accounting_date", "voucher_date", "txn_date"),
    "posting_time": ("posting_time", "time", "entry_time", "created_time"),
    "voucher_no": ("voucher_no", "voucher", "voucher_number", "journal_no", "journal_number",
                   "je_number", "je_no", "document_no", "doc_no", "reference", "jv_no",
                   "entry_no"),
    "account_code": ("account_code", "account", "account_no", "account_number", "gl_account",
                     "gl_code", "ledger_code", "acct", "acct_no"),
    "account_name": ("account_name", "account_description", "gl_account_name", "ledger_name",
                     "account_title"),
    "account_type": ("account_type", "type", "account_class", "category"),
    "debit": ("debit", "dr", "debit_amount", "debit_aed", "dr_amount"),
    "credit": ("credit", "cr", "credit_amount", "credit_aed", "cr_amount"),
    "amount": ("amount", "signed_amount", "net", "value", "amount_aed"),
    "currency": ("currency", "ccy", "currency_code"),
    "narration": ("narration", "description", "memo", "particulars", "remarks", "details",
                  "line_description"),
    "user_id": ("user_id", "user", "created_by", "posted_by", "entered_by", "username"),
    "party_id": ("party_id", "vendor_id", "customer_id", "supplier_id", "partner_id"),
    "party_name": ("party_name", "vendor_name", "customer_name", "supplier_name", "partner"),
    "trn": ("trn", "tax_registration_number", "vat_number", "vat_reg_no", "vat_trn"),
    "invoice_no": ("invoice_no", "invoice_number", "invoice", "bill_no", "tax_invoice_no"),
    "net_amount": ("net_amount", "taxable_amount", "amount_excl_vat", "net_value"),
    "vat_amount": ("vat_amount", "vat", "tax_amount", "input_vat", "output_vat"),
    "vat_code": ("vat_code", "tax_code", "vat_type"),
    "expense_category": ("expense_category", "expense_type", "cost_category"),
    # trial balance
    "closing_balance": ("closing_balance", "balance", "closing", "net_balance", "movement"),
}

GL_MANDATORY = ("line_id", "posting_date", "voucher_no", "account_code")
TB_MANDATORY = ("account_code",)


def norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", h.strip().lower().lstrip("\ufeff"))


_SYN_LOOKUP: dict[str, str] = {}
for _canon, _syns in SYNONYMS.items():
    for _s in _syns:
        _SYN_LOOKUP.setdefault(norm_header(_s), _canon)


def suggest_mapping(headers: Iterable[str], override: dict[str, str] | None = None
                    ) -> dict[str, str]:
    """Return {canonical_field: source_header}. ``override`` wins and may map to ''."""
    mapping: dict[str, str] = {}
    for h in headers:
        canon = _SYN_LOOKUP.get(norm_header(h))
        if canon and canon not in mapping:
            mapping[canon] = h
    for canon, src in (override or {}).items():
        if canon not in SYNONYMS:
            raise ValueError(f"Unknown target field '{canon}' in the mapping override.")
        if src:
            mapping[canon] = src
        else:
            mapping.pop(canon, None)
    return mapping


def missing_columns(mapping: dict[str, str], kind: str = "GL") -> list[str]:
    need = GL_MANDATORY if kind == "GL" else TB_MANDATORY
    out = [f for f in need if f not in mapping]
    has_amount = ("debit" in mapping and "credit" in mapping) or "amount" in mapping or (
        kind == "TB" and "closing_balance" in mapping)
    if not has_amount:
        out.append("debit/credit (or amount)")
    return out


# --------------------------------------------------------------------------- dates
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?$")
_YMD_SLASH = re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})$")
_DMY = re.compile(r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})(?: \d{1,2}:\d{2}(?::\d{2})?)?$")
_DMONY = re.compile(r"^(\d{1,2})[ \-/]([A-Za-z]{3})[A-Za-z]*[ \-/](\d{4})$")
_SERIAL = re.compile(r"^(\d{5})(?:\.0+)?$")
EXCEL_EPOCH = date(1899, 12, 30)
SERIAL_MIN, SERIAL_MAX = 20000, 80000  # 1954-10-03 .. 2119-01-11: plausible ledger dates


def _mk(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_date(raw: str) -> date | None:
    """Parse one date string; None if unreadable. Blank input must be handled by caller."""
    s = raw.strip()
    if m := _ISO.match(s):
        return _mk(int(m[1]), int(m[2]), int(m[3]))
    if m := _YMD_SLASH.match(s):
        return _mk(int(m[1]), int(m[2]), int(m[3]))
    if m := _DMY.match(s):
        return _mk(int(m[3]), int(m[2]), int(m[1]))
    if m := _DMONY.match(s):
        mon = _MONTHS.get(m[2].lower())
        return _mk(int(m[3]), mon, int(m[1])) if mon else None
    if m := _SERIAL.match(s):
        n = int(m[1])
        if SERIAL_MIN <= n <= SERIAL_MAX:
            return EXCEL_EPOCH + timedelta(days=n)
    return None


# --------------------------------------------------------------------------- amounts
_NUM = re.compile(r"^\d+(?:\.\d+)?$|^\.\d+$")
_CCY = re.compile(r"^(?:AED|DHS?|DH)\s*|\s*(?:AED|DHS?|DH)$", re.IGNORECASE)


@dataclass(frozen=True)
class AmountResult:
    value: Decimal | None  # None = blank
    ok: bool = True
    currency_text: bool = False


def parse_amount(raw: str) -> AmountResult:
    s = raw.strip().replace("\u2212", "-").replace("\u00a0", " ")
    if s == "":
        return AmountResult(None)
    ccy = False
    if _CCY.search(s):
        s, ccy = _CCY.sub("", s).strip(), True
    neg = False
    if s.startswith("(") and s.endswith(")"):
        s, neg = s[1:-1].strip(), True
    if s.endswith("-"):
        s, neg = s[:-1].strip(), not neg
    elif s.startswith("-"):
        s, neg = s[1:].strip(), not neg
    elif s.startswith("+"):
        s = s[1:].strip()
    s = s.replace(",", "").replace(" ", "")
    if not _NUM.match(s):
        return AmountResult(None, ok=False, currency_text=ccy)
    try:
        v = Decimal(s)
    except InvalidOperation:  # pragma: no cover - regex already guarantees a number
        return AmountResult(None, ok=False)
    return AmountResult(-v if neg else v, ok=True, currency_text=ccy)


# --------------------------------------------------------------------------- files
def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


def copy_stream(src: BinaryIO, dest: Path, max_bytes: int, chunk: int = 1 << 20
                ) -> tuple[int, str]:
    """Stream ``src`` to ``dest`` in chunks, returning (bytes, sha256). Enforces the size cap."""
    h, size = hashlib.sha256(), 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as out:
        while b := src.read(chunk):
            size += len(b)
            if size > max_bytes:
                out.close()
                dest.unlink(missing_ok=True)
                raise ValueError(
                    f"The file is larger than the {max_bytes // (1024 * 1024)} MB limit.")
            h.update(b)
            out.write(b)
    return size, h.hexdigest()


def read_headers(path: Path) -> list[str]:
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        first = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
        wb.close()
        return [str(c) if c is not None else "" for c in first]
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return next(csv.reader(f), [])


def _xlsx_cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def iter_records(path: Path, chunk_rows: int) -> Iterator[tuple[list[str], list[list[str]]]]:
    """Yield (headers, rows) chunks of raw string cells."""
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        it = wb.worksheets[0].iter_rows(values_only=True)
        headers = [_xlsx_cell(c) for c in next(it, ())]
        buf: list[list[str]] = []
        for r in it:
            buf.append([_xlsx_cell(c) for c in r])
            if len(buf) >= chunk_rows:
                yield headers, buf
                buf = []
        wb.close()
        if buf:
            yield headers, buf
        return
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        headers = next(reader, [])
        buf = []
        for r in reader:
            if not any(c.strip() for c in r):
                continue  # fully blank line
            buf.append(r)
            if len(buf) >= chunk_rows:
                yield headers, buf
                buf = []
        if buf:
            yield headers, buf


SCHEMA = pa.schema(
    [("row_no", pa.int64())]
    + [(f, pa.string()) for f in TEXT_FIELDS]
    + [(f, pa.date32()) for f in DATE_FIELDS]
    + [(f"{f}_raw", pa.string()) for f in DATE_FIELDS]
    + [(f, AMOUNT_TYPE) for f in AMOUNT_FIELDS]
    + [("closing_balance", AMOUNT_TYPE), ("parse_issues", pa.string())]
)


@dataclass
class ParseResult:
    rows: int = 0
    chunks: int = 0
    total_dr: Decimal = Decimal("0")
    total_cr: Decimal = Decimal("0")
    min_date: date | None = None
    max_date: date | None = None
    vouchers: int = 0
    accounts: int = 0
    mapping: dict[str, str] = field(default_factory=dict)
    unmapped_headers: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)

    def profile(self) -> dict[str, Any]:
        return {
            "rows": self.rows, "chunks": self.chunks, "total_dr": str(self.total_dr),
            "total_cr": str(self.total_cr),
            "min_posting_date": self.min_date.isoformat() if self.min_date else None,
            "max_posting_date": self.max_date.isoformat() if self.max_date else None,
            "vouchers": self.vouchers, "accounts": self.accounts,
            "unmapped_headers": self.unmapped_headers, "missing_columns": self.missing_columns,
        }


def _q(v: Decimal | None) -> Decimal | None:
    return None if v is None else v.quantize(Decimal("0.000001"))


def parse_to_parquet(src: Path, dest: Path, *, kind: str = "GL",
                     override: dict[str, str] | None = None, chunk_rows: int = 50_000,
                     progress: Any = None) -> ParseResult:
    """Parse ``src`` (CSV or XLSX) chunk by chunk into ``dest`` Parquet."""
    res = ParseResult()
    dest.parent.mkdir(parents=True, exist_ok=True)
    writer: pq.ParquetWriter | None = None
    vouchers: set[str] = set()
    accounts: set[str] = set()
    row_no = 0
    try:
        for headers, chunk in iter_records(src, chunk_rows):
            if writer is None:
                res.mapping = suggest_mapping(headers, override)
                used = set(res.mapping.values())
                res.unmapped_headers = [h for h in headers if h not in used]
                res.missing_columns = missing_columns(res.mapping, kind)
                writer = pq.ParquetWriter(str(dest), SCHEMA)
            idx = {canon: headers.index(src_h) for canon, src_h in res.mapping.items()
                   if src_h in headers}
            cols: dict[str, list[Any]] = {n: [] for n in SCHEMA.names}
            for raw in chunk:
                row_no += 1
                issues: list[str] = []

                def cell(name: str, _raw: list[str] = raw, _idx: dict[str, int] = idx) -> str:
                    i = _idx.get(name)
                    return _raw[i].strip() if i is not None and i < len(_raw) else ""

                cols["row_no"].append(row_no)
                for f in TEXT_FIELDS:
                    cols[f].append(cell(f))
                for f in DATE_FIELDS:
                    s = cell(f)
                    d = parse_date(s) if s else None
                    if s and d is None:
                        issues.append(f"{f}|unreadable_date|{s}")
                    cols[f].append(d)
                    cols[f"{f}_raw"].append(s)
                    if f == "posting_date" and d is not None:
                        res.min_date = d if res.min_date is None else min(res.min_date, d)
                        res.max_date = d if res.max_date is None else max(res.max_date, d)
                amounts: dict[str, Decimal | None] = {}
                for f in (*AMOUNT_FIELDS, "amount", "closing_balance"):
                    s = cell(f)
                    a = parse_amount(s)
                    if not a.ok:
                        issues.append(f"{f}|unreadable_amount|{s}")
                    elif a.currency_text:
                        issues.append(f"{f}|amount_currency_prefix|{s}")
                    if a.value is not None and a.value.as_tuple().exponent < -2:  # type: ignore[operator]
                        issues.append(f"{f}|amount_precision|{s}")
                    amounts[f] = a.value
                if "amount" in idx and "debit" not in idx and "credit" not in idx:
                    amt = amounts["amount"] or Decimal("0")
                    amounts["debit"] = amt if amt > 0 else Decimal("0")
                    amounts["credit"] = -amt if amt < 0 else Decimal("0")
                for f in (*AMOUNT_FIELDS, "closing_balance"):
                    cols[f].append(_q(amounts[f]))
                res.total_dr += amounts["debit"] or Decimal("0")
                res.total_cr += amounts["credit"] or Decimal("0")
                cols["parse_issues"].append(";".join(issues))
                vouchers.add(cell("voucher_no"))
                accounts.add(cell("account_code"))
            writer.write_table(pa.Table.from_pydict(cols, schema=SCHEMA))
            res.chunks += 1
            res.rows = row_no
            if progress is not None:
                progress(res.rows)
        if writer is None:  # empty file
            writer = pq.ParquetWriter(str(dest), SCHEMA)
            res.missing_columns = missing_columns({}, kind)
    finally:
        if writer is not None:
            writer.close()
    vouchers.discard("")
    accounts.discard("")
    res.vouchers, res.accounts = len(vouchers), len(accounts)
    return res


def read_parquet_rows(path: Path, *, batch_size: int = 65_536,
                      columns: Sequence[str] | None = None) -> Iterator[dict[str, Any]]:
    """Stream rows as dicts; ``columns`` projects (unknown names are ignored)."""
    pf = pq.ParquetFile(str(path))
    cols = None if columns is None else [c for c in columns if c in pf.schema_arrow.names]
    for batch in pf.iter_batches(batch_size=batch_size, columns=cols):
        yield from batch.to_pylist()


def to_csv_bytes(rows: list[list[str]]) -> bytes:
    """Helper for tests and the CLI: render rows to CSV bytes."""
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return buf.getvalue().encode()
