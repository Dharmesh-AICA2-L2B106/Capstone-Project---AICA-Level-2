# Model Auditor

An AI-assisted desktop tool that audits an Excel financial model without needing Excel.

**Python rules find the candidates, AI applies judgement, the human decides.**

Model Auditor opens an `.xlsx` model, checks every formula, flags modelling errors, helps Claude triage the flagged issues through manual copy and paste, and exports a colour-coded review copy, an issues register and a PDF report. The original file is only ever read and is never modified.

AICA Level 2 capstone project.

## How to run in IDLE

1. Install Python 3.9 or later from python.org.
2. Open `Model_Auditor.py` in IDLE and press **F5**.
3. Required libraries install themselves on the first run, which takes a minute or two.

If automatic installation fails, for example behind a corporate firewall, the app shows this command. Run it in Command Prompt, then start the app again:

```bash
pip install PyQt6 openpyxl pandas matplotlib reportlab
```

Excel, a database, OCR, API keys and paid services are not needed. The only internet use is the one-time pip install. Target: Windows, 8 GB RAM.

To rebuild the demo workbook, open `create_demo_model.py` in IDLE and press **F5**.

## Workflow

| Step | Screen | What happens |
|---|---|---|
| 1 | Load model | Choose an `.xlsx` file. Shows sheet, formula and input counts. |
| 2 | Scan | Runs the ten tests with a progress bar and checklist. |
| 3 | Dashboard | Health score, High / Medium / Low counts, issue charts, formula-map legend. |
| 4 | Issues register | Sort, filter and search every finding. Click a row for full detail. |
| 5 | AI review | Copy the prompt into Claude, paste the JSON reply back, and see each verified verdict. |
| 6 | Export | Create the three output files in the `Output` folder. |

## The ten audit tests

| No. | Test | Severity |
|---|---|---|
| 1 | Inconsistent formulas across a row, or down a column block | High |
| 2 | Hardcoded constants inside formulas (0, 1, 12, 100, 365, 1,000 and 1,000,000 are ignored) | Medium |
| 3 | Typed values (plugs) in a row of formulas | Medium |
| 4 | Error values, including `#REF!` in a formula and division by a zero or empty cell | High |
| 5 | External links to other workbooks | Medium |
| 6 | Risky functions: INDIRECT, OFFSET (Medium); TODAY, NOW, RAND, RANDBETWEEN (Low) | Medium / Low |
| 7 | Formulas over 250 characters or more than 5 levels deep (configurable at the top of the engine) | Low |
| 8 | Hidden sheets, and hidden rows or columns holding formulas | Low |
| 9 | Broken named ranges (`#REF!`, external, or a missing sheet) | Medium |
| 10 | Unused inputs that no formula reads | Low |

Formulas are converted to a relative (R1C1-style) pattern, so copied formulas look identical and a cell that breaks the pattern stands out. Adjacent cells with the same problem are grouped into one issue, such as `BS!D13:H13`.

Columns that differ by design are not flagged. If three or more rows on a sheet share the same formula in a column, such as a total column of `=SUM(E12:BL12)`, it counts as a summary column. A row that differs from the rest of that column, like a total that stops one month short, is still flagged. The same applies to a base-period column linking to another sheet.

## Model health score

```
Health score = 100 - (High x 4) - (Medium x 1.5) - (Low x 0.5), with a floor of 0
```

The score uses computed findings only, so it does not change when the AI dismisses an issue. In the PDF, 80 and above reads Good, 50 to 79 Needs attention, and below 50 High risk. The weights are in `HEALTH_DEDUCTIONS`.

## How the AI step works

- The prompt contains only flagged issues and tells Claude: use only the data provided, do not invent cells or numbers, and if unsure say needs_review.
- Claude replies as JSON with a verdict for each issue (likely_error, likely_intentional or needs_review), reasoning, a suggested fix, cited cells and a review memo.
- Model Auditor checks every issue id and cited cell against the scan. Verified findings get a tick. Anything else is marked **Unverified AI claim** in amber.
- Computed findings and AI commentary are kept apart on screen and in all outputs.
- No API is called. `obtain_ai_reply()` is the single function an Anthropic or Google Gemini call would replace.

**Confidentiality:** the prompt contains formulas and labels from flagged cells. Check your organisation's rules before pasting a real model into any AI tool.

## Outputs

Saved in the `Output` subfolder with a timestamp in each file name. The sample set in this folder comes from scanning the demo model and processing a real Claude reply in the AI review step, so it includes Claude's verdicts and review memo.

| File | Contents |
|---|---|
| `<ModelName>_REVIEWED_<time>.xlsx` | Copy of the model with a hatch over each formula's own colour (see below). Cell comments explain each issue. A "Model Auditor Summary" sheet sits at the front and Map_ sheets at the end. |
| `Issues_Register_<time>.xlsx` | All findings and AI verdicts with filters, plus an AI Commentary sheet. |
| `Model_Review_Report_<time>.pdf` | Title page, executive summary, health score, issue counts, charts, top 10 issues, AI triage, AI memo and disclaimer. |

### Audit marks on the reviewed copy

Models usually have their own colour coding, so Model Auditor does not replace it. Each hatch is laid over the cell's existing colour, which stays visible underneath. Inputs, labels, fonts, borders and number formats are left unchanged.

| Hatch | Meaning | Map_ symbol |
|---|---|---|
| Green vertical lines | A new formula starts here | `F` |
| Pale green diagonal | Copied formula with no break found | `<` same as left, `^` same as above |
| Red grid | Inconsistent formula | `X` |
| Purple trellis | Error | `E` |
| Orange horizontal lines | Hardcoded constant or typed plug | `H` |

New formula is not a problem flag: it shows where each calculation begins, adds no issues and does not affect the health score. The most serious mark wins on any cell, so a first cell with an error shows red, purple or orange.

Each `Map_` sheet uses the same cell addresses as its model sheet, so `Map_IS!F5` describes `IS!F5`. Typed inputs show as `N`. Click an `X`, `E` or `H` to jump to the cell. Set `ADD_FORMULA_MAPS = False` to leave these sheets out.

## Files in this folder

| File | Purpose |
|---|---|
| `Model_Auditor.py` | The app. This is the only file needed to run it. |
| `create_demo_model.py` | Builds the demo workbook. Not needed to run the app. |
| `DemoCo_DCF_Model_SYNTHETIC.xlsx` | Synthetic five-year DCF model with deliberate errors, for trying the app. |
| `Demo_Answer_Key.md` | The 14 planted errors and 5 legitimate exceptions in the demo model. Do not paste this into Claude. |
| `Output` | Sample outputs from scanning the demo model, including Claude's triage. |

All data in this folder is synthetic.

## Test results

On the demo model, all 14 planted errors were found, and all 5 legitimate exceptions were flagged for the AI to dismiss.

During development the app was also tested on five further synthetic models, which are not included here: a clean model, a flexible monthly Input / Calc / Output model, a 240-month project finance model, a 25-entity consolidation and a workbook with awkward real-world features. Every planted error the app is designed to detect was found. The three blind spots planted on purpose were missed, as expected; they are listed under Limitations. Results were the same whether or not the files had been saved in Excel.

## Capacity

Measured on a Windows PC with 7.8 GB of RAM using large synthetic test models (not included), running the audit engine and exports directly. Times vary with the PC and the model's structure.

| Formulas | Load | Audit | Reviewed copy | Issues register | Peak memory |
|---|---|---|---|---|---|
| 220,000 | 10 s | 13 s | 25 s | 8 s | 0.7 GB |
| 550,000 | 24 s | 35 s | 68 s | 30 s | 1.4 GB |
| 1.1 million | 54 s | 83 s | 3 min 15 s | 49 s | 2.4 GB |
| 2.2 million | 1 min 39 s | 2 min 53 s | 7 min 22 s | 2 min 45 s | 3.5 GB |

No test run failed, up to 2.2 million formulas. The window stayed responsive at 550,000 formulas, with its longest pause about 1 second. Excel took 39 seconds to open that reviewed copy. Above about 1 million formulas, close other programs first. Excel opening the reviewed copies of the 1 and 2 million models was not tested. If memory runs out, the app shows a message rather than crashing.

## Limitations

- **Cached values need an Excel save.** openpyxl does not calculate formulas, so a file generated by code has no stored results until it is opened and saved in Excel once. Formula checks work regardless, but only saved files show calculated errors directly; otherwise `#REF!` and division by zero are worked out from the formulas.
- **INDIRECT and OFFSET cannot be fully traced.** Cells they reach are not in the reference map, so the unused-inputs test can over-flag.
- **`.xlsb` and `.xls` are not supported.** Save as `.xlsx` first. Password-protected files must be unprotected first.
- **Mechanical errors only, not judgement errors.** The tool cannot tell whether an assumption is sensible or a method is right.
- **Flagged does not mean wrong.** Terminal-value columns and first-year openings are often flagged by design; this is what the AI triage is for.
- **Other references are not traced.** Charts, conditional formatting and data validation are not read, so an input used only by those can show as unused.
- **The reviewed copy may lose some objects.** Simple charts, tables, data validation, conditional formatting, merged cells and existing comments came through in testing, but openpyxl can drop images and shapes, and complex charts may lose formatting. The original keeps everything. The copy recalculates when opened; if Excel opens it in Protected View, click Enable Editing.
- **Errors consistent within a sheet are not seen.** If one entity's sheet uses the wrong input across a whole row, the row is internally consistent, so comparing sister sheets is a job for a human reviewer.
- **A whole column can be treated as a summary.** If three or more rows break in the same way in one column, that column counts as designed and is not flagged.
- **Conditional formatting wins.** Where a model's own conditional formatting sets a cell's fill, Excel shows that instead of the hatch. The Map_ sheets are unaffected.
- **Circular references and sign checks are not included.** They were optional and were left out to keep the build reliable.
- **Large models:** only the 150 most severe issues go into the AI prompt, and the screen says so.
- **AI output needs human review.** AI commentary is analytical support, not an audit opinion.
