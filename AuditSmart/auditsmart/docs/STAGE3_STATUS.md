# AuditSmart engine: Stage 3 status (prompts 3.1–3.12)

**Date:** 27 Oct 2026. **Status:** Stage 3 engine prompts 3.1–3.12 are complete, the tree is committed (local git only, no remote, nothing pushed), and all tests pass.
**Runtime:** Python 3.11.17, FastAPI, Pydantic 2, SQLAlchemy 2 + Alembic (migrations 0001–0008), pyarrow, openpyxl, RQ 2.12.
**AI:** No calculation uses AI. AI calls (3.7 observations, 3.9 rule extraction) go through adapters. Tests use only fakes or the offline `stub`, with no network and no API key. No key was asked for or used.

## Quality gates (run from engine/)
| Gate | Result |
|---|---|
| pytest | **338 passed, 0 failed, 0 errors, 0 skipped** (about 30–55 s) |
| coverage (branch) | **99.06 %** (fail_under 90) |
| ruff check | clean |
| mypy --strict (app) | clean, 62 source files |
| migration parity (models = Alembic head) | passes |

## Per prompt
| Prompt | What was built | Key evidence |
|---|---|---|
| 3.1 | Scaffold: config, Entra/Supabase JWT auth, roles + engagement membership, Appendix A models, Alembic 0001, scrubbed JSON logging, /v1/health, Dockerfile, CI | tests/security, unit/test_scaffold |
| 3.2 | Upload (single and chunked), SHA-256, header mapping, Parquet, plain-English validation, 409 guard downstream | edge_cases.csv: all 16 answer-key errors detected; dummy_gl only gives the 5 invalid-TRN warnings |
| 3.3 | Sampling ISA 530: MUS (firm and guide formula), random, systematic, stratified, key items + MUS; Decimal; factors from the Rules Library | Golden 90 % and 95 % values and selections match exactly (COUNTIF rule) |
| 3.4 | JE testing (13 criteria, scoring, calendar resolver), Benford | **100 % detection** of the planted weekend 25, holiday 15, Friday cutoff 10, round 20, period-end FINMGR 15, vague 10, duplicate 10 and FY21/22 non-working 60 |
| 3.5 | Output VAT + TRN; MUS / ratio evaluation | Golden VAT sheet exact (12 output-VAT errors, 5 invalid TRNs); Projection sheet exact |
| 3.6 | ISA 230 working paper (11 sheets), STALE / AI-draft gate | Every sheet and key cell checked |
| 3.7 | Anonymiser (deny list + patterns, assert_clean), AI gateway (Gemini / Azure / stub), draft labels and review | Payload security tests; no sockets |
| 3.8 | DB Rules Library (one version per date, propose / approve / reject, immutability, STALE marking) | Rules API tests |
| 3.9 | FTA rules monitor (fetcher, bs4 / pdfplumber, hash / snapshots, AI → proposed versions, alerts, manual upload) | 23 unit + 4 API tests |
| 3.10 | Working calendar API, Excel import / export, Asia/Dubai, STALE by calendar hash | Golden Calendar sheet (12 cases) + FY21/22 weekend change |
| 3.11 | Job backends (eager / thread / RQ), cancel, job list, paginated filters, streamed JE | 1M lines: import 25.9 s, validate 13.8 s, JE 34.6 s (docs/PERFORMANCE.md) |
| 3.12 | Input-VAT checks (Decisions 13 and 17 of 2026): supplier register, expense mapping, `input_vat_check` job, API, WP Input VAT sheet | **Answer key exact: 15 unverified-supplier, 3 spend-threshold (rolling totals 380,547.53 / 393,220.08 / 397,426.29), 20 employee-expense lines** |

## Addition after 3.12: multi-firm rule approval (1 Nov 2026)
Any audit firm can now use AuditSmart (D42–D45, docs/MULTI_FIRM_APPROVAL.md, migration 0008). The default best-practice rules stay shared and `pending_verification`. Each firm's partner reviews them in one list (`GET /v1/firm/rules/review`), then approves them for the firm (`POST /v1/firm/rules/{rule_key}/approve`), proposes a firm or engagement override (`POST /v1/firm/rules/{rule_key}/override`), or rejects a proposal (`POST /v1/firm/rules/{rule_key}/reject`). `RULES_ALLOW_PENDING=true` stays the default, and a firm can only tighten it. Rule versions, adoptions and STALE marking are limited to each firm or engagement, and nothing leaks across firms (tested). Golden and answer-key results are unchanged.

## Decisions
D1–D45 are recorded in plans/DECISIONS.md. Each one defaults to firm_methodology_v0.2 and names who signs it off. The 3.12 decisions are D40 (check definitions, exemption kept as a note only, TEST-ONLY date shift) and D41 (replace-on-upload, all-or-nothing register / mapping).

## Deviations from the Build Guide / prompts (all documented)
- Migrations 0002–0007 were added for the extra columns and tables; the parity test keeps models and migrations equal.
- The calendar was brought forward for JE (D10), with calendar summary layers and non-strict calendar schemas.
- The WP has 11 sheets (the prompt's order), not the 9 in the SPEC (D18).
- The AI provider is a stub by default (D22). Rules can resolve to `pending_verification` while nothing is approved (D24).
- bs4 and pdfplumber were added for the monitor. Watched sources without a known URL are `urn:auditsmart:pending:*` placeholders (D29); no URL was invented.
- The federal calendar seed is copied into the database on the first Admin edit (D32).
- rq was added. Closures stay in-process (D37). There is a separate `/v1/workpaper/jobs` endpoint.
- Validation is not yet streamed (about 1 GB peak RSS at 1M lines). This is a Stage 7 tuning item.
- 3.12: the TEST-ONLY `effective_date_override` shifts rule lookups so the 2025 dummy data uses the 2026 rule versions. The register CSV accepts the dummy-data column aliases.

## Waiting for Savio / Tax Partner
1. Source URLs for Decision 13/2026, VATP046 and the amended VAT Executive Regulation (PATCH /v1/rules-monitor/sources/{id}).
2. Approval of the seed rules (all `pending_verification`), including the input_vat values (375,000; 12 months; 10,000 / 100,000; 2026-10-01) and the Decision 17 categories.
3. The exemption-threshold treatment (10k / 100k): today it is recorded as a note only.
4. The Decision 17 category mapping for each client (accounts → categories).
5. Approval of the federal calendar seed and the UAE holiday dates.
6. AI provider and key in the deployment secret store (Stage 7). Savio holds the key; it is never pasted anywhere.
7. Teams webhook / SMTP for notifications (Stage 7). Today notifications are only logged.
8. `RULES_ALLOW_PENDING=false` in production after approval (or per firm via `require_approved_rules`). Each firm's users need the `firm_id` token claim (D45).
9. Firm sign-off on the access policy (D35, D39), the WP template (D18) and the review policy (D19, D26).
10. Deployment choice: Redis or Azure queues (D36). The GitHub repo, Lovable front end and deployment all need Savio's accounts.

## Next step
Savio reviews this status, DECISIONS.md and the seed rules. The Tax Partner then approves the rules and records the URLs. After that comes Stage 4 (Lovable front end), with Stage 7 for deployment and secrets. No real client data is used until the Stage 8 approvals.
