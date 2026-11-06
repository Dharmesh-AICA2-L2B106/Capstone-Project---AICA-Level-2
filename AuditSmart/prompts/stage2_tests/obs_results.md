# Stage 2.1 Observation writer - AI Studio test results (27 Oct 2026)

- Model: Gemini 3.8 Flash (gemini-3.8-flash), thinking level Medium
- Temperature: not exposed for this model in AI Studio (default used); Build Guide asks for 0.2
- Grounding with Google Search: OFF; structured outputs OFF
- Saved prompt: "AuditSmart 2.1 Observation writer" https://aistudio.google.com/prompts/1W-iZom5uByZrx4-rVVX3i6yDccL1XJcq
- Each test in a fresh chat; responses read from the page (verbatim)

## Test 1 - VAT recomputation (full input)
```json
{
  "condition": "During VAT recomputation testing within Purchases for item ref S-014 (book amount AED 10,500.00), VAT recorded was AED 600.00 against expected VAT of AED 500.00, resulting in a difference of AED 100.00. The supplier invoice reflects VAT of AED 500.00.",
  "criteria": "UAE VAT law - tax invoice requirements.",
  "cause": "Cause: To be confirmed with management.",
  "effect": "Overstatement of recorded VAT by AED 100.00 in respect of item ref S-014.",
  "recommendation": "Management should review the posting for item ref S-014, adjust the AED 100.00 discrepancy, and ensure recorded VAT agrees with supplier tax invoices in accordance with UAE VAT law - tax invoice requirements.",
  "ml_point": "Purchase item ref S-014 had recorded VAT of AED 600.00, exceeding the supplier invoice VAT amount of AED 500.00 by AED 100.00. Controls should ensure VAT entries match supplier tax invoices.",
  "wp_conclusion": "An exception of AED 100.00 was identified for item ref S-014 where recorded VAT exceeded the supplier invoice amount. Cause to be confirmed with management. Draft - generated with AI, subject to auditor review."
}
```

## Test 2 - auditor_remark removed
```json
{
  "condition": "During VAT recomputation testing for Purchases on item ref S-014 (book amount AED 10,500.00), VAT recorded was AED 600.00 against expected VAT of AED 500.00, resulting in an unreconciled difference of AED 100.00.",
  "criteria": "UAE VAT law - tax invoice requirements.",
  "cause": "Cause: To be confirmed with management.",
  "effect": "Input VAT is overstated by AED 100.00 in the accounting records for the tested transaction.",
  "recommendation": "Management should investigate the AED 100.00 variance for item ref S-014, process the necessary adjustment, and ensure input tax amounts match UAE VAT law - tax invoice requirements.",
  "ml_point": "During testing of Purchases, VAT recorded for item ref S-014 was AED 600.00 compared to the expected amount of AED 500.00 on a book amount of AED 10,500.00, creating an overstatement of AED 100.00. We recommend management review and adjust this item in accordance with UAE VAT law - tax invoice requirements.",
  "wp_conclusion": "A variance of AED 100.00 was noted for item ref S-014 under Purchases. Management confirmation is pending. Draft - generated with AI, subject to auditor review."
}
```

## Test 3 - weekend journal entry
```json
{
  "condition": "Journal entry JV-2025-00412 amounting to AED 45,000.00 to account 6100 Marketing expense was posted on a Saturday (2025-03-15) by user FINMGR.",
  "criteria": "In accordance with ISA 240 - journal entry testing, journal entries possessing non-standard characteristics, such as being posted outside regular business hours or during weekends, require specific consideration and testing.",
  "cause": "Cause: To be confirmed with management.",
  "effect": "Posting transactions outside normal business hours elevates the risk of unauthorised or inappropriate journal entries bypassing standard oversight and control procedures.",
  "recommendation": "Management should review JV-2025-00412 to substantiate the business rationale, verify supporting documentation, and enforce controls regarding journal entry postings made outside regular hours.",
  "ml_point": "During testing of journal entries, JV-2025-00412 for AED 45,000.00 (account 6100 Marketing expense) was identified as posted on a Saturday (2025-03-15) by FINMGR. Management should ensure out-of-hours postings are formally justified and approved.",
  "wp_conclusion": "Further audit enquiry and inspection of supporting documentation are required to ascertain the validity and business purpose of JV-2025-00412 pursuant to ISA 240 - journal entry testing. Draft - generated with AI, subject to auditor review."
}
```

## Review against Workbook checklist
- JSON with all 7 keys: PASS (3/3)
- Amounts exactly as given, no new figures: PASS (3/3)
- Cause "To be confirmed with management" when not given: PASS (3/3)
- Only supplied reference cited: PASS (3/3)
- Draft label: PARTIAL - present inside wp_conclusion, not as a separate closing line (JSON output leaves nowhere else for it)
- No invented facts: Tests 1-2 PASS. Test 3 adds general ISA 240-style wording in criteria/effect ("weekends require specific consideration") not in the JSON - borderline; and Test 2 says "unreconciled"/"Input VAT" which is interpretation.
- Under 220 words: PASS (approx.)
