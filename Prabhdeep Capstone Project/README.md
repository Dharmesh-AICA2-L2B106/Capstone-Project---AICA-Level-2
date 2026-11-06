# Analytical review for Audit by Prabhdeep

**Fictional—For Demonstration Only.** This tool highlights movements for auditor follow-up. It does not give an audit opinion and does not reach conclusions about fraud or misstatement. AI commentary is labelled **Draft—Subject to Auditor Review**.

## Files

| File | Purpose |
|---|---|
| `analytical_review_app.py` | PyQt6 desktop app. **Run this file.** |
| `audit_engine.py` | Validation, calculations, findings and the optional AI integration (standard library only). Keep it in the same folder. |
| `sample_data/` | The fictional CSV exports: Trial_Balance, Monthly_Sales, Budget and Thresholds. |
| `sample_data/error_examples/` | Broken files that show the validation checks failing. |
| `analytical_review.html` | Self-contained browser version with no installation step. |
| `review_workspace.json` | Created on first run. Findings, notes, status and threshold overrides. |

## Setup (Python 3.10 or later)

1. Open `analytical_review_app.py` in **IDLE** and press **F5**.
2. On the first run the app checks for its packages and installs any that are missing, using the same Python interpreter. **First-time installation needs an internet connection** and can take a few minutes. Progress messages appear in the IDLE shell.
3. If installation fails (no internet, proxy or permissions), run this one command in a terminal, then start the app again:

```
python -m pip install PyQt6 matplotlib anthropic
```

`anthropic` is only needed for AI drafts. If it is missing, the app still works and only the AI button is unavailable.

## Using the app

1. **Data & Validation:** click **Load sample data**, or use Browse for each CSV, then **Run validation & analysis**. The app runs 31 checks:
   - missing columns
   - blank or non-numeric amounts
   - negative amounts
   - duplicate rows
   - categories
   - whether each trial balance balances
   - 12 months per year
   - credit sales not exceeding sales
   - monthly sales reconciled to TB revenue
   - budget accounts against the TB

   If any check fails, findings are not updated and AI drafts are disabled.
2. **Thresholds:** values are read from `Thresholds.csv`. You can change the comparison or the value, then click **Apply**. **Reset** returns to the CSV values.
3. **Analytics:** ratio cards and a ratio table, annual variances, actual vs budget with favourable/adverse direction, and the monthly sales chart. Flagged rows are highlighted.
4. **Preliminary → Substantive/Interim → Final:** for each finding, record the management response, evidence reference, reviewer notes and status. All of this is saved to `review_workspace.json`.
   - **Final** shows every unresolved finding from all three stages.
   - **Carry forward unresolved** moves them into Final formally and records the move in each finding's history.
5. **Export findings CSV:** writes the full register, including the labels, AI drafts and history.

## Calculation basis

These follow the workbook's Data_Dictionary.

- **Signs:** assets and expenses are Debit − Credit. Liabilities, equity and revenue are Credit − Debit. Budgets are in reporting sign.
- **Gross profit margin** = (Revenue − Cost of sales) / Revenue.
- **Current ratio** = Current assets / Current liabilities.
- **Receivable days** = closing account 1100 / annual Credit_Sales × 365. Receivables include 5% VAT and credit sales exclude it. The workbook basis is kept as disclosed, and it is the same in both years.
- **Missing values and zero denominators** show as `n/a - missing data` or `n/a - zero denominator`. They never cause a crash or a misleading zero.

## Sample data results

| Measure | FY2024 | FY2025 |
|---|---|---|
| Gross profit margin | 20.0% | 22.0% |
| Current ratio | 2.05 | 2.25 |
| Receivable days | 61.1 | 80.3 |

All 31 checks pass. Four flags are raised:

| Rule | What is flagged |
|---|---|
| R01 | September sales up 66.7% on September 2024 |
| R02 | Receivable days up 19.2 |
| R03 | Repairs and maintenance (6450) up 222.2% on FY2024 |
| R04 | Repairs and maintenance (6450) 190.0% over budget |

## Optional AI drafts

- In the app, open **AI settings** and paste an Anthropic API key, or set the `ANTHROPIC_API_KEY` environment variable instead.
- The key is stored in `%USERPROFILE%\.analytical_review_prabhdeep\`, outside the source code and the project folder.
- Only the selected finding's verified figures are sent. Each draft is labelled *Draft—Subject to Auditor Review* and *UNVERIFIED*, and it must be ticked as reviewed by the auditor.
- If the AI is unavailable (no key, no internet, or an error), the app keeps working and offers standard inquiry prompts that are not AI-generated.

## HTML version: assessment

Feasible, and provided as `analytical_review.html`. Open it by double-clicking. It works offline and uses no external libraries. It includes CSV upload, the same checks and calculations, editable thresholds, a canvas chart, the three review stages, carry-forward and CSV export.

**Limitations**

- **Storage:**
  - Work is saved in the browser's localStorage, so it is lost if browser data is cleared.
  - It is not shared across browsers or people.
  - Private windows may not keep it.
  - Use **Export workspace** and **Import workspace** for backups.
- **No direct AI calls:** a web page cannot keep an API key secret, so no key is embedded or requested. **Copy AI prompt** copies the verified figures for pasting into an approved assistant. Paste the reply back into the labelled draft box.
- **Single user:** there is no user log-in or reviewer sign-off identity.
