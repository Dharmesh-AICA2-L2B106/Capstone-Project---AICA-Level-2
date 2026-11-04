# Workbook Steps 1.2–1.6 (verbatim extract, AuditSmart Step-by-Step Workbook)

## Step 1.2 – Create SPEC.md (the engine’s instruction book)
Open Build Guide v2.0 in Word.
Select from the heading 3. Python Engine Specifications to the end of Section 5. Copy (Ctrl+C).
Open Notepad and paste (Ctrl+V).
Go back to Word, copy Appendix A and Appendix B, paste them at the end in Notepad.
File → Save As → go to C:\Projects\auditsmart\engine → File name SPEC.md → Save as type All files → Encoding UTF-8 → Save.
## Step 1.3 – Enter the UAE public holiday list
Open Excel. In row 1 type the headings date and name.
Enter the 2025 UAE public holidays from the official UAE government announcements (one row per day; e.g. 2025-03-30 | Eid Al Fitr). Format the date column as yyyy-mm-dd.
Save as CSV UTF-8 into the data folder as uae_holidays_2025.csv.
## Step 1.4 – Generate the dummy ledgers
Easiest way: let Antigravity write and run the script for you.
Open Antigravity → Open Folder → C:\Projects\auditsmart.
Paste the prompt below, then paste prompt 1.1 from the Build Guide underneath it.
Approve the plan. It may ask to install pandas and numpy – click Accept.
When finished, open the data folder and check the five files are there.
[TABLE]
PASTE INTO ANTIGRAVITY / Save the script described below as data/make_gl.py, read the holiday list from / data/uae_holidays_2025.csv, run the script, and put all output files in the data / folder. Then show me: number of lines in each file, total debits and credits of / dummy_gl.csv, and a count of planted errors by type from answer_key.csv. / {paste prompt 1.1 here}
[/TABLE]
[TABLE]
WHAT YOU SHOULD SEE / dummy_gl.csv – 3,000 lines – total Dr = total Cr / edge_cases.csv – 60 lines / fy2021_2022.csv – 400 lines / answer_key.csv – one row per planted error, counts match prompt 1.1
[/TABLE]
## Step 1.5 – Build the golden workbook (Excel)
Create data\golden_results.xlsx with the sheets below. Use formulas, not typed numbers, so it recalculates. Mark input cells in yellow.
## Sheet ‘Population’
Data → From Text/CSV → choose dummy_gl.csv → Load.
Below the table: Total debit =SUM(debit column); Total credit =SUM(credit column); Difference =ROUND(total debit − total credit,2) → must be 0.00; Line count =COUNTA(line_id column).
Decide one test population, e.g. Expense lines with a debit amount. Use a filter or SUMIFS to get its total value and count.
## Sheets ‘MUS 95%’ and ‘MUS 90%’
[TABLE]
Cell | Formula / value
Population value (yellow) | Link to the population total from the Population sheet
Tolerable misstatement (yellow) | Your performance materiality, e.g. 450,000
Confidence factor (yellow) | 3.00 for 95%; 2.31 for 90% (confirm with firm manual)
Sample size n | =ROUNDUP(Population × CF ÷ TM, 0)
Interval J | =Population ÷ n
Top-stratum items | =COUNTIF(amount column, ">=" & J)
Random start (yellow) | Leave blank now – in Stage 3 you type the start the engine reports
[/TABLE]
Selection check (after Stage 3): list the population lines in file order with a cumulative amount column. In a second table, for k = 0 to n−1 compute point = start + k × J, then row = XMATCH(point, cumulative column, 1) and line_id = INDEX(line_id column, row). These line_ids must equal the engine’s sample.
## Sheet ‘Projection’ (worked MUS evaluation)
Pick three sample items and invent audited values (one should be a top-stratum item).
[TABLE]
Column | Formula
Book value / Audited value | Inputs
Misstatement | =Book − Audited
Tainting | =Misstatement ÷ Book (only for items smaller than J)
Projected misstatement | Items < J: =Tainting × J. Top stratum: =actual misstatement
Basic precision | =CF × J
Incremental allowance | Rank projected misstatements (items < J) largest first; multiply each by (incremental factor − 1) from the firm table (typical 95% values: 1.75, 1.55, 1.46 for the 1st, 2nd, 3rd error) and add
Upper misstatement limit | =Basic precision + Σ projected + incremental allowance
Conclusion | =IF(UML ≤ TM, "Acceptable", "Exceeds – further work")
[/TABLE]
## Sheets ‘Calendar’ and ‘VAT’
Calendar: list 12 dates (include a Friday afternoon, a Saturday, a Sunday, a public holiday and dates either side of 1 Jan 2022). For three profiles (1 day off – Friday; 2 days – Sat/Sun; 3 days – Fri–Sun) write Working / Non-working by hand.
VAT: copy the 12 planted VAT-error lines from answer_key. Expected VAT =ROUND(net × 5%, 2); Difference =recorded − expected.
## Step 1.6 – Save to GitHub for the first time
[TABLE]
PASTE INTO ANTIGRAVITY / This folder is my project C:\Projects\auditsmart. Connect it to my private GitHub / repository {paste your repository address}. Create a .gitignore that excludes .env / files, virtual environments and any file with "real" or "client" in its name. / Commit everything and push. Tell me when done.
[/TABLE]
A browser window may open asking you to sign in to GitHub and Authorize – do so.
[TABLE]
WHAT YOU SHOULD SEE / On github.com, your auditsmart repository now shows the folders data, docs, engine and prompts.
