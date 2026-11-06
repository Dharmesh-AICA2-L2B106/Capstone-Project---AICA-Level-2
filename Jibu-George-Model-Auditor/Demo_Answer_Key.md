# Demo Answer Key — DemoCo_DCF_Model_SYNTHETIC.xlsx

All data is synthetic. Keep this file away from the AI step: it is for scoring Model Auditor, not for pasting into Claude.

Columns C = FY2024A, D–H = FY2025E–FY2029E, I = Terminal (DCF only).

## Planted errors (14)

| ID | Sheet | Cell | What is wrong | Correct version | Check that should catch it | Severity |
|----|-------|------|---------------|-----------------|---------------------------|----------|
| E1 | IS | F5 | Wrong year: FY2027 revenue uses the FY2026 growth rate | `=E5*(1+Inputs!F5)` | 1 Inconsistent formula | High |
| E2 | IS | G8 | Constant 1.18 buried in one year's formula | `=-G5*Inputs!G7` | 1 Inconsistent formula and 2 Hardcoded constant | High / Medium |
| E3 | BS | D13:H13 | 5% hardcoded across the whole row; belongs on Inputs | `=IS!D5*Inputs!<new cell>` | 2 Hardcoded constant | Medium |
| E4 | BS | F7 | Typed plug (110) in a formula row | `=-IS!F6*Inputs!F11/365` | 3 Plug | Medium |
| E5 | BS | G10 | Wrong row in a total: adds Inventory (row 7), not Total current assets (row 8) | `=G8+G9` | 1 Inconsistent formula | High |
| E6 | CF | G24 | `#REF!` inside the formula | `=G11/IS!G9` | 4 Error value | High |
| E7 | DCF | C16 | OFFSET where a plain SUM would do; hides the dependency | `=SUM(D13:H13)` | 6 Risky function | Medium |
| E8 | DCF | C24 | External link to Peer_Comps_2024.xlsx | Paste the value onto Inputs with a source note | 5 External link | Medium |
| E9 | DCF | C26 | Volatile TODAY() as the valuation date | Typed date on Inputs | 6 Risky function | Low |
| E10 | DCF | C27 | `#DIV/0!`: divides by Inputs!C33 (headcount), which is zero | Populate the headcount | 4 Error value | High |
| E11 | DCF | C28 | Overly long, 7-level nested IF | Lookup table | 7 Long or nested formula | Low |
| E12 | Old_Calcs | (sheet) | Hidden sheet left over from an earlier version | Delete it | 8 Hidden items | Low |
| E13 | Workbook | Name `Old_Tax_Rate` | Named range points to `#REF!` | Delete the name | 9 Broken named range | Medium |
| E14 | Inputs | C32 | Unused input: legacy USD/AED rate, nothing refers to it | Delete it | 10 Unused input | Low |

Also planted, as a test of check 8 and scored as a bonus: **IS row 20** is a hidden row containing formulas.

## Legitimate exceptions (5): should be dismissed as likely_intentional

| ID | Sheet | Cell | Why it looks wrong | Why it is correct |
|----|-------|------|--------------------|-------------------|
| L1 | BS | D26 | Differs from E26:H26 | First forecast year opens from Inputs; later years roll from prior closing |
| L2 | BS | D32 | Differs from E32:H32 | Same, for the debt schedule |
| L3 | IS | D14 | Differs from E14:H14 | Only FY2025 uses the brought-forward tax losses (Inputs!C30); the row label says so |
| L4 | DCF | I11 | Differs from D11:H11 | Terminal column is the Gordon growth terminal value, not a yearly FCF |
| L5 | DCF | I12 | Differs from D12:H12 | Terminal value is discounted at the final year's factor |

## Expected noise (not scored)

- **IS!C5** and **BS column C** differ from the forecast columns because the base year links to Inputs. Treat these as legitimate if they are flagged.
- **Inputs!F5 and Inputs!F11** are flagged as unused inputs. These are knock-on effects, not separate errors: E1 stopped reading the FY2027 growth rate and the E4 plug stopped reading the FY2027 inventory days. They disappear when E1 and E4 are fixed.
- **DCF!C28** is also flagged as a hardcoded constant because of the thresholds typed inside the nested IF. This is true, and part of E11.
- **E4 does not trip the balance check:** BS!F7 is typed but the cash flow still reads it, so the balance sheet still balances in FY2027. Only the audit catches it, which is a good demo point.

## What the numbers should look like after an Excel save

Checked in Excel on 2 Nov 2026. These cells only have values after the file is opened and saved in Excel.

| Item | As delivered, with errors | With E1, E2, E4, E5, E6 fixed |
|------|---------------------------|-------------------------------|
| Balance check, FY2028 (BS!G22) | (734.0) | 0 |
| Enterprise value (DCF!C18) | 2,059.3 | 2,099.7 |
| Value per share (DCF!C21) | 19.79 | 20.20 |
| CF!G24 | #REF! | 73.5% |
| DCF!C27 | #DIV/0! | #DIV/0! until the headcount is filled in |

E5 is visible on the model's own balance check; the other planted errors are not, which is why cell-level auditing matters.
