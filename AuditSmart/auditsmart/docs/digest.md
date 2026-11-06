# AuditSmart – Source Document Digest
Prepared 27 Oct 2026 from Gmail thread 1a177a47b2b794a6 ("Audit Smart", 3 messages from Savio.Jose@claemirates.com, 26 Oct 2026).
A follow-up Gmail search found no other related mails or attachments.

## 1. Source files (/workspace/auditsmart/source/)
| File | What it is |
|---|---|
| AuditSmart_Build_Guide_v2.0_Firm_Production.docx | Master spec v2.0 (26 Oct 2026). Design, engine rules (S3), security (S4), validation (S5), stages and prompts (S6), plan, RACI and risks (S7), Appendices A–D |
| AuditSmart_Step_by_Step_Workbook.docx | Plain-language walkthrough v1.0 for Stages 0–10, with paste-in prompts, expected results and checklists |
| firm_methodology_v0.2.docx | **DRAFT** firm methodology (pending Assurance Partner approval): materiality, sampling, JE criteria, WP referencing, and S5 settings that differ from the Build Guide |
| AuditSmart_Lovable_Credit_Budget.xlsx | Lovable credit budget: Pro plan USD 25/month, 100 credits + 5/day (cap ~150), 15% reserve, subscribe 29 Oct 2026, submit 4 Nov 2026. Covers 4.1–5.2 for the capstone; 4.6 and 4.7 deferred |

## 2. Stages (one line each)
- **0 Governance & set-up**: partner/IT approval email (prompt 0.1); GitHub, Lovable, AI Studio and Antigravity accounts; Python 3.11; folders engine/data/docs/prompts.
- **1 Requirements & test data**: firm methodology; SPEC.md (Build Guide S3–5 + App. A–B); 2025 holidays CSV; synthetic GL + edge cases + FY21/22 file + answer key (prompt 1.1); golden_results.xlsx; first GitHub push.
- **2 AI prompts**: observation writer (2.1) and FTA rule extractor (2.2) in AI Studio; dev API key kept in a password manager only.
- **3 Python engine (Antigravity 3.1–3.12)**: scaffold/health, import & validation, sampling, JE + Benford, VAT + evaluation, 9-sheet WP, anonymiser/AI, Rules Library, FTA monitor, Working Calendar, jobs/large files, Input VAT (M15).
- **4 Front end (Lovable 4.1–4.7)**: master build, data model/RLS, UX pass, calendar screens, rules screens, jobs/dashboard, Input VAT tab.
- **5 Integration**: deploy the engine to Render (dev); Lovable engine-proxy; full run-through on the dummy files.
- **6 Testing & capstone**: TEST_REPORT.md, README, public synthetic repo, 6–8 min video, submission (queries to ai@icai.in).
- **7 Production**: Azure UAE North (or firm servers), Entra ID SSO + MFA, Key Vault, CI/CD, backups.
- **8 Validation & UAT**: Tax Partner signs App. D rules checklist; holidays/work weeks entered; parallel run; UAT; ISQM 1 validation file; QM approval.
- **9 Pilot**: 2–3 live engagements, issue log, go/no-go decision.
- **10 Go-live & sustain**: user guide, training, owners/alerts, annual review, roadmap.

## 3. Stage 1 – concrete deliverables, inputs and acceptance
| # | Deliverable | Inputs | Acceptance |
|---|---|---|---|
| 1.1 | docs/firm_methodology.docx plus a list of differences from defaults | firm manual (methodology v0.2 S5 already lists them) | saved; differences noted |
| 1.2 | engine/SPEC.md = Build Guide S3 → end of S5 + App. A + App. B | Build Guide | UTF-8 file |
| 1.3 | data/uae_holidays_2025.csv (`date,name`, one row per day, yyyy-mm-dd) | official UAE announcements | from official sources |
| 1.4 | data/make_gl.py (seed 2025), dummy_gl.csv (3,000 lines), edge_cases.csv (60), fy2021_2022.csv (400), answer_key.csv | prompt 1.1, holiday CSV | Dr = Cr; counts match prompt 1.1; edge file fails validation as expected |
| 1.5 | data/golden_results.xlsx: Population, MUS 95%, MUS 90%, Projection, Calendar, VAT (App. B also lists Input VAT) | dummy_gl.csv | live formulas, yellow inputs |
| 1.6 | push to private GitHub | repo URL | folders visible (external step: needs Savio) |

**Prompt 1.1 column spec:** line_id, entry_date, posting_date, posting_time, voucher_no, account_code, account_name, account_type, debit, credit, currency, narration, user_id, party_id, party_name, trn, invoice_no, net_amount, vat_amount, vat_code (SR/ZR/EX/RC), expense_category.

**Prompt 1.1 planted counts:**

| Planted item | Count |
|---|---|
| Sat/Sun postings | 25 |
| Friday postings after 15:00 (company half day ends 12:00) | 10 |
| Public-holiday postings | 15 |
| Round sums (multiples of 10,000) | 20 |
| Entries within 3 days of year-end by FINMGR | 15 |
| Vague/blank narrations | 10 |
| Duplicate invoices | 10 |
| Output-VAT errors | 12 |
| Invalid TRNs | 5 |
| Purchases after 1 Oct 2025 from unverified suppliers | 15 |
| Suppliers with rolling 12-month spend > AED 375,000 | 3 |
| Employee-expense lines (transport/food/accommodation/mobile/parking) | 20 |
| Top-stratum items (feature, not error) | 8 |
| Credit-note lines (feature, not error) | 40 |

**Edge-case file:** 2 unbalanced vouchers, 5 unreadable dates, amounts with commas/brackets, blank accounts, duplicate line_ids, 15- and 14-digit TRNs.

**FY2021/22 file:** 1 Dec 2021–31 Jan 2022, with Friday and Sunday postings around the Fri/Sat → Sat/Sun change on 1 Jan 2022.

## 4. Methodology parameters (firm_methodology v0.2 – DRAFT)

**Materiality**
- Benchmarks:

  | Benchmark | Range |
  |---|---|
  | PBT | 3–10% (default 5%; listed ≤ 5%) |
  | Revenue | 0.25–3% |
  | Gross profit | 0.25–4% |
  | Total assets | 0.25–2% |
  | Total expenditure | 0.25–3% |
  | Net assets | 0.5–3% |
  | EBITDA | 0.25–5% |

- Performance materiality (PM): 70% default (60% / 75%; 50% with partner approval).
- Clearly trivial: 5% of overall materiality (OM).
- TM = PM.
- Worked example: PBT 8m → OM 400,000 → PM 280,000 → trivial 20,000.

**MUS sampling**
- Confidence factors (CF): 80% 1.61, 90% 2.31, 95% 3.00 (default), 99% 4.61.
- Expected misstatement: 10% of TM. Refuse to sample if it exceeds 50% of TM.
- Expansion factors: 1.6 at 95%, 1.5 at 90%, 1.3 at 80%.
- n = ROUNDUP(Pop × CF ÷ (TM − Exp × EF), 0); J = Pop ÷ n.
- Selection: seeded random start in [0, J); select the first line whose cumulative value ≥ start + kJ.
- Items ≥ J are top stratum (tested 100%).
- Credit lines are excluded from a debit population and listed separately.
- No sampling if n < 5. Warn if the tested size differs from n by more than 10%.
- Unexamined items are treated as misstatements.
- Worked example: Pop 12.5m, TM 280k → n 160, J 78,125, BP 234,375.

**Evaluation**
- Items < J: tainting = misstatement ÷ book; projected = tainting × J.
- Top stratum: actual misstatement.
- BP = CF × J.
- Incremental allowance (IA) = Σ ranked projected (items < J) × (IF − 1).
- UML = BP + Σ projected + IA, compared with TM.
- Incremental factors: 95% 1.75 / 1.55 / 1.46 / 1.40 / 1.36; 90% 1.58 / 1.44 / 1.36 / 1.31 / 1.28.

**Non-statistical sampling (Table 2.7)**
- Minimums: <50 items: all or 15/10/5; 50–250: 40/25/15; >250: 60/40/25.
- Two strata split at the mean, 2/3 – 1/3 allocation; double the size if unstratified.
- Ratio projection.

**Tests of controls:** 25/10; 42 (1 deviation), 58 (2 deviations); 45 extended.

**JE criteria**
- Non-working day per the client calendar; after the half-day cut-off.
- Round sum: multiple of 1,000 and ≥ 10,000.
- Period-end: ±5 days.
- Users with < 1% of entries, plus a senior-management/IT user flag.
- Large amounts ≥ PM.
- Out of balance, gaps or duplicates.
- Vague narration: blank, adj, misc, correction, reversal, error, "as per MD".
- Manual entries to revenue or cash.
- Duplicates: same party + amount + date, or same invoice + party.
- Account pairs used < 3 times.
- Benford on amounts ≥ 10, MAD thresholds 0.006 / 0.012 / 0.015.
- Score = number of criteria met. Test all with score ≥ 3, score 2 by judgement (minimum 10). Never random.

**WP referencing and tickmarks**
- Sections A–Z (J purchases, L VAT/CT, N JE testing, Z-3 summary of misstatements); format J-S1, N-1.
- Tickmarks: ✓ A P V C X TB.

## 5. Prescribed tech stack
**Development**
- Lovable (React) front end with Supabase (dummy data only). All data and auth go through src/lib/data.ts, src/lib/auth.ts and src/lib/engine.ts.
- Python 3.11+ engine built in Google Antigravity:
  - FastAPI + Pydantic v2; Decimal money with ROUND_HALF_UP.
  - pandas/pyarrow, Parquet cache; numpy default_rng(seed); openpyxl; scipy.
  - SQLAlchemy 2 + Alembic on PostgreSQL; RQ/Celery + Redis.
  - pytest + hypothesis with ≥ 90% coverage; ruff, mypy strict; pre-commit; GitHub Actions; Docker.
  - Endpoints /v1/* including /v1/health.
- Gemini via Google AI Studio for prompts.
- GitHub private repo; Render for the dev engine.

**Production**
- Azure UAE North (Static Web Apps/App Service, Container Apps, PostgreSQL, Blob, Key Vault, Azure OpenAI) or firm servers.
- Entra ID SSO + MFA; Power Automate/Teams alerts.

**Capstone video:** Clipchamp.

## 6. Folder structure
`auditsmart/{engine, data, docs, docs/validation, prompts}` (Workbook uses C:\Projects\auditsmart).

## 7. Open questions, contradictions and blockers for Savio
1. **MUS formula and TM:** the Workbook (1.5) and Build Guide 3.2/3.3 use n = ceil(Pop × CF ÷ TM) with example TM 450,000. The firm methodology S5 adds expected misstatement (10% of TM) with expansion factors, and its worked example uses TM 280,000. Built per the methodology; confirm.
2. **Decision 13 effective date vs FY2025 data:** the Build Guide says Decisions 13 and 17 take effect **1 Oct 2026**, but prompt 1.1 plants "purchases after 1 Oct **2025**" in FY2025 data. A date-aware engine would not flag them under the real effective date. Needs a test-only rule version (effective 2025-10-01), or shifted test data.
3. **Spend threshold:** AED 375,000 appears only in prompt 1.1 (it equals the VAT mandatory registration threshold). The Build Guide says take it from the Rules Library. Tax Partner to verify against Decision 13.
4. **Methodology status:** firm_methodology v0.2 is a DRAFT pending Assurance Partner approval. It was benchmarked against the GT Audit Manual 2019, not the CLA Global methodology.
5. **Sheet names:** the Workbook uses "MUS 95%"/"MUS 90%"; the brief asked for MUS_95/MUS_90.
6. **Script name:** the Workbook says data/make_gl.py; the brief suggested engine/generate_stage1.py.
7. **SPEC.md:** the Workbook wants a full copy of Build Guide S3–5 + App. A–B, not a stub. The Build Guide's own Stage 1 text says "Copy Appendix A and Appendix B" and its S3 note says "Sections 3, 4 and Appendices A–B".
8. **VAT tolerance and TRN pattern:** "from Rules Library", value not given anywhere. The TRN rule of 15 digits starting 100 comes from the brief, not the docs.
9. **Half-day cut-off:** prompt 1.1 company half day is Friday to 12:00, but it plants "Friday postings after 15:00". Consistent but loose; postings between 12:00 and 15:00 are untested.
10. **Round sums:** prompt plants multiples of 10,000; the firm test is a multiple of 1,000 and ≥ 10,000 (superset). **Period-end:** plants within 3 days; the firm window is ±5 days (superset).
11. **Weekend change test calendar:** a working week for Dec 2021 is needed (Fri/Sat). No profile for it is defined in the docs.
12. **Blocked items:** GitHub push (1.6), approval email (0.1), and AI Studio key creation all need Savio. External actions were not performed.
13. **2025 National Day:** moved to **1–2 Dec** (MoHRE, 17 Nov 2025), not the 2–3 Dec in Cabinet Resolution 27/2024.
