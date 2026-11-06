#!/usr/bin/env python3
"""Build data/golden_results.xlsx (Workbook step 1.5 / Build Guide Appendix B) with LIVE formulas.

Yellow cells = inputs. Every result is an Excel formula on the Population sheet (dummy_gl.csv).
After building, recalculate with LibreOffice headless (see recalc_and_check.py) so cached values exist.
"""
import csv, datetime as dt
from decimal import Decimal
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

HERE = Path(__file__).resolve().parent
YELLOW = PatternFill("solid", fgColor="FFFF00")
HEAD = PatternFill("solid", fgColor="1F3864")
HFONT = Font(bold=True, color="FFFFFF")
B = Font(bold=True)
NUM = '#,##0.00'
N = 3000
LAST = N + 1
rows = list(csv.DictReader(open(HERE / "dummy_gl.csv", encoding="utf-8")))
ak = list(csv.DictReader(open(HERE / "answer_key.csv", encoding="utf-8")))
fk = list(csv.DictReader(open(HERE / "feature_key.csv", encoding="utf-8")))
reg = {r["party_id"]: r for r in csv.DictReader(open(HERE / "supplier_register.csv", encoding="utf-8"))}
hol = list(csv.DictReader(open(HERE / "uae_holidays_2025.csv", encoding="utf-8")))
assert len(rows) == N

wb = Workbook()


def header(ws, r, labels, c0=1):
    for i, h in enumerate(labels):
        c = ws.cell(r, c0 + i, h)
        c.fill, c.font = HEAD, HFONT
        c.alignment = Alignment(wrap_text=True, vertical="top")


def inp(c, v, fmt=None):
    c.value = v
    c.fill = YELLOW
    if fmt:
        c.number_format = fmt


# ---------------------------------------------------------------- README
ws = wb.active
ws.title = "README"
txt = [
    "AuditSmart - golden_results.xlsx (Stage 1, Workbook step 1.5 / Build Guide Appendix B)",
    "Source data: data/dummy_gl.csv (synthetic, seed 2025, built by data/make_gl.py). NO CLIENT DATA.",
    "Yellow cells are inputs. Everything else is a live formula - change an input and the sheet recalculates.",
    "Methodology settings: firm_methodology_v0.2 Section 5 (DRAFT pending Assurance Partner approval):",
    "  TM 280,000; CF 3.00 (95%) / 2.31 (90%); expected misstatement 10% of TM; expansion factor 1.6 / 1.5;",
    "  n = ROUNDUP(Pop x CF / (TM - Expected x EF), 0); J = Pop / n; top stratum = items >= J.",
    "  NOTE: Workbook step 1.5 and Build Guide 3.2 use n = ROUNDUP(Pop x CF / TM) - shown as an info cell on each MUS sheet.",
    "Test population (assumption): account_type = 'Expense' and debit > 0 (column V on Population). Expense credits listed separately.",
    "Random start is left BLANK (Workbook): paste the engine's seeded start into the yellow cell; the selection table fills itself.",
    "Selection rule: first line whose cumulative value >= start + k x J  (COUNTIF(cum,\"<\"&point)+1 = XMATCH(point,cum,1)).",
    "Sheets: Population | MUS_95 | MUS_90 | Projection | Calendar | VAT | Input_VAT",
    "Input VAT sheet uses a TEST-ONLY effective date of 2025-10-01; Decisions 13/2026 and 17/2026 are effective 1 Oct 2026.",
    "Thresholds (375,000) and VAT tolerance (0.01) are placeholders until the Tax Partner signs the Rules Library.",
]
for i, t in enumerate(txt, 1):
    ws.cell(i, 1, t).font = B if i == 1 else Font()
ws.cell(15, 1, "Legend:"); inp(ws.cell(15, 2), "input")
ws.column_dimensions["A"].width = 130

# ---------------------------------------------------------------- Population
ws = wb.create_sheet("Population")
cols = list(rows[0].keys())
header(ws, 1, cols + ["test_pop_amount", "cumulative_pop"])
for i, r in enumerate(rows, 2):
    for j, c in enumerate(cols, 1):
        v = r[c]
        if c in ("entry_date", "posting_date"):
            v = dt.date.fromisoformat(v)
        elif c == "posting_time":
            v = dt.time.fromisoformat(v)
        elif c in ("debit", "credit") or (c in ("net_amount", "vat_amount") and v != ""):
            v = float(Decimal(v))
        elif v == "":
            v = None
        cell = ws.cell(i, j, v)
        if c in ("entry_date", "posting_date"):
            cell.number_format = "yyyy-mm-dd"
        elif c == "posting_time":
            cell.number_format = "hh:mm:ss"
        elif c in ("debit", "credit", "net_amount", "vat_amount"):
            cell.number_format = NUM
    ws.cell(i, 22, f'=IF(AND(H{i}="Expense",I{i}>0),I{i},0)').number_format = NUM
    ws.cell(i, 23, f"=V{i}" if i == 2 else f"=W{i-1}+V{i}").number_format = NUM
ws.freeze_panes = "B2"
for c, w in zip("ABCDEFGHIJKLMNOPQRSTUVW", [8, 11, 11, 9, 15, 8, 34, 10, 13, 13, 6, 48, 10, 8, 34, 17, 15, 12, 11, 6, 15, 14, 16]):
    ws.column_dimensions[c].width = w
S = LAST + 2   # summary block below the table (Workbook step 1.5)
summary = [
    ("Total debit", f"=SUM(I2:I{LAST})"),
    ("Total credit", f"=SUM(J2:J{LAST})"),
    ("Difference (must be 0)", f"=ROUND(B{S}-B{S+1},2)"),
    ("Line count", f"=COUNTA(A2:A{LAST})"),
    ("Test population: account_type = Expense, debit > 0", None),
    ("Test population value (SUMIFS)", f'=SUMIFS(I2:I{LAST},H2:H{LAST},"Expense",I2:I{LAST},">0")'),
    ("Test population line count", f'=COUNTIFS(H2:H{LAST},"Expense",I2:I{LAST},">0")'),
    ("Check: helper column V total = SUMIFS", f"=IF(ROUND(SUM(V2:V{LAST})-B{S+5},2)=0,\"OK\",\"CHECK\")"),
    ("Excluded expense CREDIT lines - count (listed, not sampled)", f'=COUNTIFS(H2:H{LAST},"Expense",J2:J{LAST},">0")'),
    ("Excluded expense CREDIT lines - value", f'=SUMIFS(J2:J{LAST},H2:H{LAST},"Expense",J2:J{LAST},">0")'),
]
for k, (lab, f) in enumerate(summary):
    ws.cell(S + k, 1, lab).font = B
    if f:
        ws.cell(S + k, 2, f).number_format = NUM if "count" not in lab.lower() else "0"
POPV = f"Population!$B${S+5}"
VRANGE = f"Population!$V$2:$V${LAST}"
WRANGE = f"Population!$W$2:$W${LAST}"


# ---------------------------------------------------------------- MUS sheets
def mus(name, level, cf, ef):
    ws = wb.create_sheet(name)
    ws["A1"] = f"Monetary Unit Sampling - {level} confidence (firm_methodology v0.2 Section 5)"
    ws["A1"].font = B
    items = [
        (3, "Population value (test population)", f"={POPV}", NUM, False),
        (4, "Tolerable misstatement (TM)", 280000, NUM, True),
        (5, "Confidence level", level, None, True),
        (6, "Confidence factor (CF, Poisson, nil errors)", cf, "0.00", True),
        (7, "Expected misstatement as % of TM", 0.10, "0%", True),
        (8, "Expected misstatement", "=B4*B7", NUM, False),
        (9, "Expansion factor (EF)", ef, "0.00", True),
        (10, "Expected misstatement check (<= 50% of TM)", '=IF(B8<=0.5*B4,"OK","Do not sample - expected misstatement > 50% of TM")', None, False),
        (11, "Sample size n = ROUNDUP(Pop x CF / (TM - Exp x EF), 0)", "=ROUNDUP(B3*B6/(B4-B8*B9),0)", "0", False),
        (12, "Sampling interval J = Pop / n", "=B3/B11", NUM, False),
        (13, "Basic precision = CF x J", "=B6*B12", NUM, False),
        (14, "Top-stratum items (>= J) - count", f'=COUNTIF({VRANGE},">="&B12)', "0", False),
        (15, "Top-stratum items (>= J) - value", f'=SUMIF({VRANGE},">="&B12)', NUM, False),
        (16, "Minimum sample check (n >= 5)", '=IF(B11>=5,"OK","Do not sample (n < 5)")', None, False),
        (17, "Random start in [0, J)  - LEFT BLANK, paste from engine", None, NUM, True),
        (18, "Seed (engine)", 2025, "0", True),
        (19, "Random start check", '=IF(B17="","(blank - enter engine start)",IF(AND(B17>=0,B17<B12),"OK","Start must be in [0, J)"))', None, False),
        (20, "Info: Workbook/Build Guide 3.2 formula n = ROUNDUP(Pop x CF / TM, 0)", "=ROUNDUP(B3*B6/B4,0)", "0", False),
        (21, "Selected lines (count of filled rows below)", '=COUNTIF(D25:D274,"L*")', "0", False),
    ]
    for r, lab, v, fmt, is_inp in items:
        ws.cell(r, 1, lab)
        c = ws.cell(r, 2)
        if is_inp:
            inp(c, v, fmt)
        else:
            c.value = v
            if fmt:
                c.number_format = fmt
    header(ws, 24, ["k", "Selection point = start + k x J", "Population row", "line_id", "Book value (debit)", "Top stratum?", "Cumulative at row"])
    for k in range(250):
        r = 25 + k
        ws.cell(r, 1, k)
        ws.cell(r, 2, f'=IF(OR($B$17="",A{r}>=$B$11),"",$B$17+A{r}*$B$12)').number_format = NUM
        ws.cell(r, 3, f'=IF(B{r}="","",COUNTIF({WRANGE},"<"&B{r})+1)')
        ws.cell(r, 4, f'=IF(C{r}="","",INDEX(Population!$A$2:$A${LAST},C{r}))')
        ws.cell(r, 5, f'=IF(C{r}="","",INDEX({VRANGE},C{r}))').number_format = NUM
        ws.cell(r, 6, f'=IF(C{r}="","",IF(E{r}>=$B$12,"Yes","No"))')
        ws.cell(r, 7, f'=IF(C{r}="","",INDEX({WRANGE},C{r}))').number_format = NUM
    ws.column_dimensions["A"].width = 62
    for c in "BCDEFG":
        ws.column_dimensions[c].width = 18
    ws.freeze_panes = "A25"


mus("MUS_95", "95%", 3.00, 1.6)
mus("MUS_90", "90%", 2.31, 1.5)

# ---------------------------------------------------------------- Projection
top_id = next(f["line_id"] for f in fk if f["feature"] == "top_stratum")
cand = [r for r in rows if r["account_type"] == "Expense" and 30000 < float(r["debit"]) < 60000 and r["account_code"] == "5010"]
item2, item3 = cand[0], cand[1]
top_row = next(r for r in rows if r["line_id"] == top_id)
proj_items = [(top_id, round(float(top_row["debit"]) - 12500.00, 2), "top stratum - actual misstatement 12,500.00"),
              (item2["line_id"], round(float(item2["debit"]) * 0.90, 2), "10% tainting"),
              (item3["line_id"], round(float(item3["debit"]) * 0.75, 2), "25% tainting")]
ws = wb.create_sheet("Projection")
ws["A1"] = "Projection and evaluation (ISA 450 / ISA 530) - 3 misstatements, one in the top stratum"; ws["A1"].font = B
ws["A2"] = "Items < J: tainting = misstatement / book; projected = tainting x J. Top stratum: actual. IA = projected (items < J, ranked desc) x (factor - 1). UML = BP + sum projected + IA."
header(ws, 4, ["Rank", "95% factor", "90% factor"], c0=14)
for i, (f95, f90) in enumerate(zip([1.75, 1.55, 1.46, 1.40, 1.36], [1.58, 1.44, 1.36, 1.31, 1.28])):
    ws.cell(5 + i, 14, i + 1)
    inp(ws.cell(5 + i, 15), f95, "0.00")
    inp(ws.cell(5 + i, 16), f90, "0.00")
for blk, (sheet, fcol, r0) in enumerate([("MUS_95", "O", 4), ("MUS_90", "P", 20)]):
    ws.cell(r0, 1, f"{sheet[-2:]}% confidence").font = B
    ws.cell(r0 + 1, 1, "Sampling interval J"); ws.cell(r0 + 1, 2, f"={sheet}!B12").number_format = NUM
    ws.cell(r0 + 2, 1, "Confidence factor"); ws.cell(r0 + 2, 2, f"={sheet}!B6").number_format = "0.00"
    ws.cell(r0 + 3, 1, "Tolerable misstatement"); ws.cell(r0 + 3, 2, f"={sheet}!B4").number_format = NUM
    hr = r0 + 5
    header(ws, hr, ["Item", "line_id (input)", "Book value", "Audited value (input)", "Misstatement", "Top stratum?",
                    "Tainting", "Projected", "Rank (< J)", "Incremental factor", "Incremental allowance", "Note"])
    for k, (lid, aud, note) in enumerate(proj_items):
        r = hr + 1 + k
        ws.cell(r, 1, k + 1)
        inp(ws.cell(r, 2), lid)
        ws.cell(r, 3, f"=INDEX(Population!$I$2:$I${LAST},MATCH(B{r},Population!$A$2:$A${LAST},0))").number_format = NUM
        inp(ws.cell(r, 4), aud, NUM)
        ws.cell(r, 5, f"=C{r}-D{r}").number_format = NUM
        ws.cell(r, 6, f'=IF(C{r}>=$B${r0+1},"Yes","No")')
        ws.cell(r, 7, f'=IF(F{r}="Yes","",E{r}/C{r})').number_format = "0.00%"
        ws.cell(r, 8, f'=IF(F{r}="Yes",E{r},G{r}*$B${r0+1})').number_format = NUM
        rng_f, rng_h = f"$F${hr+1}:$F${hr+3}", f"$H${hr+1}:$H${hr+3}"
        ws.cell(r, 9, f'=IF(F{r}="Yes","",COUNTIFS({rng_f},"No",{rng_h},">"&H{r})+1)')
        ws.cell(r, 10, f'=IF(I{r}="","",INDEX(${fcol}$5:${fcol}$9,I{r}))').number_format = "0.00"
        ws.cell(r, 11, f'=IF(I{r}="","",H{r}*(J{r}-1))').number_format = NUM
        ws.cell(r, 12, note)
    t = hr + 5
    res = [("Basic precision (CF x J)", f"=B{r0+2}*B{r0+1}"),
           ("Sum of projected misstatements (incl. top-stratum actual)", f"=SUM(H{hr+1}:H{hr+3})"),
           ("Incremental allowance", f"=SUM(K{hr+1}:K{hr+3})"),
           ("Upper misstatement limit (UML)", f"=B{t}+B{t+1}+B{t+2}"),
           ("Tolerable misstatement", f"=B{r0+3}"),
           ("Conclusion", f'=IF(B{t+3}<=B{t+4},"Acceptable","Exceeds - further work")')]
    for k, (lab, f) in enumerate(res):
        ws.cell(t + k, 1, lab).font = B
        ws.cell(t + k, 2, f).number_format = NUM
ws.column_dimensions["A"].width = 52
for c in "BCDEFGHIJKL":
    ws.column_dimensions[c].width = 15
ws.column_dimensions["L"].width = 40

# ---------------------------------------------------------------- Calendar
ws = wb.create_sheet("Calendar")
ws["A1"] = "Working-calendar tests - expected results typed by hand (yellow), formula cross-check alongside"; ws["A1"].font = B
ws["A2"] = ("P1 = Friday only off | P2 = Sat/Sun off + Friday half day to 12:00 | P3 = Fri, Sat and Sun off | "
            "P4 = dated profile: Fri/Sat off to 31-Dec-2021, Sat/Sun off from 1-Jan-2022 (no half day). 2025 holidays apply to all.")
inp(ws["B3"], dt.time(12, 0), "hh:mm"); ws["A3"] = "Half-day cut-off (P2)"
inp(ws["D3"], dt.date(2022, 1, 1), "yyyy-mm-dd"); ws["C3"] = "Weekend change date (P4)"
hdr = ["Date", "Time", "Weekday", "Holiday", "Expected P1", "Expected P2", "Expected P3", "Expected P4",
       "Formula P1", "Formula P2", "Formula P3", "Formula P4", "All match?"]
header(ws, 5, hdr)
W, NW, NWH = "Working", "Non-working", "Non-working (after half-day cut-off)"
cases = [
    (dt.date(2025, 1, 6), dt.time(10, 0), W, W, W, W),
    (dt.date(2025, 1, 9), dt.time(16, 30), W, W, W, W),
    (dt.date(2025, 1, 10), dt.time(10, 30), NW, W, NW, W),
    (dt.date(2025, 1, 10), dt.time(15, 30), NW, NWH, NW, W),
    (dt.date(2025, 1, 11), dt.time(11, 0), W, NW, NW, NW),
    (dt.date(2025, 1, 12), dt.time(9, 0), W, NW, NW, NW),
    (dt.date(2025, 3, 31), dt.time(10, 0), NW, NW, NW, NW),
    (dt.date(2025, 12, 3), dt.time(10, 0), W, W, W, W),
    (dt.date(2021, 12, 30), dt.time(10, 0), W, W, W, W),
    (dt.date(2021, 12, 31), dt.time(10, 0), NW, W, NW, NW),
    (dt.date(2022, 1, 2), dt.time(10, 0), W, NW, NW, NW),
    (dt.date(2022, 1, 7), dt.time(10, 0), NW, W, NW, W),
]
header(ws, 5, ["Holiday date", "Name"], c0=16)
for i, h in enumerate(hol):
    ws.cell(6 + i, 16, dt.date.fromisoformat(h["date"])).number_format = "yyyy-mm-dd"
    ws.cell(6 + i, 17, h["name"])
HR = f"$P$6:$Q${5 + len(hol)}"
for k, (d, t, *exp) in enumerate(cases):
    r = 6 + k
    ws.cell(r, 1, d).number_format = "yyyy-mm-dd"
    ws.cell(r, 2, t).number_format = "hh:mm"
    ws.cell(r, 3, f'=TEXT(A{r},"dddd")')
    ws.cell(r, 4, f'=IFERROR(VLOOKUP(A{r},{HR},2,FALSE),"")')
    for j, e in enumerate(exp):
        inp(ws.cell(r, 5 + j), e)
    wd = f"WEEKDAY(A{r},2)"
    ws.cell(r, 9, f'=IF(D{r}<>"","{NW}",IF({wd}=5,"{NW}","{W}"))')
    ws.cell(r, 10, f'=IF(D{r}<>"","{NW}",IF({wd}>=6,"{NW}",IF(AND({wd}=5,B{r}>$B$3),"{NWH}","{W}")))')
    ws.cell(r, 11, f'=IF(D{r}<>"","{NW}",IF({wd}>=5,"{NW}","{W}"))')
    ws.cell(r, 12, f'=IF(D{r}<>"","{NW}",IF(A{r}<$D$3,IF(OR({wd}=5,{wd}=6),"{NW}","{W}"),IF({wd}>=6,"{NW}","{W}")))')
    ws.cell(r, 13, f'=IF(AND(E{r}=I{r},F{r}=J{r},G{r}=K{r},H{r}=L{r}),"Yes","NO")')
ws.cell(19, 1, "All 12 cases match").font = B
ws.cell(19, 2, '=IF(COUNTIF(M6:M17,"Yes")=12,"OK","CHECK")')
ws.cell(20, 1, "Note: 2025-12-03 is a working day (National Day holiday moved to 1-2 Dec 2025 by MoHRE). 2021/22 holidays are not in this list; the test dates avoid them.")
for c, w in zip("ABCDEFGHIJKLMPQ", [12, 8, 11, 22, 14, 22, 14, 14, 14, 22, 14, 14, 10, 12, 30]):
    ws.column_dimensions[c].width = w

# ---------------------------------------------------------------- VAT
ws = wb.create_sheet("VAT")
ws["A1"] = "Output VAT recalculation - the 12 planted lines (answer_key.csv) + population-wide checks"; ws["A1"].font = B
ws["A2"] = "VAT rate"; inp(ws["B2"], 0.05, "0%")
ws["A3"] = "Tolerance (AED) - placeholder, Rules Library"; inp(ws["B3"], 0.01, NUM)
header(ws, 5, ["line_id (input)", "Invoice", "Net amount", "VAT code", "Recorded VAT", "Expected VAT = ROUND(net x rate, 2)",
               "Difference = recorded - expected", "Result", "Planted description"])
vat_lines = [r for r in ak if r["file"] == "dummy_gl.csv" and r["error_type"] == "output_vat_error"]
MA = f"MATCH(A{{r}},Population!$A$2:$A${LAST},0)"
for k, a in enumerate(vat_lines):
    r = 6 + k
    inp(ws.cell(r, 1), a["line_id"])
    m = MA.format(r=r)
    ws.cell(r, 2, f"=INDEX(Population!$Q$2:$Q${LAST},{m})")
    ws.cell(r, 3, f"=INDEX(Population!$R$2:$R${LAST},{m})").number_format = NUM
    ws.cell(r, 4, f"=INDEX(Population!$T$2:$T${LAST},{m})")
    ws.cell(r, 5, f"=INDEX(Population!$S$2:$S${LAST},{m})").number_format = NUM
    ws.cell(r, 6, f'=IF(D{r}="SR",ROUND(C{r}*$B$2,2),0)').number_format = NUM
    ws.cell(r, 7, f"=E{r}-F{r}").number_format = NUM
    ws.cell(r, 8, f'=IF(ABS(G{r})>$B$3,"Exception","OK")')
    ws.cell(r, 9, a["description"])
t = 6 + len(vat_lines) + 1
ws.cell(t, 1, "Exceptions in table").font = B
ws.cell(t, 2, f'=COUNTIF(H6:H{t-2},"Exception")')
P = lambda c: f"Population!${c}$2:${c}${LAST}"
ws.cell(t + 1, 1, "Population-wide: Revenue SR lines with |VAT difference| > tolerance (expect 12)").font = B
ws.cell(t + 1, 2, f'=SUMPRODUCT(({P("H")}="Revenue")*({P("T")}="SR")*(ABS({P("S")}-ROUND({P("R")}*$B$2,2))>$B$3))')
ws.cell(t + 2, 1, "Population-wide: input-side SR/RC lines with |VAT difference| > tolerance (expect 0)").font = B
ws.cell(t + 2, 2, f'=SUMPRODUCT(({P("H")}<>"Revenue")*((({P("T")}="SR")+({P("T")}="RC"))>0)*(ABS({P("S")}-ROUND({P("R")}*$B$2,2))>$B$3))')
tr = t + 4
ws.cell(tr, 1, "TRN validation - 15 digits starting with 100 (rule from brief; Tax Partner to confirm)").font = B
header(ws, tr + 1, ["line_id (input)", "TRN", "Length", "First 3", "All digits?", "Valid?", "Planted description"])
trn_lines = [r for r in ak if r["file"] == "dummy_gl.csv" and r["error_type"] == "invalid_trn"]
valid_ctrl = next(r["line_id"] for r in rows if r["trn"].startswith("100") and len(r["trn"]) == 15)
for k, a in enumerate(trn_lines + [{"line_id": valid_ctrl, "description": "control - valid TRN"}]):
    r = tr + 2 + k
    inp(ws.cell(r, 1), a["line_id"])
    m = MA.format(r=r)
    ws.cell(r, 2, f'=INDEX(Population!$P$2:$P${LAST},{m})&""')
    ws.cell(r, 3, f"=LEN(B{r})")
    ws.cell(r, 4, f"=LEFT(B{r},3)")
    ws.cell(r, 5, f'=IF(LEN(B{r})=0,FALSE,SUMPRODUCT(--ISNUMBER(--MID(B{r},ROW($A$1:$A$20),1))*(ROW($A$1:$A$20)<=LEN(B{r})))=LEN(B{r}))')
    ws.cell(r, 6, f'=IF(AND(C{r}=15,D{r}="100",E{r}),"Valid","INVALID")')
    ws.cell(r, 7, a["description"])
z = tr + 2 + len(trn_lines) + 2
ws.cell(z, 1, "Invalid TRNs in table (expect 5)").font = B
ws.cell(z, 2, f'=COUNTIF(F{tr+2}:F{z-2},"INVALID")')
ws.cell(z + 1, 1, "Population-wide: non-blank TRNs failing length/prefix (expect 5; the 'letter I' case fails prefix)").font = B
ws.cell(z + 1, 2, f'=SUMPRODUCT((LEN({P("P")})>0)*(((LEN({P("P")})<>15)+(LEFT({P("P")},3)<>"100"))>0))')
ws.column_dimensions["A"].width = 60
for c in "BCDEFGH":
    ws.column_dimensions[c].width = 18
ws.column_dimensions["I"].width = 70

# ---------------------------------------------------------------- Input VAT
ws = wb.create_sheet("Input_VAT")
ws["A1"] = "Input VAT - Decision 13/2026 (supplier verification, spend threshold) and Decision 17/2026 (employee expenses) TEST data"; ws["A1"].font = B
ws["A2"] = "Effective date (TEST ONLY - real decisions effective 2026-10-01)"; inp(ws["B2"], dt.date(2025, 10, 1), "yyyy-mm-dd")
ws["A3"] = "Rolling 12-month spend threshold (AED, prompt 1.1 - Tax Partner to verify)"; inp(ws["B3"], 375000, NUM)
header(ws, 5, ["Unverified supplier (input)", "Name", "verified_on (register)", "Lines with input VAT on/after effective date",
               "Input VAT on those lines", "Flag"])
unv = sorted({r["party_id"] for r in rows for a in ak if a["error_type"] == "input_vat_unverified_supplier" and a["line_id"] == r["line_id"]})
for k, pid in enumerate(unv):
    r = 6 + k
    inp(ws.cell(r, 1), pid)
    ws.cell(r, 2, reg[pid]["party_name"])
    inp(ws.cell(r, 3), reg[pid]["verified_on"] or None)
    ws.cell(r, 4, f'=COUNTIFS({P("N")},A{r},{P("C")},">="&$B$2,{P("S")},">0")')
    ws.cell(r, 5, f'=SUMIFS({P("S")},{P("N")},A{r},{P("C")},">="&$B$2,{P("S")},">0")').number_format = NUM
    ws.cell(r, 6, f'=IF(AND(C{r}="",D{r}>0),"Flag - no verification","OK")')
ws.cell(10, 1, "Total flagged lines (expect 15)").font = B
ws.cell(10, 4, "=SUM(D6:D8)")
header(ws, 12, ["Threshold supplier (input)", "Name", "Gross purchases FY2025 (net + VAT, invoices only)", "Exceeds threshold?",
                "bank_evidence_ref (register)", "Flag", "Crossing line (answer key)"])
thr = [a for a in ak if a["error_type"] == "input_vat_spend_threshold"]
for k, a in enumerate(thr):
    r = 13 + k
    pid = next(x["party_id"] for x in rows if x["line_id"] == a["line_id"])
    inp(ws.cell(r, 1), pid)
    ws.cell(r, 2, reg[pid]["party_name"])
    ws.cell(r, 3, f'=SUMIFS({P("R")},{P("N")},A{r},{P("R")},">0",{P("S")},">0")+SUMIFS({P("S")},{P("N")},A{r},{P("R")},">0",{P("S")},">0")').number_format = NUM
    ws.cell(r, 4, f'=IF(C{r}>$B$3,"Yes","No")')
    inp(ws.cell(r, 5), reg[pid]["bank_evidence_ref"] or None)
    ws.cell(r, 6, f'=IF(AND(D{r}="Yes",E{r}=""),"Flag - bank evidence required","OK")')
    ws.cell(r, 7, a["line_id"])
header(ws, 18, ["Employee expense category (Decision 17 test)", "Lines", "Input VAT recovered", "", "", "", ""])
cats = ["transport", "food_beverages", "accommodation", "mobile_internet", "parking"]
for k, c in enumerate(cats):
    r = 19 + k
    ws.cell(r, 1, c)
    ws.cell(r, 2, f'=COUNTIF({P("U")},A{r})')
    ws.cell(r, 3, f'=SUMIFS({P("S")},{P("U")},A{r})').number_format = NUM
ws.cell(24, 1, "Total employee-expense lines (expect 20)").font = B
ws.cell(24, 2, "=SUM(B19:B23)")
ws.cell(25, 1, "Decision 17 lists 6 categories; 'temporary accommodation for new employees' has no planted line (prompt 1.1 lists 5).")
ws.column_dimensions["A"].width = 62
for c in "BCDEFG":
    ws.column_dimensions[c].width = 22

wb.save(HERE / "golden_results.xlsx")
print("saved", HERE / "golden_results.xlsx", "projection items:", proj_items)
