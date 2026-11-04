#!/usr/bin/env python3
"""Recalculate golden_results.xlsx with LibreOffice headless, then verify: no formula errors, cached values present,
and key results equal an independent Python (Decimal) calculation."""
import csv, math, shutil, subprocess, sys, tempfile
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from openpyxl import load_workbook

HERE = Path(__file__).resolve().parent
SRC = HERE / "golden_results.xlsx"
tmp = Path(tempfile.mkdtemp())
subprocess.run(["/usr/bin/soffice", "--headless", "--calc", "--convert-to", "xlsx:Calc MS Excel 2007 XML",
                "--outdir", str(tmp), str(SRC)], check=True, capture_output=True, timeout=300)
shutil.copy(tmp / SRC.name, SRC)

wf = load_workbook(SRC)                     # formulas
wv = load_workbook(SRC, data_only=True)     # cached values
fails = []
nform = nmiss = 0
for ws in wf.worksheets:
    vs = wv[ws.title]
    for row in ws.iter_rows():
        for c in row:
            if isinstance(c.value, str) and c.value.startswith("="):
                nform += 1
                v = vs[c.coordinate].value
                if v is None:
                    nmiss += 1
                elif isinstance(v, str) and (v.startswith("#") or v.startswith("Err:")):
                    fails.append(f"{ws.title}!{c.coordinate} = {v}")
print(f"formulas: {nform}; with no cached value (blank results such as empty selection rows count here): {nmiss}; errors: {len(fails)}")
for f in fails[:20]:
    print("  ERROR", f)

rows = list(csv.DictReader(open(HERE / "dummy_gl.csv")))
pop = [Decimal(r["debit"]) for r in rows if r["account_type"] == "Expense" and Decimal(r["debit"]) > 0]
P = sum(pop)
V = lambda s, a: wv[s][a].value
ok = True
def eq(label, got, exp, tol=0.005):
    global ok
    good = got is not None and abs(float(got) - float(exp)) <= tol
    ok &= good
    print(("PASS " if good else "FAIL ") + f"{label}: workbook {got} | python {exp}")

pv = wv["Population"]
eq("Population total Dr - Cr", pv["B3005"].value, 0)
eq("Population test value", pv["B3008"].value, P)
for s, cf, ef, facs in [("MUS_95", Decimal("3.00"), Decimal("1.6"), [Decimal("1.75"), Decimal("1.55")]),
                        ("MUS_90", Decimal("2.31"), Decimal("1.5"), [Decimal("1.58"), Decimal("1.44")])]:
    TM = Decimal(280000); EXP = TM / 10
    n = math.ceil(P * cf / (TM - EXP * ef)); J = P / n
    top = sum(1 for a in pop if a >= J)
    eq(f"{s} n", V(s, "B11"), n); eq(f"{s} J", V(s, "B12"), J, 0.01); eq(f"{s} top-stratum count", V(s, "B14"), top)
    eq(f"{s} basic precision", V(s, "B13"), cf * J, 0.01)
    # projection
    pr = wv["Projection"]
    r0 = 4 if s == "MUS_95" else 20
    items = []
    for k in range(3):
        r = r0 + 6 + k
        book, aud = Decimal(str(pr.cell(r, 3).value)), Decimal(str(pr.cell(r, 4).value))
        items.append((book, book - aud))
    proj = [(m if b >= J else (m / b) * J, b >= J) for b, m in items]
    small = sorted([p for p, t in proj if not t], reverse=True)
    ia = sum(p * (f - 1) for p, f in zip(small, facs))
    uml = cf * J + sum(p for p, _ in proj) + ia
    t = r0 + 10
    eq(f"{s} sum projected", pr.cell(t + 1, 2).value, sum(p for p, _ in proj), 0.01)
    eq(f"{s} incremental allowance", pr.cell(t + 2, 2).value, ia, 0.01)
    eq(f"{s} UML", pr.cell(t + 3, 2).value, uml, 0.01)
    print(f"     {s}: conclusion = {pr.cell(t + 5, 2).value}")
cal = wv["Calendar"]
print("Calendar all-match:", cal["B19"].value); ok &= cal["B19"].value == "OK"
vt = wv["VAT"]
for r in range(1, 60):
    if isinstance(vt.cell(r, 1).value, str) and vt.cell(r, 1).value.startswith(("Exceptions", "Population-wide", "Invalid TRNs")):
        print(f"VAT: {vt.cell(r,1).value} -> {vt.cell(r,2).value}")
iv = wv["Input_VAT"]
print("Input VAT: unverified flagged lines", iv["D10"].value, "| threshold flags", [iv.cell(r, 6).value for r in (13, 14, 15)],
      "| gross", [round(iv.cell(r, 3).value, 2) for r in (13, 14, 15)], "| employee lines", iv["B24"].value)
ok &= iv["D10"].value == 15 and iv["B24"].value == 20
sys.exit(0 if ok and not fails else 1)
