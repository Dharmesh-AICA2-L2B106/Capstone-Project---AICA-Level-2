#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DRN Tally TB Extractor  -  single-file tool
===========================================
Pulls the CURRENT-year and PREVIOUS-year ledger balances out of Tally (without changing the period in Tally) and writes ONE Excel file,
one row per ledger, in the
"Tally ledger export" layout that DRN FS Solution imports directly
(Name | Parent | PrimaryGroup | OpeningBalance | Net Debit | Net Credit | ClosingBalance | PY ClosingBalance | ...).

Sources
  1. Tally XML over HTTP  - recommended. Both years in one click, any company, no ODBC driver needed.
                            In Tally: F1 > Settings > Connectivity > Client/Server > Tally acts as "Server" (or "Both"), port 9000.
  2. Tally ODBC           - uses Tally's ODBC driver (DSN "TallyODBC64_9000"). ODBC cannot take dates, so it reads the period
                            open in Tally and derives the previous year from opening balances (balance sheet only).
  3. SQL database         - any database with an ODBC driver (SQL Server, MySQL, Postgres ...). You give the connection
                            string and a SELECT query; {from} and {to} are replaced with the period dates (YYYY-MM-DD).
  +  Power Query          - writes an Excel Power Query (M) script that calls Tally's XML port, if you prefer to
                            pull the data inside Excel.

Run:   python tally_tb_extractor.py            (opens the window)
       python tally_tb_extractor.py --cli --source xml --company "ABC Pvt Ltd" --fy 2025 --out ABC.xlsx
Libraries (openpyxl, pyodbc) are downloaded automatically the first time. Tkinter ships with Python.
Sign convention in the output = Tally export: CREDIT positive, DEBIT negative.
"""
import sys, os, re, io, csv, subprocess, importlib, datetime as dt, threading, queue, argparse
import urllib.request, urllib.error
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape as xesc

# --------------------------------------------------------------------------------------------------
# 0. Auto-install libraries
# --------------------------------------------------------------------------------------------------
REQUIRED = [("openpyxl", "openpyxl"), ("pyodbc", "pyodbc")]


def bootstrap():
    """Import each required library; pip-install what is missing (falls back to --user)."""
    missing = []
    for mod, pkg in REQUIRED:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(pkg)
    if not missing:
        return
    try:
        import pip  # noqa: F401
    except ImportError:
        subprocess.call([sys.executable, "-m", "ensurepip", "--upgrade"])
    for pkg in missing:
        print(f"[setup] Installing {pkg} ...")
        for extra in ([], ["--user"]):
            if subprocess.call([sys.executable, "-m", "pip", "install", "--quiet", *extra, pkg]) == 0:
                break
        else:
            print(f"[setup] Could not install {pkg}. " + ("ODBC / SQL sources will be unavailable." if pkg == "pyodbc" else ""))
    importlib.invalidate_caches()


if not os.environ.get("DRN_NO_BOOTSTRAP"):
    bootstrap()
try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
except ImportError:
    openpyxl = None
try:
    import pyodbc
except ImportError:
    pyodbc = None

# --------------------------------------------------------------------------------------------------
# 1. Helpers
# --------------------------------------------------------------------------------------------------
CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean(s):
    return CTRL.sub("", str(s if s is not None else "")).strip()


def fy_dates(start_year):
    return dt.date(start_year, 4, 1), dt.date(start_year + 1, 3, 31)


def fy_label(y):
    return f"FY {y % 100:02d}-{(y + 1) % 100:02d}"


def current_fy_start():
    t = dt.date.today()
    return t.year if t.month >= 4 else t.year - 1


def amt(v):
    """Tally amount -> float, CREDIT positive / DEBIT negative. Understands '1,234.00 Dr' / 'Cr' suffixes."""
    if v is None:
        return 0.0
    s = str(v).strip().replace(",", "")
    if not s:
        return 0.0
    m = re.search(r"\b(dr|cr)\.?$", s, re.I)
    sign = None
    if m:
        sign = -1 if m.group(1).lower() == "dr" else 1
        s = s[:m.start()].strip()
    try:
        x = float(s)
    except ValueError:
        return 0.0
    return sign * abs(x) if sign else x


def decode_tally(raw):
    """Tally may answer in UTF-8 or UTF-16 and can emit control-character references (e.g. &#4;) that break XML parsers."""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        t = raw.decode("utf-16", "replace")
    elif len(raw) > 3 and raw[1:2] == b"\x00" and raw[3:4] == b"\x00":      # UTF-16 LE without BOM (Tally report export)
        t = raw.decode("utf-16-le", "replace")
    else:
        t = raw.decode("utf-8", "replace")

    def bad(n):
        return n < 32 and n not in (9, 10, 13)
    t = re.sub(r"&#(\d+);", lambda m: "" if bad(int(m.group(1))) else m.group(0), t)
    t = re.sub(r"&#[xX]([0-9a-fA-F]+);", lambda m: "" if bad(int(m.group(1), 16)) else m.group(0), t)
    return CTRL.sub("", t)


def primary_groups(groups):
    """groups = {group: parent}. Returns function ledger_parent -> top-level (primary) group name."""
    def top(g):
        seen = set()
        while g not in seen:
            seen.add(g)
            p = groups.get(g)
            if p is None or clean(p).lower() in ("", "primary"):
                return g
            g = p
        return g
    return top


# --------------------------------------------------------------------------------------------------
# 2. Source: Tally XML over HTTP
# --------------------------------------------------------------------------------------------------
def coll_xml(coll_id, typ, fetch, company=None, frm=None, to=None):
    sv = "<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>"
    if company:
        sv += f"<SVCURRENTCOMPANY>{xesc(company)}</SVCURRENTCOMPANY>"
    if frm:
        sv += f"<SVFROMDATE>{frm:%Y%m%d}</SVFROMDATE><SVTODATE>{to:%Y%m%d}</SVTODATE>"
    return ("<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE>"
            f"<ID>{coll_id}</ID></HEADER><BODY><DESC><STATICVARIABLES>{sv}</STATICVARIABLES><TDL><TDLMESSAGE>"
            f'<COLLECTION NAME="{coll_id}" ISMODIFY="No"><TYPE>{typ}</TYPE><FETCH>{fetch}</FETCH></COLLECTION>'
            "</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>")


def tally_post(host, port, xml, timeout=600, utf16=False):
    data, ctype = (xml.encode("utf-16-le"), "text/xml;charset=utf-16") if utf16 else (xml.encode("utf-8"), "text/xml; charset=utf-8")
    req = urllib.request.Request(f"http://{host}:{port}", data=data, headers={"Content-Type": ctype})
    try:
        raw = urllib.request.urlopen(req, timeout=timeout).read()
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError(f"Cannot reach Tally at {host}:{port} ({e}). Open Tally, enable "
                           "F1 > Settings > Connectivity > Client/Server (Server or Both) and check the port.")
    text = decode_tally(raw)
    if "<LINEERROR>" in text:
        raise RuntimeError("Tally replied with an error: " + re.sub(r"<[^>]+>", " ", text)[:300].strip())
    return text


def _name_of(e):
    n = e.get("NAME")
    if n:
        return clean(n)
    n = e.findtext("NAME")
    if n:
        return clean(n)
    n = e.findtext(".//NAME")
    return clean(n) if n else ""


def xml_companies(host, port):
    t = tally_post(host, port, coll_xml("DRNCompanies", "Company", "Name,StartingFrom,BooksFrom"), 60)
    root = ET.fromstring(t)
    return sorted({_name_of(e) for e in root.iter("COMPANY") if _name_of(e)})


TB_BODY = r'''<?xml version="1.0" encoding="utf-8"?><ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Data</TYPE><ID>MyReportTrialBalanceForPeriod</ID></HEADER><BODY><DESC><STATICVARIABLES><SVFROMDATE>$fromDate$</SVFROMDATE><SVTODATE>$toDate$</SVTODATE><SVEXPORTFORMAT>ASCII (Comma Delimited)</SVEXPORTFORMAT></STATICVARIABLES><TDL><TDLMESSAGE><REPORT NAME="MyReportTrialBalanceForPeriod"><FORMS>MyForm</FORMS></REPORT><FORM NAME="MyForm"><PARTS>MyPart</PARTS></FORM><PART NAME="MyPart"><LINES>MyLine</LINES><REPEAT>MyLine : MyCollection</REPEAT><SCROLLED>Vertical</SCROLLED></PART><LINE NAME="MyLine"><FIELDS>FldName,FldParent,FldPrimaryGroup,FldOpeningBalance,FldNetDebit,FldNetCredit,FldClosingBalance,FldDescription</FIELDS></LINE><FIELD NAME="FldName"><SET>$$StringFindAndReplace:$Name:'"':'""'</SET></FIELD><FIELD NAME="FldParent"><SET>$$StringFindAndReplace:$Parent:'"':'""'</SET></FIELD><FIELD NAME="FldPrimaryGroup"><SET>if $$IsEmpty:$_PrimaryGroup then $$StrByCharCode:245 else $$StringFindAndReplace:$_PrimaryGroup:'"':'""'</SET></FIELD><FIELD NAME="FldOpeningBalance"><SET>$$StringFindAndReplace:(if $$IsDebit:$OpeningBalance then -$$NumValue:$OpeningBalance else $$NumValue:$OpeningBalance):"(-)":"-"</SET></FIELD><FIELD NAME="FldNetDebit"><SET>$$Number:$DebitTotals</SET></FIELD><FIELD NAME="FldNetCredit"><SET>$$Number:$CreditTotals</SET></FIELD><FIELD NAME="FldClosingBalance"><SET>$$StringFindAndReplace:(if $$IsDebit:$ClosingBalance then -$$NumValue:$ClosingBalance else $$NumValue:$ClosingBalance):"(-)":"-"</SET></FIELD><FIELD NAME="FldDescription"><SET>if $$IsEmpty:$Description then $$StrByCharCode:245 else $$StringFindAndReplace:$Description:'"':'""'</SET></FIELD><COLLECTION NAME="MyCollection"><TYPE>Ledger</TYPE></COLLECTION></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>'''


def _num(v):
    v = clean(v).replace("\u00f5", "").replace(",", "")
    neg = "(-)" in v
    v = v.replace("(-)", "")
    try:
        x = float(v) if v else 0.0
    except ValueError:
        x = 0.0
    return -abs(x) if neg else x


def tb_request(frm, to, company=None):
    body = TB_BODY.replace("$fromDate$", f"{frm:%Y%m%d}").replace("$toDate$", f"{to:%Y%m%d}")
    if company:
        body = body.replace("</SVTODATE>", f"</SVTODATE><SVCURRENTCOMPANY>{xesc(company)}</SVCURRENTCOMPANY>")
    return body


def xml_fetch(host, port, company, frm, to, log=print):
    """Trial balance for the period through the Tally report used in the DRN Power Query (CSV export, UTF-16).
    Gives Name, Parent, PrimaryGroup, Opening, Net Debit, Net Credit, Closing per ledger - credit +, debit -."""
    log(f"  asking Tally for the trial balance {frm:%d-%b-%Y} to {to:%d-%b-%Y} ...")
    text = tally_post(host, port, tb_request(frm, to, company), utf16=True)
    text = text.replace(",\r\n", "\r\n").replace(",\n", "\n")
    out = []
    for rec in csv.reader(io.StringIO(text)):
        if len(rec) < 7:
            continue
        name = clean(rec[0].replace("\u00f5", ""))
        if not name:
            continue
        out.append(dict(name=name, parent=clean(rec[1]).replace("\u00f5", ""), pg=clean(rec[2]).replace("\u00f5", ""),
                        open=_num(rec[3]), nd=abs(_num(rec[4])), nc=abs(_num(rec[5])), close=_num(rec[6])))
    if not out:
        raise RuntimeError("Tally returned no ledgers. Check that the company is open in Tally (or choose it) and the dates are inside its books.")
    return out


def stock_fetch(host, port, company, frm, to, log=print, timeout=300):
    """Stock-in-hand values from Tally for the period, by top-level stock group: [{group, open, close, items}] (positive rupees).
    Asks for stock GROUPS first (a handful of rows - light on Tally). Only if that returns nothing does it fall back to stock items
    (one valuation per item, which can keep Tally busy for minutes on large stock lists)."""
    def top(p):
        return clean(p).lower() in ("", "primary")
    log(f"  asking Tally for stock group values {frm:%d-%b-%Y} to {to:%d-%b-%Y} ...")
    text = tally_post(host, port, coll_xml("DRNStockGrp", "StockGroup", "Name,Parent,OpeningValue,ClosingValue", company, frm, to), timeout=timeout)
    out = []
    for e in ET.fromstring(text).iter("STOCKGROUP"):
        if not top(e.findtext("PARENT") or ""):
            continue                                                # sub-groups are already inside their parent's value
        out.append(dict(group=_name_of(e), open=abs(amt(e.findtext("OPENINGVALUE"))), close=abs(amt(e.findtext("CLOSINGVALUE"))), items=None))
    if not out:
        log("  no stock groups returned - reading stock items (slower) ...")
        text = tally_post(host, port, coll_xml("DRNStock", "StockItem", "Name,Parent,OpeningValue,ClosingValue", company, frm, to), timeout=max(timeout, 900))
        groups = {}
        for e in ET.fromstring(text).iter("STOCKITEM"):
            g = clean(e.findtext("PARENT")) or "Primary"
            r = groups.setdefault(g, dict(group=g, open=0.0, close=0.0, items=0))
            r["open"] += abs(amt(e.findtext("OPENINGVALUE"))); r["close"] += abs(amt(e.findtext("CLOSINGVALUE"))); r["items"] += 1
        out = list(groups.values())
    return sorted((dict(r, open=round(r["open"], 2), close=round(r["close"], 2)) for r in out), key=lambda r: -r["close"])


def asset_entries(host, port, company, frm, to, ledgers, log=print):
    """Every voucher entry that hits one of the given fixed-asset ledgers in the period: actual dates, voucher type / number,
    party and narration. Reads the period's vouchers in ONE collection request (a few seconds even for thousands of vouchers).
    Returns [{guid, date 'YYYY-MM-DD', type, number, party, narration, ledger, debit, credit, others}] (amounts positive)."""
    names = {clean(n) for n in ledgers}
    log(f"  reading vouchers {frm:%d-%b-%Y} to {to:%d-%b-%Y} for {len(names)} asset ledger(s) ...")
    fetch = ("Date,VoucherTypeName,VoucherNumber,Narration,PartyLedgerName,IsCancelled,IsOptional,"
             "AllLedgerEntries.LedgerName,AllLedgerEntries.Amount,LedgerEntries.LedgerName,LedgerEntries.Amount")
    text = tally_post(host, port, coll_xml("DRNVch", "Voucher", fetch, company, frm, to), timeout=300)
    out = []
    for v in ET.fromstring(text).iter("VOUCHER"):
        if clean(v.findtext("ISCANCELLED") or "").lower() == "yes" or clean(v.findtext("ISOPTIONAL") or "").lower() == "yes" or clean(v.findtext("ISDELETED") or "").lower() == "yes":
            continue
        d = clean(v.findtext("DATE") or "")
        if len(d) != 8:
            continue
        lines = []
        for tag in ("ALLLEDGERENTRIES.LIST", "LEDGERENTRIES.LIST"):      # Tally repeats the same entries under both names: use one
            items = v.findall(tag)
            if not items:
                continue
            for le in items:
                led = clean(le.findtext("LEDGERNAME") or "")
                if led:
                    lines.append((led, amt(le.findtext("AMOUNT"))))
            break
        hit = [(l, a) for l, a in lines if l in names]
        if not hit:
            continue
        others = sorted({l for l, _ in lines if l not in names})
        for led, a in hit:
            if abs(a) < 0.005:
                continue
            out.append(dict(guid=clean(v.findtext("GUID") or ""), date=f"{d[:4]}-{d[4:6]}-{d[6:]}", type=clean(v.findtext("VOUCHERTYPENAME") or ""),
                            number=clean(v.findtext("VOUCHERNUMBER") or ""), party=clean(v.findtext("PARTYLEDGERNAME") or ""), narration=clean(v.findtext("NARRATION") or ""),
                            ledger=led, debit=round(-a, 2) if a < 0 else 0.0, credit=round(a, 2) if a > 0 else 0.0, others=others[:6]))
    out.sort(key=lambda r: (r["date"], r["ledger"]))
    return out


# --------------------------------------------------------------------------------------------------
# 3. Source: Tally ODBC and generic SQL (pyodbc)
# --------------------------------------------------------------------------------------------------
def need_pyodbc():
    if pyodbc is None:
        raise RuntimeError("pyodbc could not be installed. Run:  python -m pip install pyodbc   (needs an ODBC driver on the PC).")


def odbc_fetch(conn_str, log=print):
    """Tally ODBC returns the period that is currently selected in Tally."""
    need_pyodbc()
    cn = pyodbc.connect(conn_str, autocommit=True, timeout=60)
    cur = cn.cursor()
    rows = None
    try:
        cur.execute("SELECT $Name, $Parent, $_PrimaryGroup, $OpeningBalance, $ClosingBalance FROM Ledger")
        rows = [(r[0], r[1], r[2], r[3], r[4]) for r in cur.fetchall()]
    except pyodbc.Error:
        log("  $_PrimaryGroup not available - resolving groups from the Group table")
    if rows is None:
        cur.execute("SELECT $Name, $Parent, $OpeningBalance, $ClosingBalance FROM Ledger")
        led = cur.fetchall()
        groups = {}
        for q in ("SELECT $Name, $Parent FROM Group", 'SELECT $Name, $Parent FROM "Group"'):
            try:
                cur.execute(q)
                groups = {clean(r[0]): clean(r[1]) for r in cur.fetchall()}
                break
            except pyodbc.Error:
                continue
        top = primary_groups(groups)
        rows = [(r[0], r[1], top(clean(r[1])) if clean(r[1]) else "", r[2], r[3]) for r in led]
    cn.close()
    out = [dict(name=clean(n), parent=clean(p), pg=clean(pg), open=amt(o), close=amt(c)) for n, p, pg, o, c in rows if clean(n)]
    if not out:
        raise RuntimeError("The ODBC query returned no ledgers.")
    return out


DEFAULT_SQL = ("SELECT LedgerName AS Name, ParentGroup AS Parent, PrimaryGroup, OpeningBalance, ClosingBalance\n"
               "FROM TrialBalance\nWHERE PeriodFrom = '{from}' AND PeriodTo = '{to}'")


def sql_fetch(conn_str, query, frm, to, cr_positive=True, log=print):
    """Result columns (any case): Name|Ledger, Parent|Group, PrimaryGroup (optional), OpeningBalance, ClosingBalance."""
    need_pyodbc()
    q = query.replace("{from}", f"{frm:%Y-%m-%d}").replace("{to}", f"{to:%Y-%m-%d}")
    cn = pyodbc.connect(conn_str, autocommit=True, timeout=60)
    cur = cn.cursor()
    cur.execute(q)
    cols = [re.sub(r"[^a-z]", "", c[0].lower()) for c in cur.description]

    def ix(*names):
        for n in names:
            if n in cols:
                return cols.index(n)
        return -1
    i_n, i_p, i_g = ix("name", "ledger", "ledgername"), ix("parent", "group", "parentgroup", "under"), ix("primarygroup")
    i_o, i_c = ix("openingbalance", "opening"), ix("closingbalance", "closing", "balance")
    if i_n < 0 or i_c < 0:
        raise RuntimeError(f"Query must return Name and ClosingBalance columns; got: {', '.join(c[0] for c in cur.description)}")
    f = 1 if cr_positive else -1
    out = []
    for r in cur.fetchall():
        name = clean(r[i_n])
        if not name:
            continue
        parent = clean(r[i_p]) if i_p >= 0 else ""
        out.append(dict(name=name, parent=parent, pg=clean(r[i_g]) if i_g >= 0 else parent,
                        open=f * amt(r[i_o]) if i_o >= 0 else 0.0, close=f * amt(r[i_c])))
    cn.close()
    if not out:
        raise RuntimeError("The SQL query returned no rows.")
    return out


def _hkey(x):
    return re.sub(r"[^a-z]", "", str(x if x is not None else "").lower())


def read_table(path):
    """Rows of the first sheet / CSV that looks like a Tally trial balance (header contains Name + ClosingBalance)."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".csv", ".txt"):
        with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
            sheets = [list(csv.reader(f))]
    else:
        if openpyxl is None:
            raise RuntimeError("openpyxl is not installed. Run:  python -m pip install openpyxl")
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        sheets = [[list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets]
    for rows in sheets:
        for i, r in enumerate(rows[:30]):
            k = [_hkey(c) for c in r]
            if "name" in k and "closingbalance" in k:
                return rows[i:]
    raise RuntimeError("No sheet with Name and ClosingBalance columns found in that file.")


def file_fetch(path, which, fy, cy_rows=None, log=print):
    """Read the output of the DRN Power Query (Excel / CSV). Handles
       (a) one query with an FY column (stacked years, e.g. '2025-26' / '2024-25'), or
       (b) one row per ledger with a 'PY ClosingBalance' column, or
       (c) a single year only (previous year then derived from opening balances)."""
    rows = read_table(path)
    H = [_hkey(c) for c in rows[0]]

    def ix(*names):
        for n in names:
            if n in H:
                return H.index(n)
        return -1
    c = dict(name=ix("name"), parent=ix("parent"), pg=ix("primarygroup"), open=ix("openingbalance"), nd=ix("netdebit"),
             nc=ix("netcredit"), close=ix("closingbalance"), py=ix("pyclosingbalance", "previousyearclosingbalance"), pyopen=ix("pyopeningbalance", "previousyearopeningbalance"), fy=ix("fy", "financialyear", "year"))
    g = lambda r, i: r[i] if 0 <= i < len(r) else None
    body = [r for r in rows[1:] if clean(g(r, c["name"]))]

    def rec(r, close_i):
        return dict(name=clean(g(r, c["name"])), parent=clean(g(r, c["parent"])).replace("\u00f5", ""), pg=clean(g(r, c["pg"])).replace("\u00f5", ""),
                    open=amt(g(r, c["open"])), nd=abs(amt(g(r, c["nd"]))), nc=abs(amt(g(r, c["nc"]))), close=amt(g(r, close_i)))
    if c["py"] >= 0:                                                    # (b)
        log("  one-row-per-ledger file with a PY ClosingBalance column")
        if which == "cy":
            return [rec(r, c["close"]) for r in body]
        return [dict(rec(r, c["py"]), open=(amt(g(r, c["pyopen"])) if c["pyopen"] >= 0 and g(r, c["pyopen"]) not in (None, "") else None), nd=None, nc=None) for r in body]
    if c["fy"] >= 0:                                                    # (a)
        def start(v):
            m = re.search(r"(\d{4})|(\d{2})", str(v or ""))
            return (int(m.group(1)) if m.group(1) else 2000 + int(m.group(2))) if m else None
        years = sorted({start(g(r, c["fy"])) for r in body} - {None}, reverse=True)
        want = fy if which == "cy" else fy - 1
        if want not in years:
            raise RuntimeError(f"FY {want}-{(want + 1) % 100:02d} not found in the file (it has: {', '.join(str(y) + '-' + str((y + 1) % 100).zfill(2) for y in years)}). Change the year in step 3.")
        log(f"  stacked file; using rows tagged {want}-{(want + 1) % 100:02d}")
        out, seen = [], set()
        for r in body:
            if start(g(r, c["fy"])) == want and clean(g(r, c["name"])) not in seen:
                seen.add(clean(g(r, c["name"])))
                out.append(rec(r, c["close"]))
        return out
    if which == "cy":                                                   # (c)
        return [rec(r, c["close"]) for r in body]
    if not cy_rows:
        raise RuntimeError("Fetch the current year first.")
    log("  single-year file: previous year derived from opening balances (balance sheet only)")
    return py_from_opening(cy_rows)


# --------------------------------------------------------------------------------------------------
# 4. Power Query (M) script generator
# --------------------------------------------------------------------------------------------------
def power_query_script(host, port, company, fy, company_py=None):
    """One Power Query: current + previous year from the Tally trial-balance report, merged to one row per ledger.
    CompanyCY / CompanyPY choose the Tally company for each year (they differ when Tally keeps a company per financial year)."""
    body = TB_BODY.replace("</SVTODATE>", "</SVTODATE><SVCURRENTCOMPANY>$company$</SVCURRENTCOMPANY>").replace('"', '""')
    q = lambda t: (t or "").replace('"', '""')
    return f"""/*
    DRN - Trial balance, current + previous year, ONE row per ledger
    Edit only FYStart (start year of the current financial year, e.g. 2025 for FY 2025-26), and the two company names if Tally
    keeps a separate company for each year (copy the names exactly from Tally's company list). Leave a name "" to use the company
    that is active in Tally. Then refresh.
    Output: Name, Parent, PrimaryGroup, OpeningBalance, Net Debit, Net Credit, ClosingBalance (current year),
            PY ClosingBalance (previous year), PY OpeningBalance (start of the previous year), Description.   Credit = positive, Debit = negative.
    Tally must be open with BOTH companies loaded and Client/Server enabled (port {port}).
*/
let
    FYStart = {fy},
    CompanyCY = "{q(company)}",
    CompanyPY = "{q(company_py or company)}",
    url = "http://{host}:{port}",
    _body = "{body}",
    Cols = {{ "Name", "Parent", "PrimaryGroup", "OpeningBalance", "Net Debit", "Net Credit", "ClosingBalance", "Description" }},
    fnTB = (fy as number, company as text) as table =>
        let
            fromDate = Date.ToText(#date(fy, 4, 1), "yyyyMMdd"),
            toDate = Date.ToText(#date(fy + 1, 3, 31), "yyyyMMdd"),
            body0 = Text.Replace(Text.Replace(_body, "$fromDate$", fromDate), "$toDate$", toDate),
            body = Text.Replace(Text.Replace(body0, "$company$", Text.Replace(Text.Replace(company, "&", "&amp;"), "<", "&lt;")), "<SVCURRENTCOMPANY></SVCURRENTCOMPANY>", ""),
            Source = Csv.Document(Text.Replace(Text.FromBinary(Web.Contents(url, [Content=Text.ToBinary(body, TextEncoding.Utf16), Headers=[#"Content-Type"="text/xml;charset=utf-16"]]), TextEncoding.Utf16), ",#(cr,lf)", "#(cr,lf)"), Cols),
            Tbl01 = Table.TransformColumns(Source, {{ {{ "PrimaryGroup", each Text.Replace(_,"õ","") }}, {{"OpeningBalance", each Number.FromText(if _ = "" then "0.00" else Text.Replace(Text.Replace(_,",",""),"(-)","-")) as number}}, {{"ClosingBalance", each Number.FromText(if _ = "" then "0.00" else Text.Replace(Text.Replace(_,",",""),"(-)","-")) as number}}, {{ "Description", each Text.Replace(_,"õ","") }} }}),
            Tbl02 = Table.TransformColumnTypes(Tbl01, {{{{"OpeningBalance", type number}}, {{"ClosingBalance", type number}}, {{"Net Debit", type number}}, {{"Net Credit", type number}}}})
        in
            Tbl02,
    CY = fnTB(FYStart, CompanyCY),
    PY = Table.RenameColumns(Table.SelectColumns(fnTB(FYStart - 1, CompanyPY), {{"Name", "ClosingBalance", "OpeningBalance"}}), {{{{"ClosingBalance", "PY ClosingBalance"}}, {{"OpeningBalance", "PY OpeningBalance"}}}}),
    Joined = Table.NestedJoin(CY, {{"Name"}}, PY, {{"Name"}}, "PYT", JoinKind.LeftOuter),
    Expanded = Table.ExpandTableColumn(Joined, "PYT", {{"PY ClosingBalance", "PY OpeningBalance"}}),
    Filled = Table.TransformColumns(Expanded, {{{{"PY ClosingBalance", each if _ = null then 0 else _, type number}}, {{"PY OpeningBalance", each if _ = null then 0 else _, type number}}}}),
    Ordered = Table.ReorderColumns(Filled, {{"Name", "Parent", "PrimaryGroup", "OpeningBalance", "Net Debit", "Net Credit", "ClosingBalance", "PY ClosingBalance", "PY OpeningBalance", "Description"}}),
    NoNil = Table.SelectRows(Ordered, each [OpeningBalance] <> 0 or [ClosingBalance] <> 0 or [PY ClosingBalance] <> 0 or [PY OpeningBalance] <> 0 or [#"Net Debit"] <> 0 or [#"Net Credit"] <> 0),
    FYCur = Table.AddColumn(NoNil, "FY " & Text.End(Text.From(FYStart), 2) & "-" & Text.End(Text.From(FYStart + 1), 2), each ""),
    FYPrev = Table.AddColumn(FYCur, "FY " & Text.End(Text.From(FYStart - 1), 2) & "-" & Text.End(Text.From(FYStart), 2), each "")
in
    FYPrev
"""


# --------------------------------------------------------------------------------------------------
# 5. Excel writer (Tally ledger-export layout)
# --------------------------------------------------------------------------------------------------
HEADERS = ["Name", "Parent", "PrimaryGroup", "OpeningBalance", "Net Debit", "Net Credit", "ClosingBalance", "Description", "Notes"]


def is_pl(r):
    return clean(r["parent"]).lower() == "primary" and re.match(r"profit\s*(&|and)\s*loss", r["name"], re.I)


NOMINAL = re.compile(r"sales|income|purchase|expense", re.I)


def py_from_opening(cy):
    """No second period available (e.g. Tally ODBC): previous-year closing of a balance-sheet ledger = this year's
    opening balance. Income / expense ledgers cannot be derived this way, so they are nil for the previous year."""
    return [dict(r, close=0.0 if NOMINAL.search(r["pg"] or r["parent"]) else r["open"], open=None) for r in cy]


def merge_years(cy, py):
    """One record per ledger name: current-year opening / closing and previous-year closing."""
    m = {}
    for r in cy:
        m[r["name"]] = dict(name=r["name"], parent=r["parent"], pg=r["pg"], open=r["open"], close=r["close"], pyclose=0.0, pyopen=0.0 if py else None, nd=r.get("nd"), nc=r.get("nc"))
    for r in (py or []):
        if r["name"] in m:
            m[r["name"]]["pyclose"] = r["close"]; m[r["name"]]["pyopen"] = r.get("open")     # balance at the START of the previous year (None = unknown)
        else:
            m[r["name"]] = dict(name=r["name"], parent=r["parent"], pg=r["pg"], open=0.0, close=0.0, pyclose=r["close"], pyopen=r.get("open"))
    return list(m.values())


def write_excel(path, cy, py, fy, skip_nil=True):
    """Tally ledger-export layout, ONE row per ledger: ClosingBalance = current year, PYClosingBalance = previous year."""
    if openpyxl is None:
        raise RuntimeError("openpyxl is not installed. Run:  python -m pip install openpyxl")
    rows = merge_years(cy, py)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = fy_label(fy)
    ws.append(HEADERS[:7] + ["PY ClosingBalance", "PY OpeningBalance", "Description", fy_label(fy), fy_label(fy - 1)])
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="E3EEEA")
    n = 0
    for r in rows:
        if skip_nil and abs(r["open"]) < 0.005 and abs(r["close"]) < 0.005 and abs(r["pyclose"]) < 0.005 and abs(r.get("pyopen") or 0) < 0.005:
            continue
        mv = round(r["close"] - r["open"], 2)          # derived movement (only used when Tally's own totals are not available)
        nd = r["nd"] if r.get("nd") is not None else (round(-mv, 2) if mv < 0 else 0)
        nc = r["nc"] if r.get("nc") is not None else (mv if mv > 0 else 0)
        ws.append([r["name"], r["parent"] or "Primary", "" if is_pl(r) else r["pg"], r["open"], nd, nc, r["close"], r["pyclose"], "" if r.get("pyopen") is None else r["pyopen"], "", "", ""])
        n += 1
    for col, w in zip("ABCDEFGHIJKL", (42, 30, 26, 16, 16, 16, 16, 18, 18, 12, 10, 10)):
        ws.column_dimensions[col].width = w
    for col in "DEFGHI":
        for cell in ws[col][1:]:
            cell.number_format = "#,##0.00"
    ws.freeze_panes = "A2"
    rm = wb.create_sheet("Read me")
    for line in ["Created by DRN Tally TB Extractor - one row per ledger.",
                 "ClosingBalance = " + fy_label(fy) + " (current year);  PY ClosingBalance = " + fy_label(fy - 1) + " (previous year);  PY OpeningBalance = balance at the start of the previous year (needed for the previous-year cash flow).",
                 "Credit balances are POSITIVE, debit balances NEGATIVE (same as Tally's ledger export).",
                 "Net Debit / Net Credit are Tally's period totals (derived as closing - opening only for sources that do not supply them).",
                 "Closing stock is not a ledger in Tally - enter it in the studio's Inventories step.",
                 "Import this file in DRN FS Solution > Trial balance > Choose file."]:
        rm.append([line])
    rm.column_dimensions["A"].width = 120
    wb.save(path)
    return n, n


def summary(rows):
    if not rows:
        return "-"
    rest = sum(r["close"] for r in rows if not is_pl(r))
    nominal = sum(r["close"] for r in rows if re.search(r"sales|income|purchase|expense", r["pg"], re.I))
    return f"{len(rows)} ledgers | sum of closing excl. P&L A/c = {rest:,.2f} | profit per income/expense ledgers = {nominal:,.2f}"


# --------------------------------------------------------------------------------------------------
# 6. Common fetch entry (used by GUI and CLI)
# --------------------------------------------------------------------------------------------------
def fetch_period(cfg, which, log=print, cy_rows=None):
    """Both years are read without touching Tally's own period: XML / SQL pass the dates in the request;
    ODBC (which cannot take dates) reads Tally's current period once and derives the previous year from opening balances."""
    fy = cfg["fy"] - (0 if which == "cy" else 1)
    frm, to = fy_dates(fy)
    if cfg["source"] == "file":
        if not cfg.get("file"):
            raise RuntimeError("Choose the Power Query output file first.")
        return file_fetch(cfg["file"], which, cfg["fy"], cy_rows, log)
    if cfg["source"] == "odbc":
        if which == "cy":
            log("Fetching current period via Tally ODBC (the period selected in Tally) ...")
            return odbc_fetch(cfg["conn"], log)
        if not cy_rows:
            raise RuntimeError("Fetch the current year first.")
        log("Previous year derived from opening balances (balance-sheet ledgers only; ODBC cannot read another period).")
        return py_from_opening(cy_rows)
    log(f"Fetching {'current' if which == 'cy' else 'previous'} year {fy_label(fy)} via {cfg['source']} ...")
    if cfg["source"] == "xml":
        comp = (cfg.get("company_py") or cfg["company"]) if which == "py" else cfg["company"]
        if which == "py" and cfg.get("company_py"):
            log(f"  previous year read from company: {comp}")
        return xml_fetch(cfg["host"], cfg["port"], comp, frm, to, log)
    if cfg["source"] == "sql":
        return sql_fetch(cfg["conn"], cfg["query"], frm, to, cfg.get("cr_positive", True), log)
    raise RuntimeError("Unknown source")


# --------------------------------------------------------------------------------------------------
# 7. GUI
# --------------------------------------------------------------------------------------------------
def run_gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, scrolledtext

    root = tk.Tk()
    root.title("DRN Tally TB Extractor")
    root.geometry("860x760")
    q = queue.Queue()
    data = {"cy": None, "py": None}
    v = dict(source=tk.StringVar(value="xml"), host=tk.StringVar(value="localhost"), port=tk.StringVar(value="9000"),
             company=tk.StringVar(), company_py=tk.StringVar(), fy=tk.IntVar(value=current_fy_start()),
             conn=tk.StringVar(value="DSN=TallyODBC64_9000"), file=tk.StringVar(), skip=tk.BooleanVar(value=True), crpos=tk.BooleanVar(value=True))

    def log(m):
        q.put(m)

    def pump():
        try:
            while True:
                t = q.get_nowait()
                log_box.configure(state="normal")
                log_box.insert("end", t + "\n")
                log_box.see("end")
                log_box.configure(state="disabled")
        except queue.Empty:
            pass
        root.after(150, pump)

    pad = dict(padx=8, pady=4)
    src = ttk.LabelFrame(root, text="1. Source")
    src.pack(fill="x", **pad)
    for t, val in (("Tally XML (HTTP)  - recommended", "xml"), ("Tally ODBC", "odbc"), ("SQL database (ODBC)", "sql"), ("Power Query output (Excel / CSV)", "file")):
        ttk.Radiobutton(src, text=t, value=val, variable=v["source"], command=lambda: show()).pack(side="left", padx=10, pady=6)

    box = ttk.LabelFrame(root, text="2. Connection")
    box.pack(fill="x", **pad)
    f_xml, f_odbc, f_sql, f_file = ttk.Frame(box), ttk.Frame(box), ttk.Frame(box), ttk.Frame(box)
    ttk.Label(f_xml, text="Host").grid(row=0, column=0, sticky="w")
    ttk.Entry(f_xml, textvariable=v["host"], width=16).grid(row=0, column=1, padx=4)
    ttk.Label(f_xml, text="Port").grid(row=0, column=2, sticky="w")
    ttk.Entry(f_xml, textvariable=v["port"], width=7).grid(row=0, column=3, padx=4)
    ttk.Label(f_xml, text="Company (open in Tally)").grid(row=1, column=0, sticky="w", pady=4)
    cb = ttk.Combobox(f_xml, textvariable=v["company"], width=52)
    cb.grid(row=1, column=1, columnspan=3, padx=4, sticky="w")
    ttk.Button(f_xml, text="Load companies", command=lambda: bg(load_companies)).grid(row=1, column=4, padx=4)
    ttk.Label(f_xml, text="Previous-year company").grid(row=2, column=0, sticky="w", pady=4)
    cb2 = ttk.Combobox(f_xml, textvariable=v["company_py"], width=52)
    cb2.grid(row=2, column=1, columnspan=3, padx=4, sticky="w")
    ttk.Label(f_xml, text="Leave blank if one company holds both years. If Tally keeps a separate company per year, pick the FY 24-25 company here (it must be loaded in Tally).",
              foreground="#555", wraplength=760, justify="left").grid(row=3, column=0, columnspan=5, sticky="w")
    ttk.Label(f_odbc, text="ODBC connection string").grid(row=0, column=0, sticky="w")
    ttk.Entry(f_odbc, textvariable=v["conn"], width=70).grid(row=0, column=1, padx=4)
    ttk.Label(f_odbc, text="ODBC cannot take dates: it reads the period open in Tally; previous year is derived from opening balances (no P&L comparatives). Use Tally XML for full comparatives.",
              foreground="#555").grid(row=1, column=0, columnspan=2, sticky="w")
    ttk.Label(f_sql, text="ODBC connection string").grid(row=0, column=0, sticky="w")
    sql_conn = tk.StringVar(value="DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost;DATABASE=Tally;Trusted_Connection=yes;")
    ttk.Entry(f_sql, textvariable=sql_conn, width=80).grid(row=0, column=1, padx=4)
    ttk.Label(f_sql, text="Query ({from} / {to} = period dates)").grid(row=1, column=0, sticky="nw")
    sql_box = scrolledtext.ScrolledText(f_sql, width=78, height=5)
    sql_box.insert("1.0", DEFAULT_SQL)
    sql_box.grid(row=1, column=1, padx=4, pady=4)
    ttk.Checkbutton(f_sql, text="Balances in query: credit positive (untick if debit positive)", variable=v["crpos"]).grid(row=2, column=1, sticky="w")

    ttk.Label(f_file, text="Excel / CSV saved from the Power Query").grid(row=0, column=0, sticky="w")
    ttk.Entry(f_file, textvariable=v["file"], width=64).grid(row=0, column=1, padx=4)
    ttk.Button(f_file, text="Browse...", command=lambda: v["file"].set(filedialog.askopenfilename(
        filetypes=[("Excel / CSV", "*.xlsx *.xlsm *.csv *.txt"), ("All files", "*.*")]) or v["file"].get())).grid(row=0, column=2)
    ttk.Label(f_file, text="Works with the PQ output with an FY column (both years stacked), or the one-row-per-ledger query with PY ClosingBalance. "
                           "The years are picked using step 3.", foreground="#555", wraplength=760, justify="left").grid(row=1, column=0, columnspan=3, sticky="w", pady=4)

    def show():
        for f in (f_xml, f_odbc, f_sql, f_file):
            f.pack_forget()
        {"xml": f_xml, "odbc": f_odbc, "sql": f_sql, "file": f_file}[v["source"].get()].pack(fill="x", padx=8, pady=6)
    show()

    per = ttk.LabelFrame(root, text="3. Financial year")
    per.pack(fill="x", **pad)
    ttk.Label(per, text="Current year starts 1-Apr of").pack(side="left", padx=6)
    ttk.Spinbox(per, from_=2000, to=2100, textvariable=v["fy"], width=7, command=lambda: lbl()).pack(side="left")
    pl = ttk.Label(per, text="")
    pl.pack(side="left", padx=12)

    def lbl():
        try:
            y = int(v["fy"].get())
            pl.config(text=f"Current {fy_label(y)}   |   Previous {fy_label(y - 1)}")
        except (tk.TclError, ValueError):
            pass
    lbl()
    v["fy"].trace_add("write", lambda *_: lbl())

    act = ttk.LabelFrame(root, text="4. Fetch and export")
    act.pack(fill="x", **pad)
    status = ttk.Label(root, text="Nothing fetched yet.", foreground="#444")

    def cfg():
        s = v["source"].get()
        return dict(source=s, host=v["host"].get().strip(), port=v["port"].get().strip(), company=v["company"].get().strip(),
                    fy=int(v["fy"].get()), conn=sql_conn.get().strip() if s == "sql" else v["conn"].get().strip(),
                    query=sql_box.get("1.0", "end").strip(), cr_positive=v["crpos"].get(), file=v["file"].get().strip(),
                    company_py=v["company_py"].get().strip())

    def refresh():
        status.config(text=f"CY: {summary(data['cy'])}\nPY: {summary(data['py'])}")

    def bg(fn, *a):
        def run():
            try:
                fn(*a)
            except Exception as e:  # shown in the log, never crashes the window
                log(f"ERROR: {e}")
        threading.Thread(target=run, daemon=True).start()

    def load_companies():
        c = cfg()
        names = xml_companies(c["host"], c["port"])
        root.after(0, lambda: (cb.configure(values=names), cb2.configure(values=names)))
        if names and not v["company"].get():
            root.after(0, lambda: v["company"].set(names[0]))
        log(f"{len(names)} company(ies) found: {', '.join(names[:8])}")

    def do(which):
        c = cfg()
        if c["source"] == "xml" and not c["company"]:
            log("No company chosen - using the company currently active in Tally.")
        which_list = ["cy", "py"] if which == "both" else [which]
        for w in which_list:
            data[w] = fetch_period(c, w, log, data['cy'])
            log(f"  done: {summary(data[w])}")
        if c["source"] == "xml" and data["cy"] and data["py"] and not c.get("company_py"):
            nom = lambda rows: sum(abs(r["close"]) for r in rows if NOMINAL.search(r["pg"] or r["parent"]))
            if nom(data["cy"]) > 0.5 and nom(data["py"]) < 0.5:
                log("WARNING: the previous year has no income / expense in this company - its books probably start in the current year. "
                    "Pick the separate FY 24-25 company in 'Previous-year company' and fetch again.")
        root.after(0, refresh)

    def export():
        if not data["cy"]:
            raise RuntimeError("Fetch the current year first.")
        c = cfg()
        name = re.sub(r'[\\/:*?"<>|]+', "", c["company"] or "Tally") + f" - Tally TB - {fy_label(c['fy'])}.xlsx"
        path = {"p": None}
        ev = threading.Event()

        def ask():
            path["p"] = filedialog.asksaveasfilename(defaultextension=".xlsx", initialfile=name, filetypes=[("Excel", "*.xlsx")])
            ev.set()
        root.after(0, ask)
        ev.wait()
        if not path["p"]:
            return
        n1, n2 = write_excel(path["p"], data["cy"], data["py"], c["fy"], v["skip"].get())
        log(f"Saved {path['p']}  ({n1} ledgers, one row each). Import it in the studio's Trial balance step.")

    def pq():
        c = cfg()
        p = {"p": None}
        ev = threading.Event()

        def ask():
            p["p"] = filedialog.asksaveasfilename(defaultextension=".pq", initialfile="Tally_TB_PowerQuery.pq", filetypes=[("Power Query M", "*.pq"), ("Text", "*.txt")])
            ev.set()
        root.after(0, ask)
        ev.wait()
        if p["p"]:
            with open(p["p"], "w", encoding="utf-8") as f:
                f.write(power_query_script(c["host"], c["port"], c["company"], c["fy"], c.get("company_py")))
            log(f"Power Query script saved: {p['p']}")

    for t, fn in (("Fetch CURRENT year", lambda: bg(do, "cy")), ("Fetch PREVIOUS year", lambda: bg(do, "py")),
                  ("Fetch BOTH", lambda: bg(do, "both")), ("Export Excel (for the studio)", lambda: bg(export)),
                  ("Save Power Query script", lambda: bg(pq))):
        ttk.Button(act, text=t, command=fn).pack(side="left", padx=5, pady=8)
    ttk.Checkbutton(root, text="Leave out ledgers that are nil in the year (smaller file)", variable=v["skip"]).pack(anchor="w", padx=14)
    status.pack(fill="x", padx=12, pady=4)
    log_box = scrolledtext.ScrolledText(root, height=14, state="disabled")
    log_box.pack(fill="both", expand=True, **pad)
    if pyodbc is None:
        log("Note: pyodbc is not installed - only the Tally XML source will work.")
    pump()
    root.mainloop()


# --------------------------------------------------------------------------------------------------
# 8. CLI
# --------------------------------------------------------------------------------------------------
def run_cli(a):
    c = dict(source=a.source, host=a.host, port=a.port, company=a.company, company_py=a.company_py, fy=a.fy or current_fy_start(), conn=a.conn, file=a.file,
             query=open(a.query_file, encoding="utf-8").read() if a.query_file else DEFAULT_SQL, cr_positive=not a.dr_positive)

    cy = fetch_period(c, "cy", print)
    py = fetch_period(c, "py", print, cy)
    print("CY:", summary(cy), "\nPY:", summary(py))
    out = a.out or f"Tally TB {fy_label(c['fy'])}.xlsx"
    n1, n2 = write_excel(out, cy, py, c["fy"], not a.keep_nil)
    print(f"Saved {out} ({n1} ledgers, one row each)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Extract current + previous year Tally trial balance to Excel.")
    ap.add_argument("--cli", action="store_true", help="run without the window")
    ap.add_argument("--source", choices=["xml", "odbc", "sql", "file"], default="xml")
    ap.add_argument("--file", help="Power Query output (Excel / CSV) for --source file")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", default="9000")
    ap.add_argument("--company", default="")
    ap.add_argument("--company-py", default="", help="separate company holding the previous year (if any)")
    ap.add_argument("--fy", type=int, help="start year of current FY, e.g. 2025 for FY 25-26")
    ap.add_argument("--conn", default="DSN=TallyODBC64_9000", help="ODBC connection string (odbc / sql sources)")
    ap.add_argument("--query-file", help="SQL file using {from} / {to}")
    ap.add_argument("--dr-positive", action="store_true", help="SQL balances are debit-positive")
    ap.add_argument("--keep-nil", action="store_true", help="keep ledgers with nil balances")
    ap.add_argument("--out")
    args = ap.parse_args()
    if args.cli:
        try:
            run_cli(args)
        except Exception as e:
            sys.exit(f"ERROR: {e}")
    else:
        try:
            run_gui()
        except ImportError:
            sys.exit("Tkinter is missing from this Python install - use --cli, or reinstall Python with the 'tcl/tk' option.")
