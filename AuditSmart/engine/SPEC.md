# AuditSmart Engine – SPEC.md

**Status:** Stage 1 working copy, 27 Oct 2026. Not yet approved.

**How this file is built**
- **Part 1:** firm overrides from firm_methodology_v0.2 Section 5. That document is a DRAFT pending Assurance Partner approval.
- **Part 2:** the calculation rules as implemented and verified in data/golden_results.xlsx.
- **Part 3:** a VERBATIM copy of AuditSmart Build Guide v2.0, Sections 3–5 plus Appendices A and B. This follows Workbook step 1.2. The text was extracted from the .docx, so tables appear as `a | b | c` rows.
- **Precedence:** where Part 1 differs from Part 3, Part 1 (the firm settings) applies. Each difference is listed.

---
## Part 1 – Firm overrides (firm_methodology v0.2 §5)

| Setting | Build Guide v2.0 | Firm methodology v0.2 (applied) |
|---|---|---|
| MUS sample size | n = ceil(Pop × CF / TM) | n = ROUNDUP(Pop × CF / (TM − Expected × EF), 0) |
| Expected misstatement | not used (0) | 10% of TM; refuse to sample if > 50% of TM |
| Expansion factor (EF) | – | 1.6 (95%), 1.5 (90%), 1.3 (80%) |
| Confidence factors | 3.00 / 2.31 | 80% 1.61 · 90% 2.31 · 95% 3.00 (default) · 99% 4.61 |
| Minimum n | – | n < 5 → no statistical sampling; warn if tested size differs from n by > 10% |
| Incremental factors (ranks 1–5) | "×(factor−1)" | 95%: 1.75, 1.55, 1.46, 1.40, 1.36 · 90%: 1.58, 1.44, 1.36, 1.31, 1.28 |
| TM (worked example) | 450,000 (prompt 3.3 example) | 280,000 (PBT 8m × 5% = OM 400,000; PM 70%) |
| Vague-narration keywords | "vague" | blank, adj, misc, correction, reversal, error, "as per MD" |
| Unusual account pairs | – | combination used < 3 times |
| Large amounts | – | ≥ performance materiality |
| Users | < 1% of entries | < 1% of entries **plus** senior-management / IT user flag |
| JE selection | – | score = number of criteria met; test all with score ≥ 3, and score 2 by judgement (minimum 10); never random |

## Part 2 – Stage 1 calculation rules (as verified in golden_results.xlsx)
1. **Test population:** lines where account_type = "Expense" and debit > 0. Zero lines are excluded. Expense credit lines (credit notes) are excluded and listed separately.
2. **Sample size and interval:**
   - n = ROUNDUP(Pop × CF / (TM − 0.10·TM·EF), 0)
   - J = Pop / n
   - Basic precision BP = CF × J
3. **Top stratum:** book value ≥ J. These items are tested 100%. Their count is COUNTIF(pop_amount, ">=" & J).
4. **Selection:** the random start is in [0, J) and comes from numpy default_rng(seed). The selection point is start + k·J for k = 0 … n−1. The selected line is the first line whose cumulative population value ≥ the point. In Excel this is COUNTIF(cum, "<"&point)+1, which equals XMATCH(point, cum, 1). A line ≥ J can be hit more than once; report the distinct lines.
5. **Evaluation:**
   - For items < J: tainting = (book − audited)/book, and projected = tainting × J.
   - For top-stratum items: projected = actual misstatement.
   - Incremental allowance IA = Σ over items < J, ranked by projected value descending, of projected × (factor_rank − 1).
   - UML = BP + Σ projected + IA.
   - Conclusion = "Acceptable" if UML ≤ TM, otherwise "Exceeds – further work".
6. **Output VAT:**
   - Expected = ROUND_HALF_UP(net × 5%, 2) for SR and RC; 0 for ZR and EX.
   - Exception if |recorded − expected| > tolerance. The 0.01 tolerance is a PLACEHOLDER: the Rules Library value is not given in the docs.
7. **TRN:** must be 15 digits starting with "100". This pattern came from the brief and still needs Tax Partner confirmation. A blank TRN is allowed only on ZR export and RC overseas lines.
8. **Calendar:**
   - Precedence: company exception > company work week > emirate > federal.
   - A Friday half day runs to 12:00. A posting is non-working if its time is after the cut-off.
   - Weekend change: Fri/Sat off until 31-Dec-2021; Sat/Sun off from 1-Jan-2022.
9. **JE criteria used for the planted data:**
   - Non-working day per the calendar.
   - Round sum: a multiple of 1,000 and ≥ 10,000.
   - Period-end: within ±5 days of the year end.
   - Duplicates: same invoice + party, or same party + amount + date.
   - Benford: first-digit test on amounts ≥ 10, with MAD thresholds 0.006 / 0.012 / 0.015.
10. **Input VAT (Decision 13/2026 and 17/2026 TEST data):**
    - The test data uses a TEST-ONLY effective date of 2025-10-01. The real effective date is 1 Oct 2026.
    - Flag purchase lines with input VAT > 0 dated on/after the effective date where the supplier has no verified_on in data/supplier_register.csv.
    - Flag a supplier whose rolling 12-month gross purchases exceed 375,000 (placeholder from prompt 1.1) when there is no bank_evidence_ref.
    - Employee-expense lines are identified by expense_category. Prompt 1.1 defines 5 categories; Decision 17 has 6.
    - All thresholds must be read from the Rules Library (status pending_verification). The decision text is NOT reproduced here.
11. **Money:** Decimal with ROUND_HALF_UP, matching to the fils. Excel ROUND rounds half away from zero, which equals ROUND_HALF_UP for both signs.

---
## Part 3 – VERBATIM: Build Guide v2.0 Sections 3–5 and Appendices A–B
## 3. Python Engine Specifications
Save Sections 3, 4 and Appendices A–B as engine/SPEC.md. Antigravity reads it before every prompt.
## 3.1 Technology stack
[TABLE]
Component | Specification
Language | Python 3.11+
API | FastAPI + Pydantic v2 (strict validation)
Money | decimal.Decimal everywhere (never float); ROUND_HALF_UP to 2 dp at presentation only
Data loading | pandas / pyarrow; chunked reading for large CSV; Parquet cache per dataset
Randomness | numpy.random.default_rng(seed); seed always stored and returned
Excel | openpyxl
Statistics | scipy (chi-square); MAD for Benford
Database | PostgreSQL via SQLAlchemy 2 + Alembic migrations
Background jobs | Job table + worker (RQ/Celery with Redis, or Azure-native queue); progress %, cancel, retry
Testing | pytest + hypothesis; ≥ 90% coverage on services/; golden and edge-case suites
Quality | ruff, mypy (strict on services/), pre-commit; GitHub Actions blocks merge on failure
Security | JWT from Entra ID / Supabase validated on every call; role checks; CORS whitelist; no ledger rows or party names in logs
Deployment | Docker image; same image in dev and production
[/TABLE]
## 3.2 Calculation rules
[TABLE]
Calculation | Exact rule
Population | Absolute or signed amounts per user choice; zero lines excluded; count and value recorded; blocked if Dr ≠ Cr beyond tolerance from Rules Library
Confidence factors | From Rules Library (SAMPLING domain). Typical 0-error values: 80% 1.61, 90% 2.31, 95% 3.00, 99% 4.61 – to be confirmed against firm methodology
MUS sample size | n = ceil(Population × CF ÷ Tolerable misstatement); interval J = Population ÷ n. Response returns CF used, rule version and the formula with values substituted
MUS selection | Random start in [0, J) from seed; item selected when cumulative value first ≥ start + k·J; items ≥ J are top stratum, tested 100%
Credit / negative lines | Excluded from MUS on debit-side populations, listed separately for consideration; never silently dropped
Random / systematic | Without replacement; systematic = random start + fixed count interval
Stratified | User or quantile strata; value-proportional allocation; minimum 1 per stratum
Key items | Items ≥ threshold removed and tested 100% before sampling the remainder
Projection (MUS) | Tainting = misstatement ÷ book value; projected = tainting × J for items < J; actual for top stratum
Upper misstatement limit | Basic precision (CF × J) + projected misstatement + incremental allowance using ranked taintings and incremental factors from Rules Library
Projection (non-MUS) | Ratio estimation: (misstatement in sample ÷ sample value) × population value
Benford | First digit, amounts ≥ 10; chi-square and MAD; thresholds in Rules Library
Non-working day | Resolved from the engagement's Working Calendar (3.5) for the posting date; never hard-coded
Round sums / period-end / users / narrations | Parameters in firm methodology settings; defaults: multiple of 1,000 and ≥ 10,000; ±5 days; users < 1% of entries; keyword list
Output VAT | Rate per VAT code and tolerance from rule version valid on invoice date; TRN format pattern from Rules Library
Input VAT (M15) | See 3.8; thresholds, effective dates and categories from Rules Library
Duplicates | Same party + amount + date; same invoice number + party
[/TABLE]
## 3.3 API endpoints
[TABLE]
Endpoint | Purpose
POST /v1/datasets (async) | Upload GL/TB → job id; mapping suggestion, profile, SHA-256
POST /v1/datasets/{id}/validate | Row-level checks; returns errors with row numbers and guidance
GET /v1/datasets/{id}/rows | Paginated, filterable rows
POST /v1/sample | Sampling; returns sample, CF, formula, seed, rule versions
POST /v1/je-tests (async) | Risk tests with calendar; per-line flags, summary, calendar hash
POST /v1/benford | Distribution, chi-square, MAD, conclusion
POST /v1/vat-check | Output VAT and TRN checks
POST /v1/input-vat-check | Decision 13 supplier verification and Decision 17 employee-expense checks
POST /v1/evaluate | Projection and upper limit vs tolerable misstatement
POST /v1/workpaper | 9-sheet Excel; refused if any result is stale or unreviewed
POST /v1/ai/observation | Anonymise → AI → validated JSON draft
/v1/rules, /v1/rules/monitor | Rule look-up, proposals, approvals, FTA monitor
/v1/calendar/* | Resolve engagement calendar; import/export
GET /v1/jobs/{id} | Job status, progress %, result link, errors
GET /v1/health | Version, database and queue status
[/TABLE]
## 3.4 Regulatory Rules Library
The FTA publishes laws, decisions and clarifications on its website but does not, as far as I am aware, provide a data feed for rules. The tool therefore watches the website, AI proposes changes, and the Tax Partner approves them. Rules carry effective dates so earlier periods are tested under the rules that applied then.
Figure 5 – How FTA changes reach the tool
[TABLE]
Element | Specification
Domains | VAT, INPUT_VAT, CT, TRN, SAMPLING, BENFORD, LEGAL_REF
Versioning | effective_from / effective_to; no overlapping approved versions; approved versions immutable
Watched sources | Seeded with FTA legislation page, public clarifications, guides, and specifically: FTA Decision No. 13 of 2026, FTA Decision No. 17 of 2026, VAT Public Clarification VATP046, amended VAT Executive Regulation
Monitor | Weekly + 'Check now'; respectful fetching; manual PDF upload mode
AI proposal | Few-shot extraction prompt (2.2) → JSON proposal with citation → status 'proposed'
Approval | Tax Partner (tax domains) or Partner (methodology domains), never Admin (D43, D47); mandatory comment; side-by-side old vs new
Stale results | When a rule version used by a result is superseded for the same period, the result is marked STALE; WP sign-off and export are blocked until re-run or the reviewer records a justified override
[/TABLE]
## 3.5 Working Calendar
Non-working days differ by emirate and employer (one, two or three days off; half days; historical weekend changes such as Fri/Sat to Sat/Sun from 1 January 2022). Users maintain this through screens; the engine never assumes a weekend.
Figure 6 – Calendar layers
[TABLE]
Layer | Detail
1 Federal holidays | Admin; yearly list; Islamic holidays 'Provisional' until announced
2 Emirate profile | Admin; emirate-specific weekend or holidays
3 Company work week | Manager/Senior; off-days Mon–Sun, half-day cut-off times, dated periods (non-overlapping)
4 Company exceptions | Extra closures or working holidays
5 Engagement calendar | Resolved automatically; month preview; hash stored with JE results and printed in WP
Stale results | Any change to layers 1–4 affecting the audit period marks JE results STALE (same blocking rule as 3.4)
[/TABLE]
## 3.6 Large data and background jobs
Upload: chunked/resumable upload; default limit 500 MB (configurable); stored in private storage, not in the browser.
Processing: chunked parsing into Parquet; validation, JE tests and Benford run as background jobs with progress %, cancel and retry.
Screens: server-side pagination, filtering and sorting; exports generated as jobs for large tables.
Performance target: 1 million GL lines imported and JE-tested in under 10 minutes on production sizing (to be confirmed in UAT).
## 3.7 User experience and error standards
[TABLE]
Standard | Requirement
Formatting | AED 1,234,567.89, right-aligned; dates dd-MMM-yyyy; navy/white theme; sortable, filterable tables with CSV/Excel export
Error messages | Say what, where and what to do, e.g. 'Debits exceed credits by AED 0.05 – check voucher JV-0142 (rows 142, 387).' Critical errors block the next step; warnings allow continue with a reason
Help | Every tab has a Help panel: purpose, ISA reference, two-line plain-language guide
Empty states | Explain the next step ('Upload a ledger to start') with a button
Stale banner | Amber banner with 'Re-run' button and list of what changed
Confirmation | Destructive actions (delete, unlock) require confirmation and reason
Accessibility | Keyboard navigation, readable contrast, no information by colour alone
[/TABLE]
## 3.8 Input-VAT recovery checks (M15)
FTA Decision No. 13 of 2026 (issued 22 July 2026, effective 1 October 2026) requires taxable persons to verify suppliers and supplies before deducting input tax, under Article 54 (bis) of the VAT Law. FTA Decision No. 17 of 2026 (issued 9 September 2026, effective 1 October 2026) sets six cases and conditions for recovering input tax on employee expenses: transport, food and beverages, accommodation, temporary accommodation for new employees, mobile/internet and parking. For audit clients, these create new exposure areas worth testing.
Figure 7 – Input-VAT checks
[TABLE]
Check | How the engine supports it
Scope | Purchase lines where input VAT is deducted on or after the effective date in the Rules Library
Supplier verification register | Lists suppliers with deductions; client's verification date and evidence reference imported or entered; flags first-time suppliers and suppliers not verified within the period set in the Rules Library
Spend threshold | Rolling 12-month spend per supplier; flags suppliers above the threshold in the Rules Library needing bank-account evidence and public-information review
Risk indicators | Fields for address/key-staff changes and disproportionate transactions; requires a written explanation where indicated
Employee expenses | Auditor maps expense accounts to the six Decision 17 categories; lines in mapped accounts listed for condition testing (all conditions per category must be met); unmapped staff-cost accounts flagged
Output | Exceptions flow to the testing grid, observations and WP sheet 'Input VAT'
Limits | The tool supports testing; whether conditions are met remains an auditor/tax judgement. All thresholds and conditions to be verified by the Tax Partner before go-live
[/TABLE]
## 4. Security and Data Protection
[TABLE]
Control | Requirement
Data residency | Production data, backups and logs in the UAE (Azure UAE North or firm servers)
Identity | Entra ID SSO, MFA, role mapping from security groups; no shared accounts
Authorisation | Engagement membership checked on every API call and in database row-level security
AI payload | Only anonymised fields; unit test fails if TRN, party, client name, email, phone or IBAN reaches the payload
Encryption | TLS in transit; encryption at rest; private storage for evidence
Logging | No ledger rows or party names; insert-only audit log for user actions
Backups & retention | Daily backups, tested restore quarterly, retention aligned with firm and legal requirements
Change control | Pull requests, automated tests, reviewer approval, release notes, version printed on every WP
Vendor review | IT to review Lovable, AI provider and hosting terms before production
[/TABLE]
## 5. Reliability and Tool Validation
[TABLE]
No software can guarantee correct audit conclusions. AuditSmart aims for calculations that are exact and reproducible against independent checks, AI kept out of all numbers and approvals, and every output reviewed by a qualified auditor.
[/TABLE]
Figure 8 – Five layers of control
## 5.1 Controls
[TABLE]
Control | How
Golden tests | Engine output vs Excel workbook to the fils; mismatch blocks release
Edge-case suite | Appendix B file: top stratum, credit notes, unbalanced vouchers, bad dates, weekend change, half days, invalid TRNs
Property tests | Same seed = same sample; sample ⊆ population; strata sum to population
Reproducibility record | File hash, seed, rule versions, calendar hash, engine version, user, time
Stale-result lock | Sign-off and export blocked when rules or calendars change after a run
Parallel run | Re-perform a closed engagement area; partner accepts differences
[/TABLE]
## 5.2 Tool validation file (ISQM 1)
Because the firm will rely on AuditSmart in performing engagements, keep a validation file that the quality management function can review:
Scope and intended use statement (what the tool does and does not do).
Methodology mapping to ISA requirements and firm manual.
Test report (unit, golden, edge-case, security) for the release.
Parallel-run comparison and partner acceptance.
Rules Library verification checklist signed by the Tax Partner (Appendix D).
UAT sign-off by preparers and reviewers.
Known limitations and user guidance.
Change log; re-validation required for any change to calculation services.

## Appendix A – Database Schema (core tables)
[TABLE]
Table | Key columns and rules
clients | id, client_code (unique), name, emirate, entity_type
engagements | id, client_id, fye, framework, materiality, perf_materiality, trivial, status
engagement_members | engagement_id, user_id, role
datasets | id, engagement_id, file_name, sha256, rows, total_dr, total_cr, storage_ref, status
validation_errors | dataset_id, severity, field, rows (int[]), message, guidance
samples | id, engagement_id, dataset_id, method, parameters jsonb, cf_value, formula_text, seed, file_hash, rule_versions_used jsonb, engine_version, status (current/STALE), created_by/at
sample_items | id, sample_id, line_ref, book_value, top_stratum bool, attributes jsonb, audited_value, misstatement, remarks, evidence_ref
je_runs | id, engagement_id, dataset_id, parameters jsonb, calendar_hash, rule_versions_used jsonb, engine_version, status
je_flags | je_run_id, line_ref, flags text[], risk_score
input_vat_runs / supplier_register / expense_mapping | per SPEC 3.8
observations | id, sample_item_id, text jsonb, ai_generated, prompt_version, model, reviewed_by, reviewed_at
workpapers | id, engagement_id, wp_ref, status (draft/prepared/reviewed/locked), preparer, reviewer, dates, tool_version
rule_versions | id, rule_key, value jsonb, effective_from, effective_to, source_url, source_doc_hash, status (pending_verification/proposed/approved/rejected/superseded), proposed_by, approved_by, approved_at, comment. Constraint: no overlapping approved periods per rule_key
watched_sources / update_alerts | url, type, active, last_hash, last_checked / source_id, detected_at, summary, proposal_ids, status
holidays | date, name, scope (FEDERAL/EMIRATE), emirate, status (provisional/confirmed)
emirate_profiles | emirate, off_days int[], effective_from, effective_to
company_workweeks | client_id, off_days int[], half_days jsonb {weekday: cutoff}, effective_from, effective_to. Constraint: non-overlapping per client
company_exceptions | client_id, date, type (EXTRA_HOLIDAY/WORKING_DAY), note
jobs | id, type, engagement_id, status, progress, error, result_ref, timestamps
audit_log | id, user_id, action, entity, entity_id, old jsonb, new jsonb, at – insert-only
[/TABLE]
## Appendix B – Test Data Specification
[TABLE]
File / sheet | Must contain
dummy_gl.csv | 3,000 balanced multi-line vouchers; top-stratum items; credit notes; all planted errors in answer_key.csv
edge_cases.csv | Unbalanced vouchers, bad dates, formatted amounts, blank accounts, duplicate IDs, 14/15-digit TRNs
fy2021_2022.csv | Postings across a Fri/Sat → Sat/Sun weekend change on 1 Jan 2022
answer_key.csv | line_id and error_type for every planted error
golden_results.xlsx – Population | Totals, counts, Dr/Cr check
– MUS 90% / MUS 95% | CF, n, J, random start, selected line_ids for seed 2025
– Projection | Fully worked MUS evaluation with 3 misstatements incl. one top-stratum item
– Calendar | Expected non-working flags for 3 client profiles (1, 2, 3 off-days) and half day
– VAT / Input VAT | Expected variances, TRN failures, supplier and threshold flags
[/TABLE]

---
## Part 4 – Stage 3 implementation notes (engine changes, kept in sync per prompt)

### 3.2 Import and validation
- **Schema additions (marked `# +` in models):**
  - datasets: status, size_bytes, chunks_received, rows, total_dr, total_cr, mapping, profile, parquet_ref, created_by
  - validation_errors: id (int), code, row_count
  - jobs table
- **Dataset status flow:** uploading → uploaded → parsing → parsed → validated | blocked (or failed).
- **Upload protocol:** see plans/3.2_plan.md. Each chunk is ≤ UPLOAD_CHUNK_MB (8); a file is ≤ MAX_UPLOAD_MB (500). SHA-256 is stored, and a mismatch returns 409.
- **Row convention:** row 1 = the first data row under the header (same as answer_key.csv).
- **Error codes:**
  - critical: unbalanced_voucher, total_out_of_balance, unreadable_date, unreadable_amount, blank_account, missing_mandatory_field, missing_mandatory_column, duplicate_line_id
  - warning: amount_currency_prefix, amount_precision, invalid_trn (`^100\d{12}$`), voucher_gap, gl_tb_difference
  - When a column is missing, only missing_mandatory_column is reported for it; the row-level blanks are suppressed.
- **Rules placeholders:** validation.balance_tolerance = 0.00, validation.trn_pattern, validation.amount_decimal_places = 2. All are pending_verification.
- **Downstream guard:** `app.api.v1.datasets.ValidatedDataset` returns 409 unless status = validated.
- **CLI:** `python -m app.cli validate FILE [--kind GL|TB] [--json] [--map field=Header]`.

### 3.3 Sampling (ISA 530)
- **Endpoints:**
  - `POST /v1/sample` → 201 SampleOut
    - 409 if the dataset is blocked or not validated
    - 422 for sampling input errors (plain message)
    - 403 for non-members
  - `GET /v1/samples/{id}`.
- **Request:**
  - `dataset_id`
  - `method` (mus | random | systematic | stratified | key_items_mus)
  - `basis` (debit | credit | signed | absolute)
  - `account_types[]`, `account_codes[]` (`prefix*` allowed)
  - `confidence` ("80" | "90" | "95" | "99")
  - `tolerable_misstatement`
  - `expected_misstatement_pct` (default from rules: 0.10)
  - `size_formula` (firm | guide)
  - `sample_size`, `key_item_threshold`, `strata_boundaries[]`, `num_strata`
  - `seed` (0..2^31−1)
  - Money is sent as strings.
- **Firm size formula (default, D1):**
  - n = ROUNDUP(Pop×CF/(TM − Exp×EF)); J = Pop/n; BP = CF×J.
  - Expected misstatement > 50% of TM is refused; n < 5 → `status: no_sampling`.
- **Selection:** first line with cumulative ≥ start + kJ. The start is truncated to 0.01 and drawn from numpy `default_rng(seed)` (D7). docs/step3.3_golden_start.md holds the seed-2025 start for golden B17.
- **Rules:** `sampling.*` keys are in seed_data/rules_seed.json (pending_verification). Each result stores `rule_versions_used`.
- **Schema addition:** `samples.result` JSON `# +` (migration 0002). SampleItems hold row_no, hits, selection_points and stratum in `attributes`.

### 3.4 JE testing (ISA 240) & Benford
- **Endpoints:**
  - `POST /v1/je-tests` → 202 `{je_run_id, job_id, status_url, result_url}`; runs as a background job (`type je_tests`).
    - 409 if the dataset is blocked or not validated; 404 unknown dataset; 403 non-member; 422 for an unknown test or parameter.
  - `GET /v1/je-tests/{id}` → the full result (summary per test, flags with reasons, score distribution, selection, sequence gaps, Benford, calendar summary + hash, parameters with sources, rule versions).
  - `POST /v1/benford` → 200 `{dataset_id, account_types, min_amount}`; 422 when no amounts qualify.
- **Criteria (13):** non_working_day (weekend / holiday / company_closure from the resolved calendar), after_half_day_cutoff, round_sum, period_end, rare_user, senior_user, large_amount, vague_narration, manual_sensitive, duplicate_invoice, duplicate_party_amount_date, unusual_account_pair, unbalanced_voucher. Sequence gaps per voucher series are reported (summary only).
- **Parameters:** defaults from `je.*` rules (firm_methodology_v0.2 §5, D3); per-request overrides `parameters{}` (round_multiple, round_min, period_end_days, rare_user_max_pct, vague_keywords, account_pair_min_count, score_test, score_judgement, judgement_min_items, manual_voucher_prefixes, sensitive_account_types, sensitive_account_codes, senior_users, large_amount, tests[]). Each parameter's source ("override" or rule ref) is stored.
- **Scoring:** risk_score = number of flags; ≥ 3 → `test`; ≥ 2 → `judgement`; if fewer than `judgement_min_items` are tested, the largest score-2 lines are topped up as `test_topup` (D13).
- **Calendar (core brought forward from 3.10, D10):** `services/calendar.py` resolves company exception > company work week > emirate > federal, holidays on top. Federal fallback layer in `seed_data/calendar_seed.json` (Fri/Sat to 2021-12-31, Sat/Sun + Friday half-day 12:00 from 2022-01-01; holidays per docs/holiday_sources.md; pending_verification). Each run stores `calendar_hash` (sha256 of the canonical resolved days).
- **Benford:** first digit, amounts ≥ `benford.min_amount` (10); MAD thresholds 0.006 / 0.012 / 0.015 (Nigrini); chi-square 8 df at alpha 0.05 (scipy); z with continuity correction, significant at z > 1.96.
- **Schema additions (migration 0003):** `je_runs.job_id`, `result` JSON, `created_by`, `created_at`; `emirate_profiles.half_days` JSON (all `# +`). Older current runs on the same dataset become `superseded`. JeFlag rows hold one row per flagged line.
- **Detection (tests/golden/test_je_detection.py):** 100% planted vs detected, 0 extras, for dummy_gl (7 types) and fy2021_2022 (weekend change, 60/60), with both methodology defaults and the prompt values.

### 3.5 Output VAT & evaluation
- **Endpoints:**
  - `POST /v1/vat-check` → 200 `{dataset_id, sides[output|input]}`: line-level recalculation, an exceptions list (variance / unknown_code / missing_net) with a likely cause, a summary by side and code, and TRN pattern checks on every non-blank TRN with the reason. Errors: 409 dataset blocked or not validated; 404; 403; 422 bad sides or a missing rule for a date.
  - `POST /v1/evaluate` → 200 `{sample_id, method?: mus|ratio, tolerable_misstatement?, items[{line_ref, audited_value, remarks?, evidence_ref?}]}`. It writes audited value, misstatement, remarks and evidence_ref to the SampleItems and stores `result.evaluation` (returned by `GET /v1/samples/{id}`). Errors: 404 unknown sample; 403; 422 for an unknown or duplicated line, a missing TM, MUS on a non-MUS sample, or no factors for the confidence level (D6).
- **VAT:** expected = ROUND_HALF_UP(net × rate, 2), with the rate from `vat.rate.{code}` valid on the invoice date (entry_date, else posting_date). An exception is |recorded − expected| > `vat.tolerance` (0.01, D17). Output side = Revenue accounts; input = everything else.
- **MUS evaluation (classic, firm_methodology_v0.2 §5):**
  - Misstatement = book − audited.
  - Top stratum (book ≥ J) and key items are counted at actual value.
  - Otherwise projected = tainting × J.
  - BP = CF × J.
  - IA = Σ |projected| × (factor(rank) − 1). The factors come from `sampling.mus.if.{conf}`; ranks follow COUNTIFS ties; a rank beyond the table uses the last factor (D14).
  - UML = BP + Σ projected + IA, checked against TM → "Acceptable" / "Exceeds - further work". Understatements are reported separately (D15).
- **Ratio evaluation:** per stratum, Σ misstatement / Σ book × the population value of the stratum (excluding key/top items), plus actual key/top misstatements. It is non-statistical (D16).
- **Golden:** tests/golden/test_evaluation_vat_golden.py matches every cell of the Projection sheet (95% and 90%, to 1e-6 on exact values and to the cent on rounded ones) and of the VAT sheet (12 output exceptions F6:G17, 0 input, 5 invalid TRNs). The module docstring holds the hand-worked example.

### 3.6 Working paper (ISA 230)
- `POST /v1/workpaper` (201) builds an 11-sheet `.xlsx` from **stored** results only (no recalculation): Lead, Population, Sampling, Sample & Testing, JE Risk, Benford, Evaluation, Input VAT, AI Drafts, Rules & Calendar, Sign-offs (D18). `GET /v1/workpapers/{id}` returns metadata and `GET /v1/workpapers/{id}/file` the file.
- Gate (D19): a STALE included result → 409 unless a Manager/Partner override with a justification ≥ 20 chars; non-Manager override → 403; short justification → 422; AI-generated observations without `reviewed_by` → 409 listing line refs.
- Formatting: title "{client} – {sheet}", WP ref | FYE | tool version line, frozen panes, landscape A4 fit-to-width, print titles, footer "WP {ref} / Page &P of &N / tool version", AED number format; Yes/No/N/A validations on Sample & Testing; Benford bar chart.
- Rules & Calendar lists every rule version used (key, ref, version, value, status, used by, source URL — blank until 3.8, D20) and the calendar hash, period, emirate and layers (`calendar.summary()["layers"]`).
- Storage: `storage/workpapers/{id}.xlsx`; `workpapers` gains `file_ref`, `sha256`, `manifest`, `created_at` (migration 0004). Status `prepared`; an audit-log row `generate` per WP.

### 3.7 Anonymiser & AI gateway
- `POST /v1/ai/observation` {sample_item_id, failed_attribute, test, remark?, rule_keys[]} → 201. The anonymised payload has only these whitelisted keys: area, test, item_ref, amounts{book_value, audited_value, misstatement}, failed_attribute, applicable_references[{ref, citation}], auditor_remark. It goes to the provider with the system prompt `app/ai_prompts/observation_v1.txt` (a copy of prompts/observation_system_prompt.txt; `PROMPT_VERSION = observation@v1+<sha8>`) at temperature 0.2.
- The reply is validated by `ObservationDraft` (condition, criteria, cause, effect, recommendation, ml_point, wp_conclusion; extra=forbid). Code fences are tolerated. One retry with a corrective note; then 502. The draft label is appended to `wp_conclusion`. More than 220 words → warning.
- Stored as `observations` (ai_generated, prompt_version, model). The audit log holds ids, provider, model and prompt version only, never the payload.
- `GET /v1/observations/{id}`; `POST /v1/observations/{id}/review` (Senior/Manager/Partner; optional edited `text`) sets reviewed_by/at, which clears the 3.6 WP gate.
- Providers: `AI_PROVIDER` = gemini | azure_openai | stub; empty → 503. Keys come only from env (`GEMINI_API_KEY`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`) and are never logged. HTTPS only (D22).
- Security test (tests/security/test_ai_payload.py): every party name, TRN and the client name from data/*.csv is fed into remarks; the test fails if any reaches any payload. Sockets are blocked during AI tests.

### 3.8 Rules Library
- `rule_versions` gains `version`, `domain`, `unit`, `source_ref`, `created_at` (migration 0005). The seed (`seed_data/rules_seed.json`, 53 rules) is loaded idempotently by `rules.seed_database()` at app start-up (non-production) and in tests; production runs it as a deployment step.
- `get_rule(key, on_date)` returns exactly one version: approved wins; `pending_verification` is used only while `RULES_ALLOW_PENDING=true` (D24); duplicates → `RuleConflict` (409 on the API); none → `RuleNotFound` with a clear message. In-process cache, cleared on every write, 30 s TTL.
- Workflow: `propose` (status proposed, version N+1) → `approve` / `reject` (TaxPartner for tax domains, Partner for methodology domains, never Admin - D47; comment ≥ 10 characters). Approve closes the earlier open version, rejects other overlaps (D25), writes `audit_log` (rule_propose / rule_close / rule_approve / rule_reject), and marks STALE every current Sample / JeRun / InputVatRun whose stored refs lost coverage in an overlapping period (D26).
- Immutability: a `before_flush` guard refuses edits or deletes of approved rows except closing `effective_to` earlier and status → superseded.
- API: `GET /v1/rules`, `GET /v1/rules/resolve/{key}?on=`, `POST /v1/rules/proposals` (Manager/Partner/TaxPartner/Admin), `POST /v1/rules/{id}/approve`, `POST /v1/rules/{id}/reject`.
- `rule_proposals.parse_extraction` validates the AI rule-extractor JSON (schema + allowed key families, D28); `create_proposals` turns dated changes into proposed versions. The WP Rules sheet now reads source_ref/source_url from the library.

### 3.9 FTA rules monitor
- `watched_sources` gains `name`, `last_error`, `last_links`; `update_alerts` gains `kind` (change / failure / upload) and `details`, and `source_id` becomes nullable for uploads (migration 0006). Seed `seed_data/watched_sources.json` (9 rows): FTA legislation page and archive, VAT and CT guides & references (public clarifications), FTA news, and the Decision 17/2026 PDF, all active. Decision 13/2026, VATP046 and the amended VAT Executive Regulation have no recorded URL, so they are inactive `urn:auditsmart:pending:*` placeholders until the Tax Partner records the URL (D29).
- Fetching (`PoliteFetcher`): https only, `User-Agent: AuditSmart-RulesMonitor/<version> (...)`, robots.txt honoured (401/403 → disallow all, missing → allowed), 5 s per-host interval, 20 s timeout, 20 MB cap, no cookies, logins or auth headers. The transport is injectable; tests never touch the network.
- Text: BeautifulSoup (scripts and styles removed; same-host .pdf/.aspx/.htm(l) links collected) and pdfplumber; whitespace is normalised; SHA-256 of the text; snapshot stored at `storage/rules_monitor/<sha>.txt`.
- On a change (or the first check): the AI rule extractor (`app/ai_prompts/rule_extraction_v1.txt`, the same text as `prompts/rule_extraction_prompt.txt`, temperature 0) gets the Stage 2.2 input layout (`current_rules` / `document_url` / `document_text`, ≤ 60,000 chars). Its output goes through `parse_extraction` → `create_proposals` (status proposed; never approved automatically). If the AI is not configured or returns invalid output, an alert asks for manual review. A changed page with "No relevant change" is only audit-logged. New document links raise an alert even when the text is unchanged. Failures (HTTP, robots, empty text, bad PDF) create a `failure` alert and set `last_error`; one failing source never stops the run.
- Notifications: `log_notifier` by default; `teams_notifier` (https webhook) is available for Stage 7 configuration. Email and Teams are not enabled in Stage 3 (D30). A notifier error is recorded on the alert and never loses it.
- Schedule: `python -m app.cli monitor-check [--force]` checks sources not checked for 7 days; run it weekly (cron `0 6 * * 1` Asia/Dubai, Stage 7). Check-now: `POST /v1/rules-monitor/check` (background job).
- API (Admin / TaxPartner): `GET/POST /v1/rules-monitor/sources`, `PATCH /v1/rules-monitor/sources/{id}` (a placeholder can only be activated once it has an https URL; a URL change resets the baseline), `POST /v1/rules-monitor/check`, `POST /v1/rules-monitor/upload` (multipart PDF/HTML/text + optional https `source_url`), `GET /v1/rules-monitor/alerts`, `POST /v1/rules-monitor/alerts/{id}/close`.

### 3.10 Working calendar
- **Resolve:** `calendar.resolve_client(client_id, emirate|None, start, end)` returns a `ResolvedCalendar`: one `DayStatus` per day with is_working, reason, half_day_cutoff, source and provisional, plus a SHA-256 hash and a summary. Precedence: company exception > company work week > emirate > federal; holidays apply after the work week and before the company exception. `emirate` overrides the client's emirate (what-if).
- **Time zone:** times are Asia/Dubai (UTC+4, no DST). `to_dubai()` treats naive datetimes as Dubai wall time (UAE ERP exports) and converts aware ones. `posting_label()` gives the golden wording, and a posting exactly at the cut-off is still working.
- **Validation:** periods must not overlap within a level (and, for emirates, within one emirate). There is one company exception per date. A day cannot be both off and a half day. Cut-offs are HH:MM. EMIRATE holidays need an emirate; FEDERAL holidays have none. Status is confirmed or provisional.
- **Seed:** before the first DB edit of the federal weeks or holidays, the seed rows are copied into the tables, so nothing is dropped silently (D32).
- **Roles:**
  - Company layer (work weeks, exceptions, import): Admin, or a Partner/Manager who is a member of any engagement of the client.
  - Federal/emirate weeks and holidays: Admin only.
  - Reads: Admin or any engagement member of the client.
- **Excel:** sheets Instructions, WorkWeeks (Off days "Sat, Sun", Half days "Fri 12:00", Effective from, Effective to, Source), Exceptions (Date, Type, Note) and Holidays (Date, Name, Scope, Emirate, Status).
  - Import defaults to preview: counts plus errors located by sheet, row, column and message. `apply=true` is refused while any error remains.
  - Applying replaces the client's work weeks and exceptions and adds new holidays (Admin only; duplicates are skipped).
  - Limits: 5 MB and 5,000 rows per sheet.
- **STALE (D33):** after every write, each current JE run of the affected clients is re-resolved over its stored period (`result.calendar.start/end`). If the hash differs from `je_runs.calendar_hash`, the run becomes STALE with an `audit_log` "stale" row (reason, old and new hash). Writes return the list of runs marked STALE.
- **API:**
  - `GET /v1/calendar/resolve`
  - `GET /v1/calendar/clients/{id}`
  - `POST /v1/calendar/clients/{id}/workweeks|exceptions`
  - `DELETE /v1/calendar/clients/{id}/{workweeks|exceptions}/{item}`
  - `POST /v1/calendar/emirate-profiles|holidays`
  - `PATCH /v1/calendar/holidays/{id}`
  - `DELETE /v1/calendar/{emirate-profiles|holidays}/{id}`
  - `GET /v1/calendar/template`
  - `GET /v1/calendar/clients/{id}/export`
  - `POST /v1/calendar/clients/{id}/import?apply=`
- **Golden:** the Calendar sheet's 12 cases match for P1–P4, and also when given as UTC instants. fy2021_2022: the non-working lines equal the 60 planted lines.

### 3.11 Background jobs and large files
- **Jobs table** (3.2, no migration): id, type, engagement_id, status queued/running/succeeded/failed/cancelled, progress 0–100 (monotonic), started_at, finished_at, error, result_ref, created_by.
- **Backends (D36):** `JobBackend` protocol (`dispatch(job_id, task, kwargs)`, `run_callable`). Eager (JOB_EAGER, tests), Thread (default without Redis) and RQ (`REDIS_URL` set; queue `auditsmart`; worker `python -m app.cli worker [--burst]`). An Azure Queue adapter only needs the same two methods (`jobs.set_backend`).
- **Tasks:** registered with `@jobs.task(name)`, JSON kwargs only, so they can run in another process: `parse` (import), `validate`, `je_tests`, `workpaper` (large export), `input_vat_check` (3.12). Closures with live objects (FTA monitor) stay in-process via `jobs.submit` (D37).
- **Errors:** a `JobError`/message is stored as given; any other exception is stored as "{Type}: the job failed. Check the file and try again." (no stack traces or data in the row).
- **Cancel (D38):** `POST /v1/jobs/{id}/cancel` → queued jobs never start; running jobs stop at their next progress update; a cancel wins over a late finish; finished jobs → 409. Allowed for the creator, an engagement Manager/Partner, or an Admin who can see the job (D39).
- **List:** `GET /v1/jobs?engagement_id&status&type&offset&limit≤200` → {total, items}; visible = jobs of the caller's engagements, plus their own jobs without an engagement.
- **Paginated rows:** `GET /v1/datasets/{id}/rows` adds `user_id`, `date_from`, `date_to` (posting date) and `min_amount` (max(debit, credit) ≥), pushed down to Parquet; `GET /v1/je-tests/{run_id}/flags?flag&min_score&offset&limit≤1000` ordered by risk score. `POST /v1/workpaper/jobs` → 202 {job_id, status_url}.
- **Large files:** JE reads only `JE_COLUMNS` from Parquet in batches and runs Benford column by column (D39). `scripts/perf.py` gives the 1M-line timings in docs/PERFORMANCE.md.

### 3.12 Input-VAT checks (Decisions 13 and 17 of 2026)
- **Inputs:** the validated GL dataset (purchase lines: `vat_amount > 0` and `debit > 0`; gross = debit + VAT; date = posting date, else entry date), the engagement **supplier register** (`supplier_registers`, CSV upload, replaces; aliases party_id→supplier_id, party_name→supplier_name, verification_ref→evidence_ref, bank_evidence→bank_evidence_ref; risk indicators split on `;`/`|`; row errors (blank / duplicate ID, bad date) reject the whole upload with row numbers, 422) and the **expense mapping** (`expense_mappings`, account → Decision 17 category; each category must be in `input_vat.employee_expense.categories`). Both replacements are audit-logged (`supplier_register_replace`, `expense_mapping_replace`).
- **Rules (all `pending_verification`, D24/D27):** `input_vat.verification.effective_date` (2026-10-01), `.spend_threshold` (375,000.00), `.revalidate_months` (12), `.exception_below` (10,000.00, note only), `input_vat.employee_expense.categories`. Each lookup uses the deduction date; versions used are stored in `rule_versions_used`, so a rule change marks the run STALE (3.8).
- **Checks (D40):** `unverified_supplier` (deduction on/after the effective date; supplier not in register, no verification date, verified after the deduction, or verified ≥ revalidate_months before it), `spend_threshold` (rolling 12-month gross per supplier > threshold and no bank evidence; one exception per supplier at the crossing line, with `rolling_total`), `risk_indicator_unexplained` (once per supplier), `employee_expense` (every line in a mapped account, whole period, `before_effective_date` flag), `staff_cost_unmapped` (unmapped account with categorised lines or a staff-like name and VAT lines). Exemption thresholds are recorded as `below_exception_threshold`, never applied.
- **TEST-ONLY `effective_date_override` (D4/D40):** moves the effective date; rules are resolved on deduction date + (rule effective date − override) so 2025 test data uses the same versions. A warning is put on the result.
- **Job + API:** `POST /v1/input-vat-check {dataset_id, effective_date_override?}` → 202 {input_vat_run_id, job_id, status_url, result_url}; task `input_vat_check` streams `COLUMNS` from Parquet; run status queued → current (earlier current runs for the dataset → superseded) or failed / cancelled. `GET /v1/input-vat-check/{id}`, `GET /v1/input-vat-check/{id}/exceptions?check&offset&limit≤1000`. `PUT/GET /v1/engagements/{id}/supplier-register`, `PUT/GET /v1/engagements/{id}/expense-mapping` (write: Partner/Manager/Senior/Staff members; read: any member). Migration 0007 adds `job_id`, `result`, `created_by`, `created_at` to `input_vat_runs`.
- **Result:** engine_version, effective_date, parameters, population, summary [{check, lines, value}], exceptions, employee_expense_by_category, conclusion, basis, warnings, rule_versions_used, rules_pending_verification. The WP "Input VAT" sheet (3.6) reads it via `input_vat_run_id`.
- **Answer key (dummy_gl.csv, override 2025-10-01, mapping 6050 transport / 6060 accommodation_operational / 6070 mobile_phone_internet / 6080 parking / 6090 food_beverages_remote):** 15 unverified-supplier, 3 spend-threshold and 20 employee-expense lines, exact line sets (tests/api/test_input_vat_api.py).

### 5.2 Engagement sync (Stage 5, D50–D55)
- **Why:** Lovable (Supabase) owns clients, engagements and teams; every engagement-scoped engine call checks membership and the firm boundary, so the engine needs a copy. Details: docs/MULTI_FIRM_APPROVAL.md §10.
- **`PUT /v1/engagements/{id}`** (id = the Lovable uuid, ≤36 chars) body `{client:{id, client_code, name, emirate, entity_type?}, fye, framework?, materiality?, perf_materiality?, trivial?, status?, members:[{user_id, role}]}` → **201** (created) / **200** (updated) `{created, engagement, client, members, stale}`. Idempotent: the same body twice → 200 and no new audit row. `members` replaces the whole team (needs ≥1 Manager or Partner; user_ids unique; roles normalised, e.g. `tax_partner` → TaxPartner). Optional fields left out keep their value; `null` clears. Money is Decimal (≤2 dp, ≥0; perf_materiality and trivial ≤ materiality) and returned as strings. `status` lower-cased, default `planning`. Emirate codes (DXB, AUH, …) map to names.
- **`GET /v1/engagements/{id}`** → the same shape (`created: null`) for team members or the firm's Admin.
- **Authorisation (D51):** firm from the token only, must be registered (`POST /v1/firms`; otherwise 403). Create: app role Manager / Partner / TaxPartner / Admin. Update: team member with engagement role Manager / Partner / TaxPartner, or the firm Admin. Other firm's engagement → 403; other firm's client id → 404; client or engagement not linked to a firm → 409; an engagement never moves to another client → 409; client_code unique per firm (D52, migration 0010) → 409.
- **Audit:** `client_sync_create/update`, `engagement_sync_create/update` with old/new values (members and firm_id included), only when something changed.
- **STALE (D53):** a changed `fye` marks every current sample, JE run and input-VAT run of the engagement STALE (`stale` rows, reason "year end changed A -> B"); a changed client emirate re-checks the client's JE runs against the calendar (hash comparison, D33). Materiality, framework, status and team changes are audit-only (materiality feeds no engine calculation).

### 5.3 Import mapping overrides and error text (Stage 5, D56, engine 0.2.2)
- **Where:** `mapping_override` on `POST /v1/datasets` (form field, JSON), `POST /v1/uploads/{id}/complete` and `PUT /v1/datasets/{id}/mapping`. All three run `importer.normalise_override` against the file's header row **before** any job is queued.
- **Accepted:** `{field: header}` with canonical field names, labels or synonyms as keys (`posting_date`, `Posting Date`, `date`, `GL Date`; `Dr` → debit); the reversed `{header: field}` when the key is a column of the file and the value names a field (an exact field name when the key could itself be a field, e.g. `{"Dr": "debit"}`); header values matched exactly, then by a unique case/space-insensitive match; `""` or `null` unmaps a field. Fields not in the override keep the automatic suggestion.
- **Refused (422, `detail` is one plain-English string, every problem listed):** unknown keys (with the allowed field list), a header not in the file (with the file's columns, first 40), non-text values, a field mapped twice, a non-object override. The dataset keeps its status and no job is created; a chunked upload keeps its chunks so `complete` can be retried. A file whose header block is not UTF-8 is refused at upload (422).
- **Parse job errors:** `importer`/`ValueError` failures become a `DatasetError` with the reason (mapping problem, "The file is not UTF-8 text …", CSV/Excel unreadable, first line of any other `ValueError`, max 200 chars). `jobs.job_error_text` keeps `.message`, or `str(exc)` for errors marked `user_facing`; anything else stays generic. No stack trace or row values are stored.
