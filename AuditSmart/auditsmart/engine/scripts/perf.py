"""Performance harness (prompt 3.11): synthetic GL of N lines -> import -> validate -> JE.

    .venv/bin/python scripts/perf.py --lines 1000000 [--workdir /tmp/perf] [--report]

Synthetic data only (balanced two/three-line vouchers across FY2025). Every stage goes
through the same services and job path the API uses (JOB_EAGER, temporary SQLite DB and
storage). Peak RSS is the process high-water mark after each stage. ``--report`` rewrites
the results table in ../docs/PERFORMANCE.md.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import random
import resource
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ENGINE = Path(__file__).resolve().parents[1]
HEADERS = ["line_id", "entry_date", "posting_date", "posting_time", "voucher_no",
           "account_code", "account_name", "account_type", "debit", "credit", "currency",
           "narration", "user_id", "party_id", "party_name", "trn", "invoice_no",
           "net_amount", "vat_amount", "vat_code", "expense_category"]
EXPENSES = [("6100", "Rent Expense"), ("6200", "Utilities"), ("6300", "Travel"),
            ("6400", "Office Supplies"), ("6500", "Professional Fees"), ("5100", "Purchases")]
USERS = [f"USER{i:02d}" for i in range(1, 31)]
WORDS = ["Invoice", "Monthly", "Service", "Supply", "Maintenance", "Consulting", "Freight",
         "Stationery", "Licence", "Subscription"]


def generate(path: Path, lines: int, seed: int = 2025) -> int:
    """Write ``lines`` balanced GL lines (vouchers of 2 or 3 lines). Returns lines written."""
    rnd = random.Random(seed)  # noqa: S311 - synthetic data, not security
    start = date(2025, 1, 1)
    n = v = 0
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(HEADERS)
        while n < lines:
            v += 1
            day = start + timedelta(days=rnd.randrange(365))
            if day.weekday() >= 5 and rnd.random() > 0.01:  # ~1% weekend postings
                day -= timedelta(days=day.weekday() - 4)  # move to Friday
            hour = rnd.randrange(8, 12) if day.weekday() == 4 else rnd.randrange(8, 18)
            d = day.isoformat()
            t = f"{hour:02d}:{rnd.randrange(60):02d}:{rnd.randrange(60):02d}"
            acct, name = rnd.choice(EXPENSES)
            net = rnd.randrange(5_000, 2_500_000) / 100
            rem = lines - n  # 2- or 3-line vouchers; never leave a single line over
            with_vat = rem == 3 or (rem >= 5 and rnd.random() < 0.5)
            vat = round(net * 0.05, 2) if with_vat else 0.0
            if rem < 2:  # pragma: no cover - only when lines == 1
                break
            user, vno = rnd.choice(USERS), f"PV-{v:07d}"
            sup = f"S{rnd.randrange(1, 400):04d}"
            inv = f"INV-{v:07d}"
            narr = f"{rnd.choice(WORDS)} {rnd.choice(WORDS).lower()} {inv}"
            gross = round(net + vat, 2)
            rows = [[acct, name, "Expense", f"{net:.2f}", "0.00", f"{net:.2f}", "", "", ""]]
            if vat:
                rows.append(["1410", "Input VAT Recoverable", "Asset", f"{vat:.2f}", "0.00",
                             f"{net:.2f}", f"{vat:.2f}", "SR", ""])
            rows.append(["2100", "Trade Payables", "Liability", "0.00", f"{gross:.2f}", "", "",
                         "", ""])
            for a, an, at, dr, cr, na, va, vc, ec in rows:
                n += 1
                w.writerow([f"L{n:08d}", d, d, t, vno, a, an, at, dr, cr, "AED", narr, user,
                            sup, f"Supplier {sup}", "", inv, na, va, vc, ec])
    return n


def _peak_mb() -> float:
    kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(kb / 1024, 1)


def run(lines: int, workdir: Path, seed: int = 2025) -> dict[str, Any]:
    workdir.mkdir(parents=True, exist_ok=True)
    os.environ.update({
        "ENVIRONMENT": "test", "DATABASE_URL": f"sqlite:///{workdir / 'perf.db'}",
        "STORAGE_URL": f"file://{workdir / 'storage'}", "JOB_EAGER": "true", "REDIS_URL": "",
        "AUTH_PROVIDER": "entra", "AUTH_ISSUER": "https://perf.invalid/",
        "AUTH_AUDIENCE": "perf", "AUTH_JWKS_JSON": '{"keys": []}',
    })
    sys.path.insert(0, str(ENGINE))
    from app.core import config, db

    config.reset_settings()
    db.reset_engine()
    db.create_all()
    from app.core.db import session_factory
    from app.models import Client, Engagement, Job
    from app.services import datasets, je_tests, rules

    rules.seed_database()
    rules.use_database(True)
    with session_factory()() as s:
        c = Client(client_code="PERF01", name="Perf Synthetic LLC", emirate="Dubai")
        s.add(c)
        s.flush()
        e = Engagement(client_id=c.id, fye=date(2025, 12, 31))
        s.add(e)
        s.commit()
        eng_id = e.id

    src = workdir / "perf_gl.csv"
    out: dict[str, Any] = {"lines_requested": lines}
    t0 = time.perf_counter()
    out["lines"] = generate(src, lines, seed)
    out["generate_s"] = round(time.perf_counter() - t0, 2)
    out["csv_mb"] = round(src.stat().st_size / 1e6, 1)

    t0 = time.perf_counter()
    with src.open("rb") as fh:
        ds, _parse_job = datasets.upload_stream(eng_id, "perf_gl.csv", fh, "GL", "perf", None)
    out["import_s"] = round(time.perf_counter() - t0, 2)
    out["peak_mb_after_import"] = _peak_mb()
    d = datasets.get_dataset(ds.id)
    out["parsed_rows"], out["status_after_import"] = d.rows, d.status
    out["parquet_mb"] = round(Path(d.parquet_ref or "").stat().st_size / 1e6, 1)

    t0 = time.perf_counter()
    rep = datasets.run_validation(ds.id)
    out["validate_s"] = round(time.perf_counter() - t0, 2)
    out["peak_mb_after_validate"] = _peak_mb()
    out["validation"] = {"critical": rep.critical, "warnings": rep.warnings}

    t0 = time.perf_counter()
    run_id, _je_job = je_tests.start_je_run(ds.id, {}, user_id="perf")
    out["je_s"] = round(time.perf_counter() - t0, 2)
    out["peak_mb_after_je"] = _peak_mb()
    _, res = je_tests.get_je_run(run_id)
    out["je_status"], out["je_flagged_lines"] = res["status"], res.get("flagged_lines")
    with session_factory()() as s:
        out["job_statuses"] = {j.type: j.status for j in s.query(Job).all()}
    out["python"] = platform.python_version()
    out["cpu_count"] = os.cpu_count()
    rules.use_database(False)
    db.reset_engine()
    config.reset_settings()
    return out


def write_report(res: dict[str, Any], doc: Path) -> None:
    text = doc.read_text(encoding="utf-8")
    begin, end = "<!-- perf:begin -->", "<!-- perf:end -->"
    table = "\n".join([
        begin,
        f"Run {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}, Python {res['python']}, "
        f"{res['cpu_count']} vCPU, SQLite, local file storage.",
        "",
        "| Stage | Lines | Seconds | Lines/s | Peak RSS (MB) |",
        "|---|---:|---:|---:|---:|",
        f"| Generate CSV ({res['csv_mb']} MB) | {res['lines']:,} | {res['generate_s']} | "
        f"{int(res['lines'] / max(res['generate_s'], 0.01)):,} | - |",
        f"| Import (upload + parse to Parquet, {res['parquet_mb']} MB) | {res['parsed_rows']:,} "
        f"| {res['import_s']} | {int(res['lines'] / max(res['import_s'], 0.01)):,} | "
        f"{res['peak_mb_after_import']} |",
        f"| Validate | {res['parsed_rows']:,} | {res['validate_s']} | "
        f"{int(res['lines'] / max(res['validate_s'], 0.01)):,} | "
        f"{res['peak_mb_after_validate']} |",
        f"| JE tests (incl. Benford, flag rows) | {res['parsed_rows']:,} | {res['je_s']} | "
        f"{int(res['lines'] / max(res['je_s'], 0.01)):,} | {res['peak_mb_after_je']} |",
        "",
        f"Validation: {res['validation']}; JE status {res['je_status']}, flagged lines "
        f"{res['je_flagged_lines']:,}; jobs {res['job_statuses']}.",
        end,
    ])
    if begin in text:
        text = text[:text.index(begin)] + table + text[text.index(end) + len(end):]
    else:
        text = text.rstrip() + "\n\n" + table + "\n"
    doc.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--lines", type=int, default=int(os.environ.get("PERF_LINES", "1000000")))
    p.add_argument("--workdir", type=Path, default=Path(tempfile.gettempdir()) / "auditsmart_perf")
    p.add_argument("--report", action="store_true")
    a = p.parse_args(argv)
    res = run(a.lines, a.workdir)
    print(json.dumps(res, indent=2, default=str))
    if a.report:
        write_report(res, ENGINE.parent / "docs" / "PERFORMANCE.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
