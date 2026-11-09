# DRN FS Solution – demo walkthrough (fictitious data)

Company: **Sunrise Engineering Works Pvt Ltd** (made-up, a small fabrication unit). FY 2025-26 with comparative FY 2024-25.
File: `DRN Demo - Sunrise Engineering - Tally TB.xlsx` (same layout the Tally extractor produces, both years, PY opening balances included).

## Before recording
1. Start `Start DRN FS Solution.bat`. To keep your real clients out of the video, run a separate database:
   `set DRN_DB=C:\DRN Studio\DRN FS Solution\Demo\demo.db` then `set DRN_PORT=8790` then `python drn_studio.py`.
2. Open the DRN FS Solution page, create client **Sunrise Engineering Works Pvt Ltd**, framework = Company (Schedule III).

## Scenes (about 8 minutes)
1. **Import** – Trial balance step → *Import Tally TB* → pick the demo xlsx. Point out: 62 ledgers, one row per ledger, both years, "TB agrees" checks go green.
2. **Mapping** – every ledger is mapped automatically. Show the points that usually need a human:
   - *Interest on Income Tax Refund* → Other income
   - *Income Tax Paid* → Tax expense – current tax
   - all *Duties & Taxes* ledgers (CGST/SGST/TDS/PF) → Statutory dues payable
   - *Kiran Tools (MSME)* → MSME creditors
   - Disclosure column: tag *Director Loan – Rajesh Sharma* and *Director Remuneration* as Related party / KMP, *Audit Fees* as Auditor, *Share Capital* as Shareholder.
3. **Inventories** – enter closing stock: 31-Mar-26 Raw material 8,50,000 / Finished goods 14,00,000; 31-Mar-25 7,00,000 / 11,50,000. The check "opening stock agrees with previous-year closing stock" turns green.
4. **Fixed assets** – pick the Income-tax block per class (Plant & Machinery → P&M 15%, Computers → Computers 40%, Furniture, Car). Add:
   - Plant & Machinery ₹2,50,000 on 15-Jul-25
   - Computers & Laptops ₹1,40,000 on 10-Oct-25
   Show Companies Act schedule block-wise, IT block-wise depreciation, opening WDV edit, deferred tax.
5. **Financial statements** – Balance Sheet (₹95,65,200 both sides), P&L (PBT ₹16.67 lakh, PAT ₹12.62 lakh), Cash Flow (opening cash ₹11.10 lakh → closing ₹12.43 lakh, equals Balance Sheet). Click through note numbers.
6. **Disclosures** – *Fill disclosures from tagged ledgers*.
7. **Excel export** – open the workbook: unit dropdown (rupees / thousands / lakhs), face → Notes → TB trace with Ctrl+[ , Fixed Assets, Depreciation, Deferred Tax sheets.
8. **Roll forward** – Clients → roll forward to FY 2026-27 and show that comparatives and IT opening WDV are carried.

## Numbers to quote
| | FY 2025-26 | FY 2024-25 |
|---|---|---|
| Revenue | ₹1,84,00,000 | ₹1,53,00,000 |
| Profit before tax | ₹16,66,700 | ₹13,96,500 |
| Profit after tax | ₹12,61,700 | ₹10,71,500 |
| Balance Sheet total | ₹95,65,200 | ₹85,67,500 |

All figures verified: TB agrees for both years and for the start of the previous year, Balance Sheet tallies, cash flow reconciles to Balance Sheet cash.
`make_demo_data.py` regenerates the file (`python make_demo_data.py 2250000 out.xlsx`).
