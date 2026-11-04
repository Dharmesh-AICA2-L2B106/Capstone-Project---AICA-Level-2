# Stage 5 status – Step 1: development deployment files + two engine fixes

Date: 2 Nov 2026. Builds on Stage 4 (GitHub `Savio2358/AuditSmart` at `c062f7b`, plus the
Stage 4 status / Lovable docs). Nothing was pushed by the AI; no Lovable credits were used.
**Dummy data only** on the development deployment.

## What was added
| Item | Purpose |
|---|---|
| `render.yaml` | Render Blueprint: free Docker web service `auditsmart-engine` + free PostgreSQL 16 `auditsmart-db`, Frankfurt. Secrets are `sync: false` (typed into the Render dashboard, never in git). Weekly FTA monitor cron is included **commented out** (no free cron plan) |
| `engine/scripts/start.sh` | Container start: `alembic upgrade head` (when `DATABASE_URL` is set), then uvicorn on `$PORT` with proxy headers |
| `engine/Dockerfile` | Copies `scripts/`, makes `/app/storage` writable by the non-root user, health check on `$PORT`, starts via `start.sh` |
| `.gitattributes` | Keeps `*.sh` with LF line endings when committed from Windows |
| `docs/DEPLOY_DEV.md` | Step-by-step for Savio: copy, push, Render Blueprint, environment variables, checks, troubleshooting, role/firm-claim notes |
| Migration `0009_rule_unit_length` | Widens `rule_versions.unit` to 128 (found by a PostgreSQL rehearsal, D49) |

## Fixes
- **Fix A – Admin never approves (D47).** Shared defaults are approved / rejected by the
  TaxPartner (VAT, INPUT_VAT, CT, TRN, LEGAL_REF) or the Partner (SAMPLING, JE, BENFORD,
  VALIDATION). Admin, alone or with Manager, gets 403. Matches the firm-level rule (D43).
- **Fix B – Supabase firm claim from `app_metadata` only (D48).** A top-level `firm_id`,
  `user_metadata`, or a non-object `app_metadata` is ignored for `AUTH_PROVIDER=supabase`.
  Entra keeps the top-level claim; `dev` keeps its fallback.
- Also: `postgres://` URLs map to psycopg 3 (D46), `ALLOWED_ORIGINS` tolerates a trailing `/`,
  `%` in a database password no longer breaks Alembic.

## Verification (on the AI's box)
- `pytest --cov`: 340 passed, total coverage 99.06% (gate 90%), SQLite.
- Same 340 tests on a local PostgreSQL 16 (`AUDITSMART_TEST_PG_URL`): all passed.
- `ruff check .`: clean. `mypy` (project config) and `mypy --strict app`: no issues.
- Render rehearsal without Docker (Docker is not available on the box): same file layout as
  the image, `PORT=10000`, Render-style `postgresql://` URL, Supabase HS256 dummy secret →
  migrations to 0009, 53 rule versions + 9 watched sources seeded, `/v1/health` ok with db ok,
  401 without a token / with a wrong issuer, Admin approval 403, CORS preflight ok for the
  allowed origin and refused for others, restart idempotent, idle memory about 160 MB.
- `render.yaml` validated against Render's published JSON schema: 0 errors.
- Lovable contract export re-run: unchanged (no API shape changes).

## Not done / waiting for Savio
1. Copy the files into `C:\Projects\auditsmart`, commit and push (see `docs/DEPLOY_DEV.md` §2).
2. Create the Render Blueprint and enter the secret values (§3–5).
3. Decide how roles and `firm_id` reach `app_metadata` in the Supabase token (§10) –
   Custom Access Token Hook (recommended) or server-side `app_metadata`. This touches the
   Lovable project: ask before spending Lovable credits.
4. Confirm whether Lovable Cloud exposes JWKS (asymmetric keys) or only the legacy HS256
   secret (§5.2).
5. AI provider / Gemini key for the rules monitor (optional; leave blank to keep AI off).
6. The free database expires 30 days after creation; decide on a paid plan before then
   if the data must be kept. Enabling the weekly monitor cron needs a paid cron plan.

---

# Stage 5 – Step 2: engagement sync endpoint + Lovable prompt 5.2

Date: 2 Nov 2026. Builds on step 1 (`ab59111`, pushed by Savio). Engine **0.2.1**. Nothing
was pushed by the AI; no Lovable credits were used.

## What was added
| Item | Purpose |
|---|---|
| `PUT /v1/engagements/{id}` | Idempotent upsert of client + engagement + whole team from Lovable (201 create / 200 update, `created` flag), firm from the token, audited old/new, STALE on year-end / emirate change (D50–D54) |
| `GET /v1/engagements/{id}` | The engine's copy (team members or the firm Admin) |
| Migration `0010_code_unique_per_firm` (file name avoids the `*client*` .gitignore pattern) | `client_code` unique per firm instead of globally (D52); tested on SQLite and PostgreSQL 16 (upgrade, downgrade, upgrade) |
| Version 0.2.1 | Visible in `/v1/health`, so the redeploy can be confirmed (D55) |
| `docs/lovable/5.2_engine_connect.md` | One-message Lovable prompt: engine-proxy edge function, mocks removed, roles/firm into `app_metadata` by trigger, engagement sync, firm registration, Engine status card, audit of each call |
| Docs | SPEC 5.2 section, DECISIONS D50–D55, MULTI_FIRM_APPROVAL §10, Lovable contract re-exported (69 operations) |

## Verification (on the AI's box)
- `pytest --cov`: 361 passed (21 new), total coverage 99.10% (gate 90%); new modules 100%. SQLite.
- Same 361 tests on a local PostgreSQL 16 (`AUDITSMART_TEST_PG_URL`): all passed.
- `ruff check .`: clean. `mypy` (project config) and `mypy --strict app`: no issues.

## Waiting for Savio
1. Copy the zip contents into `C:\Projects\auditsmart`, commit, push; check `/v1/health` shows 0.2.1.
2. Paste `docs/lovable/5.2_engine_connect.md` (block only) into the Lovable project (~8–12 credits).
3. Send back Lovable's report: roles table, firm_id storage, JWT `alg` (header only).

---

# Stage 5 – Step 2b: clearer import errors (engine 0.2.2)

Date: 3 Nov 2026. Builds on step 2 (`1c95785`). Approved by Savio ("A"). Nothing was pushed by
the AI; no Lovable credits were used. AI is not involved in any calculation.

## Problem
A parse job failed with only "ValueError: the job failed. Check the file and try again."
`dummy_gl.csv` itself parses cleanly (3,000 rows). The only plain `ValueError` in the parse
path was a mapping override key that is not an engine field name (e.g. `Posting Date`,
`date`). `PUT /v1/datasets/{id}/mapping` queued the job without checking, and the job runner
replaced the reason with the generic text.

## What changed (D56)
| Item | Change |
|---|---|
| `importer.normalise_override` | Field names, labels and synonyms as keys; reversed `{header: field}`; `""`/`null` unmaps; header values matched exactly or case/space-insensitively; all problems listed in one message (`MappingError`, a `ValueError` with `.message`) |
| All upload routes + `PUT .../mapping` | Mapping checked against the file's headers before a job is queued → 422 with the reason (multipart was 400). Dataset status unchanged, no job created; chunked uploads keep their chunks so `complete` can be retried |
| Parse job | Errors stored as plain reasons (mapping, "The file is not UTF-8 text …", unreadable CSV / Excel). Old queued jobs with label keys are normalised too |
| `jobs.job_error_text` | Keeps `.message`, or `str(exc)` for `user_facing` errors; others stay generic (no stack trace) |
| Schemas | `mapping_override` values typed `Any` in OpenAPI so a wrong type gets the engine's plain message, not a schema error list; Lovable contract re-exported |
| Version | 0.2.2 (`/v1/health`) |

Example messages (exact text):
- `Mapping problem: Unknown field 'Posting Dt' in the mapping. Allowed fields: line_id, entry_date, posting_date, …, closing_balance.`
- `Mapping problem: Column 'Txn Date' (mapped to posting_date) is not in the file. Columns in the file: line_id, entry_date, posting_date, ….`
- `Mapping problem: The value for 'debit' must be a column header (text), or "" to leave the field unmapped; got a number.`
- `The file is not UTF-8 text (a character near byte 1234 could not be read). In Excel use Save As > 'CSV UTF-8', or upload the .xlsx file, then try again.`

## Verification (box)
- 379 tests pass (361 before + 18 new: `tests/unit/test_mapping_override.py`, `tests/api/test_import_errors_api.py`), on SQLite and on PostgreSQL; coverage 99.13% (gate 90%).
- ruff clean; `mypy` (app) and `mypy --strict app` clean; the two new test files are `--strict` clean.
- `dummy_gl.csv` with a six-field override (labels, synonyms or reversed) parses all 3,000 rows.

## Waiting for Savio
1. Copy / `git am` the zip into `C:\Projects\auditsmart`, commit, push; check `/v1/health` shows **0.2.2**
   (the 5.2 prompt's "0.2.1" check is superseded; the Engine status card shows whatever the engine reports).
2. Re-run the upload of `dummy_gl.csv`. If it fails again, the job error now says why; send that text.
3. Optional later: Windows-1252 fallback for non-UTF-8 CSVs (D56, not done).
