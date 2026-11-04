"""Command line helpers (no server needed).

    python -m app.cli validate ../data/edge_cases.csv [--json] [--map field=Header ...]
    python -m app.cli monitor-check [--force]
    python -m app.cli worker [--burst]          (RQ worker; REDIS_URL must be set)
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from app.services.importer import parse_to_parquet
from app.services.validation import render_text, validate_parquet


def monitor_check(force: bool = False) -> int:
    from app.core.db import session_factory
    from app.services import rules, rules_monitor

    rules.use_database(True)
    with session_factory()() as s:
        rules_monitor.seed_sources(s)
        res = rules_monitor.check_all(s, rules_monitor.PoliteFetcher(), force=force)
        s.commit()
    print(json.dumps(res))
    return 0


def worker(burst: bool = False) -> int:  # pragma: no cover - needs a Redis server
    """Run an RQ worker on queue ``auditsmart`` (REDIS_URL must be set)."""
    import redis
    from rq import Queue, Worker

    from app.core.config import get_settings
    from app.services import jobs

    url = get_settings().redis_url
    if not url:
        print("REDIS_URL is empty: jobs run in-process; no worker is needed.")
        return 2
    jobs.load_tasks()
    conn = redis.Redis.from_url(url)
    Worker([Queue(jobs.QUEUE_NAME, connection=conn)], connection=conn).work(burst=burst)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="Import and validate a GL/TB file; print the errors")
    v.add_argument("file", type=Path)
    v.add_argument("--kind", choices=["GL", "TB"], default="GL")
    v.add_argument("--json", action="store_true", help="machine-readable output")
    v.add_argument("--map", action="append", default=[], metavar="FIELD=HEADER")
    m = sub.add_parser("monitor-check", help="FTA rules monitor: check due watched sources "
                                             "(schedule weekly, e.g. cron '0 6 * * 1')")
    m.add_argument("--force", action="store_true", help="check every active source now")
    w = sub.add_parser("worker", help="RQ background-job worker (needs REDIS_URL)")
    w.add_argument("--burst", action="store_true", help="exit when the queue is empty")
    args = p.parse_args(argv)
    if args.cmd == "worker":  # pragma: no cover - needs a Redis server
        return worker(burst=args.burst)
    if args.cmd == "monitor-check":
        return monitor_check(force=args.force)
    if any("=" not in m for m in args.map):
        p.error("--map expects FIELD=HEADER")
    override = dict(m.split("=", 1) for m in args.map)
    with tempfile.TemporaryDirectory() as tmp:
        pq = Path(tmp) / "data.parquet"
        res = parse_to_parquet(args.file, pq, kind=args.kind, override=override)
        report = validate_parquet(pq, kind=args.kind, missing_cols=res.missing_columns)
    if args.json:
        print(json.dumps({"summary": report.summary(),
                          "errors": [i.as_dict() for i in report.issues]}, indent=2))
    else:
        print(f"File: {args.file.name}")
        print(render_text(report))
    return 1 if report.blocked else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
