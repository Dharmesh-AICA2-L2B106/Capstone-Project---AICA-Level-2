# UAE Corporate Tax Workpaper Assistant

AICA Level 2 Capstone Project

**Participant:** Rakesh Jaiswal

**Source code:** this repository

## Problem
UAE Corporate Tax (9% above AED 375,000) requires accounting profit to be adjusted for non-deductible and exempt items before tax is computed. Preparing this workpaper from a trial balance is repetitive and error-prone, especially for small practices handling many clients.

## Solution
A privacy-first HTML App (works offline, installable on phone or laptop) plus a Python command-line version. Upload a trial balance CSV and the tool:

1. Classifies every account into a tax category (keyword and account-code rules, fully editable by the user).
2. Computes accounting profit.
3. Applies adjustments: 50% client entertainment, fines and penalties, non-approved donations, personal expenses, private share of mixed-use costs, exempt dividends, and the interest limitation rule.
4. Applies tax losses (75% cap), the AED 375,000 zero band and 9% rate, and optional Small Business Relief.
5. Exports the workpaper to CSV or PDF and drafts an explanation note (template, or AI-generated if the user supplies a Gemini API key).

## AICA Level 2 modules used
| Module | How it is used |
|---|---|
| 1, 2 AI agents / ICAI AI Agent | Requirements, rules research and code generated with agent assistance |
| 4 Google AI / automation | Optional Gemini call for the explanation note |
| 6 Python fundamentals | `python/ct_workpaper.py` |
| 7 Full-stack | `app/` (offline, installable) |
| 5 Offline GPTs | Tool runs fully offline; core logic needs no AI |

## Folder structure
```
app/      index.html, core.js, sw.js, manifest.json, icon.svg   (PWA)
python/   ct_workpaper.py                                       (CLI)
data/     sample_trial_balance.csv
docs/     VIDEO_SCRIPT.md, TEST_CASES.md
```

## How to run
**Web app:** double-click `app/index.html` (works directly), or host the `app` folder on GitHub Pages / Netlify / any static host to enable install-as-app. Click **Load sample data**.

**Python:** `python python/ct_workpaper.py data/sample_trial_balance.csv --loss-bf 0 -o workpaper.csv`

**Desktop app (double-click):** double-click `Start CT Workpaper.bat` (or `python/ct_app.pyw`). A window opens: click *Load sample data* or open your own CSV, then *Calculate*. Needs Python installed. To make a standalone `CTWorkpaper.exe` that runs without Python, double-click `Build EXE (optional).bat` on Windows.

## Input format
`account_code, account_name, debit, credit, category (optional), business_use_pct (optional)`

Allowed categories: revenue, other_income, dividend_income, interest_income, cogs, opex, depreciation, interest_expense, entertainment_client, fines, donations, donations_approved, personal, mixed, bs.
If `category` is blank, accounts starting with 1, 2 or 3 are treated as balance sheet; others are matched by name keywords. Auto-classified rows are highlighted for review.

## Sample result
Accounting profit AED 1,044,000, net adjustments +AED 70,000, taxable income AED 1,114,000, corporate tax **AED 66,510**.

## Rules implemented (simplified)
- 0% up to AED 375,000, 9% above
- Client entertainment 50% deductible
- Fines, penalties, personal expenses and non-approved donations not deductible
- Dividend income treated as exempt (assumes participation exemption is met)
- Net interest limited to the greater of AED 12m and 30% of EBITDA
- Tax losses offset up to 75% of taxable income
- Small Business Relief when revenue is AED 3m or less (time-limited, confirm availability)

## Limitations
Not covered: Qualifying Free Zone Person income split, related-party and transfer pricing adjustments, group and unincorporated partnership rules, domestic minimum top-up tax, capital asset elections, foreign tax credit. Output is a draft for professional review, not tax advice.

## Data safety
No real client data was used. Sample data is fictional. The app processes files locally; only aggregated figures are sent to an AI service, and only if an API key is entered.

## Sources used for rules
UAE Federal Tax Authority guidance on Corporate Tax and public explainer articles (bcl.ae, avyanco.com), checked October 2026. Re-verify before real use.

