import openpyxl, json, sys
from openpyxl.styles import Font, PatternFill
L = 100000.0
# (name, parent, primary group, Mar-24, Mar-25, Mar-26); Cr = +, Dr = -  (Tally ledger-export sign); rupees
BS = [
 ("Share Capital","Capital Account","Capital Account",10*L,10*L,10*L),
 ("Director Loan - Rajesh Sharma","Unsecured Loans","Loans (Liability)",5*L,4*L,3*L),
 ("Term Loan - HDFC Bank","Secured Loans","Loans (Liability)",20*L,16*L,12*L),
 ("Cash Credit - SBI","Bank OD A/c","Loans (Liability)",4*L,3.5*L,2*L),
 ("Apex Steel Traders","Sundry Creditors","Current Liabilities",6.2*L,7.8*L,9.4*L),
 ("Bharat Components","Sundry Creditors","Current Liabilities",3.1*L,3.9*L,4.6*L),
 ("Shree Logistics","Sundry Creditors","Current Liabilities",.9*L,1.2*L,1.4*L),
 ("Kiran Tools (MSME)","Sundry Creditors","Current Liabilities",1.1*L,1.4*L,1.8*L),
 ("Advance from Customers","Current Liabilities","Current Liabilities",.8*L,1.1*L,1.5*L),
 ("Salary Payable","Current Liabilities","Current Liabilities",.7*L,.8*L,.9*L),
 ("Audit Fee Payable","Current Liabilities","Current Liabilities",.5*L,.5*L,.5*L),
 ("Provision for Gratuity","Provisions","Current Liabilities",1.2*L,1.5*L,1.9*L),
 ("CGST Output","Duties & Taxes","Current Liabilities",.6*L,.8*L,.9*L),
 ("SGST Output","Duties & Taxes","Current Liabilities",.6*L,.8*L,.9*L),
 ("CGST Input","Duties & Taxes","Current Liabilities",-.5*L,-.6*L,-.7*L),
 ("SGST Input","Duties & Taxes","Current Liabilities",-.5*L,-.6*L,-.7*L),
 ("TDS Payable","Duties & Taxes","Current Liabilities",.18*L,.22*L,.26*L),
 ("PF Payable","Duties & Taxes","Current Liabilities",.12*L,.14*L,.16*L),
 ("Plant & Machinery","Fixed Assets","Fixed Assets",-18*L,-19.2*L,-19.1*L),
 ("Computers & Laptops","Fixed Assets","Fixed Assets",-1.2*L,-1.35*L,-1.6*L),
 ("Furniture & Fixtures","Fixed Assets","Fixed Assets",-2.5*L,-2.25*L,-2.02*L),
 ("Motor Vehicle - Car","Fixed Assets","Fixed Assets",-9*L,-7.65*L,-6.5*L),
 ("Fixed Deposit - HDFC Bank","Deposits (Asset)","Current Assets",-5*L,-5.5*L,-6*L),
 ("Security Deposit - Electricity","Deposits (Asset)","Current Assets",-.5*L,-.5*L,-.5*L),
 ("Metro Fabricators Ltd","Sundry Debtors","Current Assets",-9*L,-11.5*L,-14.2*L),
 ("Zenith Industries","Sundry Debtors","Current Assets",-4.2*L,-5*L,-6.1*L),
 ("Omkar Engineering","Sundry Debtors","Current Assets",-2.8*L,-3.6*L,-4.4*L),
 ("Neo Auto Components","Sundry Debtors","Current Assets",-1.9*L,-2.4*L,-2.9*L),
 ("Advance to Suppliers","Loans & Advances (Asset)","Current Assets",-.6*L,-.8*L,-1.1*L),
 ("Staff Advances","Loans & Advances (Asset)","Current Assets",-.2*L,-.25*L,-.3*L),
 ("Prepaid Insurance","Loans & Advances (Asset)","Current Assets",-.15*L,-.18*L,-.2*L),
 ("TDS Receivable","Loans & Advances (Asset)","Current Assets",-1.1*L,-1.4*L,-1.8*L),
 ("Cash in Hand","Cash-in-Hand","Current Assets",-.4*L,-.55*L,-.62*L),
]
# income / expense (name, parent, group, FY24-25, FY25-26)
NOM = [
 ("Sales - Fabrication","Sales Accounts","Sales Accounts",135*L,162*L),
 ("Sales - Job Work","Sales Accounts","Sales Accounts",18*L,22*L),
 ("Interest on Fixed Deposit","Indirect Incomes","Indirect Incomes",.38*L,.42*L),
 ("Interest on Income Tax Refund","Indirect Incomes","Indirect Incomes",.065*L,.092*L),
 ("Discount Received","Indirect Incomes","Indirect Incomes",.04*L,.055*L),
 ("Opening Stock - Raw Material","Direct Expenses","Direct Expenses",-6*L,-7*L),
 ("Opening Stock - Finished Goods","Direct Expenses","Direct Expenses",-9*L,-11.5*L),
 ("Purchases - Raw Material","Purchase Accounts","Purchase Accounts",-91*L,-113*L),
 ("Freight Inward","Direct Expenses","Direct Expenses",-2*L,-2.4*L),
 ("Wages - Direct","Direct Expenses","Direct Expenses",-12.4*L,-14.5*L),
 ("Power & Fuel","Direct Expenses","Direct Expenses",-5.3*L,-6.2*L),
 ("Job Work Charges","Direct Expenses","Direct Expenses",-4.2*L,-5.1*L),
 ("Salaries","Indirect Expenses","Indirect Expenses",-8.4*L,-9.6*L),
 ("Director Remuneration - Rajesh Sharma","Indirect Expenses","Indirect Expenses",-6*L,-6*L),
 ("Rent","Indirect Expenses","Indirect Expenses",-2.4*L,-2.4*L),
 ("Audit Fees","Indirect Expenses","Indirect Expenses",-.5*L,-.5*L),
 ("Professional Fees","Indirect Expenses","Indirect Expenses",-.7*L,-.85*L),
 ("Telephone & Internet","Indirect Expenses","Indirect Expenses",-.44*L,-.48*L),
 ("Travelling & Conveyance","Indirect Expenses","Indirect Expenses",-.92*L,-1.1*L),
 ("Insurance","Indirect Expenses","Indirect Expenses",-.55*L,-.62*L),
 ("Repairs & Maintenance","Indirect Expenses","Indirect Expenses",-1.1*L,-1.35*L),
 ("Office Expenses","Indirect Expenses","Indirect Expenses",-.64*L,-.7*L),
 ("Bank Charges","Indirect Expenses","Indirect Expenses",-.21*L,-.24*L),
 ("Interest on Term Loan","Indirect Expenses","Indirect Expenses",-1.75*L,-1.45*L),
 ("Interest on Cash Credit","Indirect Expenses","Indirect Expenses",-.36*L,-.28*L),
 ("Depreciation","Indirect Expenses","Indirect Expenses",-4.15*L,-5.13*L),
 ("Income Tax Paid","Indirect Expenses","Indirect Expenses",-3.25*L,-4.05*L),
]
STOCK = {1: (7*L, 11.5*L), 2: (8.5*L, 14*L)}      # closing stock Mar-25 / Mar-26 (RM, FG) - entered in the Inventories step
S0 = float(sys.argv[1]) if len(sys.argv) > 1 else 20*L      # surplus brought forward at 1 Apr 2024
profit = {y: sum(n[2+y] for n in NOM) + sum(STOCK[y]) for y in (1, 2)}
S1 = S0 + profit[1]
plac = {0: S0, 1: S0, 2: S1}                                # P&L A/c balance carried in the TB at each date
def tb_sum(i):
    return sum(b[3+i] for b in BS) + plac[i] + (sum(n[2+i] for n in NOM) if i > 0 else 0)
bank = [-tb_sum(i) for i in range(3)]                       # bank balance (Cr+/Dr-) that makes each TB agree
print("bank Dr:", [round(-b) for b in bank], "| profit FY24-25/FY25-26:", round(profit[1]), round(profit[2]), "| surplus Mar-24/25/26:", round(S0), round(S1), round(S1+profit[2]))
rows = []
def add(name, par, pg, p0, py, cy, nominal=False, gross=0):
    op = 0 if nominal else py
    mv = cy - op
    if nominal: nd, nc = (-cy, 0) if cy < 0 else (0, cy)
    else:
        nd, nc = (-mv, 0) if mv < 0 else (0, mv)
        nd += gross; nc += gross
    rows.append([name, par, pg, op, round(nd, 2), round(nc, 2), round(cy, 2), round(py, 2), 0 if nominal else round(p0, 2), ""])
GROSS = {"Apex Steel Traders": 2200000, "Bharat Components": 900000, "Director Loan - Rajesh Sharma": 60000, "Metro Fabricators Ltd": 9000000, "Cash in Hand": 1500000}
for b in BS: add(*b, gross=GROSS.get(b[0], 0))
add("HDFC Bank - Current A/c", "Bank Accounts", "Current Assets", bank[0], bank[1], bank[2], gross=22000000)
for n in NOM: add(n[0], n[1], n[2], 0, n[3], n[4], nominal=True)
# as in a Tally ledger export, the P&L A/c closing already includes the profit of the year (the studio removes it again on import)
nomCY = sum(n[4] for n in NOM); nomPY = sum(n[3] for n in NOM)
rows.append(["Profit & Loss A/c", "Primary", "", plac[2], 0, 0, round(plac[2] + nomCY, 2), round(plac[1] + nomPY, 2), plac[0], ""])
if len(sys.argv) > 2:
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "FY 2025-26"
    ws.append(["Name", "Parent", "PrimaryGroup", "OpeningBalance", "Net Debit", "Net Credit", "ClosingBalance", "PY ClosingBalance", "PY OpeningBalance", "Description", "FY 2025-26", "FY 2024-25"])
    for c in ws[1]: c.font = Font(bold=True); c.fill = PatternFill("solid", fgColor="E3EEEA")
    for r in rows: ws.append(r)
    for c, w in zip("ABCDEFGHIJKL", (42, 30, 26, 16, 16, 16, 16, 18, 18, 12, 10, 10)): ws.column_dimensions[c].width = w
    for c in "DEFGHI":
        for cell in ws[c][1:]: cell.number_format = "#,##0.00"
    ws.freeze_panes = "A2"
    rm = wb.create_sheet("Read me")
    for t in ["DEMO DATA - fictitious company 'Sunrise Engineering Works Pvt Ltd'. Not real.",
              "Same layout as the DRN Tally extractor output: one row per ledger, Cr positive / Dr negative.",
              "Closing stock is not in a Tally TB - enter it in the Inventories step:",
              "   31-Mar-26: Raw material 8,50,000 / Finished goods 14,00,000;   31-Mar-25: 7,00,000 / 11,50,000.",
              "Asset additions to type in the Fixed assets step (FY 2025-26): Plant & Machinery 2,50,000 (15-Jul-25); Computers & Laptops 1,40,000 (10-Oct-25)."]:
        rm.append([t])
    wb.save(sys.argv[2])
    json.dump([["Name", "Parent", "PrimaryGroup", "OpeningBalance", "Net Debit", "Net Credit", "ClosingBalance", "PY ClosingBalance", "PY OpeningBalance", "Description"]] + rows, open(sys.argv[2] + ".json", "w"))
