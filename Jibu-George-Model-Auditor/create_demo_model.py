# create_demo_model.py
# Generates DemoCo_DCF_Model_SYNTHETIC.xlsx, the demo workbook for Model Auditor.
# All data is SYNTHETIC. The errors planted in it are listed in Demo_Answer_Key.md.
#
# How to run: open this file in Python IDLE and press F5.
# Manual install if needed (one line):
#   pip install openpyxl
#
# Note: openpyxl does not calculate formulas, so the file has no cached values
# until it has been opened and saved in Excel once. Model Auditor's formula
# checks work either way.

import importlib
import subprocess
import sys

REQUIRED_PACKAGES = [("openpyxl", "openpyxl")]  # (pip name, import name)
MANUAL_PIP_COMMAND = "pip install openpyxl"


def show_install_failure(package):
    message = (
        "Could not install '" + package + "' automatically.\n\n"
        "This is usually a firewall or network restriction.\n"
        "Open Command Prompt, run this command, then try again:\n\n"
        "    " + MANUAL_PIP_COMMAND
    )
    print(message)
    try:
        import tkinter
        from tkinter import messagebox
        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror("Demo model generator", message)
        root.destroy()
    except Exception:
        pass


def ensure_packages():
    for pip_name, import_name in REQUIRED_PACKAGES:
        try:
            importlib.import_module(import_name)
        except ImportError:
            print("Installing " + pip_name + " (first run only)...")
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", pip_name],
                               check=True, capture_output=True)
                importlib.invalidate_caches()
                importlib.import_module(import_name)
            except Exception:
                show_install_failure(pip_name)
                raise SystemExit(1)


ensure_packages()

import os

from openpyxl import Workbook
from openpyxl.packaging.relationship import Relationship
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.workbook.external_link.external import (
    ExternalBook, ExternalCell, ExternalLink, ExternalRow, ExternalSheetData,
    ExternalSheetDataSet, ExternalSheetNames)

OUTPUT_NAME = "DemoCo_DCF_Model_SYNTHETIC.xlsx"
SYNTHETIC_NOTE = "SYNTHETIC DATA - fictional company, created for a software demo. Not real financial information."

YEARS = ["FY2025E", "FY2026E", "FY2027E", "FY2028E", "FY2029E"]
YEAR_COLS = ["D", "E", "F", "G", "H"]  # forecast columns on every sheet
PREV_COL = {"D": "C", "E": "D", "F": "E", "G": "F", "H": "G"}

NAVY = "1F3864"
TITLE_FONT = Font(name="Calibri", size=14, bold=True, color=NAVY)
NOTE_FONT = Font(name="Calibri", size=10, bold=True, color="C00000")
HEADER_FONT = Font(name="Calibri", bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor=NAVY)
SECTION_FONT = Font(name="Calibri", bold=True, color=NAVY)
BOLD_FONT = Font(name="Calibri", bold=True)
INPUT_FONT = Font(name="Calibri", color="0000FF")

FMT_NUM = "#,##0.0;(#,##0.0);-"
FMT_PCT = "0.0%"
FMT_DAYS = "0"
FMT_FACTOR = "0.000"


def start_sheet(wb, name, title, base_label="FY2024A", extra_headers=()):
    ws = wb.create_sheet(name)
    ws["A1"] = "DemoCo - " + title
    ws["A1"].font = TITLE_FONT
    ws["A2"] = SYNTHETIC_NOTE
    ws["A2"].font = NOTE_FONT
    headers = ["USD m unless stated", "Unit", base_label] + YEARS + list(extra_headers)
    for index, text in enumerate(headers, start=1):
        cell = ws.cell(row=4, column=index, value=text)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="left" if index == 1 else "center")
    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 8
    for col in ["C"] + YEAR_COLS + ["I"]:
        ws.column_dimensions[col].width = 12
    ws.freeze_panes = "C5"
    ws.sheet_view.showGridLines = False
    return ws


def label(ws, row, text, unit="USD m", bold=False):
    ws.cell(row=row, column=1, value=text).font = BOLD_FONT if bold else Font(name="Calibri")
    ws.cell(row=row, column=2, value=unit)


def section(ws, row, text):
    ws.cell(row=row, column=1, value=text).font = SECTION_FONT


def fill_row(ws, row, template, number_format=FMT_NUM, bold=False):
    """Write one formula across the forecast years. {c} is the year column, {p} the prior one."""
    for col in YEAR_COLS:
        cell = ws[col + str(row)]
        cell.value = template.format(c=col, p=PREV_COL[col])
        cell.number_format = number_format
        if bold:
            cell.font = BOLD_FONT


def put(ws, address, value, number_format=FMT_NUM, bold=False):
    cell = ws[address]
    cell.value = value
    cell.number_format = number_format
    if bold:
        cell.font = BOLD_FONT


def build_inputs(wb):
    ws = start_sheet(wb, "Inputs", "Inputs and Assumptions")
    series = [
        (5, "Revenue growth", "%", [0.08, 0.09, 0.10, 0.08, 0.06], FMT_PCT),
        (6, "COGS % of revenue", "%", [0.58, 0.58, 0.575, 0.57, 0.57], FMT_PCT),
        (7, "Operating expenses % of revenue", "%", [0.20, 0.20, 0.195, 0.195, 0.19], FMT_PCT),
        (8, "Depreciation % of opening PP&E", "%", [0.12] * 5, FMT_PCT),
        (9, "Capex % of revenue", "%", [0.05, 0.05, 0.06, 0.05, 0.05], FMT_PCT),
        (10, "Receivable days", "days", [45] * 5, FMT_DAYS),
        (11, "Inventory days", "days", [50, 50, 48, 48, 48], FMT_DAYS),
        (12, "Payable days", "days", [40] * 5, FMT_DAYS),
        (13, "Tax rate", "%", [0.25] * 5, FMT_PCT),
        (14, "Interest rate on debt", "%", [0.09] * 5, FMT_PCT),
        (15, "Scheduled debt repayment", "USD m", [20] * 5, FMT_NUM),
    ]
    for row, text, unit, values, number_format in series:
        label(ws, row, text, unit)
        for col, value in zip(YEAR_COLS, values):
            put(ws, col + str(row), value, number_format)
            ws[col + str(row)].font = INPUT_FONT

    section(ws, 17, "Valuation and opening balance inputs (FY2024A)")
    scalars = [
        (18, "WACC", "%", 0.11, FMT_PCT),
        (19, "Terminal growth rate", "%", 0.03, FMT_PCT),
        (20, "Base-year revenue", "USD m", 1000, FMT_NUM),
        (21, "Opening cash", "USD m", 120, FMT_NUM),
        (22, "Opening receivables", "USD m", 123, FMT_NUM),
        (23, "Opening inventory", "USD m", 79, FMT_NUM),
        (24, "Opening PP&E (net)", "USD m", 400, FMT_NUM),
        (25, "Opening payables", "USD m", 64, FMT_NUM),
        (26, "Opening other current liabilities", "USD m", 50, FMT_NUM),
        (27, "Opening debt", "USD m", 200, FMT_NUM),
        (28, "Opening share capital", "USD m", 150, FMT_NUM),
        (29, "Opening retained earnings", "USD m", 258, FMT_NUM),
        (30, "Tax losses brought forward", "USD m", 30, FMT_NUM),
        (31, "Shares outstanding", "m", 100, FMT_NUM),
        (32, "Legacy USD/AED rate (from old version)", "x", 3.67, "0.00"),  # PLANTED: unused input
        (33, "Headcount (to be populated)", "no.", 0, "0"),
    ]
    for row, text, unit, value, number_format in scalars:
        label(ws, row, text, unit)
        put(ws, "C" + str(row), value, number_format)
        ws["C" + str(row)].font = INPUT_FONT


def build_is(wb):
    ws = start_sheet(wb, "IS", "Income Statement")
    label(ws, 5, "Revenue", bold=True)
    put(ws, "C5", "=Inputs!$C$20", bold=True)
    fill_row(ws, 5, "={p}5*(1+Inputs!{c}5)", bold=True)
    label(ws, 6, "Cost of goods sold")
    fill_row(ws, 6, "=-{c}5*Inputs!{c}6")
    label(ws, 7, "Gross profit", bold=True)
    fill_row(ws, 7, "={c}5+{c}6", bold=True)
    label(ws, 8, "Operating expenses")
    fill_row(ws, 8, "=-{c}5*Inputs!{c}7")
    label(ws, 9, "EBITDA", bold=True)
    fill_row(ws, 9, "={c}7+{c}8", bold=True)
    label(ws, 10, "Depreciation")
    fill_row(ws, 10, "=-BS!{c}28")
    label(ws, 11, "EBIT", bold=True)
    fill_row(ws, 11, "={c}9+{c}10", bold=True)
    label(ws, 12, "Interest expense")
    fill_row(ws, 12, "=-BS!{c}32*Inputs!{c}14")
    label(ws, 13, "Profit before tax", bold=True)
    fill_row(ws, 13, "={c}11+{c}12", bold=True)
    label(ws, 14, "Tax (FY2025 after brought-forward losses)")
    fill_row(ws, 14, "=-MAX(0,{c}13)*Inputs!{c}13")
    label(ws, 15, "Net income", bold=True)
    fill_row(ws, 15, "={c}13+{c}14", bold=True)

    section(ws, 17, "Ratios")
    label(ws, 18, "Gross margin", "%")
    fill_row(ws, 18, "={c}7/{c}5", FMT_PCT)
    label(ws, 19, "EBITDA margin", "%")
    fill_row(ws, 19, "={c}9/{c}5", FMT_PCT)
    label(ws, 20, "Internal check: net margin (hidden row)", "%")
    fill_row(ws, 20, "={c}15/{c}5", FMT_PCT)

    # LEGITIMATE L3: only the first forecast year uses the brought-forward tax losses
    ws["D14"] = "=-MAX(0,D13-Inputs!$C$30)*Inputs!D13"
    # PLANTED E1: FY2027 growth picks up the FY2026 assumption (wrong year)
    ws["F5"] = "=E5*(1+Inputs!E5)"
    # PLANTED E2: constant buried in one year's formula
    ws["G8"] = "=-G5*Inputs!G7*1.18"
    # PLANTED E14: hidden row containing formulas
    ws.row_dimensions[20].hidden = True


def build_bs(wb):
    ws = start_sheet(wb, "BS", "Balance Sheet")
    section_rows = {
        5: ("Cash", "=Inputs!$C$21", "=CF!{c}21"),
        6: ("Receivables", "=Inputs!$C$22", "=IS!{c}5*Inputs!{c}10/365"),
        7: ("Inventory", "=Inputs!$C$23", "=-IS!{c}6*Inputs!{c}11/365"),
        9: ("PP&E (net)", "=Inputs!$C$24", "={c}29"),
        12: ("Payables", "=Inputs!$C$25", "=-IS!{c}6*Inputs!{c}12/365"),
        # PLANTED E3: 5% hardcoded across the whole row instead of an assumption on Inputs
        13: ("Other current liabilities", "=Inputs!$C$26", "=IS!{c}5*0.05"),
        15: ("Debt", "=Inputs!$C$27", "={c}34"),
        18: ("Share capital", "=Inputs!$C$28", "={p}18"),
        19: ("Retained earnings", "=Inputs!$C$29", "={p}19+IS!{c}15"),
    }
    for row, (text, base, template) in section_rows.items():
        label(ws, row, text)
        put(ws, "C" + str(row), base)
        fill_row(ws, row, template)

    totals = {
        8: ("Total current assets", "=SUM({c}5:{c}7)"),
        10: ("Total assets", "={c}8+{c}9"),
        14: ("Total current liabilities", "=SUM({c}12:{c}13)"),
        16: ("Total liabilities", "={c}14+{c}15"),
        20: ("Total equity", "=SUM({c}18:{c}19)"),
        21: ("Total liabilities and equity", "={c}16+{c}20"),
        22: ("Balance check (should be zero)", "=ROUND({c}10-{c}21,2)"),
    }
    for row, (text, template) in totals.items():
        label(ws, row, text, bold=True)
        put(ws, "C" + str(row), template.format(c="C"), bold=True)
        fill_row(ws, row, template, bold=True)

    section(ws, 25, "PP&E schedule")
    label(ws, 26, "Opening PP&E")
    fill_row(ws, 26, "={p}29")
    label(ws, 27, "Capex")
    fill_row(ws, 27, "=IS!{c}5*Inputs!{c}9")
    label(ws, 28, "Depreciation")
    fill_row(ws, 28, "={c}26*Inputs!{c}8")
    label(ws, 29, "Closing PP&E", bold=True)
    fill_row(ws, 29, "={c}26+{c}27-{c}28", bold=True)

    section(ws, 31, "Debt schedule")
    label(ws, 32, "Opening debt")
    fill_row(ws, 32, "={p}34")
    label(ws, 33, "Repayment")
    fill_row(ws, 33, "=Inputs!{c}15")
    label(ws, 34, "Closing debt", bold=True)
    fill_row(ws, 34, "={c}32-{c}33", bold=True)

    # LEGITIMATE L1, L2: the first forecast year opens from the Inputs sheet
    ws["D26"] = "=Inputs!$C$24"
    ws["D32"] = "=Inputs!$C$27"
    # PLANTED E4: typed plug in a formula row
    ws["F7"] = 110
    ws["F7"].number_format = FMT_NUM
    # PLANTED E5: total picks up Inventory (row 7) instead of Total current assets (row 8)
    ws["G10"] = "=G7+G9"


def build_cf(wb):
    ws = start_sheet(wb, "CF", "Cash Flow Statement", base_label="")
    rows = {
        5: ("Net income", "=IS!{c}15", False),
        6: ("Add back: depreciation", "=BS!{c}28", False),
        7: ("(Increase)/decrease in receivables", "=BS!{p}6-BS!{c}6", False),
        8: ("(Increase)/decrease in inventory", "=BS!{p}7-BS!{c}7", False),
        9: ("Increase/(decrease) in payables", "=BS!{c}12-BS!{p}12", False),
        10: ("Increase/(decrease) in other liabilities", "=BS!{c}13-BS!{p}13", False),
        11: ("Cash flow from operations", "=SUM({c}5:{c}10)", True),
        13: ("Capex", "=-BS!{c}27", False),
        14: ("Cash flow from investing", "={c}13", True),
        16: ("Debt repayment", "=-BS!{c}33", False),
        17: ("Cash flow from financing", "={c}16", True),
        19: ("Net change in cash", "={c}11+{c}14+{c}17", True),
        20: ("Opening cash", "=BS!{p}5", False),
        21: ("Closing cash", "={c}20+{c}19", True),
    }
    for row, (text, template, bold) in rows.items():
        label(ws, row, text, bold=bold)
        fill_row(ws, row, template, bold=bold)

    section(ws, 23, "Memo")
    label(ws, 24, "Cash conversion (CFO / EBITDA)", "%")
    fill_row(ws, 24, "={c}11/IS!{c}9", FMT_PCT)
    # PLANTED E6: broken reference, kept on a memo line so it does not flow through the model
    ws["G24"] = "=G11/#REF!"


def build_dcf(wb):
    ws = start_sheet(wb, "DCF", "Discounted Cash Flow Valuation", extra_headers=["Terminal"])
    label(ws, 5, "Period", "no.")
    put(ws, "C5", 0, "0")
    fill_row(ws, 5, "={p}5+1", "0")
    label(ws, 6, "EBIT")
    fill_row(ws, 6, "=IS!{c}11")
    label(ws, 7, "Tax on EBIT")
    fill_row(ws, 7, "=-{c}6*Inputs!{c}13")
    label(ws, 8, "Add back: depreciation")
    fill_row(ws, 8, "=BS!{c}28")
    label(ws, 9, "Capex")
    fill_row(ws, 9, "=-BS!{c}27")
    label(ws, 10, "Change in working capital")
    fill_row(ws, 10, "=SUM(CF!{c}7:{c}10)")
    label(ws, 11, "Free cash flow (Terminal col = terminal value)", bold=True)
    fill_row(ws, 11, "=SUM({c}6:{c}10)", bold=True)
    label(ws, 12, "Discount factor", "x")
    fill_row(ws, 12, "=1/(1+WACC)^{c}5", FMT_FACTOR)
    label(ws, 13, "Present value", bold=True)
    fill_row(ws, 13, "={c}11*{c}12", bold=True)

    # LEGITIMATE L4, L5: the terminal column is a different calculation by design
    put(ws, "I11", "=H11*(1+Inputs!$C$19)/(WACC-Inputs!$C$19)", bold=True)
    put(ws, "I12", "=H12", FMT_FACTOR)
    put(ws, "I13", "=I11*I12", bold=True)

    section(ws, 15, "Valuation summary")
    label(ws, 16, "Sum of PV of free cash flows")
    # PLANTED E7: OFFSET where a plain SUM(D13:H13) would do
    put(ws, "C16", "=SUM(OFFSET(D13,0,0,1,5))")
    label(ws, 17, "PV of terminal value")
    put(ws, "C17", "=I13")
    label(ws, 18, "Enterprise value", bold=True)
    put(ws, "C18", "=C16+C17", bold=True)
    label(ws, 19, "Less: net debt at FY2024A")
    put(ws, "C19", "=-(BS!C15-BS!C5)")
    label(ws, 20, "Equity value", bold=True)
    put(ws, "C20", "=C18+C19", bold=True)
    label(ws, 21, "Value per share", "USD", bold=True)
    put(ws, "C21", "=C20/Inputs!$C$31", "0.00", bold=True)

    section(ws, 23, "Cross-checks and memo items")
    label(ws, 24, "Peer EV/EBITDA multiple (from comps file)", "x")
    # PLANTED E8: link to another workbook (see add_external_link)
    put(ws, "C24", "=[1]Multiples!$C$5", "0.0x")
    label(ws, 25, "Implied EV at peer multiple")
    put(ws, "C25", "=C24*IS!D9")
    label(ws, 26, "Valuation date", "date")
    # PLANTED E9: volatile function, the valuation date changes every day
    put(ws, "C26", "=TODAY()", "dd-mmm-yyyy")
    label(ws, 27, "Enterprise value per employee")
    # PLANTED E10: divides by Inputs!C33, which is zero, so this is #DIV/0! in Excel
    put(ws, "C27", "=C18/Inputs!$C$33")
    label(ws, 28, "Valuation commentary", "text")
    # PLANTED E11: overly long, deeply nested IF
    ws["C28"] = (
        '=IF(C21<=0,"Equity value is negative - review the model assumptions before relying on this output",'
        'IF(C21<5,"Very low value per share compared with the expected range - investigate",'
        'IF(C21<10,"Low value per share compared with the expected range",'
        'IF(C21<15,"Below the mid-point of the expected range",'
        'IF(C21<20,"Around the mid-point of the expected range",'
        'IF(C21<25,"Above the mid-point of the expected range",'
        'IF(C21<30,"High value per share compared with the expected range",'
        '"Very high value per share compared with the expected range - investigate")))))))'
    )


def build_hidden_sheet(wb):
    # PLANTED E12: hidden sheet left over from an earlier version
    ws = start_sheet(wb, "Old_Calcs", "Superseded calculations - do not use")
    label(ws, 5, "Revenue (old link)")
    fill_row(ws, 5, "=IS!{c}5")
    label(ws, 6, "EBITDA (old link)")
    fill_row(ws, 6, "=IS!{c}9")
    ws.sheet_state = "hidden"


def add_defined_names(wb):
    wb.defined_names["WACC"] = DefinedName("WACC", attr_text="Inputs!$C$18")
    # PLANTED E13: named range whose target was deleted
    wb.defined_names["Old_Tax_Rate"] = DefinedName("Old_Tax_Rate", attr_text="#REF!")


def add_external_link(wb):
    """Register the comps file the way Excel does, so DCF!C24 reads [1]Multiples!$C$5."""
    cached_multiple = ExternalRow(r=5, cell=[ExternalCell(r="C5", v="9.5")])
    book = ExternalBook(
        sheetNames=ExternalSheetNames(sheetName=["Multiples"]),
        sheetDataSet=ExternalSheetDataSet(
            sheetData=[ExternalSheetData(sheetId=0, row=[cached_multiple])]))
    book.id = "rId1"
    link = ExternalLink(externalBook=book)
    link.file_link = Relationship(type="externalLinkPath", Id="rId1",
                                  Target="Peer_Comps_2024.xlsx", TargetMode="External")
    wb._external_links.append(link)


def build_workbook():
    wb = Workbook()
    wb.remove(wb.active)
    build_inputs(wb)
    build_is(wb)
    build_bs(wb)
    build_cf(wb)
    build_dcf(wb)
    build_hidden_sheet(wb)
    add_defined_names(wb)
    add_external_link(wb)
    return wb


def main():
    folder = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(folder, OUTPUT_NAME)
    try:
        build_workbook().save(path)
    except PermissionError:
        print("Could not save " + OUTPUT_NAME + ". Close it in Excel and run this script again.")
        return
    except Exception as error:
        print("Could not create the demo model: " + str(error))
        return
    print("Created: " + path)
    print("Open and save it once in Excel if you want cached values (optional).")


if __name__ == "__main__":
    main()
