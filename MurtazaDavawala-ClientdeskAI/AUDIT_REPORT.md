# Clientdesk AI v1.1: Code & Architecture Audit

**Scope:** `clientdesk_verification.py` (schema DDL, domain logic, 16-gate test suite)
**Environment:** Python 3.11, SQLite 3.40.1 (FTS5 enabled)
**Method:** (1) ran the supplied suite unchanged; (2) ran 31 adversarial probes (`adversarial_probes.py`), each attempting something the requirements say must be impossible; (3) built a hardened v1.2 (`clientdesk_v1_2.py`) and re-verified it.

---

## 1. Test results

| Suite | Result |
|---|---|
| Supplied v1.1 suite | **16 / 16 passed** (10.6 s) |
| Adversarial probes vs v1.1 | **29 gaps confirmed / 31 probes** |
| v1.2 suite (16 original gates + 38 regression tests) | **54 / 54 passed** (6.5 s) |

**Why 16/16 is misleading:** the suite only checks the "happy path". Each gate proves that one route is blocked, not that every route is blocked. Examples:
* `test_06` itself **deletes snapshot rows** from an open engagement. That is the exact loophole that defeats the readiness gate.
* `test_05` is named "immutable snapshot" but actually tests template isolation. Immutability is only tested in `05b`, and only for 2 of 5 columns.
* `assertRaises(IntegrityError)` never checks the error message, so a test can pass for the wrong reason (a different trigger firing).
* No test covers INSERT paths, the COMPLETED status, NULL reviewers, or what happens after submission.

---

## 2. Requirement-by-requirement verdict (v1.1)

| # | Requirement | Verdict | Key evidence |
|---|---|---|---|
| 1 | Scope lock: 6 groups / 8 services | ⚠ **PARTIAL** | INSERT is locked by CHECK. But `GST_REG` can be **re-labelled under group 'ITR'** (no code↔group pairing), services can be **deleted** (8→7), and GST variants can be **re-pointed to ITR via UPDATE** (the trigger is INSERT-only). |
| 2 | PBKDF2 600k, salt, constant-time, downgrade protection, masking | ⚠ **PARTIAL** | 600k rounds, 16-byte salt and `hmac.compare_digest` ✔. **Downgrade floor is 100k**, so a 100k hash still verifies (6× weaker than OWASP). No salt/hash length check, no rehash-on-login, no lockout. Masking is **display-only**: the DB accepts any PAN/GSTIN text, and `mask_gstin` reveals GSTIN position 12, which is the PAN check character. |
| 3 | SoD: operator cannot approve own work | ❌ **FAIL** | Assignee sets `reviewer_id = NULL` and approves (the role trigger skips NULL). An engagement can be **INSERTed directly as APPROVED**. `NOT_STARTED → APPROVED` skips review entirely. There is no `approved_by` column, so the DB never records *who* approved. A SENIOR assignee can **waive their own** mandatory items. |
| 4 | Readiness vs collection; N/A excluded | ⚠ **PARTIAL** | The two metrics are separated and `applicability_status = NOT_APPLICABLE` is excluded ✔. But: N/A has **two sources of truth** (`collection_status='NOT_APPLICABLE'` still counts); **collection % drops 100→0** when items move RECEIVED → UNDER_VERIFICATION; STAFF can mark **every MANDATORY item N/A** with no approval; and Python and the DB **disagree on an empty checklist** (Python says not ready, DB lets it through). |
| 5 | DB gate blocks SUBMITTED/APPROVED < 100% | ❌ **FAIL** | `NOT_STARTED → COMPLETED` at 0% is allowed (COMPLETED isn't gated). The gate only fires when entering from *outside* the review set, so items flipped to DEFICIENT during review can still be **APPROVED**. INSERT is ungated. Deleting mandatory rows also satisfies the gate. |
| 6 | Snapshots tamper/delete-proof | ⚠ **PARTIAL** | The 3 text columns are immutable ✔. Rows **can be deleted while open**, **moved to another engagement** (`engagement_id` is mutable), **inserted after completion**, and statuses **edited after approval**. `PRAGMA foreign_keys=ON` is only set inside the DDL script, so every new app connection runs **without FK enforcement**. |
| 7 | SHA-256 duplicate prevention | ✅ **PASS (scoped)** | `UNIQUE(engagement_id, sha256)` works through `register_document`. Hardening gaps: no hex/length CHECK (an upper-case digest bypasses the duplicate check via direct SQL), a document can point at **another engagement's checklist item**, and FK errors are reported as "Duplicate file". Same file across engagements is allowed, which is reasonable (the same PAN card serves GST and ITR) but should be a stated decision. |
| 8 | Offline FTS5 auto-sync | ✅ **PASS** | INSERT/UPDATE/DELETE triggers keep the index in sync (verified). Improvements: raw user text crashes `MATCH` (e.g. `GST-REG "`), there is no stemming ("thresholds" ≠ "threshold"), and content is stored twice (not external-content). |

### Overall verdict v1.1: **NOT COMPLIANT** (2 pass · 4 partial · 2 fail)
The design is sound: DB-level enforcement, snapshots, and splitting readiness from collection are the right ideas. But most controls guard one code path and leave neighbouring paths (INSERT, DELETE, other statuses, NULLs) open.

### Verdict v1.2: **COMPLIANT** with requirements 1–8 (all 54 tests pass, all 29 gaps closed or deliberately accepted with a test documenting the decision)

---

## 3. What v1.2 changes

| Area | Fix |
|---|---|
| Catalogue | One `LOCKED_CATALOGUE` constant; CHECK on `code|group` pairs; no-delete and no-rekey triggers; variant trigger also on UPDATE; NULL-safe subquery. |
| Passwords | Floor = 600k; salt ≥ 16 B and hash = 32 B enforced; `needs_rehash()`; `authenticate()` with 5-try / 15-min lockout and dummy-hash timing equalisation; DB CHECK on hash format; max password length. |
| PAN/GSTIN | GLOB format CHECKs; GSTIN chars 3–12 must equal PAN; `v_clients_masked` view for STAFF/READ_ONLY screens; GSTIN mask shows only state code + last 3. |
| Workflow | Enforced state machine (9 legal transitions); engagements must be created `NOT_STARTED`; no engagement deletes. |
| SoD | `submitted_by`, `approved_by`, `approved_at`, `last_actor_id`. Approver must be **the designated reviewer**, active, SENIOR+, ≠ assignee, ≠ submitter. Team/scope frozen once submitted. Waivers and mandatory-N/A decisions need an independent SENIOR+ and a reason (INSERT + UPDATE). |
| Readiness | Gate fires on **every** move into SUBMITTED/UNDER_REVIEW/APPROVED/COMPLETED; empty checklist = not ready (matches Python). CONDITIONAL items start `UNDECIDED` and must be decided; if APPLICABLE they become required. Collection counts UNDER_VERIFICATION. A single CHECK keeps both N/A fields in sync. `readiness_report()` lists the blockers for the UI. |
| Snapshots | No deletes; `engagement_id`/PK immutable; inserts only into open engagements in `NOT_REQUESTED`; fully frozen after approval; DEFICIENT needs a note. |
| Documents | Lower-case 64-hex CHECK; composite FK (item must belong to the same engagement); immutable rows; uploads closed after approval; accurate error messages; `find_document_elsewhere()` reuse hint. |
| Audit | Append-only `audit_log` filled by triggers (status moves, item status changes, uploads). |
| Search | External-content FTS5 with `porter unicode61`; `search_knowledge()` sanitises input, prefix-matches, ranks with bm25, returns snippets. |
| Platform | `connect()` turns FKs on for **every** connection and verifies it; `init_db()` is idempotent and versioned via `PRAGMA user_version`; indexes for dashboard queries; `sys.exit` instead of the `exit()` builtin. |

---

## 4. Architectural risks the triggers can't solve

1. **The DB doesn't know who is logged in.** Triggers can only check the `*_by` columns the app writes. All writes must go through `set_status()`, with `actor_id` taken from the authenticated session and never from form input. Users must never get raw SQL access.
2. **SQLite file = full trust.** Anyone with write access to the `.db` file can `DROP TRIGGER`. These controls protect against app bugs and staff misuse through the UI, not against someone holding the file. For a multi-user team, use PostgreSQL with DB roles (app role without DDL rights) or, at minimum, a hash-chained audit log plus off-box backups.
3. **Don't put the SQLite file on a shared network drive.** WAL mode does not work over SMB/NFS and corruption is likely. Run one server process (e.g. FastAPI) on one machine and let the team use a browser.
4. **Statutory content changes.** Thresholds, due dates and forms change through CBIC and CBDT notifications. Keep them as dated data rows with an effective-from date, not as code, and show "last verified on" on every knowledge article.

---

## 5. Requirement gap against *your* business brief

Your brief listed: company formation, LLP, GST registration, ITR filing, **GST monthly filing**.

| Your need | Catalogue v1.1 | Action |
|---|---|---|
| Company formation | `COMPANY_INC` ✔ | – |
| LLP | `LLP_INC` ✔ | – |
| GST registration | `GST_REG` + 8 variants ✔ | – |
| ITR filing | `ITR_SALARIED`, `ITR_BUSINESS` ✔ | – |
| **GST monthly filing (GSTR-1 / GSTR-3B / QRMP)** | **Missing**; only `GST_ANNUAL` exists | Add `GST_RETURN_PERIODIC` under group *GST* (keeps 6 groups → 9 services). Needs a sign-off change to the "exactly 8" lock. v1.2 already adds `period_label` + `UNIQUE(client, service, period)` so monthly jobs can't be duplicated. |
| Partnership, MCA annual | present (not in your brief) | Fine to keep. |

**Recommended next features (by value):**
1. **Recurring job generator**: auto-create monthly GST and annual ITR/MCA engagements per client on the 1st of each period.
2. **Client upload link**: a tokenised, expiring link per engagement so clients upload against each checklist line instead of WhatsApp. Files are hashed, size/MIME-whitelisted and stored encrypted outside the DB.
3. **Reminders**: `reminder_count` / `requested_at` already exist in v1.2. Add scheduled email/WhatsApp nudges at T-7, T-3, T-1.
4. **Client KYC vault**: store PAN/Aadhaar/address proof once per client and reuse them across engagements (`find_document_elsewhere`).
5. **Reports**: staff workload, ageing of pending documents, overdue by service, reviewer turnaround.
6. **Privacy (DPDP Act 2023)**: consent capture, retention and purge policy, masked-by-default screens, and logging every "reveal identifier" action (prototype shows this).

---

## 6. UI review & prototype (`clientdesk_dashboard.html`)

v1.1 contains no UI code, so the prototype applies these visibility principles to the v1.2 data model:

* **Two bars per job**: blue *Collection* vs. traffic-light *Statutory readiness*. This is the core idea of the product, and the UI should show it on every row.
* **KPI cards you can click to filter**: Active, Overdue, Due ≤ 7 days, Waiting on client, Ready to submit.
* **Pipeline strip** with a count per workflow stage (click to filter).
* **Due-date status pill** (overdue / due today / days left) and a **"Next action"** column computed from the data ("Ask client to re-send 1 deficient doc", "Decide applicability of 1 conditional item").
* **Detail drawer**: workflow stepper, both gauges, a red **"N items blocking submission"** box listing the reasons, checklist grouped by category, requirement badges, status chips with icon + text (not colour alone).
* **"Copy client request"**: generates the pending-documents message (same logic as `pending_request_message()`), including correction notes for deficient items.
* **Submit button disabled** until readiness is 100%, with the reason shown (mirrors the DB gate).
* **PAN/GSTIN masked by default**; reveal is SENIOR-only and logged.
* Keyboard: `/` focuses search, Enter opens a row, Esc closes the drawer. Responsive below 1100 px.
