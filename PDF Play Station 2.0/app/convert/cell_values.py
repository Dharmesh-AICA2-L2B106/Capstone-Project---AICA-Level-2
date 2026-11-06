"""Conservative conversion of extracted cell text into typed Excel values.

The guiding rule is: when in doubt, keep the original text. A number-like
string is converted only when the conversion is lossless and unambiguous.
Identifiers (PAN, GSTIN, account numbers, codes with leading zeros, long
digit strings) always stay text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional, Union

CellValue = Union[str, int, float, datetime, None]


@dataclass(frozen=True)
class ParsedCell:
    value: CellValue
    number_format: Optional[str] = None   # None -> leave Excel's "General"
    is_numeric: bool = False
    is_date: bool = False


# Minus signs that occur in PDFs: hyphen-minus, Unicode minus, en dash.
_MINUS = "-−–"
_NUMBER = re.compile(
    rf"^(?P<sign>[{_MINUS}])?(?P<open>\()?(?P<num>\d[\d,]*(?:\.\d+)?|\.\d+)(?P<close>\))?(?P<pct>\s?%)?$"
)
_WESTERN = re.compile(r"^\d{1,3}(?:,\d{3})+$")
_INDIAN = re.compile(r"^\d{1,2}(?:,\d{2})*,\d{3}$")

_PAN = re.compile(r"^[A-Z]{5}\d{4}[A-Z]$")
_GSTIN = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_DATE_NUMERIC = re.compile(r"^(\d{1,2})([/.\-])(\d{1,2})\2(\d{4})$")
_DATE_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_DATE_MONTH = re.compile(r"^(\d{1,2})([\- ])([A-Za-z]{3})[a-z]*\.?\2(\d{4})$")

# Excel number format that displays Indian digit grouping (12,34,567.89) for
# non-negative values. Negative values fall back to the standard grouping.
_INDIAN_FMT = "[>=10000000]##\\,##\\,##\\,##0{d};[>=100000]##\\,##\\,##0{d};##,##0{d}"

MAX_SIGNIFICANT_DIGITS = 15     # Excel stores IEEE doubles: 15 digits are exact
ID_DIGITS_WITHOUT_SEPARATOR = 10  # 10+ bare digits are treated as an identifier


def is_identifier(text: str) -> bool:
    t = text.strip().upper()
    return bool(_PAN.match(t) or _GSTIN.match(t))


def parse_number(text: str, indian_format: bool = True) -> Optional[ParsedCell]:
    t = text.strip().replace(" ", " ")
    m = _NUMBER.match(t.replace(" ", "") if t.endswith("%") else t)
    if not m:
        return None
    sign, opened, closed, pct = m.group("sign"), m.group("open"), m.group("close"), m.group("pct")
    num = m.group("num")
    if bool(opened) != bool(closed) or (opened and sign):
        return None
    int_part, _, frac = num.partition(".")
    grouping = None
    if "," in int_part:
        if _WESTERN.match(int_part):
            grouping = "western"
        elif _INDIAN.match(int_part):
            grouping = "indian"
        else:
            return None                  # malformed grouping such as 1,23,4 -> keep text
    digits = int_part.replace(",", "")
    if len(digits) > 1 and digits.startswith("0"):
        return None                      # leading zeros: an identifier, not an amount
    if grouping is None and not frac and len(digits) >= ID_DIGITS_WITHOUT_SEPARATOR:
        return None                      # account / reference numbers
    if len(digits.lstrip("0")) + len(frac) > MAX_SIGNIFICANT_DIGITS:
        return None
    try:
        dec = Decimal(digits + ("." + frac if frac else ""))
    except InvalidOperation:
        return None
    negative = bool(sign or opened)
    if negative:
        dec = -dec
    decimals = len(frac)
    if pct:
        value = float(dec / 100)
        fmt = "0" + ("." + "0" * decimals if decimals else "") + "%"
        return ParsedCell(value, fmt, is_numeric=True)

    value: Union[int, float] = int(dec) if decimals == 0 else float(dec)
    dec_fmt = "." + "0" * decimals if decimals else ""
    if grouping == "indian" and indian_format and not negative:
        fmt = _INDIAN_FMT.format(d=dec_fmt)
    elif grouping:
        fmt = f"#,##0{dec_fmt}"
    else:
        fmt = f"0{dec_fmt}" if decimals else None
    if opened:
        base = fmt or "0"
        fmt = f"{base}_);({base})"
    return ParsedCell(value, fmt, is_numeric=True)


def parse_date(text: str) -> Optional[ParsedCell]:
    """Day-first dates only (Indian convention); 2-digit years stay text."""
    t = text.strip()
    try:
        m = _DATE_NUMERIC.match(t)
        if m:
            day, sep, month, year = int(m.group(1)), m.group(2), int(m.group(3)), int(m.group(4))
            return ParsedCell(datetime(year, month, day), f"dd{sep}mm{sep}yyyy", is_date=True)
        m = _DATE_ISO.match(t)
        if m:
            return ParsedCell(datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))), "yyyy-mm-dd", is_date=True)
        m = _DATE_MONTH.match(t)
        if m and m.group(3).lower() in _MONTHS:
            sep = m.group(2)
            return ParsedCell(datetime(int(m.group(4)), _MONTHS[m.group(3).lower()], int(m.group(1))),
                              f"dd{sep}mmm{sep}yyyy", is_date=True)
    except ValueError:
        return None                      # e.g. 31/02/2024 - not a real date, keep text
    return None


def parse_cell(text: Optional[str], convert_dates: bool = True, indian_format: bool = True) -> ParsedCell:
    if text is None:
        return ParsedCell(None)
    stripped = text.strip()
    if not stripped:
        return ParsedCell(None)
    if "\n" in stripped or is_identifier(stripped):
        return ParsedCell(text.strip())
    number = parse_number(stripped, indian_format)
    if number:
        return number
    if convert_dates:
        date = parse_date(stripped)
        if date:
            return date
    return ParsedCell(stripped)


def looks_numeric(text: Optional[str]) -> bool:
    """True for amounts/percentages and amounts with a Dr/Cr suffix."""
    if not text:
        return False
    t = text.strip()
    t = re.sub(r"\s*(Dr|Cr|DR|CR)\.?$", "", t)
    return parse_number(t) is not None
