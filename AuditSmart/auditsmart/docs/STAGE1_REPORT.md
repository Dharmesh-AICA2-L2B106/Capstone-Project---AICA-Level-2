# AuditSmart – Stage 1 build report (27 Oct 2026)

**Status:** dummy data only. No client data was used. Nothing was pushed or emailed.

**Re-running the build:**
- Command: `python3 engine/generate_stage1.py`
- Requirements: Python 3, openpyxl and numpy; LibreOffice is needed for the recalculation step.
- Output is deterministic with seed 2025 (dummy_gl.csv md5 3037ba38…7842).

## Deliverables
| File | Rows (excluding header) | Purpose |
|---|---|---|
| data/dummy_gl.csv | 3,000 lines / 1,066 vouchers | FY2025 GL. Dr = Cr = 35,728,611.45 |
| data/edge_cases.csv | 60 | Import and validation failures |
| data/fy2021_2022.csv | 400 | Weekend change on 1 Jan 2022 |
| data/answer_key.csv | 236 | Every planted error: file, row, line_id, error_type, expected_severity |
| data/feature_key.csv | 115 | Planted non-errors: top stratum, credit notes, controls, parse-OK formats |
| data/supplier_register.csv | 58 | Supplier TRN, verified_on, bank_evidence_ref. Used for Input VAT. |
| data/uae_holidays_2025.csv | 12 | Verified list (docs/holiday_sources.md) |
| data/golden_results.xlsx | 8 sheets, 9,333 live formulas | Independent Excel golden results |
| data/make_gl.py, verify_stage1.py, build_golden_workbook.py, recalc_and_check.py | – | Generate, verify, build, then recalc and cross-check |
| engine/SPEC.md, engine/generate_stage1.py | – | Spec and pipeline wrapper |

## Planted errors (answer_key.csv)
| Error type | Count |
|---|---|
| weekend_posting | 25 |
| friday_after_cutoff | 10 |
| public_holiday_posting | 15 |
| round_sum | 20 (multiples of 10,000) |
| period_end_finmgr | 15 (29–31 Dec) |
| vague_narration | 10 |
| duplicate_invoice | 10 |
| output_vat_error | 12 |
| invalid_trn | 5 (dummy_gl) + 4 (edge cases) |
| input_vat_unverified_supplier | 15 |
| input_vat_spend_threshold | 3 |
| employee_expense | 20 |
| fy2021_2022 non_working_day | 60 |
| unbalanced_voucher | 2 |
| unreadable_date | 5 |
| blank_account | 3 |
| duplicate_line_id | 2 |

verify_stage1.py re-detects every category independently and requires an exact set match with the answer key. Result: ALL PASS.

## Golden workbook
- **Sheets:** README, Population, MUS_95, MUS_90, Projection, Calendar, VAT, Input_VAT. Yellow cells are inputs.
- **Recalculation:** done in LibreOffice headless with 0 errors. All values were cross-checked against Python Decimal.

| | 95% (CF 3.00, EF 1.6) | 90% (CF 2.31, EF 1.5) |
|---|---|---|
| Population (Expense debits) | 12,553,004.07 | 12,553,004.07 |
| n | 161 | 122 |
| J | 77,968.97 | 102,893.48 |
| Top-stratum items (≥ J) | 8 | 8 |
| Basic precision | 233,906.91 | 237,683.93 |
| Σ projected | 39,789.14 | 48,512.72 |
| Incremental allowance | 18,907.48 | 19,446.87 |
| UML vs TM 280,000 | 292,603.53 → Exceeds | 305,643.52 → Exceeds |

**Projection items:**
- L00159: top stratum, book 227,018.17, audited 214,518.17, actual misstatement 12,500.
- L00019: 28,613.37 at 10% tainting.
- L00081: 33,206.35 at 25% tainting.

The projected misstatement exceeds the 28,000 expected misstatement built into n, so "Exceeds – further work" is the correct golden outcome.

## Assumptions (docs silent)
1. **Test population:** Expense-account debit lines. Credit notes are excluded and listed separately.
2. **Dates and invoice fields:** entry_date = posting_date. Invoice, party, TRN and VAT fields sit on the primary voucher line only.
3. **VAT and TRN rules:**
   - VAT tolerance is 0.01 (placeholder).
   - TRN = 15 digits starting with "100" (placeholder pending Tax Partner sign-off).
   - A blank TRN is allowed only on ZR export and RC overseas lines.
4. **Spend threshold:** spend = gross invoice value, rolling 12 months, excluding credit notes. The 375,000 threshold is used with a TEST-ONLY effective date of 2025-10-01; the real date is 1 Oct 2026.
5. **Calendar profiles:**
   - P1 = 1 off-day (Sun)
   - P2 = Sat/Sun
   - P3 = Fri/Sat/Sun
   - P4 = Sat/Sun with no Friday half day
   - The half-day cut-off is 12:00. Planted Friday postings are ≥ 15:00, so they fail under both readings.
6. **Amount parsing:**
   - '1,234.50', '(500.00)' and '750.00-' parse.
   - 'AED 500' parses with a warning.
   - Excel serial dates and dd/mm/yyyy parse.
7. **Users and flags:** no senior-management/IT user and no manual/system flag column, because prompt 1.1 does not list them.
8. **Employee expense:** 5 categories planted, per prompt 1.1. Decision 17's sixth category is not planted.
9. **Workbook layout:** sheet names are MUS_95 and MUS_90, and the random start is left blank (yellow) for the engine's seeded start. A test with starts 12,345.67 and 50,000.50 returned selections identical to Python (161 and 122 lines).
10. **File locations:**
    - The generator is data/make_gl.py, the name used in the Workbook.
    - engine/generate_stage1.py only runs the pipeline.
    - supplier_register.csv was added because input-VAT tests need verification dates.

## Contradictions for Savio
- **Tolerable misstatement:** TM is 450k in the prompt 3.3 example but 280k in the firm methodology (280k used). The sample-size formula also differs: the Guide uses Pop×CF/TM, the firm uses the expected-misstatement form (firm used).
- **Effective dates:** the Decisions take effect 1 Oct 2026, while the test data uses 2025. A test-only date is used.
- **Firm methodology status:** firm_methodology v0.2 is a DRAFT and is not yet approved by the Assurance Partner.
- **Friday cut-off:** the half day ends at 12:00, but prompt 1.1 plants Friday postings "after 15:00".
- **Window definitions:** the round-sum and period-end windows differ between the prompt (10,000 / 3 days) and the methodology (1,000 / ±5 days).
- **Spend threshold:** the 375k figure and the TRN pattern are not in the docs as confirmed rules.
- **SPEC.md scope:** the Workbook asks for SPEC.md to be a verbatim copy. It is verbatim in Part 3, with firm overrides and the implemented rules added on top.
- **Step 1.6 (GitHub push):** not done. It needs Savio's repository and his own sign-in.
