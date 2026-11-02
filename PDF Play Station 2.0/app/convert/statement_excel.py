"""Excel workbook for bank-statement mode.

Sheets:
  Statement           one row per transaction, live balance-check formula per row,
                      status colour (OK / Re-read / Corrected / Inferred / Check)
  Review              only the rows that need a human look, with the reason
  Bank Totals Check   the bank's printed totals against formula-computed totals
  Notes               header text of the statement, method and legend
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import APP_NAME, APP_VERSION
from .bank_statement import StatementResult

NAVY = "0B1E3D"
INR = '[>=10000000]##\\,##\\,##\\,##0.00;[>=100000]##\\,##\\,##0.00;##,##0.00'
PLAIN = "#,##0.00;-#,##0.00"
HEAD = Font(bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor=NAVY)
THIN = Side(style="thin", color="C9CED8")
BOX = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)
STATUS_FILL = {
    "OK": None,
    "Re-read": PatternFill("solid", fgColor="EAF4EE"),
    "Corrected": PatternFill("solid", fgColor="EAF0F8"),
    "Inferred": PatternFill("solid", fgColor="FFF6E5"),
    "Check": PatternFill("solid", fgColor="FDECEA"),
}
LEGEND = [
    ("OK", "Read from the PDF and balances with the previous row."),
    ("Re-read", "First reading did not balance; the cell was read again from the scan and the new reading balances."),
    ("Corrected", "Value corrected and proven by two independent sources: the running balance plus either the "
                  "direction of the balance change (wrong column) or the bank's printed totals."),
    ("Inferred", "A value could not be read and was COMPUTED from the neighbouring balances - verify against the PDF."),
    ("Check", "Could not be reconciled or the date looks wrong - compare with the PDF before use."),
]
VERIFY = ("Please verify the extracted figures, dates and other critical information against the original PDF "
          "before relying on this output, in particular every row not marked OK.")


def _header(ws, row: int, labels: list[str]) -> None:
    for c, h in enumerate(labels, start=1):
        cell = ws.cell(row=row, column=c, value=h)
        cell.font, cell.fill, cell.border = HEAD, HEAD_FILL, BOX
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = 30


def build_statement_workbook(result: StatementResult) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "Statement"
    fmt = INR if all((r.balance or 0) >= 0 for r in result.rows) else PLAIN

    ws["A1"] = f"Bank statement - {result.source.name}"
    ws["A1"].font = Font(bold=True, size=14, color=NAVY)
    counts = {s: result.count(s) for s in STATUS_FILL}
    ws["A2"] = (f"{len(result.rows)} rows · " + " · ".join(f"{k}: {v}" for k, v in counts.items() if v)
                + f" · source: {'scanned (OCR)' if result.method == 'ocr' else 'PDF text'}")
    ws["A2"].font = Font(color="4A5568")
    ws["A3"] = VERIFY
    ws["A3"].font = Font(italic=True, color="9A5B00")

    cols = ["Sr", "Date", "Particulars", "Additional details", "Chq No", "Withdrawals", "Deposits", "Balance",
            "Cr/Dr", "Status", "Verification notes", "OCR read (W | D | Balance)", "PDF page", "Balance check"]
    HR = 5
    _header(ws, HR, cols)
    first = HR + 1
    for i, r in enumerate(result.rows):
        x = first + i
        ws.cell(row=x, column=1, value=i if r.kind == "txn" else None)
        if r.date is not None:
            ws.cell(row=x, column=2, value=r.date).number_format = "dd-mm-yyyy"
        elif r.date_text:
            ws.cell(row=x, column=2, value=r.date_text).data_type = "s"
        c = ws.cell(row=x, column=3, value=r.particulars or ("B/F" if r.kind == "bf" else ""))
        c.data_type = "s"
        if r.details:
            ws.cell(row=x, column=4, value="; ".join(r.details)).data_type = "s"
        if r.cheque:
            ws.cell(row=x, column=5, value=r.cheque).data_type = "s"
        for col, v in ((6, r.withdrawal), (7, r.deposit), (8, r.balance)):
            if v is not None:
                ws.cell(row=x, column=col, value=float(v)).number_format = fmt
        ws.cell(row=x, column=9, value=f'=IF(H{x}="","",IF(H{x}<0,"Dr","Cr"))')
        ws.cell(row=x, column=10, value=r.status).font = Font(bold=r.status != "OK")
        if r.notes:
            ws.cell(row=x, column=11, value=" ".join(r.notes))
        if r.status != "OK" and r.raw:
            ws.cell(row=x, column=12, value=f"{r.raw.get('w', '')} | {r.raw.get('d', '')} | {r.raw.get('b', '')}"
                    ).data_type = "s"
        ws.cell(row=x, column=13, value=r.page)
        prev = f"H{x - 1}" if i else "0"
        if i == 0:
            check = f"=ROUND(N(G{x})-N(F{x})-N(H{x}),2)" if r.kind == "bf" else '=""'
        else:
            check = f"=ROUND(N({prev})-N(F{x})+N(G{x})-N(H{x}),2)"
        ws.cell(row=x, column=14, value=check).number_format = "0.00"
        fill = STATUS_FILL.get(r.status)
        for col in range(1, 15):
            cell = ws.cell(row=x, column=col)
            cell.border = BOX
            if fill is not None:
                cell.fill = fill
        for col in (3, 4, 11):
            ws.cell(row=x, column=col).alignment = Alignment(wrap_text=True, vertical="top")
    last = first + len(result.rows) - 1

    tr = last + 1
    ws.cell(row=tr, column=3, value="Totals").font = Font(bold=True)
    for col in (6, 7):
        L = get_column_letter(col)
        c = ws.cell(row=tr, column=col, value=f"=SUM({L}{first}:{L}{last})")
        c.font, c.number_format = Font(bold=True), fmt
    c = ws.cell(row=tr, column=8, value=f"=H{last}")
    c.font, c.number_format = Font(bold=True), fmt
    ws.cell(row=tr, column=14, value=f'=IF(COUNTIF(N{first}:N{last},">0")+COUNTIF(N{first}:N{last},"<0")=0,'
                                     f'"All rows balance","CHECK ROWS")').font = Font(bold=True)
    for col in range(1, 15):
        ws.cell(row=tr, column=col).border = Border(top=Side(style="medium", color=NAVY),
                                                    bottom=Side(style="medium", color=NAVY))
    ws.conditional_formatting.add(f"N{first}:N{last}", CellIsRule(
        operator="notEqual", formula=["0"], fill=PatternFill("solid", fgColor="F8C9C4")))
    ws.freeze_panes = ws.cell(row=first, column=3)
    ws.auto_filter.ref = f"A{HR}:N{last}"
    for col, width in zip("ABCDEFGHIJKLMN", (5, 11, 48, 30, 8, 14, 14, 15, 5, 10, 46, 30, 6, 9)):
        ws.column_dimensions[col].width = width
    ws.print_title_rows = f"{HR}:{HR}"
    ws.page_setup.orientation = "landscape"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0

    # ------------------------------------------------ review
    rv = wb.create_sheet("Review")
    rv["A1"] = "Rows that need a human check (everything not marked OK)"
    rv["A1"].font = Font(bold=True, size=12, color=NAVY)
    _header(rv, 3, ["Statement row", "PDF page", "Date", "Particulars", "Withdrawals", "Deposits", "Balance",
                    "Status", "Why"])
    rr = 4
    for i, r in enumerate(result.rows):
        if r.status == "OK":
            continue
        vals = [first + i, r.page, r.date_text, r.particulars,
                float(r.withdrawal) if r.withdrawal is not None else None,
                float(r.deposit) if r.deposit is not None else None,
                float(r.balance) if r.balance is not None else None, r.status, " ".join(r.notes)]
        for c, v in enumerate(vals, start=1):
            cell = rv.cell(row=rr, column=c, value=v)
            cell.border = BOX
            if 5 <= c <= 7 and v is not None:
                cell.number_format = fmt
            if STATUS_FILL.get(r.status) is not None:
                cell.fill = STATUS_FILL[r.status]
        rv.cell(row=rr, column=9).alignment = Alignment(wrap_text=True, vertical="top")
        rr += 1
    if rr == 4:
        rv.cell(row=4, column=1, value="None - every row was read and balances.").font = Font(italic=True)
    for col, width in zip("ABCDEFGHI", (10, 8, 11, 44, 14, 14, 15, 10, 70)):
        rv.column_dimensions[col].width = width
    rv.freeze_panes = "A4"

    # ------------------------------------------------ totals check
    tc = wb.create_sheet("Bank Totals Check")
    tc["A1"] = "The bank's printed totals compared with totals computed from the Statement sheet"
    tc["A1"].font = Font(bold=True, size=12, color=NAVY)
    _header(tc, 3, ["PDF page", "Label", "Up to row", "Bank: Withdrawals", "Bank: Deposits", "Bank: Balance",
                    "Computed: Withdrawals", "Computed: Deposits", "Computed: Balance", "Result"])
    for k, cp in enumerate(result.checkpoints):
        x = 4 + k
        srow = first + cp.after_row
        vals = [cp.page, cp.label, srow,
                float(cp.withdrawals) if cp.withdrawals is not None else None,
                float(cp.deposits) if cp.deposits is not None else None,
                float(cp.balance) if cp.balance is not None else None,
                f"=SUM(Statement!F{first}:F{srow})", f"=SUM(Statement!G{first}:G{srow})", f"=Statement!H{srow}",
                {True: "Match", False: "Differs", None: "Not checked"}[cp.matches]]
        for c, v in enumerate(vals, start=1):
            cell = tc.cell(row=x, column=c, value=v)
            cell.border = BOX
            if 4 <= c <= 9:
                cell.number_format = fmt
        if cp.matches is False:
            tc.cell(row=x, column=10).fill = STATUS_FILL["Check"]
    if not result.checkpoints:
        tc.cell(row=4, column=1, value="The statement has no printed totals lines to compare with.").font = Font(italic=True)
    tc.cell(row=5 + len(result.checkpoints), column=1, value=(
        "Banks print either running (cumulative) totals or per-page totals; a total counts as a match when it "
        "agrees with either.")).font = Font(italic=True, color="4A5568")
    for col, width in zip("ABCDEFGHIJ", (8, 20, 9, 16, 16, 15, 16, 16, 15, 11)):
        tc.column_dimensions[col].width = width

    # ------------------------------------------------ notes
    nt = wb.create_sheet("Notes")
    lines: list[tuple[str, bool]] = [("Statement header (as read)", True)]
    lines += [(t, False) for t in result.header_text[:25]]
    lines += [("", False), ("How this sheet was produced", True),
              (f"{APP_NAME} {APP_VERSION}, bank-statement mode. All processing was done on this computer "
               "(no internet / cloud services).", False),
              ("Each row was checked with: previous balance - withdrawal + deposit = balance. Values that did not "
               "balance were re-read from the scan; values that still could not be read were computed from the "
               "neighbouring balances only when the following row confirmed them.", False),
              ("Handwritten annotations on scanned copies are not transcribed.", False),
              ("", False), ("Status legend", True)]
    lines += [(f"{k}: {v}", False) for k, v in LEGEND]
    if result.warnings:
        lines += [("", False), ("Warnings", True)] + [(w, False) for w in result.warnings]
    for i, (t, bold) in enumerate(lines, start=1):
        c = nt.cell(row=i, column=1, value=t)
        c.data_type = "s"
        if bold:
            c.font = Font(bold=True, size=12, color=NAVY)
    nt.column_dimensions["A"].width = 130

    wb.properties.creator = APP_NAME
    wb.properties.title = f"{result.source.stem} (bank statement)"
    return wb


def write_statement_excel(result: StatementResult, target: Path) -> list[str]:
    build_statement_workbook(result).save(str(target))
    return list(result.warnings)
