#!/usr/bin/env python3
"""AuditSmart Stage 1 - synthetic test-data generator (Build Guide prompt 1.1 / Workbook step 1.4).

Reproducible: fixed seed 2025, Decimal money (ROUND_HALF_UP), no network.
Writes into the folder of this script:
  dummy_gl.csv          3,000 balanced lines, UAE trading company, FY 1 Jan - 31 Dec 2025
  edge_cases.csv        60 lines that must fail / warn on import validation
  fy2021_2022.csv       400 lines, 1 Dec 2021 - 31 Jan 2022 (weekend change Fri/Sat -> Sat/Sun)
  supplier_register.csv supplier verification register for the Input VAT tests (Decision 13 test data)
  answer_key.csv        every planted error, one row per line (file,row_no,line_id,voucher_no,error_type,...)
  feature_key.csv       planted features that are NOT errors (top stratum, credit notes, controls, parse cases)
ALL DATA IS FICTITIOUS. Names of Emirates NBD / DEWA are used only as account labels requested by prompt 1.1;
every TRN, party id and invoice number is random.
"""
from __future__ import annotations

import csv
import datetime as dt
import math
import random
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

SEED = 2025
OUT = Path(__file__).resolve().parent
Q = Decimal("0.01")
VAT_RATE = Decimal("0.05")
PM = Decimal("280000")            # performance / tolerable misstatement (firm worked example)
TARGET_LINES = 3000
EFFECTIVE_TEST = dt.date(2025, 10, 1)   # TEST-ONLY effective date for Decision 13 rules (real: 1 Oct 2026)
SPEND_THRESHOLD = Decimal("375000")     # from prompt 1.1; Tax Partner to verify
OTHER_SUPPLIER_CAP = Decimal("300000")  # keeps every other supplier clearly below the threshold

COLUMNS = ["line_id", "entry_date", "posting_date", "posting_time", "voucher_no", "account_code",
           "account_name", "account_type", "debit", "credit", "currency", "narration", "user_id",
           "party_id", "party_name", "trn", "invoice_no", "net_amount", "vat_amount", "vat_code",
           "expense_category"]

ACCOUNTS = {
    "1010": ("Emirates NBD - Current Account", "Asset"),
    "1100": ("Trade Receivables", "Asset"),
    "1150": ("Staff Advances", "Asset"),
    "1300": ("VAT Recoverable (Input Tax)", "Asset"),
    "1400": ("Prepaid Rent", "Asset"),
    "2010": ("Trade Payables", "Liability"),
    "2100": ("VAT Payable (Output Tax)", "Liability"),
    "2200": ("Accrued Expenses", "Liability"),
    "2210": ("Provision for End-of-Service Benefits", "Liability"),
    "4010": ("Sales - Local (Standard Rated)", "Revenue"),
    "4020": ("Sales - Export (Zero Rated)", "Revenue"),
    "4100": ("Interest Income - Emirates NBD", "Revenue"),
    "5010": ("Purchases - Goods for Resale", "Expense"),
    "5020": ("Freight Inward and Customs Clearing", "Expense"),
    "6010": ("Rent - Dubai Warehouse (Al Quoz)", "Expense"),
    "6020": ("Rent - Dubai Office (Business Bay)", "Expense"),
    "6030": ("DEWA - Electricity and Water", "Expense"),
    "6040": ("Salaries and Wages - WPS", "Expense"),
    "6045": ("End-of-Service Benefits Expense", "Expense"),
    "6050": ("Staff Transport", "Expense"),
    "6060": ("Staff Accommodation", "Expense"),
    "6070": ("Staff Mobile and Internet", "Expense"),
    "6080": ("Staff Parking", "Expense"),
    "6090": ("Staff Food and Beverages", "Expense"),
    "6100": ("Marketing and Advertising", "Expense"),
    "6110": ("Repairs and Maintenance", "Expense"),
    "6120": ("Bank Charges - Emirates NBD", "Expense"),
    "6130": ("Professional Fees - Overseas (Reverse Charge)", "Expense"),
    "6150": ("Office Supplies and Stationery", "Expense"),
}
EMPLOYEE_ACCOUNTS = {"6050": "transport", "6090": "food_beverages", "6060": "accommodation",
                     "6070": "mobile_internet", "6080": "parking"}

HOLIDAYS_2025 = {}
with open(OUT / "uae_holidays_2025.csv", newline="", encoding="utf-8") as fh:
    for r in csv.DictReader(fh):
        HOLIDAYS_2025[dt.date.fromisoformat(r["date"])] = r["name"]

rng = random.Random(SEED)


# ----------------------------------------------------------------------------- helpers
def D(x) -> Decimal:
    return Decimal(str(x)).quantize(Q, rounding=ROUND_HALF_UP)


def vat_of(net: Decimal) -> Decimal:
    return (net * VAT_RATE).quantize(Q, rounding=ROUND_HALF_UP)


def is_round_sum(a: Decimal) -> bool:        # firm criterion: multiple of 1,000 and >= 10,000
    return a >= 10000 and a % 1000 == 0


def amount(lo: float, hi: float) -> Decimal:
    """Log-uniform amount (Benford-friendly) with non-zero fils."""
    while True:
        x = math.exp(rng.uniform(math.log(lo), math.log(hi)))
        a = D(x)
        if a % 1 != 0 and not is_round_sum(a):
            return a


def trn_valid() -> str:
    return "100" + "".join(rng.choice("0123456789") for _ in range(12))


def year_days(year=2025):
    d = dt.date(year, 1, 1)
    while d.year == year:
        yield d
        d += dt.timedelta(days=1)


def clean_workday(d: dt.date) -> bool:
    """Background postings: Mon-Fri, not a holiday, outside the +/-5 day period-end windows."""
    if d.weekday() >= 5 or d in HOLIDAYS_2025:
        return False
    if d <= dt.date(2025, 1, 5) or d >= dt.date(2025, 12, 26):
        return False
    return True


WORKDAYS = [d for d in year_days() if clean_workday(d)]
MON_THU = [d for d in WORKDAYS if d.weekday() <= 3]


def clean_time(d: dt.date) -> dt.time:
    if d.weekday() == 4:                       # Friday half day: 08:00-11:59
        return dt.time(rng.randint(8, 11), rng.randint(0, 59), rng.randint(0, 59))
    return dt.time(rng.randint(8, 17), rng.randint(0, 59), rng.randint(0, 59))


def rand_workday(after: dt.date | None = None, before: dt.date | None = None, mon_thu=False):
    pool = MON_THU if mon_thu else WORKDAYS
    pool = [d for d in pool if (after is None or d >= after) and (before is None or d <= before)]
    return rng.choice(pool)


# ----------------------------------------------------------------------------- master data
LOCAL_CUSTOMER_NAMES = ["Al Safa Trading LLC", "Gulf Horizon General Trading", "Desert Rose Supermarket LLC",
    "Marina Star Retail LLC", "Al Barsha Hypermarket LLC", "Creek View Foodstuff Trading", "Palm Coast Stores LLC",
    "Jumeirah Fresh Mart LLC", "Al Wasl Wholesale LLC", "Sharjah Bay Distributors LLC", "Ajman Pearl Trading",
    "Al Ain Oasis Retail LLC", "Fujairah Harbour Supplies LLC", "Ras Al Khaimah Mega Stores", "Deira Grand Trading",
    "Karama Mini Mart LLC", "Mirdif City Retail LLC", "Silicon Oasis Traders LLC", "Al Nahda Consumer Goods LLC",
    "Abu Hail Provisions LLC", "Business Bay Convenience LLC", "Al Qusais Retail Hub LLC", "Dubai Hills Market LLC",
    "Musaffah Trading Co LLC", "Al Mamzar Stores LLC"]
EXPORT_CUSTOMER_NAMES = ["Muscat Retail SAOC (Oman)", "Doha Consumer Co WLL (Qatar)", "Manama Foods BSC (Bahrain)",
    "Kuwait City Traders WLL", "Mombasa Imports Ltd (Kenya)", "Colombo Distribution Pvt Ltd (Sri Lanka)"]
GOODS_SUPPLIER_NAMES = ["Jebel Ali Packaging LLC", "Al Ghurair Foods Supply LLC*", "Emirates Wholesale Imports LLC",
    "Gulf Pack Industries LLC", "Al Quoz Industrial Supplies", "Union Paper Products LLC", "Ras Al Khor Traders",
    "Dubai Global Commodities LLC", "Sahara Food Ingredients LLC", "Arabian Plastics Co LLC", "Hatta Mountain Water LLC",
    "Al Jaddaf Electronics Trading", "Oud Metha Garments LLC", "Sharjah Can Makers LLC", "Hamriyah Free Zone Supplies",
    "Khalifa Port Logistics Trading", "Al Rigga Beverages LLC", "Al Fahidi Spices Trading", "Bur Dubai Textiles LLC",
    "Nad Al Sheba Agro LLC", "Al Twar Household Goods LLC", "Umm Suqeim Cosmetics Trading", "Al Garhoud Auto Parts LLC",
    "Satwa Kitchenware Trading", "International City Wholesale LLC", "Al Khawaneej Dairy LLC", "Al Rashidiya Toys LLC",
    "Muhaisnah Building Materials", "Al Warqa Stationery Trading", "Jafza Chemicals Trading FZE"]
GOODS_SUPPLIER_NAMES = [n.replace("*", "") for n in GOODS_SUPPLIER_NAMES]
OPEX_SUPPLIERS = {  # account -> supplier name
    "6100": "Brandwave Media FZ-LLC", "6110": "FixPro Technical Services LLC",
    "6150": "OfficeHub Stationery LLC", "5020": "Seagate Customs Clearing LLC"}
EMP_SUPPLIERS = {"6050": "MetroLink Staff Transport LLC", "6090": "Al Kareem Catering LLC",
                 "6060": "Sunrise Labour Accommodation LLC", "6070": "SkyNet Telecom Services LLC*",
                 "6080": "ParkEasy Dubai LLC"}
EMP_SUPPLIERS = {k: v.replace("*", "") for k, v in EMP_SUPPLIERS.items()}
THRESHOLD_SUPPLIER_NAMES = ["Al Mansoori Bulk Foods Trading LLC", "Golden Dunes Import Export LLC",
                            "Crescent Wholesale Distribution LLC"]
UNVERIFIED_SUPPLIER_NAMES = ["Quickstock General Trading LLC", "Blue Lagoon Trading FZE", "Nova Supply Hub LLC"]
TOP_SUPPLIER_NAMES = ["Al Futtaim Bulk Commodities LLC*", "Arabian Gulf Rice Mills LLC", "Emirates Sugar Traders LLC",
                      "Delta Edible Oils Trading LLC", "Najma Frozen Foods Import LLC", "Atlas Grain Trading LLC",
                      "Oasis Coffee Importers LLC", "Coral Bay Seafood Trading LLC"]
TOP_SUPPLIER_NAMES = [n.replace("*", "").replace("Al Futtaim", "Al Fajr") for n in TOP_SUPPLIER_NAMES]

parties = {}   # party_id -> dict(name, trn, kind)


def add_party(prefix, i, name, kind, trn=True):
    pid = f"{prefix}{i:03d}"
    parties[pid] = {"name": name, "trn": trn_valid() if trn else "", "kind": kind}
    return pid


CUSTOMERS = [add_party("C", i + 1, n, "customer") for i, n in enumerate(LOCAL_CUSTOMER_NAMES)]
EXPORTERS = [add_party("C", 100 + i, n, "export_customer", trn=False) for i, n in enumerate(EXPORT_CUSTOMER_NAMES)]
GOODS_SUPPLIERS = [add_party("S", i + 1, n, "supplier") for i, n in enumerate(GOODS_SUPPLIER_NAMES)]
OPEX_SUP_IDS = {acc: add_party("S", 100 + i, n, "supplier") for i, (acc, n) in enumerate(OPEX_SUPPLIERS.items())}
EMP_SUP_IDS = {acc: add_party("S", 120 + i, n, "supplier") for i, (acc, n) in enumerate(EMP_SUPPLIERS.items())}
THRESH_SUP = [add_party("S", 200 + i, n, "supplier") for i, n in enumerate(THRESHOLD_SUPPLIER_NAMES)]
UNVER_SUP = [add_party("S", 300 + i, n, "supplier") for i, n in enumerate(UNVERIFIED_SUPPLIER_NAMES)]
TOP_SUP = [add_party("S", 400 + i, n, "supplier") for i, n in enumerate(TOP_SUPPLIER_NAMES)]
DEWA = add_party("S", 500, "Dubai Electricity and Water Authority (DEWA)", "supplier")
ENBD = add_party("S", 501, "Emirates NBD Bank PJSC", "supplier")
LANDLORD_WH = add_party("S", 502, "Al Quoz Warehousing Properties LLC", "supplier")
LANDLORD_OF = add_party("S", 503, "Bay Square Office Leasing LLC", "supplier")
CONSULTANT = add_party("S", 600, "Northbridge Advisory Ltd (UK) - overseas", "supplier", trn=False)

USERS_AP = ["APCLERK1", "APCLERK2"]
DEPTS = ["Sales", "Warehouse", "Logistics", "Finance", "Admin", "Management"]

# ----------------------------------------------------------------------------- voucher model
vouchers = []      # dict(prefix, date, time, user, lines=[...], tags=[(line_idx, error_type, desc, related)], feats)
supplier_spend = {}  # party -> Decimal gross purchases (invoices only)


def L(acc, dr=Decimal("0"), cr=Decimal("0"), narr="", party="", inv="", net=None, vat=None, code="", cat="",
      trn=None):
    p = parties.get(party, {})
    return {"account_code": acc, "debit": D(dr), "credit": D(cr), "narration": narr, "party_id": party,
            "party_name": p.get("name", "") if party else "",
            "trn": (p.get("trn", "") if trn is None else trn) if party else "",
            "invoice_no": inv, "net_amount": "" if net is None else D(net), "vat_amount": "" if vat is None else D(vat),
            "vat_code": code, "expense_category": cat}


def V(prefix, date, lines, user, time=None, tags=None, feats=None, kind=""):
    v = {"prefix": prefix, "date": date, "time": time or clean_time(date), "user": user, "lines": lines,
         "tags": tags or [], "feats": feats or [], "kind": kind}
    vouchers.append(v)
    return v


inv_counter = {"n": 0}


def new_inv(prefix):
    inv_counter["n"] += 1
    return f"{prefix}-{rng.randint(10, 99)}{inv_counter['n']:05d}"


def purchase(date, supplier, net, acc="5010", user=None, narr=None, inv=None, time=None, tags_primary=None,
             feats_primary=None, cat="", trn=None, count_spend=True):
    vat = vat_of(net)
    gross = net + vat
    inv = inv or new_inv("SINV")
    nm = parties[supplier]["name"]
    narr = narr or f"Purchase invoice {inv} - {nm}"
    lines = [L(acc, dr=net, narr=narr, party=supplier, inv=inv, net=net, vat=vat, code="SR", cat=cat, trn=trn),
             L("1300", dr=vat, narr=f"Input VAT 5% on {inv}"),
             L("2010", cr=gross, narr=f"Payable to {nm} - {inv}")]
    tags = [(0,) + t for t in (tags_primary or [])]
    feats = [(0,) + f for f in (feats_primary or [])]
    if count_spend:
        supplier_spend[supplier] = supplier_spend.get(supplier, Decimal(0)) + gross
    return V("PI", date, lines, user or rng.choice(USERS_AP), time=time, tags=tags, feats=feats, kind="purchase")


def sale_sr(date, customer, net, vat=None, user="ARCLERK", time=None, tags_primary=None, trn=None, two_line=False):
    vat_ok = vat_of(net)
    vat = vat_ok if vat is None else D(vat)
    inv = new_inv("TI")
    nm = parties[customer]["name"]
    narr = f"Tax invoice {inv} - {nm}"
    lines = [L("1100", dr=net + vat, narr=f"Receivable from {nm} - {inv}"),
             L("4010", cr=net, narr=narr, party=customer, inv=inv, net=net, vat=vat, code="SR", trn=trn)]
    if not two_line:
        lines.append(L("2100", cr=vat, narr=f"Output VAT 5% on {inv}"))
    tags = [(1,) + t for t in (tags_primary or [])]
    return V("SI", date, lines, user, time=time, tags=tags, kind="sale")


def safe_voucher_amounts(lines, allow_big=False):
    for ln in lines:
        for a in (ln["debit"], ln["credit"]):
            if a and (is_round_sum(a) or a >= PM):
                return False
            if not allow_big and ln["debit"] and ACCOUNTS[ln["account_code"]][1] == "Expense" and ln["debit"] >= 75000:
                return False
    return True


def with_clean_amounts(builder, *args, **kw):
    """Build a voucher; regenerate amounts until no line is accidentally a round sum / >= PM."""
    for _ in range(200):
        v = builder(*args, **kw)
        if safe_voucher_amounts(v["lines"], allow_big=bool(v["feats"])):
            return v
        vouchers.pop()
        if v["kind"] == "purchase":
            p = v["lines"][0]
            supplier_spend[p["party_id"]] -= p["debit"] + v["lines"][1]["debit"]
    raise RuntimeError("could not build clean voucher")


# ============================================================================ PLANTED ITEMS
def pay_lines(supplier, amt, narr=None):
    nm = parties[supplier]["name"]
    narr = narr if narr is not None else f"Payment to {nm} - Emirates NBD transfer"
    return [L("2010", dr=amt, narr=narr), L("1010", cr=amt, narr=narr)]


def weekend_days():
    return [d for d in year_days() if d.weekday() >= 5 and d not in HOLIDAYS_2025
            and dt.date(2025, 1, 5) < d < dt.date(2025, 12, 26)]


# 1. Sat/Sun postings - 25 lines: 11 payments x2 + 1 purchase x3
wk = rng.sample(weekend_days(), 12)
for i, d in enumerate(wk):
    t = dt.time(rng.randint(9, 17), rng.randint(0, 59), rng.randint(0, 59))
    desc = f"Posted on {d.strftime('%A')} {d.isoformat()} - weekly off day (Sat/Sun weekend)"
    if i < 11:
        sup = rng.choice(GOODS_SUPPLIERS)
        lines = pay_lines(sup, amount(3000, 60000))
        V("PV", d, lines, rng.choice(USERS_AP), time=t, tags=[(0, "weekend_posting", desc, ""), (1, "weekend_posting", desc, "")])
    else:
        v = purchase(d, rng.choice(GOODS_SUPPLIERS), amount(3000, 40000), time=t)
        v["tags"] = [(j, "weekend_posting", desc, "") for j in range(3)]

# 2. Friday postings after 15:00 - 10 lines (5 payments)
fridays = [d for d in WORKDAYS if d.weekday() == 4]
for d in rng.sample(fridays, 5):
    t = dt.time(rng.randint(15, 18), rng.randint(1, 59), rng.randint(0, 59))
    desc = f"Friday {d.isoformat()} at {t.strftime('%H:%M')} - after the 12:00 half-day cut-off (planted >15:00)"
    V("PV", d, pay_lines(rng.choice(GOODS_SUPPLIERS), amount(3000, 60000)), rng.choice(USERS_AP), time=t,
      tags=[(0, "friday_after_cutoff", desc, ""), (1, "friday_after_cutoff", desc, "")])

# 3. Public holiday postings - 15 lines: 6 payments x2 + 1 purchase x3
hol_dates = [dt.date(2025, 3, 31), dt.date(2025, 4, 1), dt.date(2025, 6, 5), dt.date(2025, 12, 1),
             dt.date(2025, 12, 2), dt.date(2025, 6, 6)]
for d in hol_dates:
    t = dt.time(rng.randint(9, 11), rng.randint(0, 59), rng.randint(0, 59))
    desc = f"Posted on public holiday {d.isoformat()} ({HOLIDAYS_2025[d]})"
    V("PV", d, pay_lines(rng.choice(GOODS_SUPPLIERS), amount(3000, 60000)), rng.choice(USERS_AP), time=t,
      tags=[(0, "public_holiday_posting", desc, ""), (1, "public_holiday_posting", desc, "")])
d = dt.date(2025, 9, 5)
v = purchase(d, rng.choice(GOODS_SUPPLIERS), amount(3000, 40000), time=dt.time(10, 17, 44))
v["tags"] = [(j, "public_holiday_posting", f"Posted on public holiday {d.isoformat()} ({HOLIDAYS_2025[d]})", "") for j in range(3)]

# 4. Round sums - 20 lines: 10 staff-advance / supplier payments in multiples of 10,000
for i in range(10):
    d = rand_workday(before=dt.date(2025, 12, 15))
    amt = Decimal(rng.choice([10000, 20000, 30000, 40000, 50000, 60000, 70000]))
    desc = f"Round sum AED {amt:,.2f} (multiple of 10,000)"
    if i < 5:
        nm = f"Staff advance - employee E{rng.randint(1000, 1999)}"
        lines = [L("1150", dr=amt, narr=nm), L("1010", cr=amt, narr=nm)]
    else:
        lines = pay_lines(rng.choice(GOODS_SUPPLIERS), amt, narr="Payment on account - Emirates NBD transfer")
    V("PV", d, lines, "APCLERK2", tags=[(0, "round_sum", desc, ""), (1, "round_sum", desc, "")])

# 5. Period-end entries by FINMGR within 3 days of year end - 15 lines (5 accrual vouchers x 3 lines)
for d in [dt.date(2025, 12, 29), dt.date(2025, 12, 30), dt.date(2025, 12, 30), dt.date(2025, 12, 31), dt.date(2025, 12, 31)]:
    a1, a2 = amount(2000, 40000), amount(1000, 20000)
    narr = "Year-end accrual - utilities and maintenance Dec 2025"
    desc = f"Manual journal by FINMGR on {d.isoformat()} - within 3 days of year end 31-Dec-2025"
    V("JV", d, [L("6030", dr=a1, narr=narr), L("6110", dr=a2, narr=narr), L("2200", cr=a1 + a2, narr=narr)],
      "FINMGR", tags=[(j, "period_end_finmgr", desc, "") for j in range(3)])

# 6. Vague / blank narrations - 10 lines (5 payments)
for narr in ["", "adj", "misc", "correction", "as per MD"]:
    d = rand_workday(before=dt.date(2025, 12, 15))
    desc = f"Vague narration: '{narr}'" if narr else "Blank narration"
    V("PV", d, pay_lines(rng.choice(GOODS_SUPPLIERS), amount(3000, 60000), narr=narr), "APCLERK2",
      tags=[(0, "vague_narration", desc, ""), (1, "vague_narration", desc, "")])

# 7. Output VAT errors - 12 sales lines
vat_err = ([("wrong_calc", "VAT computed on the gross amount (net x 1.05 x 5%)")] * 5 +
           [("missing_vat", "SR invoice with no VAT charged")] * 4 +
           [("wrong_rate", "VAT keyed at 0.5% instead of 5%")] * 3)
for kind, text in vat_err:
    d = rand_workday(before=dt.date(2025, 12, 20))
    net = amount(8000, 150000)
    if kind == "wrong_calc":
        vat = (net * Decimal("1.05") * VAT_RATE).quantize(Q, rounding=ROUND_HALF_UP)
    elif kind == "missing_vat":
        vat = Decimal("0.00")
    else:
        vat = (net * Decimal("0.005")).quantize(Q, rounding=ROUND_HALF_UP)
    exp = vat_of(net)
    desc = f"Output VAT error ({kind}): {text}; recorded {vat}, expected {exp}, difference {vat - exp}"
    with_clean_amounts(sale_sr, d, rng.choice(CUSTOMERS), net, vat=vat, two_line=(kind == "missing_vat"),
                       tags_primary=[("output_vat_error", desc, "")])

# 8. Invalid TRNs - 5 sales primary lines
bad_trns = [("10012345678901", "14 digits"), ("1003456789012345", "16 digits"),
            ("300123456789012", "does not start with 100"), ("I00234567890123", "letter I instead of digit 1"),
            ("1.00567E+14", "Excel scientific notation")]
for trn, why in bad_trns:
    d = rand_workday(before=dt.date(2025, 12, 20))
    with_clean_amounts(sale_sr, d, rng.choice(CUSTOMERS), amount(5000, 120000), trn=trn,
                       tags_primary=[("invalid_trn", f"Invalid TRN '{trn}' ({why}); valid = 15 digits starting 100", "")])

# 9. Input VAT - purchases after 1 Oct 2025 from suppliers with no verification date - 15 lines (3 suppliers x 5)
for sup in UNVER_SUP:
    for _ in range(5):
        d = rand_workday(after=dt.date(2025, 10, 2), before=dt.date(2025, 12, 22))
        desc = (f"Input VAT deducted on {d.isoformat()} (after test effective date 2025-10-01) - supplier "
                f"{sup} has no verification date in supplier_register.csv (Decision 13/2026 test)")
        with_clean_amounts(purchase, d, sup, amount(2500, 30000), tags_primary=[("input_vat_unverified_supplier", desc, "")])

# 10. Employee-expense lines - 20 (4 per category)
for acc, cat in EMPLOYEE_ACCOUNTS.items():
    for _ in range(4):
        d = rand_workday()
        sup = EMP_SUP_IDS[acc]
        desc = f"Employee-related expense ({cat}) with input VAT recovered - check Decision 17/2026 rules"
        with_clean_amounts(purchase, d, sup, amount(800, 25000), acc=acc, cat=cat,
                           narr=f"{ACCOUNTS[acc][0]} - {parties[sup]['name']} - monthly staff invoice",
                           tags_primary=[("employee_expense", desc, "")])

# 11. Top-stratum features - 8 expense debit lines 110k-265k (>= J at 95% and 90%, < PM incl. VAT)
for sup in TOP_SUP:
    d = rand_workday(mon_thu=True)
    for _ in range(100):
        net = amount(110000, 265000)
        if not is_round_sum(net + vat_of(net)):
            break
    with_clean_amounts(purchase, d, sup, net, feats_primary=[("top_stratum", "Expense debit line >= sampling interval J (95% and 90%)")])

# 12. Spend-threshold suppliers - 3 suppliers whose rolling 12-month gross purchases first exceed 375,000 after 1 Oct
thresh_vouchers = {}
for sup in THRESH_SUP:
    while True:
        pre = [amount(18000, 30000) for _ in range(13)]
        pre_gross = sum(n + vat_of(n) for n in pre)
        if Decimal("320000") < pre_gross < Decimal("350000"):
            break
    dates_pre = sorted(rng.sample([d for d in WORKDAYS if d < dt.date(2025, 9, 25)], 13))
    dates_post = sorted(rng.sample([d for d in WORKDAYS if dt.date(2025, 10, 5) < d < dt.date(2025, 12, 20)], 3))
    vs = []
    for d, n in zip(dates_pre, pre):
        vs.append(with_clean_amounts(purchase, d, sup, n))
    for d in dates_post:
        vs.append(with_clean_amounts(purchase, d, sup, amount(18000, 30000)))
    thresh_vouchers[sup] = vs

# ============================================================================ BACKGROUND
# fixed monthly / quarterly items
for m in range(1, 13):
    month_days = [d for d in WORKDAYS if d.month == m]
    # payroll (WPS) by department, around the 24th
    pd_ = [d for d in month_days if d.day >= 20 and d.weekday() <= 3][0]
    lines = []
    for dep in DEPTS:
        a = amount(28000, 68000)
        lines.append(L("6040", dr=a, narr=f"Salaries {dep} - {pd_.strftime('%b %Y')} - WPS run"))
    for dep, ln in zip(DEPTS, list(lines)):
        lines.append(L("1010", cr=ln["debit"], narr=f"WPS salary transfer {dep} - {pd_.strftime('%b %Y')}"))
    V("PR", pd_, lines, "PAYROLL", kind="payroll")
    e = amount(6000, 14000)
    V("PR", pd_, [L("6045", dr=e, narr=f"EOSB provision {pd_.strftime('%b %Y')}"),
                  L("2210", cr=e, narr=f"EOSB provision {pd_.strftime('%b %Y')}")], "PAYROLL", kind="eosb")
    # DEWA monthly bill
    with_clean_amounts(purchase, rng.choice([d for d in month_days if 8 <= d.day <= 18]), DEWA, amount(11000, 19000),
                       acc="6030", narr=f"DEWA bill {dt.date(2025, m, 1).strftime('%b %Y')} - warehouse and office")
    # FINMGR month-end accrual and rent amortisation (Dec on/before 22nd to stay outside the planted window)
    ae = [d for d in month_days if d.day <= (22 if m == 12 else 31)][-1]
    a1, a2 = amount(2000, 9000), amount(1000, 6000)
    narr = f"Month-end accrual - utilities and maintenance {ae.strftime('%b %Y')}"
    V("JV", ae, [L("6030", dr=a1, narr=narr), L("6110", dr=a2, narr=narr), L("2200", cr=a1 + a2, narr=narr)], "FINMGR",
      kind="accrual")
    narr = f"Rent amortisation {ae.strftime('%b %Y')} - warehouse and office"
    V("JV", ae, [L("6010", dr=D("19437.50"), narr=narr), L("6020", dr=D("7062.75"), narr=narr),
                 L("1400", cr=D("26500.25"), narr=narr)], "FINMGR", kind="amort")
    # bank charges
    bc = amount(350, 1800)
    d = rand_workday(after=dt.date(2025, m, 1), before=month_days[-1])
    narr = f"Bank charges {dt.date(2025, m, 1).strftime('%b %Y')} - Emirates NBD"
    vat = vat_of(bc)
    V("JV", d, [L("6120", dr=bc, narr=narr, party=ENBD, inv=new_inv("ENBD"), net=bc, vat=vat, code="SR"),
                L("1300", dr=vat, narr="Input VAT 5% on bank charges"), L("1010", cr=bc + vat, narr=narr)], "GLACCT",
      kind="bankchg")
    supplier_spend[ENBD] = supplier_spend.get(ENBD, Decimal(0)) + bc + vat
for q in range(4):
    # quarterly rent prepayment (landlords) and interest
    d = rand_workday(after=dt.date(2025, 3 * q + 1, 6), before=dt.date(2025, 3 * q + 1, 25), mon_thu=True)
    for sup, net in [(LANDLORD_WH, D("58312.50")), (LANDLORD_OF, D("21188.25"))]:
        inv = new_inv("RENT")
        vat = vat_of(net)
        nm = parties[sup]["name"]
        V("PI", d, [L("1400", dr=net, narr=f"Quarterly rent Q{q + 1} 2025 - {nm}", party=sup, inv=inv, net=net, vat=vat, code="SR"),
                    L("1300", dr=vat, narr=f"Input VAT 5% on {inv}"), L("2010", cr=net + vat, narr=f"Payable to {nm} - {inv}")],
          "APCLERK1", kind="rent")
        supplier_spend[sup] = supplier_spend.get(sup, Decimal(0)) + net + vat
    d = rand_workday(after=dt.date(2025, 3 * q + 3, 15), before=dt.date(2025, 3 * q + 3, 28) if q < 3 else dt.date(2025, 12, 22))
    it = amount(2000, 9000)
    V("JV", d, [L("1010", dr=it, narr=f"Interest on call deposit Q{q + 1} - Emirates NBD"),
                L("4100", cr=it, narr=f"Interest on call deposit Q{q + 1}", party=ENBD, inv=new_inv("ENBD"), net=it,
                  vat=Decimal("0"), code="EX")], "GLACCT", kind="interest")
# reverse charge overseas fees (8)
for _ in range(8):
    d = rand_workday()
    net = amount(8000, 45000)
    vat = vat_of(net)
    inv = new_inv("NBA")
    narr = f"Advisory fees {inv} - Northbridge Advisory Ltd (UK) - reverse charge"
    V("JV", d, [L("6130", dr=net, narr=narr, party=CONSULTANT, inv=inv, net=net, vat=vat, code="RC"),
                L("1300", dr=vat, narr="Input VAT - reverse charge"), L("2100", cr=vat, narr="Output VAT - reverse charge"),
                L("2010", cr=net, narr=narr)], "GLACCT", kind="rc")
    supplier_spend[CONSULTANT] = supplier_spend.get(CONSULTANT, Decimal(0)) + net + vat


def pick_supplier(gross):
    pool = [s for s in GOODS_SUPPLIERS if supplier_spend.get(s, 0) + gross <= OTHER_SUPPLIER_CAP]
    return rng.choice(pool)


# duplicate invoices - 10 (copy of an earlier background purchase, posted 4-25 days later)
regular_purchases = []
for _ in range(230):
    net = amount(2000, 60000)
    sup = pick_supplier(net + vat_of(net))
    regular_purchases.append(with_clean_amounts(purchase, rand_workday(before=dt.date(2025, 12, 22)), sup, net))
for _ in range(10):
    while True:
        orig = rng.choice(regular_purchases)
        p = orig["lines"][0]
        sup, net = p["party_id"], p["debit"]
        gross = net + vat_of(net)
        later = [d for d in WORKDAYS if 4 <= (d - orig["date"]).days <= 25 and d <= dt.date(2025, 12, 22)]
        if later and supplier_spend[sup] + gross <= OTHER_SUPPLIER_CAP and not orig.get("duplicated"):
            break
    orig["duplicated"] = True
    v = purchase(rng.choice(later), sup, net, inv=p["invoice_no"])
    v["dup_of"] = orig
    v["tags"] = [(0, "duplicate_invoice", f"Invoice {p['invoice_no']} from {sup} already posted on {orig['date'].isoformat()}", "ORIG")]

# opex purchases (60)
for _ in range(60):
    acc = rng.choice(list(OPEX_SUP_IDS))
    with_clean_amounts(purchase, rand_workday(before=dt.date(2025, 12, 22)), OPEX_SUP_IDS[acc], amount(600, 30000), acc=acc,
                       narr=f"{ACCOUNTS[acc][0]} - {parties[OPEX_SUP_IDS[acc]]['name']}")

# credit notes - 20 purchase CNs + 20 sales CNs (features)
for _ in range(20):
    net = amount(400, 12000)
    vat = vat_of(net)
    sup = rng.choice(GOODS_SUPPLIERS)
    d = rand_workday(before=dt.date(2025, 12, 22))
    inv = new_inv("SCN")
    narr = f"Supplier credit note {inv} - goods returned - {parties[sup]['name']}"
    V("PC", d, [L("2010", dr=net + vat, narr=narr), L("5010", cr=net, narr=narr, party=sup, inv=inv, net=-net, vat=-vat, code="SR"),
                L("1300", cr=vat, narr=f"Input VAT 5% on supplier credit note {inv}")], rng.choice(USERS_AP),
      feats=[(1, "credit_note", "Purchase credit note - credit line in expense account (excluded from debit population, listed)")],
      kind="pcn")
for _ in range(20):
    net = amount(500, 15000)
    vat = vat_of(net)
    cus = rng.choice(CUSTOMERS)
    d = rand_workday(before=dt.date(2025, 12, 22))
    inv = new_inv("CN")
    narr = f"Credit note {inv} - price allowance agreed - {parties[cus]['name']}"
    V("SC", d, [L("4010", dr=net, narr=narr, party=cus, inv=inv, net=-net, vat=-vat, code="SR"),
                L("2100", dr=vat, narr=f"Output VAT 5% on credit note {inv}"), L("1100", cr=net + vat, narr=narr)], "ARCLERK",
      feats=[(0, "credit_note", "Sales credit note - debit to revenue with negative net/VAT")], kind="scn")

# sales: SR and ZR
for _ in range(225):
    with_clean_amounts(sale_sr, rand_workday(before=dt.date(2025, 12, 22)), rng.choice(CUSTOMERS), amount(4000, 160000))
for _ in range(40):
    net = amount(8000, 150000)
    cus = rng.choice(EXPORTERS)
    inv = new_inv("EX")
    nm = parties[cus]["name"]
    V("SI", rand_workday(before=dt.date(2025, 12, 22)),
      [L("1100", dr=net, narr=f"Receivable from {nm} - {inv}"),
       L("4020", cr=net, narr=f"Export invoice {inv} - {nm} - zero rated", party=cus, inv=inv, net=net, vat=Decimal("0"), code="ZR")],
      "ARCLERK", kind="export")


def line_count():
    return sum(len(v["lines"]) for v in vouchers)


# fill to exactly TARGET_LINES with receipts and payments (2 lines each); one 3-line opex purchase if odd
remaining = TARGET_LINES - line_count()
if remaining < 0:
    raise SystemExit(f"over budget by {-remaining}")
if remaining % 2:
    acc = "6150"
    with_clean_amounts(purchase, rand_workday(before=dt.date(2025, 12, 22)), OPEX_SUP_IDS[acc], amount(600, 9000), acc=acc,
                       narr=f"{ACCOUNTS[acc][0]} - {parties[OPEX_SUP_IDS[acc]]['name']}")
    remaining -= 3
n_pairs = remaining // 2
n_rec = n_pairs * 45 // 100
for i in range(n_pairs):
    d = rand_workday(after=dt.date(2025, 1, 20), before=dt.date(2025, 12, 22))
    if i < n_rec:
        cus = rng.choice(CUSTOMERS + EXPORTERS)
        a = amount(5000, 180000)
        narr = f"Receipt from {parties[cus]['name']} - Emirates NBD"
        V("RV", d, [L("1010", dr=a, narr=narr), L("1100", cr=a, narr=narr)], "ARCLERK", kind="receipt")
    else:
        sup = rng.choice(GOODS_SUPPLIERS + list(OPEX_SUP_IDS.values()))
        V("PV", d, pay_lines(sup, amount(3000, 120000)), rng.choice(USERS_AP), kind="payment")
assert line_count() == TARGET_LINES, line_count()

# ============================================================================ NUMBERING & OUTPUT
vouchers.sort(key=lambda v: (v["date"], v["time"]))
seq = {}
rows, answer, features = [], [], []
lid = 0
for v in vouchers:
    seq[v["prefix"]] = seq.get(v["prefix"], 0) + 1
    v["voucher_no"] = f"{v['prefix']}-2025-{seq[v['prefix']]:05d}"
    v["line_ids"] = []
    for ln in v["lines"]:
        lid += 1
        v["line_ids"].append(f"L{lid:05d}")
for v in vouchers:
    assert sum(l["debit"] for l in v["lines"]) == sum(l["credit"] for l in v["lines"]), v["voucher_no"]
    for i, ln in enumerate(v["lines"]):
        acc = ln["account_code"]
        rows.append({"line_id": v["line_ids"][i], "entry_date": v["date"].isoformat(), "posting_date": v["date"].isoformat(),
                     "posting_time": v["time"].strftime("%H:%M:%S"), "voucher_no": v["voucher_no"], "account_code": acc,
                     "account_name": ACCOUNTS[acc][0], "account_type": ACCOUNTS[acc][1],
                     "debit": f"{ln['debit']:.2f}", "credit": f"{ln['credit']:.2f}", "currency": "AED",
                     "narration": ln["narration"], "user_id": v["user"], "party_id": ln["party_id"],
                     "party_name": ln["party_name"], "trn": ln["trn"], "invoice_no": ln["invoice_no"],
                     "net_amount": "" if ln["net_amount"] == "" else f"{ln['net_amount']:.2f}",
                     "vat_amount": "" if ln["vat_amount"] == "" else f"{ln['vat_amount']:.2f}",
                     "vat_code": ln["vat_code"], "expense_category": ln["expense_category"]})
    for (i, etype, desc, rel) in v["tags"]:
        if rel == "ORIG":
            rel = v["dup_of"]["line_ids"][0]
        answer.append([v["line_ids"][i], v["voucher_no"], etype, desc, rel])
    for (i, ftype, desc) in v["feats"]:
        features.append(["dummy_gl.csv", v["line_ids"][i], v["voucher_no"], ftype, desc])

# spend threshold answer rows: the line on which the rolling 12-month gross spend first exceeds the threshold
for sup, vs in thresh_vouchers.items():
    cum = Decimal(0)
    for v in sorted(vs, key=lambda x: (x["date"], x["time"])):
        cum += v["lines"][0]["debit"] + v["lines"][1]["debit"]
        if cum > SPEND_THRESHOLD:
            answer.append([v["line_ids"][0], v["voucher_no"], "input_vat_spend_threshold",
                           f"Supplier {sup} rolling 12-month gross purchases reach AED {cum:,.2f} (> 375,000) on "
                           f"{v['date'].isoformat()}; no bank-account evidence in supplier_register.csv", ""])
            break
    supplier_spend[sup] = sum(x["lines"][0]["debit"] + x["lines"][1]["debit"] for x in vs)
assert all(s in THRESH_SUP or tot <= OTHER_SUPPLIER_CAP for s, tot in supplier_spend.items()), "supplier cap breached"

SEVERITY = {"weekend_posting": "High", "friday_after_cutoff": "Medium", "public_holiday_posting": "High",
            "round_sum": "Medium", "period_end_finmgr": "High", "vague_narration": "Medium",
            "duplicate_invoice": "High", "output_vat_error": "High", "invalid_trn": "Medium",
            "input_vat_unverified_supplier": "High", "input_vat_spend_threshold": "High", "employee_expense": "Medium",
            "non_working_day": "High", "unbalanced_voucher": "Critical", "unreadable_date": "Critical",
            "blank_account": "Critical", "duplicate_line_id": "Critical"}
row_of = {r["line_id"]: n + 1 for n, r in enumerate(rows)}


def write_csv(name, header, data):
    with open(OUT / name, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(data)


write_csv("dummy_gl.csv", COLUMNS, [[r[c] for c in COLUMNS] for r in rows])
answer_rows = [["dummy_gl.csv", row_of[a[0]], a[0], a[1], a[2], SEVERITY[a[2]], a[3], a[4]] for a in answer]
answer_rows.sort(key=lambda r: (r[4], r[1]))

# supplier register
reg = []
for pid, p in parties.items():
    if p["kind"] != "supplier":
        continue
    if pid in UNVER_SUP:
        reg.append([pid, p["name"], p["trn"], "", "", "", "first-time supplier - verification not yet performed"])
    elif pid in THRESH_SUP:
        vd = dt.date(2025, rng.randint(8, 9), rng.randint(1, 28))
        reg.append([pid, p["name"], p["trn"], vd.isoformat(), f"VER-{rng.randint(10000, 99999)}", "",
                    "TRN checked on FTA portal; bank-account confirmation not obtained"])
    else:
        vd = dt.date(2025, rng.randint(8, 9), rng.randint(1, 28))
        reg.append([pid, p["name"], p["trn"], vd.isoformat(), f"VER-{rng.randint(10000, 99999)}",
                    f"BANK-{rng.randint(10000, 99999)}", "TRN checked on FTA portal; bank letter on file"])
write_csv("supplier_register.csv", ["party_id", "party_name", "trn", "verified_on", "verification_ref",
                                    "bank_evidence_ref", "notes"], reg)

# ============================================================================ FY2021/2022 WEEKEND-CHANGE FILE
FY_HOL = {dt.date(2021, 12, 1), dt.date(2021, 12, 2), dt.date(2021, 12, 3), dt.date(2022, 1, 1)}
fy_days = [dt.date(2021, 12, 1) + dt.timedelta(days=i) for i in range(62)]
fy_days = [d for d in fy_days if d not in FY_HOL and d.weekday() != 5]   # never a Saturday (off under both regimes)
groups = {
    "dec_fri": [d for d in fy_days if d.year == 2021 and d.weekday() == 4],   # off (Fri/Sat weekend)  -> ERROR
    "jan_sun": [d for d in fy_days if d.year == 2022 and d.weekday() == 6],   # off (Sat/Sun weekend)  -> ERROR
    "dec_sun": [d for d in fy_days if d.year == 2021 and d.weekday() == 6],   # working day (Sun-Thu)  -> control
    "jan_fri": [d for d in fy_days if d.year == 2022 and d.weekday() == 4],   # working half day       -> control
    "mon_thu": [d for d in fy_days if d.weekday() <= 3],
}
fy_v = []
for g, nv in [("dec_fri", 15), ("jan_sun", 15), ("dec_sun", 15), ("jan_fri", 15), ("mon_thu", 140)]:
    for _ in range(nv):
        d = rng.choice(groups[g])
        if g == "jan_fri" or (d.weekday() == 4):
            t = dt.time(rng.randint(8, 11), rng.randint(0, 59), rng.randint(0, 59))
        else:
            t = dt.time(rng.randint(8, 17), rng.randint(0, 59), rng.randint(0, 59))
        k = rng.random()
        if k < 0.4:
            sup = rng.choice(GOODS_SUPPLIERS)
            a = amount(3000, 60000)
            lines = pay_lines(sup, a)
            pre = "PV"
        elif k < 0.75:
            cus = rng.choice(CUSTOMERS)
            a = amount(5000, 90000)
            narr = f"Receipt from {parties[cus]['name']} - Emirates NBD"
            lines = [L("1010", dr=a, narr=narr), L("1100", cr=a, narr=narr)]
            pre = "RV"
        else:
            a = amount(1500, 25000)
            narr = f"Accrual - utilities {d.strftime('%b %Y')}"
            lines = [L("6030", dr=a, narr=narr), L("2200", cr=a, narr=narr)]
            pre = "JV"
        fy_v.append({"g": g, "date": d, "time": t, "lines": lines, "prefix": pre,
                     "user": "FINMGR" if pre == "JV" else rng.choice(USERS_AP + ["ARCLERK"])})
fy_v.sort(key=lambda v: (v["date"], v["time"]))
fy_rows, n, seqf = [], 0, {}
for v in fy_v:
    seqf[v["prefix"]] = seqf.get(v["prefix"], 0) + 1
    vno = f"{v['prefix']}-FY-{seqf[v['prefix']]:05d}"
    for ln in v["lines"]:
        n += 1
        line_id = f"F{n:05d}"
        acc = ln["account_code"]
        fy_rows.append([line_id, v["date"].isoformat(), v["date"].isoformat(), v["time"].strftime("%H:%M:%S"), vno, acc,
                        ACCOUNTS[acc][0], ACCOUNTS[acc][1], f"{ln['debit']:.2f}", f"{ln['credit']:.2f}", "AED",
                        ln["narration"], v["user"], "", "", "", "", "", "", "", ""])
        wd = v["date"].strftime("%A")
        if v["g"] == "dec_fri":
            answer_rows.append(["fy2021_2022.csv", n, line_id, vno, "non_working_day", "High",
                                f"{wd} {v['date']} - weekly off day under the Fri/Sat weekend in force until 31-Dec-2021", ""])
        elif v["g"] == "jan_sun":
            answer_rows.append(["fy2021_2022.csv", n, line_id, vno, "non_working_day", "High",
                                f"{wd} {v['date']} - weekly off day under the Sat/Sun weekend from 1-Jan-2022", ""])
        elif v["g"] == "dec_sun":
            features.append(["fy2021_2022.csv", line_id, vno, "working_day_control",
                             f"{wd} {v['date']} - normal working day before the change (must NOT be flagged)"])
        elif v["g"] == "jan_fri":
            features.append(["fy2021_2022.csv", line_id, vno, "working_day_control",
                             f"{wd} {v['date']} before 12:00 - Friday half day after the change (must NOT be flagged)"])
assert len(fy_rows) == 400, len(fy_rows)
write_csv("fy2021_2022.csv", COLUMNS, fy_rows)

# ============================================================================ EDGE CASES (60 lines)
E = []   # (row dict, [(error_type, severity, desc)], [(feature, desc)])


def er(vno, acc, dr, cr, date="2025-03-17", trn="", party="", net="", vat="", code="", narr=None, line_id=None):
    nm, typ = ACCOUNTS.get(acc, ("", ""))
    return {"line_id": line_id, "entry_date": date, "posting_date": date, "posting_time": "10:15:00", "voucher_no": vno,
            "account_code": acc, "account_name": nm, "account_type": typ, "debit": dr, "credit": cr, "currency": "AED",
            "narration": narr if narr is not None else f"Edge case {vno}", "user_id": "APCLERK1",
            "party_id": party, "party_name": parties[party]["name"] if party else "", "trn": trn, "invoice_no": "",
            "net_amount": net, "vat_amount": vat, "vat_code": code, "expense_category": ""}


def add(rowsv, errs=None, feats=None):
    for i, r in enumerate(rowsv):
        E.append((r, (errs or {}).get(i, []), (feats or {}).get(i, [])))


add([er("EV-001", "6150", "1000.00", "0.00"), er("EV-001", "2010", "0.00", "999.95")],
    {0: [("unbalanced_voucher", "Critical", "Voucher EV-001 debits 1,000.00 vs credits 999.95 (difference 0.05)")]})
add([er("EV-002", "5010", "12345.60", "0.00"), er("EV-002", "1300", "617.28", "0.00"), er("EV-002", "2010", "0.00", "12952.88")],
    {0: [("unbalanced_voucher", "Critical", "Voucher EV-002 debits 12,962.88 vs credits 12,952.88 (difference 10.00)")]})
for k, bad in enumerate(["2025-02-30", "31/13/2025", "TBD", "2025-13-05", "00/00/0000"]):
    vno = f"EV-{3 + k:03d}"
    a = f"{amount(500, 9000):.2f}"
    add([er(vno, "6150", a, "0.00", date=bad), er(vno, "2010", "0.00", a)],
        {0: [("unreadable_date", "Critical", f"posting/entry date '{bad}' cannot be parsed")]})
add([er("EV-008", "6150", "845.30", "0.00", date="15/03/2025"), er("EV-008", "2010", "0.00", "845.30", date="15/03/2025")],
    feats={0: [("parse_ok_date", "dd/mm/yyyy date 15/03/2025 must parse to 2025-03-15")]})
add([er("EV-009", "6150", "612.45", "0.00", date="45731"), er("EV-009", "2010", "0.00", "612.45", date="45731")],
    feats={0: [("parse_ok_date", "Excel serial date 45731 must parse to 2025-03-15")]})
add([er("EV-010", "6150", "1,234.50", "0.00"), er("EV-010", "2010", "0.00", "1,234.50")],
    feats={0: [("parse_ok_amount", "Amount '1,234.50' with thousands separator must parse to 1234.50")]})
add([er("EV-011", "5010", "2,500.00", "0.00"), er("EV-011", "5010", "(500.00)", "0.00"), er("EV-011", "2010", "0.00", "2,000.00")],
    feats={1: [("parse_ok_amount", "Bracketed amount '(500.00)' must parse to -500.00; voucher then balances")]})
add([er("EV-012", "6150", "1750.00", "0.00"), er("EV-012", "6150", "750.00-", "0.00"), er("EV-012", "2010", "0.00", "1000.00")],
    feats={1: [("parse_ok_amount", "Trailing-minus amount '750.00-' must parse to -750.00; voucher then balances")]})
add([er("EV-013", "6150", "AED 500", "0.00"), er("EV-013", "2010", "0.00", "AED 500.00")],
    feats={0: [("parse_warning_amount", "Currency prefix 'AED 500' - strip prefix and warn (or reject) - firm to decide")]})
add([er("EV-014", "", "3210.40", "0.00"), er("EV-014", "1010", "0.00", "3210.40")],
    {0: [("blank_account", "Critical", "account_code blank")]})
add([er("EV-015", "6110", "2876.15", "0.00"), er("EV-015", "", "0.00", "2876.15")],
    {1: [("blank_account", "Critical", "account_code blank")]})
add([er("EV-016", "6110", "1500.25", "0.00"), er("EV-016", "", "75.01", "0.00"), er("EV-016", "2010", "0.00", "1575.26")],
    {1: [("blank_account", "Critical", "account_code blank")]})
add([er("EV-017", "6150", "455.10", "0.00"), er("EV-017", "2010", "0.00", "455.10")])
add([er("EV-018", "6150", "389.65", "0.00"), er("EV-018", "2010", "0.00", "389.65")])
sup = GOODS_SUPPLIERS[0]
for k, (trn, why, ok) in enumerate([(trn_valid(), "valid 15-digit TRN starting 100", True),
                                    ("10045678901234", "14 digits", False), ("1004567890123456", "16 digits", False),
                                    ("TRN100456789012", "text prefix / letters", False),
                                    ("1.00456E+14", "Excel scientific notation", False)]):
    vno = f"EV-{19 + k:03d}"
    net = amount(1000, 9000)
    vat = vat_of(net)
    rowsv = [er(vno, "5010", f"{net:.2f}", "0.00", trn=trn, party=sup, net=f"{net:.2f}", vat=f"{vat:.2f}", code="SR"),
             er(vno, "1300", f"{vat:.2f}", "0.00"), er(vno, "2010", "0.00", f"{net + vat:.2f}")]
    if ok:
        add(rowsv, feats={0: [("valid_trn_control", f"TRN '{trn}' ({why}) must pass")]})
    else:
        add(rowsv, {0: [("invalid_trn", "Medium", f"TRN '{trn}' ({why})")]})
add([er("EV-024", "6110", "1820.70", "0.00"), er("EV-024", "1300", "91.04", "0.00"), er("EV-024", "2010", "0.00", "1911.74")])
add([er("EV-025", "6150", "2214.35", "0.00"), er("EV-025", "2010", "0.00", "2214.35")])
assert len(E) == 60, len(E)
for i, (r, _, _) in enumerate(E):
    r["line_id"] = f"E{i + 1:04d}"
# duplicate line_ids: EV-017 and EV-018 reuse the ids of the lines before them
dup_pairs = []
for vno in ["EV-017", "EV-018"]:
    idx = next(i for i, (r, _, _) in enumerate(E) if r["voucher_no"] == vno) + 1   # second line of the voucher
    E[idx][0]["line_id"] = E[idx - 1][0]["line_id"]
    E[idx][1].append(("duplicate_line_id", "Critical", f"line_id {E[idx][0]['line_id']} appears twice"))
for i, (r, errs, feats) in enumerate(E):
    for (t, sev, desc) in errs:
        answer_rows.append(["edge_cases.csv", i + 1, r["line_id"], r["voucher_no"], t, sev, desc, ""])
    for (t, desc) in feats:
        features.append(["edge_cases.csv", r["line_id"], r["voucher_no"], t, desc])
write_csv("edge_cases.csv", COLUMNS, [[r[c] for c in COLUMNS] for r, _, _ in E])

write_csv("answer_key.csv", ["file", "row_no", "line_id", "voucher_no", "error_type", "expected_severity", "description",
                             "related_line_id"], answer_rows)
write_csv("feature_key.csv", ["file", "line_id", "voucher_no", "feature", "description"], features)

if __name__ == "__main__":
    from collections import Counter
    print("dummy_gl lines", len(rows), "vouchers", len(vouchers))
    print(Counter((r[0], r[4]) for r in answer_rows))
    print(Counter((f[0], f[3]) for f in features))
