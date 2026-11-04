# Stage 2.2 FTA rule extractor - AI Studio test results (27 Oct 2026)

- Model: Gemini 3.8 Flash (gemini-3.8-flash), thinking Medium; temperature not exposed (default)
- Grounding, URL context, structured outputs: OFF
- Saved prompt: "AuditSmart 2.2 FTA rule extractor" https://aistudio.google.com/prompts/125KT7SxNKl3uV6yxAHNo3k2aAadi_Nrs (holds Test 2 chat)
- Stray auto-saved copy of Test 1 chat: https://aistudio.google.com/prompts/1ciOm0UyMI6HWB9YP6HMw-QsNxJqG7Sjc (can be deleted)
- Inputs: rule_test1_input.txt (FTA Decision 17 of 2026, official tax.gov.ae PDF), rule_test2_input.txt (FTA news 22 Oct 2026)

## Test 1 - FTA Decision No. 17 of 2026 (relevant)
```json
{
  "summary": "Updates input VAT recovery rules and legal references for employee expenses pursuant to FTA Decision No. 17 of 2026, setting conditions for recovery including maximum temporary accommodation duration, policy documentation, and restriction on cash-in-lieu options.",
  "changes": [
    {"rule_key": "input_vat.employee_expense.new_employee_accommodation_max_days", "current_value": null, "proposed_value": 30, "effective_date": "2026-10-01", "citation": "FTA Decision No. 17 of 2026, Article 2(4)(a)", "confidence": "high"},
    {"rule_key": "input_vat.employee_expense.contract_or_policy_required", "current_value": null, "proposed_value": true, "effective_date": "2026-10-01", "citation": "FTA Decision No. 17 of 2026, Article 1", "confidence": "high"},
    {"rule_key": "input_vat.employee_expense.cash_alternative_prohibits_recovery", "current_value": null, "proposed_value": true, "effective_date": "2026-10-01", "citation": "FTA Decision No. 17 of 2026, Article 2, Clauses 1(c), 2(d), and 3(a)", "confidence": "high"},
    {"rule_key": "legal_ref.input_vat.employee_expenses", "current_value": null, "proposed_value": "FTA Decision No. 17 of 2026", "effective_date": "2026-10-01", "citation": "FTA Decision No. 17 of 2026, Article 3", "confidence": "high"}
  ]
}
```

## Test 2 - unrelated FTA news item
```json
{"summary": "No relevant change", "changes": []}
```

## Review against Workbook checklist
- Schema valid, only allowed rule-key families: PASS (both)
- Every change cites decision + article/clause: PASS; citations checked against source text and correct (30 days = Art 2(4)(a); cash-in-lieu = Art 2 cl. 1(c), 2(d), 3(a); effective date = Art 3)
- Effective date taken from text (1 Oct 2026), not guessed: PASS
- Nothing invented: PASS
- Unrelated page returns "No relevant change" with empty list: PASS
- Coverage gap: the six recoverable cases (transport, food in remote areas, operational accommodation, new-employee accommodation, phones/data, parking) are not each captured as a rule; only 4 cross-cutting rules proposed. Cash-in-lieu citation also omits case 1's "financial compensation" wording consistency - fine. Consider adding to the prompt: "propose one change per case/condition set".
