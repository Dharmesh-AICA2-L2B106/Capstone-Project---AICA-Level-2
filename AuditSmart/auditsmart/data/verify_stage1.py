#!/usr/bin/env python3
"""Independent checker for the Stage 1 data set.

Re-detects every planted error with simple, independent rules and asserts the detected set equals
answer_key.csv EXACTLY (so the background is clean and every planted line triggers only its own test).
Run:  python verify_stage1.py   (exit code 1 on any failure)
"""
import csv, datetime as dt, math, re, sys
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from pathlib import Path

HERE = Path(__file__).resolve().parent
Q = Decimal("0.01")
fails = []


def read(name):
    with open(HERE / name, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def check(label, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + label + (f"  [{detail}]" if detail else ""))
    if not cond:
        fails.append(label)


gl = read("dummy_gl.csv")
ak = read("answer_key.csv")
fk = read("feature_key.csv")
hol = {dt.date.fromisoformat(r["date"]): r["name"] for r in read("uae_holidays_2025.csv")}
reg = {r["party_id"]: r for r in read("supplier_register.csv")}
key = defaultdict(set)
for r in ak:
    if r["file"] == "dummy_gl.csv":
        key[r["error_type"]].add(r["line_id"])

for r in gl:
    r["d"] = dt.date.fromisoformat(r["posting_date"])
    r["t"] = dt.time.fromisoformat(r["posting_time"])
    r["dr"], r["cr"] = Decimal(r["debit"]), Decimal(r["credit"])
    r["amt"] = r["dr"] or r["cr"]

check("dummy_gl has 3,000 lines", len(gl) == 3000, len(gl))
check("columns exactly as prompt 1.1", list(gl[0].keys())[:21] == ["line_id", "entry_date", "posting_date", "posting_time",
      "voucher_no", "account_code", "account_name", "account_type", "debit", "credit", "currency", "narration", "user_id",
      "party_id", "party_name", "trn", "invoice_no", "net_amount", "vat_amount", "vat_code", "expense_category"])
check("line_ids unique", len({r["line_id"] for r in gl}) == 3000)
tdr, tcr = sum(r["dr"] for r in gl), sum(r["cr"] for r in gl)
check("total Dr = total Cr", tdr == tcr, f"Dr {tdr:,.2f} Cr {tcr:,.2f}")
bal = defaultdict(Decimal)
for r in gl:
    bal[r["voucher_no"]] += r["dr"] - r["cr"]
check("every voucher balances", all(v == 0 for v in bal.values()), f"{len(bal)} vouchers")
check("every line one-sided and non-zero", all((r["dr"] > 0) != (r["cr"] > 0) for r in gl))
check("all dates within FY2025", all(r["d"].year == 2025 for r in gl))

def ids(pred):
    return {r["line_id"] for r in gl if pred(r)}

def same(label, detected, etype):
    exp = key[etype]
    check(f"{label}: detected {len(detected)} == answer key {len(exp)}", detected == exp,
          f"missing {sorted(exp - detected)[:5]} extra {sorted(detected - exp)[:5]}")

same("weekend Sat/Sun", ids(lambda r: r["d"].weekday() >= 5 and r["d"] not in hol), "weekend_posting")
same("Friday after 12:00 cut-off", ids(lambda r: r["d"].weekday() == 4 and r["d"] not in hol and r["t"] > dt.time(12)), "friday_after_cutoff")
check("all Friday-cut-off lines are after 15:00", all(r["t"] >= dt.time(15) for r in gl if r["line_id"] in key["friday_after_cutoff"]))
same("public holiday", ids(lambda r: r["d"] in hol), "public_holiday_posting")
same("round sum (multiple of 1,000 and >= 10,000)", ids(lambda r: r["amt"] >= 10000 and r["amt"] % 1000 == 0), "round_sum")
check("round sums are multiples of 10,000", all(r["amt"] % 10000 == 0 for r in gl if r["line_id"] in key["round_sum"]))
same("period end +/-5 days (26-31 Dec, 1-5 Jan)", ids(lambda r: r["d"] >= dt.date(2025, 12, 26) or r["d"] <= dt.date(2025, 1, 5)), "period_end_finmgr")
check("period-end lines: FINMGR within 3 days", all(r["user_id"] == "FINMGR" and r["d"] >= dt.date(2025, 12, 29) for r in gl if r["line_id"] in key["period_end_finmgr"]))
VAGUE = re.compile(r"\b(adj|misc|correction|reversal|error|as per md)", re.I)
same("vague / blank narration", ids(lambda r: r["narration"].strip() == "" or VAGUE.search(r["narration"])), "vague_narration")
check("no narration contains a vague keyword substring outside planted",
      not ids(lambda r: re.search(r"adj|misc|correct|reversal|error", r["narration"], re.I)) - key["vague_narration"])
prim = [r for r in gl if r["invoice_no"]]
seen, dups = {}, set()
for r in sorted(prim, key=lambda r: (r["d"], r["t"], r["line_id"])):
    k = (r["invoice_no"], r["party_id"])
    if k in seen:
        dups.add(r["line_id"])
    seen[k] = r["line_id"]
same("duplicate invoice (same invoice + party)", dups, "duplicate_invoice")
pad = Counter((r["party_id"], r["amt"], r["d"]) for r in prim)
check("no same party + amount + date duplicates", all(c == 1 for c in pad.values()))

def exp_vat(net, code):
    return (net * Decimal("0.05")).quantize(Q, ROUND_HALF_UP) if code in ("SR", "RC") else Decimal("0")
vat_bad = ids(lambda r: r["vat_code"] and r["account_type"] == "Revenue" and
              abs(Decimal(r["vat_amount"]) - exp_vat(Decimal(r["net_amount"]), r["vat_code"])) > Decimal("0.01"))
same("output VAT (revenue lines, tolerance 0.01)", vat_bad, "output_vat_error")
inp_bad = ids(lambda r: r["vat_code"] and r["account_type"] != "Revenue" and
              abs(Decimal(r["vat_amount"]) - exp_vat(Decimal(r["net_amount"]), r["vat_code"])) > Decimal("0.01"))
check("input-side VAT all correct", not inp_bad, len(inp_bad))
TRN = re.compile(r"^100\d{12}$")
same("invalid TRN (non-blank, not 15 digits starting 100)", ids(lambda r: r["trn"] and not TRN.match(r["trn"])), "invalid_trn")
check("TRN blank only for ZR export / RC overseas lines", all(r["vat_code"] in ("ZR", "RC") for r in prim if not r["trn"]))
# input VAT: purchases (input tax claimed) on/after the TEST effective date from suppliers lacking verified_on
purch = [r for r in prim if r["account_type"] in ("Expense", "Asset") and Decimal(r["vat_amount"] or 0) > 0]
same("input VAT unverified supplier (>= 2025-10-01)", {r["line_id"] for r in purch if r["d"] >= dt.date(2025, 10, 1)
     and not reg.get(r["party_id"], {}).get("verified_on")}, "input_vat_unverified_supplier")
check("all purchase parties in supplier register", all(r["party_id"] in reg for r in purch))
cum, cross = defaultdict(Decimal), set()
for r in sorted(purch, key=lambda r: (r["d"], r["t"], r["line_id"])):
    before = cum[r["party_id"]]
    cum[r["party_id"]] += Decimal(r["net_amount"]) + Decimal(r["vat_amount"])
    if before <= 375000 < cum[r["party_id"]]:
        cross.add(r["line_id"])
same("rolling 12-month spend crosses 375,000", cross, "input_vat_spend_threshold")
check("threshold suppliers lack bank evidence", all(not reg[r["party_id"]]["bank_evidence_ref"] for r in gl if r["line_id"] in cross))
check("threshold crossings after 2025-10-01", all(r["d"] >= dt.date(2025, 10, 1) for r in gl if r["line_id"] in cross))
same("employee expense (expense_category set)", ids(lambda r: r["expense_category"]), "employee_expense")
check("employee categories 4 each x 5", sorted(Counter(r["expense_category"] for r in gl if r["expense_category"]).values()) == [4] * 5)
check("one error type per line", max(Counter(r["line_id"] for r in ak if r["file"] == "dummy_gl.csv").values()) == 1)

# population / features
pop = [r for r in gl if r["account_type"] == "Expense" and r["dr"] > 0]
P = sum(r["dr"] for r in pop)
res = {}
for lab, cf, ef in [("95", Decimal("3.00"), Decimal("1.6")), ("90", Decimal("2.31"), Decimal("1.5"))]:
    tm = Decimal(280000); exp = tm * Decimal("0.10")
    n = math.ceil(P * cf / (tm - exp * ef)); J = P / n
    top = [r for r in pop if r["dr"] >= J]
    res[lab] = (n, J, len(top))
    print(f"     MUS {lab}%: Pop {P:,.2f} n={n} J={J:,.2f} top-stratum={len(top)}")
    check(f"top stratum at {lab}% = 8 planted", {r["line_id"] for r in top} == {f["line_id"] for f in fk if f["feature"] == "top_stratum"})
cn = {f["line_id"] for f in fk if f["feature"] == "credit_note"}
check("40 credit-note lines", len(cn) == 40)
check("expense credit lines = 20 purchase CNs", len(ids(lambda r: r["account_type"] == "Expense" and r["cr"] > 0)) == 20)
check("no line >= PM 280,000", max(r["amt"] for r in gl) < 280000, f"max {max(r['amt'] for r in gl):,.2f}")
vch_users = Counter()
for v in {(r["voucher_no"], r["user_id"]) for r in gl}:
    vch_users[v[1]] += 1
tot = sum(vch_users.values())
check("every user >= 1% of vouchers", min(vch_users.values()) / tot >= 0.01, {u: f"{c/tot:.1%}" for u, c in vch_users.items()})
pairs = Counter()
byv = defaultdict(list)
for r in gl:
    byv[r["voucher_no"]].append(r)
for v, ls in byv.items():
    for a in {x["account_code"] for x in ls if x["dr"] > 0}:
        for b in {x["account_code"] for x in ls if x["cr"] > 0}:
            pairs[(a, b)] += 1
check("every Dr/Cr account pair used >= 3 times", min(pairs.values()) >= 3, f"min {min(pairs.values())}, pairs {len(pairs)}")
amts = [r["amt"] for r in gl if r["amt"] >= 10]
fd = Counter(int(str(a).lstrip("0.")[0]) for a in amts)
mad = sum(abs(fd[d] / len(amts) - math.log10(1 + 1 / d)) for d in range(1, 10)) / 9
print(f"     Benford first-digit MAD (all lines >= 10) = {mad:.4f}")
check("Benford MAD < 0.015 (not 'non-conformity')", mad < 0.015, f"{mad:.4f}")
# voucher-number gaps
seqs = defaultdict(list)
for v in byv:
    p, y, n = v.split("-")
    seqs[p].append(int(n))
check("no voucher-number gaps", all(sorted(s) == list(range(1, len(s) + 1)) for s in seqs.values()))

# FY2021/2022 file
fy = read("fy2021_2022.csv")
check("fy2021_2022 has 400 lines", len(fy) == 400)
def off(d, t):
    if d in {dt.date(2021, 12, 1), dt.date(2021, 12, 2), dt.date(2021, 12, 3), dt.date(2022, 1, 1)}:
        return True
    wd = d.weekday()
    if d < dt.date(2022, 1, 1):
        return wd in (4, 5)
    return wd in (5, 6) or (wd == 4 and t > dt.time(12))
det = {r["line_id"] for r in fy if off(dt.date.fromisoformat(r["posting_date"]), dt.time.fromisoformat(r["posting_time"]))}
check("fy non-working (dated weekend profile) == answer key", det == {r["line_id"] for r in ak if r["file"] == "fy2021_2022.csv"}, len(det))
naive = {r["line_id"] for r in fy if dt.date.fromisoformat(r["posting_date"]).weekday() in (5, 6)}
print(f"     naive Sat/Sun-only calendar would flag {len(naive)} lines (should miss Dec-2021 Fridays, flag Dec-2021 Sundays wrongly)")
fyb = defaultdict(Decimal)
for r in fy:
    fyb[r["voucher_no"]] += Decimal(r["debit"]) - Decimal(r["credit"])
check("fy vouchers balance", all(v == 0 for v in fyb.values()))

# Edge cases
ed = read("edge_cases.csv")
check("edge_cases has 60 lines", len(ed) == 60)
def parse_amt(s):
    s = s.strip().replace(",", "").replace("AED", "").strip()
    neg = s.startswith("(") and s.endswith(")") or s.endswith("-")
    s = s.strip("()-")
    return -Decimal(s) if neg else Decimal(s)
def parse_date(s):
    for f in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(s, f).date()
        except ValueError:
            pass
    if s.isdigit() and 20000 < int(s) < 60000:
        return dt.date(1899, 12, 30) + dt.timedelta(days=int(s))
    return None
eb = defaultdict(Decimal)
for r in ed:
    eb[r["voucher_no"]] += parse_amt(r["debit"]) - parse_amt(r["credit"])
exp_e = {(r["error_type"]) for r in ak if r["file"] == "edge_cases.csv"}
ek = Counter(r["error_type"] for r in ak if r["file"] == "edge_cases.csv")
check("edge: exactly 2 unbalanced vouchers after parsing", sum(1 for v in eb.values() if v != 0) == ek["unbalanced_voucher"] == 2)
check("edge: exactly 5 unreadable dates", sum(1 for r in ed if parse_date(r["posting_date"]) is None) == ek["unreadable_date"] == 5)
check("edge: blank accounts == key", sum(1 for r in ed if not r["account_code"]) == ek["blank_account"])
check("edge: duplicate line_ids == key", sum(c - 1 for c in Counter(r["line_id"] for r in ed).values()) == ek["duplicate_line_id"])
check("edge: invalid TRNs == key", sum(1 for r in ed if r["trn"] and not TRN.match(r["trn"])) == ek["invalid_trn"])

print("\nSUMMARY:", "ALL CHECKS PASSED" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
