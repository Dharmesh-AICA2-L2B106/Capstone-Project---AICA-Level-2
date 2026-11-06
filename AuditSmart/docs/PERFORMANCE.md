# AuditSmart engine – performance

Prompt 3.11 asks for a 1,000,000-line performance test. `engine/scripts/perf.py` creates a
**synthetic** GL (balanced 2–3 line vouchers, about 1% weekend postings and some out-of-hours
and round-amount lines, client "Perf Synthetic LLC"; no real data). It then runs the same
service calls the API uses: streamed upload and parse to Parquet, validation, and JE tests
(all rules incl. Benford and per-line flag rows). Each stage is timed and the process peak RSS
is recorded.

```
cd engine
.venv/bin/python scripts/perf.py --lines 1000000 --report   # rewrites the table below
```

`tests/perf/test_perf_smoke.py` runs the same pipeline on 3,000 lines in CI.

Notes
* Jobs ran eagerly (JOB_EAGER) on SQLite and local file storage in the build sandbox; in
  production they run in the RQ worker (`python -m app.cli worker`) on PostgreSQL / Blob.
* Before 3.11 the JE run loaded every row as a dict (peak about 1 GB at 200k lines). JE now
  streams only the columns it needs from Parquet and computes Benford column by column.

## Results

<!-- perf:begin -->
Run 2026-10-27 19:51 UTC, Python 3.11.17, 8 vCPU, SQLite, local file storage.

| Stage | Lines | Seconds | Lines/s | Peak RSS (MB) |
|---|---:|---:|---:|---:|
| Generate CSV (181.0 MB) | 1,000,000 | 5.44 | 183,823 | - |
| Import (upload + parse to Parquet, 52.7 MB) | 1,000,000 | 25.87 | 38,654 | 401.4 |
| Validate | 1,000,000 | 13.8 | 72,463 | 1064.1 |
| JE tests (incl. Benford, flag rows) | 1,000,000 | 34.6 | 28,901 | 1999.1 |

Validation: {'critical': 0, 'warnings': 0}; JE status current, flagged lines 59,878; jobs {'parse': 'succeeded', 'je_tests': 'succeeded'}.
<!-- perf:end -->

Reading: about 80 s end to end for 1,000,000 lines (import ~39k lines/s, JE ~29k lines/s) with
a peak RSS of about 2.0 GB, inside a 4 GB worker. Validation (about 1 GB at 1M) still loads
its columns in full; streaming it is a Stage 7 tuning item if workers are smaller.
