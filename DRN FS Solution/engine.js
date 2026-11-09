/* DRN FS Engine — Schedule III (Division I) financial statement engine.
   Pure functions, no DOM. Balances: Debit = +, Credit = − (Rupees).          */
(function (root) {
'use strict';

/* ---------- 1. Head master (presentation order = Schedule III Div I) ---------- */
const HEADS = [
  // id, name, statement, credit-nature?, caption group
  ['SC',   'Share capital', 'BS', true],
  ['RS',   'Reserves and surplus', 'BS', true],
  ['SW',   'Money received against share warrants', 'BS', true],
  ['SAM',  'Share application money pending allotment', 'BS', true],
  ['LTB',  'Long-term borrowings', 'BS', true],
  ['DTL',  'Deferred tax liabilities (Net)', 'BS', true],
  ['OLTL', 'Other long-term liabilities', 'BS', true],
  ['LTP',  'Long-term provisions', 'BS', true],
  ['STB',  'Short-term borrowings', 'BS', true],
  ['TP',   'Trade payables', 'BS', true],
  ['OCL',  'Other current liabilities', 'BS', true],
  ['SP',   'Short-term provisions', 'BS', true],
  ['PPE',  'Property, Plant and Equipment', 'BS', false],
  ['INTANG','Intangible assets', 'BS', false],
  ['CWIP', 'Capital work-in-progress', 'BS', false],
  ['IAUD', 'Intangible assets under development', 'BS', false],
  ['NCI',  'Non-current investments', 'BS', false],
  ['DTA',  'Deferred tax assets (Net)', 'BS', false],
  ['LTLA', 'Long-term loans and advances', 'BS', false],
  ['ONCA', 'Other non-current assets', 'BS', false],
  ['CINV', 'Current investments', 'BS', false],
  ['INV',  'Inventories', 'BS', false],
  ['TR',   'Trade receivables', 'BS', false],
  ['CCE',  'Cash and cash equivalents', 'BS', false],
  ['STLA', 'Short-term loans and advances', 'BS', false],
  ['OCA',  'Other current assets', 'BS', false],
  ['REV',  'Revenue from operations', 'PL', true],
  ['OI',   'Other income', 'PL', true],
  ['COMC', 'Cost of materials consumed', 'PL', false],
  ['PSIT', 'Purchases of stock-in-trade', 'PL', false],
  ['CHG',  'Changes in inventories of finished goods, work-in-progress and stock-in-trade', 'PL', false],
  ['EB',   'Employee benefits expense', 'PL', false],
  ['FC',   'Finance costs', 'PL', false],
  ['DEP',  'Depreciation and amortisation expense', 'PL', false],
  ['OE',   'Other expenses', 'PL', false],
  ['EXC',  'Exceptional items', 'PL', false],
  ['EXTRA','Extraordinary items', 'PL', false],
  ['TAX',  'Tax expense', 'PL', false],
].map(([id, name, stmt, credit]) => ({ id, name, stmt, credit }));
const HEAD = Object.fromEntries(HEADS.map(h => [h.id, h]));

/* Mappable line items (sub-heads). INV_* closing lines come from the Inventories step. */
const LINES = [
  ['SC_EQ','SC','Equity share capital'], ['SC_PREF','SC','Preference share capital'],
  ['RS_CAP','RS','Capital reserve'], ['RS_SEC','RS','Securities premium'], ['RS_GEN','RS','General reserve'],
  ['RS_OTH','RS','Other reserves'], ['RS_SURPLUS','RS','Surplus in Statement of Profit and Loss – opening balance'],
  ['SW','SW','Money received against share warrants'], ['SAM','SAM','Share application money pending allotment'],
  ['LTB_BANK','LTB','Term loans from banks (secured)'], ['LTB_OTHS','LTB','Term loans from others (secured)'],
  ['LTB_VEH','LTB','Vehicle loans (secured)'], ['LTB_DIR','LTB','Loans from directors (unsecured)'],
  ['LTB_REL','LTB','Loans from other related parties (unsecured)'], ['LTB_UNS','LTB','Other loans (unsecured)'],
  ['DTL','DTL','Deferred tax liabilities (Net)'],
  ['OLTL_DEP','OLTL','Trade / security deposits received'], ['OLTL_OTH','OLTL','Other long-term liabilities'],
  ['LTP_GRAT','LTP','Provision for gratuity'], ['LTP_LEAVE','LTP','Provision for leave encashment'], ['LTP_OTH','LTP','Other long-term provisions'],
  ['STB_CC','STB','Cash credit / overdraft from banks (secured)'], ['STB_CURMAT','STB','Current maturities of long-term borrowings'],
  ['STB_DEM','STB','Loans repayable on demand – others'], ['STB_REL','STB','Loans from related parties'],
  ['TP_MSME','TP','Total outstanding dues of micro enterprises and small enterprises'],
  ['TP_OTH','TP','Total outstanding dues of creditors other than micro enterprises and small enterprises'],
  ['OCL_STAT','OCL','Statutory dues payable'], ['OCL_ADV','OCL','Advances from customers'],
  ['OCL_EMP','OCL','Employee benefits payable'], ['OCL_CAP','OCL','Creditors for capital goods'],
  ['OCL_INT','OCL','Interest accrued'], ['OCL_EXP','OCL','Other payables'],
  ['SP_TAX','SP','Provision for income tax'], ['SP_EXP','SP','Provision for expenses'],
  ['SP_EMP','SP','Provision for employee benefits'], ['SP_OTH','SP','Other short-term provisions'],
  ['PPE_GROSS','PPE','Gross block'], ['PPE_ACCDEP','PPE','Less: Accumulated depreciation'],
  ['INTANG','INTANG','Intangible assets (net)'], ['CWIP','CWIP','Capital work-in-progress'],
  ['IAUD','IAUD','Intangible assets under development'],
  ['NCI','NCI','Non-current investments'], ['DTA','DTA','Deferred tax assets (Net)'],
  ['LTLA_CAP','LTLA','Capital advances'], ['LTLA_SD','LTLA','Security deposits'],
  ['LTLA_REL','LTLA','Loans and advances to related parties'], ['LTLA_OTH','LTLA','Other long-term loans and advances'],
  ['ONCA_FD','ONCA','Bank deposits with more than 12 months maturity'], ['ONCA_OTH','ONCA','Other non-current assets'],
  ['CINV','CINV','Current investments'],
  ['TR_SEC','TR','Secured, considered good'], ['TR_GOOD','TR','Unsecured, considered good'],
  ['TR_DOUBT','TR','Doubtful'], ['TR_PROV','TR','Less: Allowance for doubtful debts'],
  ['CCE_BANK','CCE','Balances with banks in current accounts'], ['CCE_CASH','CCE','Cash on hand'],
  ['CCE_FD3','CCE','Deposits with original maturity up to 3 months'], ['CCE_OBB','CCE','Other bank balances (deposits)'],
  ['STLA_SUPP','STLA','Advances to suppliers'], ['STLA_GOVT','STLA','Balances with government authorities'],
  ['STLA_PRE','STLA','Prepaid expenses'], ['STLA_EMP','STLA','Loans and advances to employees'],
  ['STLA_REL','STLA','Loans and advances to related parties'], ['STLA_OTH','STLA','Other short-term loans and advances'],
  ['OCA_INT','OCA','Interest accrued'], ['OCA_OTH','OCA','Other current assets'],
  ['REV_PROD','REV','Sale of products'], ['REV_SERV','REV','Sale of services'], ['REV_OOR','REV','Other operating revenues'],
  ['OI_INT','OI','Interest income'], ['OI_DIV','OI','Dividend income'],
  ['OI_GAIN','OI','Net gain on sale of investments / assets'], ['OI_MISC','OI','Other non-operating income'],
  ['INV_OP_RM','COMC','Opening stock of raw materials'], ['PUR_RM','COMC','Add: Purchases (incl. freight inward)'],
  ['PUR_SIT','PSIT','Purchases of stock-in-trade'],
  ['INV_OP_WIP','CHG','Opening stock – work-in-progress'], ['INV_OP_FG','CHG','Opening stock – finished goods'],
  ['INV_OP_SIT','CHG','Opening stock – stock-in-trade'],
  ['EB_SAL','EB','Salaries and wages'], ['EB_DIR','EB',"Directors' remuneration"],
  ['EB_PF','EB','Contribution to provident and other funds'], ['EB_GRAT','EB','Gratuity'], ['EB_WEL','EB','Staff welfare expenses'],
  ['FC_INT','FC','Interest expense'], ['FC_OTH','FC','Other borrowing costs'],
  ['DEP','DEP','Depreciation and amortisation'],
  ['INV_OP_STORES','OE','Opening stock – stores and spares'],
  ['OE_POWER','OE','Power and fuel'], ['OE_STORES','OE','Consumption of stores and spares'], ['OE_JOB','OE','Job work charges'],
  ['OE_RENT','OE','Rent'], ['OE_REP_BLD','OE','Repairs to buildings'], ['OE_REP_MAC','OE','Repairs to machinery'],
  ['OE_REP_OTH','OE','Repairs – others'], ['OE_INS','OE','Insurance'], ['OE_RATES','OE','Rates and taxes'],
  ['OE_AUD','OE','Payment to auditors'], ['OE_PROF','OE','Legal and professional fees'], ['OE_FRT','OE','Freight outward'],
  ['OE_TRAV','OE','Travelling and conveyance'], ['OE_COMM','OE','Communication expenses'], ['OE_PRINT','OE','Printing and stationery'],
  ['OE_ADV','OE','Advertisement and sales promotion'], ['OE_BANK','OE','Bank charges'],
  ['OE_CSR','OE','Corporate social responsibility expenditure'], ['OE_BADDEBT','OE','Bad debts written off'],
  ['OE_MISC','OE','Miscellaneous expenses'],
  ['EXC','EXC','Exceptional items'], ['EXTRA','EXTRA','Extraordinary items'],
  ['TAX_CUR','TAX','Current tax'], ['TAX_DEF','TAX','Deferred tax'], ['TAX_EARL','TAX','Tax of earlier years'],
].map(([code, head, label]) => ({ code, head, label }));
/* Non-Corporate Entity (ICAI NCE format) lines: partnership firms, LLPs, proprietorships, AOPs. */
[ ['OC_CAP','SC',"Partners' / proprietor's capital accounts"], ['OC_CUR','SC',"Partners' current accounts"], ['OC_DRAW','SC','Less: Drawings'],
  ['EB_PART','EB','Remuneration to partners / proprietor'], ['FC_PINT','FC',"Interest on partners' capital"],
].forEach(([code, head, label]) => LINES.push({ code, head, label }));
const LINE = Object.fromEntries(LINES.map(l => [l.code, l]));

/* Reporting framework: 'company' = Schedule III (Division I); 'nce' = ICAI format for Non-Corporate Entities. */
const NCE_ONLY = new Set(['OC_CAP','OC_CUR','OC_DRAW','EB_PART','FC_PINT']);
const NCE_OFF  = new Set(['SC_EQ','SC_PREF','RS_SEC','SW','SAM','EB_DIR','OE_CSR']);
const NCE_X = { SC_EQ:'OC_CAP', SC_PREF:'OC_CAP', SW:'OC_CAP', SAM:'OC_CAP', RS_SEC:'RS_OTH', EB_DIR:'EB_PART', OE_CSR:'OE_MISC' };
const CO_X  = { OC_CAP:'SC_EQ', OC_CUR:'RS_OTH', OC_DRAW:'RS_OTH', EB_PART:'EB_DIR', FC_PINT:'FC_INT' };
const isNCE = fw => fw === 'nce';
const linesFor = fw => LINES.filter(l => isNCE(fw) ? !NCE_OFF.has(l.code) : !NCE_ONLY.has(l.code));
const headsFor = fw => HEADS.filter(h => !(isNCE(fw) && (h.id === 'SW' || h.id === 'SAM')));
const xlate = (code, fw) => !code ? code : isNCE(fw) ? (NCE_X[code] || code) : (CO_X[code] || code);
const headName = (id, fw) => (isNCE(fw) && id === 'SC') ? "Owners' capital accounts" : HEAD[id].name;

/* Closing inventory categories (entered in the Inventories step) */
const INV_CATS = [
  { key: 'RM',     label: 'Raw materials',            openCode: 'INV_OP_RM',     target: 'COMC' },
  { key: 'WIP',    label: 'Work-in-progress',         openCode: 'INV_OP_WIP',    target: 'CHG' },
  { key: 'FG',     label: 'Finished goods',           openCode: 'INV_OP_FG',     target: 'CHG' },
  { key: 'SIT',    label: 'Stock-in-trade',           openCode: 'INV_OP_SIT',    target: 'CHG' },
  { key: 'STORES', label: 'Stores and spares',        openCode: 'INV_OP_STORES', target: 'OE'  },
];

/* Lines whose negative presentation is expected (contra lines) */
const CONTRA_OK = new Set(['PPE_ACCDEP', 'TR_PROV', 'RS_SURPLUS', 'OC_DRAW', 'OC_CUR', 'OCL_STAT']);   // statutory dues are shown net of input credits / advance taxes

/* ---------- 2. Tally group defaults (tier 3) ---------- */
const GROUPS = {
  'capital account': ['L', 'SC_EQ'], 'reserves & surplus': ['L', 'RS_OTH'], 'reserves and surplus': ['L', 'RS_OTH'],
  'loans (liability)': ['L', 'LTB_UNS'], 'secured loans': ['L', 'LTB_BANK'], 'unsecured loans': ['L', 'LTB_UNS'],
  'bank od a/c': ['L', 'STB_CC'], 'bank occ a/c': ['L', 'STB_CC'], 'bank od': ['L', 'STB_CC'],
  'current liabilities': ['L', 'OCL_EXP'], 'duties & taxes': ['L', 'OCL_STAT'], 'duties and taxes': ['L', 'OCL_STAT'],
  'provisions': ['L', 'SP_EXP'], 'sundry creditors': ['L', 'TP_OTH'],
  'fixed assets': ['A', 'PPE_GROSS'], 'investments': ['A', 'NCI'], 'current assets': ['A', 'OCA_OTH'],
  'deposits (asset)': ['A', 'LTLA_SD'], 'loans & advances (asset)': ['A', 'STLA_OTH'], 'loans and advances (asset)': ['A', 'STLA_OTH'],
  'sundry debtors': ['A', 'TR_GOOD'], 'cash-in-hand': ['A', 'CCE_CASH'], 'cash in hand': ['A', 'CCE_CASH'],
  'bank accounts': ['A', 'CCE_BANK'], 'misc. expenses (asset)': ['A', 'ONCA_OTH'], 'stock-in-hand': ['A', null],
  'sales accounts': ['I', 'REV_PROD'], 'direct incomes': ['I', 'REV_OOR'], 'indirect incomes': ['I', 'OI_MISC'],
  'income (direct)': ['I', 'REV_OOR'], 'income (indirect)': ['I', 'OI_MISC'],
  'purchase accounts': ['E', 'PUR_RM'], 'direct expenses': ['E', 'OE_MISC'], 'indirect expenses': ['E', 'OE_MISC'],
  'expenses (direct)': ['E', 'OE_MISC'], 'expenses (indirect)': ['E', 'OE_MISC'],
  'opening stock': ['E', null], 'suspense a/c': [null, null], 'branch / divisions': [null, null], 'primary': [null, null],
};
const normG = g => String(g || '').trim().toLowerCase().replace(/\s+/g, ' ');
function groupInfo(group) {
  const g = normG(group);
  if (GROUPS[g]) return { nature: GROUPS[g][0], code: GROUPS[g][1], known: true };
  // custom sub-group: infer nature from its words
  if (/creditor|payable/.test(g)) return { nature: 'L', code: 'TP_OTH', known: false };
  if (/debtor|receivable/.test(g)) return { nature: 'A', code: 'TR_GOOD', known: false };
  if (/expense|purchase/.test(g)) return { nature: 'E', code: /purchase/.test(g) ? 'PUR_RM' : 'OE_MISC', known: false };
  if (/income|sales|revenue/.test(g)) return { nature: 'I', code: /sales|revenue/.test(g) ? 'REV_PROD' : 'OI_MISC', known: false };
  if (/loan.*liab|borrow/.test(g)) return { nature: 'L', code: 'LTB_UNS', known: false };
  if (/asset|advance|deposit/.test(g)) return { nature: 'A', code: null, known: false };
  if (/liabilit|provision/.test(g)) return { nature: 'L', code: null, known: false };
  return { nature: null, code: null, known: false };
}

/* ---------- 3. Keyword rules (tier 2). First match wins. ---------- */
// nat: group nature filter (A/L/I/E); dr: true = debit balance, false = credit balance
const R = (re, code, nat, dr) => ({ re, code, nat, dr });
const DT = /def+er+e?d? tax/;
const RULES = [
  // interest received on an income-tax refund is income (other income), wherever the ledger was created
  R(/interest[\s\-:.]*(on|from|received on|u\/s|under)?[\s\-:.]*(the )?(income[\s\-]?tax|\bit\b|i\.t\.?|itr|tax)[\s\-]*refund|(income[\s\-]?tax|\bit\b|i\.t\.?|tax)[\s\-]*refund[\s\-]*interest|interest[\s\-:.]*(received[\s\-]*)?(on[\s\-]*)?refund|244a/, 'OI_INT'),
  // income tax debited to the profit and loss account = current tax (not an advance-tax asset)
  R(/^(?!.*(professional|property|gst|stamp|road|sales|\btds\b|\btcs\b|interest|penalty|late fee)).*(income[\s\-]?tax|advance[\s\-]*tax|self[\s\-]*assess|tax[\s\-]*paid|\bit[\s\-]*paid)/, 'TAX_CUR', 'E'),
  R(/current maturit/, 'STB_CURMAT', 'L'),
  R(DT, 'TAX_DEF', 'E'), R(DT, 'TAX_DEF', 'I'),
  R(DT, 'DTA', null, true), R(DT, 'DTL', null, false),
  R(/\bacc?u?m[a-z]*\.?\s+(of\s+|on\s+)?dep|acc\.? ?dep|provision for dep|depreciation (reserve|fund)/, 'PPE_ACCDEP'),
  R(/provision for doubtful|allowance for doubtful|doubtful debts? provision/, 'TR_PROV'),
  R(/profit (&|and) loss|surplus/, 'RS_SURPLUS', 'L'), R(/^profit (&|and) loss/, 'RS_SURPLUS', null),
  R(/general reserve/, 'RS_GEN'), R(/securities premium|share premium/, 'RS_SEC'), R(/capital reserve/, 'RS_CAP'),
  R(/preference/, 'SC_PREF', 'L'),
  R(/vehicle loan|car loan|auto loan/, 'LTB_VEH', 'L'),
  R(/director.*loan|loan.*director|director'?s? (a\/c|account)/, 'LTB_DIR', 'L'),
  R(/director'?s?'? (remuneration|salary|sitting)|remuneration.*director|sitting fee|managing director|whole.?time director/, 'EB_DIR', 'E'),
  R(/gratuity/, 'LTP_GRAT', 'L'), R(/gratuity/, 'EB_GRAT', 'E'),
  R(/leave encash/, 'LTP_LEAVE', 'L'), R(/leave encash/, 'EB_SAL', 'E'),
  R(/current tax|income tax expense|tax expense|provision for (income )?tax.*expense/, 'TAX_CUR', 'E'),
  R(/earlier year|prior year tax|short provision/, 'TAX_EARL', 'E'),
  R(/advance tax|tds receivable|tcs receivable|income tax refund|self assessment tax/, 'STLA_GOVT'),
  R(/income tax|provision for tax|tax provision/, 'SP_TAX', 'L'),
  R(/\bmsme\b|micro|small enterprise/, 'TP_MSME', 'L'),
  R(/\binput\b|\bitc\b|credit ledger|gst receivable/, 'STLA_GOVT', null, true),
  R(/\bgst\b|cgst|sgst|igst|\btds\b|\btcs\b|\bcess\b/, 'STLA_GOVT', 'L', true),   // debit balance in Duties & Taxes = asset
  R(/salar(y|ies) payable|wages payable|bonus payable|salary outstanding/, 'OCL_EMP', 'L'),
  R(/output|gst|cgst|sgst|igst|\bcess\b|\btds\b|\btcs\b|\bpf\b|\besic?\b|professional tax|statutory/, 'OCL_STAT', 'L'),
  R(/advance from|advance received|customer advance|advances? from customer/, 'OCL_ADV', 'L'),
  R(/creditors? for capital|capital creditor/, 'OCL_CAP', 'L'),
  R(/interest accrued|accrued interest/, 'OCL_INT', 'L'), R(/interest accrued|accrued interest/, 'OCA_INT', 'A'),
  R(/software|goodwill|trademark|patent|copyright|licen[cs]e/, 'INTANG', 'A'),
  R(/capital w|\bcwip\b|work[- ]in[- ]progress/, 'CWIP', 'A'),
  R(/mutual fund|liquid fund/, 'CINV', 'A'),
  R(/capital advance|advance for capital|advance for machinery/, 'LTLA_CAP', 'A'),
  R(/security deposit|deposit with|electricity deposit|rent deposit|msedcl/, 'LTLA_SD', 'A'),
  R(/fixed deposit|\bfd\b|term deposit/, 'CCE_OBB', 'A'),
  R(/advance to supplier|supplier advance|advance to creditor/, 'STLA_SUPP', 'A'),
  R(/prepaid/, 'STLA_PRE', 'A'),
  R(/staff advance|employee advance|salary advance|loan to staff/, 'STLA_EMP', 'A'),
  // incomes
  R(/job ?work/, 'REV_SERV', 'I'), R(/job ?work/, 'OE_JOB', 'E'),
  R(/scrap|export incentive|duty drawback|rodtep/, 'REV_OOR', 'I'),
  R(/service|consultancy|commission income/, 'REV_SERV', 'I'),
  R(/interest/, 'OI_INT', 'I'), R(/dividend/, 'OI_DIV', 'I'),
  R(/profit on sale|gain on sale|capital gain/, 'OI_GAIN', 'I'),
  // purchases / expenses
  R(/traded|trading goods|stock.in.trade|resale/, 'PUR_SIT', 'E'),
  R(/freight inward|carriage inward|inward freight|octroi|clearing/, 'PUR_RM', 'E'),
  R(/staff welfare|canteen/, 'EB_WEL', 'E'),
  R(/contribution|provident|\bpf\b|\besic?\b/, 'EB_PF', 'E'),
  R(/wages|salar|bonus|stipend/, 'EB_SAL', 'E'),
  R(/processing fee|processing charge|loan charges/, 'FC_OTH', 'E'),
  R(/bank charge|bank commission/, 'OE_BANK', 'E'),
  R(/interest|finance charge/, 'FC_INT', 'E'),
  R(/depreciation|amorti[sz]ation/, 'DEP', 'E'),
  R(/power|electricity|fuel|diesel/, 'OE_POWER', 'E'),
  R(/stores|consumable|spares/, 'OE_STORES', 'E'),
  R(/\brent\b|lease rent/, 'OE_RENT', 'E'),
  R(/repair.*(build|premises|office)/, 'OE_REP_BLD', 'E'), R(/repair.*(mach|plant)/, 'OE_REP_MAC', 'E'),
  R(/repair|maintenance/, 'OE_REP_OTH', 'E'),
  R(/insurance/, 'OE_INS', 'E'),
  R(/\brates\b|municipal|property tax|stamp duty/, 'OE_RATES', 'E'),
  R(/audit/, 'OE_AUD', 'E'),
  R(/legal|professional|consultancy/, 'OE_PROF', 'E'),
  R(/freight|carriage|transport/, 'OE_FRT', 'E'),
  R(/travel|conveyance/, 'OE_TRAV', 'E'),
  R(/telephone|internet|mobile|postage|courier/, 'OE_COMM', 'E'),
  R(/printing|stationery/, 'OE_PRINT', 'E'),
  R(/advertis|sales promotion|business promotion/, 'OE_ADV', 'E'),
  R(/\bcsr\b|corporate social/, 'OE_CSR', 'E'),
  R(/bad debt|written off/, 'OE_BADDEBT', 'E'),
];
const NCE_RULES = [
  R(/drawing/, 'OC_DRAW'),
  R(/current (a\/c|account)|partner.*current/, 'OC_CUR', 'L'),
  R(/partner.*loan|loan.*partner|proprietor.*loan/, 'LTB_REL', 'L'),
  R(/partner.*capital|capital (a\/c|account)|proprietor.*capital|^capital\b|fixed capital/, 'OC_CAP', 'L'),
  R(/(partner|proprietor).*(remuneration|salary)|(remuneration|salary).*(partner|proprietor)/, 'EB_PART', 'E'),
  R(/interest.*(partner|capital)|partner.*interest/, 'FC_PINT', 'E'),
];
function openingStockCode(n) {
  if (/raw|\brm\b/.test(n)) return 'INV_OP_RM';
  if (/wip|work.in.progress|semi/.test(n)) return 'INV_OP_WIP';
  if (/trad|stock.in.trade/.test(n)) return 'INV_OP_SIT';
  if (/store|spare|consumable/.test(n)) return 'INV_OP_STORES';
  return 'INV_OP_FG';
}

/** Map one ledger. saved = {ledgerName: code} for this client. fw = 'company' | 'nce'. */
function autoMap(led, saved, fw) {
  if (saved && saved[led.name] && LINE[saved[led.name]]) return { code: xlate(saved[led.name], fw), source: 'saved' };
  const n = String(led.name).toLowerCase();
  // interest on an income-tax refund is a profit and loss item even if it sits in a balance-sheet group
  if (RULES[0].re.test(n)) return { code: 'OI_INT', source: 'rule', rule: 'interest on income-tax refund' };
  // every ledger of the Tally group "Duties & Taxes" (and its sub-groups) is a statutory due, shown net
  if (/^duties (&|and) taxes$/.test(normG(led.pg)) || /^duties (&|and) taxes$/.test(normG(led.group)))
    return { code: 'OCL_STAT', source: 'group', rule: 'duties & taxes' };
  let gi = groupInfo(led.group);
  if (!gi.known && led.pg) { const g2 = groupInfo(led.pg); if (g2.known || !gi.nature) gi = g2; }
  if (/opening stock|opening inventory/.test(n) || normG(led.group) === 'opening stock')
    return { code: openingStockCode(n), source: 'rule', rule: 'opening stock' };
  const bal = led.cy !== 0 ? led.cy : led.py;
  const run = (rules, text) => {
    for (const r of rules) {
      if (r.nat && gi.nature && r.nat !== gi.nature) continue;
      if (r.nat && !gi.nature) continue;
      if (r.dr === true && !(bal > 0)) continue;
      if (r.dr === false && !(bal < 0)) continue;
      if (r.re.test(text)) return { code: xlate(r.code, fw), source: 'rule', rule: r.re.source };
    }
    return null;
  };
  const hit = (isNCE(fw) && run(NCE_RULES, n)) || run(RULES, n);
  if (hit) return hit;
  // custom Tally sub-group of a balance-sheet group (e.g. "TDS PAYABALE", "SECURITY DEPOSITS"): try the keyword rules on its name
  const parent = String(led.group || '').toLowerCase();
  if (led.pg && parent && normG(led.group) !== normG(led.pg) && (gi.nature === 'A' || gi.nature === 'L')) {
    const h2 = (isNCE(fw) && run(NCE_RULES, parent)) || run(RULES, parent);
    if (h2) return h2;
  }
  if (gi.code) return { code: xlate(gi.code, fw), source: 'group' };
  return { code: null, source: 'none' };
}

/* ---------- 4. Amount & sheet parsing ---------- */
function parseAmount(v) {
  if (v === null || v === undefined || v === '') return 0;
  if (typeof v === 'number') return isFinite(v) ? v : 0;
  let s = String(v).trim();
  if (!s || s === '-' || s === '—') return 0;
  let sign = 1;
  if (/\bcr\.?$/i.test(s)) { sign = -1; s = s.replace(/\bcr\.?$/i, ''); }
  else if (/\bdr\.?$/i.test(s)) { s = s.replace(/\bdr\.?$/i, ''); }
  if (/^\(.*\)$/.test(s.trim())) { sign *= -1; s = s.trim().slice(1, -1); }
  s = s.replace(/[₹,\s]/g, '').replace(/^rs\.?/i, '');
  const n = parseFloat(s);
  return isFinite(n) ? sign * n : 0;
}

/** Guess header row & columns from a 2-D array of cell values. */
function detectColumns(rows) {
  let hdr = 0;
  for (let i = 0; i < Math.min(rows.length, 25); i++) {
    const t = (rows[i] || []).map(c => String(c ?? '').toLowerCase());
    if (t.some(c => /ledger|particulars|account name|account|^name$/.test(c))) { hdr = i; break; }
  }
  const H = (rows[hdr] || []).map(c => String(c ?? '').toLowerCase().trim());
  const find = (re, not) => H.findIndex(h => re.test(h) && !(not && not.test(h)));
  const isPY = /\bpy\b|previous|prior|last year|2024|2023|p\.y/;
  const cm = { header: hdr, ledger: find(/ledger|particulars|account|^name$/), group: find(/group|under|parent|head/) };
  const cyDr = find(/debit|\bdr\b/, isPY), cyCr = find(/credit|\bcr\b/, isPY);
  const pyDr = H.findIndex(h => /debit|\bdr\b/.test(h) && isPY.test(h));
  const pyCr = H.findIndex(h => /credit|\bcr\b/.test(h) && isPY.test(h));
  if (cyDr >= 0 && cyCr >= 0) { cm.cyMode = 'drcr'; cm.cyDr = cyDr; cm.cyCr = cyCr; }
  else { cm.cyMode = 'signed'; cm.cy = find(/\bcy\b|current|closing|balance|amount|2026|2025-26/, isPY); }
  if (pyDr >= 0 && pyCr >= 0) { cm.pyMode = 'drcr'; cm.pyDr = pyDr; cm.pyCr = pyCr; }
  else { cm.pyMode = 'signed'; cm.py = H.findIndex(h => isPY.test(h)); }
  cm.crPositive = false;
  return cm;
}

/* ---- Tally "ledger export" layout: Name | Parent | PrimaryGroup | OpeningBalance | Net Debit | Net Credit | ClosingBalance | … | FY 25-26 | FY 24-25
   Credit balances are POSITIVE in this export; one sheet stacks the current-year and previous-year ledgers, tagged in the FY columns. ---- */
const cleanCell = s => String(s ?? '').replace(/[\u0000-\u001f]/g, '').trim();
const normH = s => cleanCell(s).toLowerCase().replace(/[\s_]+/g, '');
function findTallyHeader(rows) {
  for (let i = 0; i < Math.min(rows.length, 30); i++) {
    const H = (rows[i] || []).map(normH);
    if (H.includes('closingbalance') && (H.includes('name') || H.includes('ledger')) && (H.includes('parent') || H.includes('primarygroup'))) return i;
  }
  return -1;
}
const isTallyExport = rows => findTallyHeader(rows) >= 0;
/** A "Total" summary line - not a ledger whose name merely starts with "Total" (e.g. a debtor called "Total Foundation"): real ledgers carry a group. */
function isTotalRow(name, parent, pg) {
  if (!/^(grand\s+)?total\b/i.test(name)) return false;
  return /^(grand\s+)?total\s*:?\s*$/i.test(name) || (!cleanCell(parent) && !cleanCell(pg));
}

/** Returns { ledgers:[{name,group,pg,cy,py}], hasPY, info } or null if the sheet is not a Tally ledger export. Dr = +, Cr = −. */
function buildTallyTB(rows, opt) {
  opt = opt || {};
  const hdr = findTallyHeader(rows); if (hdr < 0) return null;
  const H = rows[hdr].map(normH), ix = re => H.findIndex(h => re.test(h));
  const c = { name: ix(/^(name|ledger)$/), parent: ix(/^(parent|under)$/), pg: ix(/^primarygroup$/), close: ix(/^closingbalance$/),
    pyClose: ix(/^(py|previousyear|prioryear)(closing)?(balance)?$/), open: ix(/^openingbalance$/), pyOpen: ix(/^(py|previousyear|prioryear)opening(balance)?$/), dr: ix(/^netdebit$/), cr: ix(/^netcredit$/) };   // one-row-per-ledger layout: current and previous closing side by side
  const fy = [];
  H.forEach((h, i) => { const m = /^fy(\d{2,4})[-–\/](\d{2,4})$/.exec(h); if (m) { let y = +m[1]; if (y < 100) y += 2000; fy.push({ i, y, label: cleanCell(rows[hdr][i]) }); } });
  fy.sort((a, b) => b.y - a.y);                       // latest year first = current year
  const blk = { cy: new Map(), py: new Map(), p0: new Map() }, order = [], meta = {}, nds = new Map(), ncs = new Map(); let sawP0 = false;
  let cur = 'cy', dupes = 0;
  for (let r = hdr + 1; r < rows.length; r++) {
    const row = rows[r] || [], name = cleanCell(row[c.name]), parent0 = rw => (c.parent >= 0 ? rw[c.parent] : ''), pg0 = rw => (c.pg >= 0 ? rw[c.pg] : '');
    if (!name || isTotalRow(name, parent0(row), pg0(row))) continue;
    if (c.pyClose < 0 && fy.length) { const hit = fy.find(f => cleanCell(row[f.i]) !== ''); if (hit) cur = hit === fy[0] ? 'cy' : 'py'; }
    const parent = c.parent >= 0 ? cleanCell(row[c.parent]) : '';
    const pg = (c.pg >= 0 ? cleanCell(row[c.pg]) : '') || (/^primary$/i.test(parent) ? 'Primary' : '');
    const dr = -parseAmount(row[c.close]);            // export is Cr-positive → flip to Dr-positive
    const put = (m, v) => { if (m.has(name)) { m.set(name, m.get(name) + v); dupes++; } else m.set(name, v); };
    if ((c.pyClose >= 0 || cur === 'cy') && c.dr >= 0) { nds.set(name, Math.abs(parseAmount(row[c.dr]))); ncs.set(name, Math.abs(c.cr >= 0 ? parseAmount(row[c.cr]) : 0)); }   // current-year debit / credit totals
    if (c.pyClose >= 0) {
      put(blk.cy, dr); put(blk.py, -parseAmount(row[c.pyClose]));
      if (c.pyOpen >= 0 && cleanCell(row[c.pyOpen]) !== '') { sawP0 = true; put(blk.p0, -parseAmount(row[c.pyOpen])); }
    } else {
      put(blk[cur], dr);
      if (cur === 'py' && c.open >= 0) { sawP0 = true; put(blk.p0, -parseAmount(row[c.open])); }      // stacked layout: the previous-year block's opening balance
    }
    if (!meta[name]) { meta[name] = { parent, pg }; order.push(name); }
  }
  // Tally's "Profit & Loss A/c" closing already includes the current period's profit, which the income and expense
  // ledgers carry separately. Keep only the brought-forward part so the profit is not counted twice.
  const isPL = n => /^profit\s*(&|and)\s*loss/i.test(n) && /^(primary|)$/i.test(meta[n].pg) ;
  const plAdj = {};
  for (const p of ['cy', 'py']) {
    const plName = [...blk[p].keys()].find(isPL);
    if (!plName) continue;
    let nominal = 0;
    for (const [n, v] of blk[p]) {
      if (n === plName) continue;
      const g = groupInfo(meta[n].pg || meta[n].parent);
      if (g.nature === 'I' || g.nature === 'E') nominal += v;
    }
    plAdj[p] = round2(blk[p].get(plName) - nominal);
    blk[p].set(plName, plAdj[p]);
  }
  const ledgers = []; let nil = 0;
  for (const n of order) {
    const cy = round2(blk.cy.get(n) || 0), py = round2(blk.py.get(n) || 0), pl = isPL(n);
    // balance at the start of the previous year = the previous-year OPENING balance (the P&L A/c too: its opening is the surplus before any
    // transfer to reserves during that year); income / expense ledgers start at nil
    const nominal = (() => { const g = groupInfo(meta[n].pg || meta[n].parent); return g.nature === 'I' || g.nature === 'E'; })();
    const p0 = !sawP0 ? undefined : nominal ? 0 : round2(blk.p0.get(n) || 0);
    if (opt.skipNil !== false && Math.abs(cy) < 0.005 && Math.abs(py) < 0.005 && Math.abs(p0 || 0) < 0.005) { nil++; continue; }
    const row = { name: n, group: meta[n].parent || meta[n].pg, pg: meta[n].pg, cy, py };
    if (p0 !== undefined) row.p0 = p0;
    if (nds.has(n)) { row.nd = round2(nds.get(n)); row.nc = round2(ncs.get(n) || 0); }
    if (pl) row.pl = true;
    ledgers.push(row);
  }
  const hasPY = c.pyClose >= 0 || (fy.length > 1 && blk.py.size > 0);
  return { ledgers, hasPY, info: { header: hdr, cyLabel: fy[0] ? fy[0].label : 'Current year', pyLabel: fy[1] ? fy[1].label : '',
    cyY: fy[0] ? fy[0].y : null, pyY: fy[1] ? fy[1].y : null, cyRows: blk.cy.size, pyRows: blk.py.size, nil, dupes, plAdj, hasP0: sawP0 } };
}

/** Build ledgers from rows using a column map. */
function buildTB(rows, cm) {
  const out = [], seen = {};
  const amt = (row, mode, s, d, c) => {
    if (mode === 'drcr') return parseAmount(row[d]) - Math.abs(parseAmount(row[c]));
    if (s == null || s < 0) return 0;
    const raw = row[s];
    let v = parseAmount(raw);
    if (cm.crPositive && !/(dr|cr)\.?$/i.test(String(raw ?? '').trim())) v = v; // as supplied
    return v;
  };
  for (let i = cm.header + 1; i < rows.length; i++) {
    const row = rows[i] || [];
    const name = String(row[cm.ledger] ?? '').trim();
    if (!name || isTotalRow(name, cm.group >= 0 ? row[cm.group] : '', '') || /^difference in opening|^opening balance difference/i.test(name)) continue;
    const cy = round2(amt(row, cm.cyMode, cm.cy, cm.cyDr, cm.cyCr));
    const py = round2(amt(row, cm.pyMode, cm.py, cm.pyDr, cm.pyCr));
    let key = name, k = 2;
    while (seen[key]) key = name + ' (' + (k++) + ')';
    seen[key] = 1;
    out.push({ name: key, group: cm.group >= 0 ? String(row[cm.group] ?? '').trim() : '', cy, py });
  }
  return out;
}
const round2 = x => Math.round((x + Number.EPSILON) * 100) / 100;

/* ---------- 5. Units & rounding (Schedule III, General Instructions) ---------- */
const UNITS = {
  rupees:   { div: 1,        dec: 0, label: '₹' },
  hundreds: { div: 100,      dec: 0, label: '₹ in hundreds' },
  thousands:{ div: 1000,     dec: 0, label: '₹ in thousands' },
  lakhs:    { div: 100000,   dec: 2, label: '₹ in lakhs' },
  millions: { div: 1000000,  dec: 2, label: '₹ in millions' },
  crores:   { div: 10000000, dec: 2, label: '₹ in crores' },
};
const rnd = (x, u) => { const f = Math.pow(10, u.dec); return Math.round((x / u.div) * f + 1e-9 * Math.sign(x)) / f; };

/* ---------- 6. Compute statements ---------- */
const PERIODS = ['cy', 'py'];
const BS_LIAB = ['SC','RS','SW','SAM','LTB','DTL','OLTL','LTP','STB','TP','OCL','SP'];
const BS_ASSET = ['PPE','INTANG','CWIP','IAUD','NCI','DTA','LTLA','ONCA','CINV','INV','TR','CCE','STLA','OCA'];

/**
 * @param ledgers [{name,group,cy,py}]
 * @param map {ledgerName: code}
 * @param inv {cy:{RM,WIP,...}, py:{...}}  closing stock
 * @param opt {unit, hasPY, shares:{cy,py}}
 */
function compute(ledgers, map, inv, opt) {
  opt = opt || {};
  const fw = isNCE(opt.framework) ? 'nce' : 'company', NC = fw === 'nce';
  const fwName = NC ? 'the NCE format' : 'Schedule III';
  const APPR = NC && !!opt.appropriate;   // NCE: profit appropriated to partners' capital accounts instead of reserves
  const partners = (opt.partners || []).filter(x => String(x.name || '').trim());
  const u = UNITS[opt.unit] || UNITS.rupees;
  const sub = {};    // code -> {cy,py,p0,ledgers:[]}   (p0 = start of the previous year, used for the previous-year cash flow)
  const ensure = c => sub[c] || (sub[c] = { cy: 0, py: 0, p0: 0, ledgers: [] });
  const tb = { cy: 0, py: 0 }, unmapped = [];
  for (const l of ledgers) {
    tb.cy += l.cy; tb.py += l.py;
    const code = xlate(map[l.name], fw);
    if (!code || !LINE[code] || (NC ? NCE_OFF : NCE_ONLY).has(code)) { unmapped.push(l); continue; }
    const sign = HEAD[LINE[code].head].credit ? -1 : 1;
    const s = ensure(code);
    s.cy += sign * l.cy; s.py += sign * l.py; s.p0 += sign * (+l.p0 || 0);
    s.ledgers.push({ name: l.name, group: l.group, cy: sign * l.cy, py: sign * l.py, p0: sign * (+l.p0 || 0), raw: l });
  }
  // closing inventory
  inv = inv || { cy: {}, py: {} };
  for (const c of INV_CATS) {
    const s = ensure('INV_' + c.key);
    s.cy = +(inv.cy && inv.cy[c.key]) || 0; s.py = +(inv.py && inv.py[c.key]) || 0;
  }
  const v = (code, p) => (sub[code] ? sub[code][p] : 0);
  const res = {};
  for (const p of PERIODS) {
    const H = {};
    for (const h of HEADS) H[h.id] = 0;
    for (const code in sub) {
      if (code.startsWith('INV_') && !code.startsWith('INV_OP')) continue;
      H[LINE[code].head] += sub[code][p];
    }
    // closing stock adjustments
    H.INV = INV_CATS.reduce((a, c) => a + v('INV_' + c.key, p), 0);
    for (const c of INV_CATS) H[c.target] -= v('INV_' + c.key, p);
    // P&L
    const pl = {};
    pl.totalIncome = H.REV + H.OI;
    pl.totalExp = H.COMC + H.PSIT + H.CHG + H.EB + H.FC + H.DEP + H.OE;
    pl.pbei = pl.totalIncome - pl.totalExp;
    pl.pbt = pl.pbei - H.EXC - H.EXTRA;
    pl.pat = pl.pbt - H.TAX;
    if (APPR) H.SC += pl.pat; else H.RS += pl.pat;   // profit to partners' accounts (NCE) or surplus carried to reserves
    const totL = BS_LIAB.reduce((a, k) => a + H[k], 0);
    const totA = BS_ASSET.reduce((a, k) => a + H[k], 0);
    res[p] = { H, pl, totL, totA, tb: round2(tb[p]) };
  }
  // balance sheet heads at the start of the previous year (no P&L: income / expense ledgers start at nil)
  {
    const H = {}; for (const h of HEADS) H[h.id] = 0;
    for (const code in sub) { if (code.startsWith('INV_')) continue; H[LINE[code].head] += sub[code].p0; }
    H.INV = INV_CATS.reduce((a, c) => a + v(c.openCode, 'py'), 0);          // stock at the start of the previous year = its opening stock
    res.p0 = { H, hasP0: ledgers.some(l => l.p0 !== undefined && l.p0 !== null) };
  }

  /* --- note numbering (non-nil heads, BS then P&L, starting at 3) --- */
  const nil = id => Math.abs(res.cy.H[id]) < 0.005 && Math.abs(res.py.H[id]) < 0.005;
  const noteNo = {}; let n = 3;
  for (const h of HEADS) if (!nil(h.id) && h.id !== 'TAX') noteNo[h.id] = n++;

  /* --- rounded face figures --- */
  const R = id => ({ cy: rnd(res.cy.H[id], u), py: rnd(res.py.H[id], u) });
  const face = { bs: [], pl: [] };
  const sumR = (ids) => ({ cy: rsum(ids.map(i => R(i).cy), u), py: rsum(ids.map(i => R(i).py), u) });

  const bsItem = (id, lab) => ({ id, label: lab || HEAD[id].name, note: noteNo[id], ...R(id), nil: nil(id) });
  face.bs = [
    ...(NC ? [
      { t: 'title', label: "I. OWNERS' FUNDS AND LIABILITIES" },
      { t: 'group', label: "(1) Owners' funds" },
      { t: 'line', ...bsItem('SC', '(a) Capital accounts') }, { t: 'line', ...bsItem('RS', '(b) Reserves and surplus') },
    ] : [
      { t: 'title', label: 'I. EQUITY AND LIABILITIES' },
      { t: 'group', label: "(1) Shareholders' funds" },
      { t: 'line', ...bsItem('SC', '(a) Share capital') }, { t: 'line', ...bsItem('RS', '(b) Reserves and surplus') },
      { t: 'line', ...bsItem('SW', '(c) Money received against share warrants') },
      { t: 'line', ...bsItem('SAM', '(2) Share application money pending allotment'), lvl: 0 },
    ]),
    { t: 'group', label: NC ? '(2) Non-current liabilities' : '(3) Non-current liabilities' },
    { t: 'line', ...bsItem('LTB', '(a) Long-term borrowings') }, { t: 'line', ...bsItem('DTL', '(b) Deferred tax liabilities (Net)') },
    { t: 'line', ...bsItem('OLTL', '(c) Other long-term liabilities') }, { t: 'line', ...bsItem('LTP', '(d) Long-term provisions') },
    { t: 'group', label: NC ? '(3) Current liabilities' : '(4) Current liabilities' },
    { t: 'line', ...bsItem('STB', '(a) Short-term borrowings') },
    { t: 'line', ...bsItem('TP', '(b) Trade payables') , noAmt: true },
    { t: 'subline', label: '(A) total outstanding dues of micro enterprises and small enterprises', id: 'TP_MSME', note: noteNo.TP,
      cy: rnd(v('TP_MSME', 'cy'), u), py: rnd(v('TP_MSME', 'py'), u), nil: nil('TP') },
    { t: 'subline', label: '(B) total outstanding dues of creditors other than micro enterprises and small enterprises', id: 'TP_OTH', note: noteNo.TP,
      cy: rnd(res.cy.H.TP - v('TP_MSME', 'cy'), u), py: rnd(res.py.H.TP - v('TP_MSME', 'py'), u), nil: nil('TP') },
    { t: 'line', ...bsItem('OCL', '(c) Other current liabilities') }, { t: 'line', ...bsItem('SP', '(d) Short-term provisions') },
  ];
  const liabVals = face.bs.filter(r => (r.t === 'line' && !r.noAmt) || r.t === 'subline');
  const totLR = { cy: rsum(liabVals.map(r => r.cy), u), py: rsum(liabVals.map(r => r.py), u) };
  face.bs.push({ t: 'total', label: 'TOTAL', ...totLR });
  const aStart = face.bs.length;
  face.bs.push(
    { t: 'title', label: 'II. ASSETS' },
    { t: 'group', label: '(1) Non-current assets' },
    { t: 'group2', label: '(a) Property, Plant and Equipment and Intangible assets' },
    { t: 'subline', ...bsItem('PPE', '(i) Property, Plant and Equipment') },
    { t: 'subline', ...bsItem('INTANG', '(ii) Intangible assets') },
    { t: 'subline', ...bsItem('CWIP', '(iii) Capital work-in-progress') },
    { t: 'subline', ...bsItem('IAUD', '(iv) Intangible assets under development') },
    { t: 'line', ...bsItem('NCI', '(b) Non-current investments') }, { t: 'line', ...bsItem('DTA', '(c) Deferred tax assets (Net)') },
    { t: 'line', ...bsItem('LTLA', '(d) Long-term loans and advances') }, { t: 'line', ...bsItem('ONCA', '(e) Other non-current assets') },
    { t: 'group', label: '(2) Current assets' },
    { t: 'line', ...bsItem('CINV', '(a) Current investments') }, { t: 'line', ...bsItem('INV', '(b) Inventories') },
    { t: 'line', ...bsItem('TR', '(c) Trade receivables') }, { t: 'line', ...bsItem('CCE', '(d) Cash and cash equivalents') },
    { t: 'line', ...bsItem('STLA', '(e) Short-term loans and advances') }, { t: 'line', ...bsItem('OCA', '(f) Other current assets') },
  );
  const assetVals = face.bs.slice(aStart).filter(r => r.t === 'line' || r.t === 'subline');
  const totAR = { cy: rsum(assetVals.map(r => r.cy), u), py: rsum(assetVals.map(r => r.py), u) };
  face.bs.push({ t: 'total', label: 'TOTAL', ...totAR });
  // hide TP sublines / PPE caption when nil
  if (nil('PPE') && nil('INTANG') && nil('CWIP') && nil('IAUD')) face.bs.forEach(r => { if (r.t === 'group2') r.nil = true; });

  // P&L face (rounded lines; totals from rounded lines)
  const rv = R('REV'), oi = R('OI');
  const ti = { cy: rsum([rv.cy, oi.cy], u), py: rsum([rv.py, oi.py], u) };
  const expIds = ['COMC','PSIT','CHG','EB','FC','DEP','OE'];
  const te = sumR(expIds);
  const p5 = { cy: rsum([ti.cy, -te.cy], u), py: rsum([ti.py, -te.py], u) };
  const exc = R('EXC'), ext = R('EXTRA');
  const p7 = { cy: rsum([p5.cy, -exc.cy], u), py: rsum([p5.py, -exc.py], u) };
  const p9 = { cy: rsum([p7.cy, -ext.cy], u), py: rsum([p7.py, -ext.py], u) };
  const taxCur = { cy: rnd(v('TAX_CUR','cy') + v('TAX_EARL','cy'), u), py: rnd(v('TAX_CUR','py') + v('TAX_EARL','py'), u) };
  const taxDef = { cy: rnd(v('TAX_DEF','cy'), u), py: rnd(v('TAX_DEF','py'), u) };
  const p11 = { cy: rsum([p9.cy, -taxCur.cy, -taxDef.cy], u), py: rsum([p9.py, -taxCur.py, -taxDef.py], u) };
  const sh = opt.shares || {};
  const eps = p => (sh[p] > 0 ? Math.round(res[p].pl.pat / sh[p] * 100) / 100 : null);
  const PLL = { TI: NC ? 'III. Total revenue (I + II)' : 'III. Total income (I + II)', TE: 'Total expenses (IV)',
    P5: 'V. Profit before exceptional and extraordinary items and tax (III − IV)', P7: 'VII. Profit before extraordinary items and tax (V − VI)',
    P9: 'IX. Profit before tax (VII − VIII)', PAT: NC ? 'XI. Profit / (Loss) for the year (IX − X)' : 'XV. Profit / (Loss) for the period' };
  const split = p => { let rest = res[p].pl.pat; return partners.map((x, i) => { const v = i === partners.length - 1 ? rest : round2(res[p].pl.pat * (+x.share || 0) / 100); rest -= v; return v; }); };
  const sCy = split('cy'), sPy = split('py');
  const apprRows = APPR ? partners.map((x, i) => ({ name: x.name.trim(), share: +x.share || 0, cy: sCy[i], py: sPy[i] })) : [];
  const plItem = (id, lab) => ({ t: 'line', id, label: lab, note: noteNo[id], ...R(id), nil: nil(id) });
  face.pl = [
    { ...plItem('REV', 'I. Revenue from operations'), lvl: 0 },
    { ...plItem('OI', 'II. Other income'), lvl: 0 },
    { t: 'total', label: PLL.TI, ...ti },
    { t: 'group', label: 'IV. Expenses' },
    plItem('COMC', 'Cost of materials consumed'), plItem('PSIT', 'Purchases of stock-in-trade'),
    plItem('CHG', 'Changes in inventories of finished goods, work-in-progress and stock-in-trade'),
    plItem('EB', 'Employee benefits expense'), plItem('FC', 'Finance costs'),
    plItem('DEP', 'Depreciation and amortisation expense'), plItem('OE', 'Other expenses'),
    { t: 'total', label: PLL.TE, ...te },
    { t: 'total', label: PLL.P5, ...p5 },
    { ...plItem('EXC', 'VI. Exceptional items'), lvl: 0, keep: true },
    { t: 'total', label: PLL.P7, ...p7 },
    { ...plItem('EXTRA', 'VIII. Extraordinary items'), lvl: 0, keep: true },
    { t: 'total', label: PLL.P9, ...p9 },
    { t: 'group', label: 'X. Tax expense' },
    { t: 'line', id: 'TAX_CUR', label: '(1) Current tax', ...taxCur, keep: true },
    { t: 'line', id: 'TAX_DEF', label: '(2) Deferred tax', ...taxDef, keep: true },
    ...(NC ? [{ t: 'total', label: PLL.PAT, ...p11, strong: true }, ...(APPR ? [
      { t: 'group', label: "Appropriation of profit (transferred to partners' capital accounts)" },
      ...(apprRows.length ? apprRows.map(x => ({ t: 'line', label: `${x.name} (${x.share}%)`, cy: rnd(x.cy, u), py: rnd(x.py, u) }))
                          : [{ t: 'line', label: "Transferred to partners' capital accounts", ...p11 }]),
      { t: 'total', label: 'Total appropriated', ...p11 }] : [])] : [
      { t: 'total', label: 'XI. Profit / (Loss) for the period from continuing operations (IX − X)', ...p11 },
      { t: 'total', label: PLL.PAT, ...p11, strong: true },
      { t: 'group', label: 'XVI. Earnings per equity share (₹)' },
      { t: 'eps', label: '(1) Basic', cy: eps('cy'), py: eps('py') },
      { t: 'eps', label: '(2) Diluted', cy: eps('cy'), py: eps('py') },
    ]),
  ];

  /* --- notes --- */
  const notes = [];
  for (const h of HEADS) {
    if (!noteNo[h.id]) continue;
    const rows = [];
    const subLines = LINES.filter(l => l.head === h.id);
    for (const l of subLines) {
      const s = sub[l.code];
      if (!s || (Math.abs(s.cy) < 0.005 && Math.abs(s.py) < 0.005)) continue;
      rows.push({ code: l.code, label: l.label, cy: s.cy, py: s.py, ledgers: s.ledgers });
    }
    if (h.id === 'SC' && APPR) rows.push({ code: 'PAT', label: "Add: Share of profit for the year (appropriated to partners' accounts)", cy: res.cy.pl.pat, py: res.py.pl.pat, ledgers: [] });
    if (h.id === 'RS' && !APPR) rows.push({ code: 'PAT', label: 'Add: Profit / (Loss) for the year', cy: res.cy.pl.pat, py: res.py.pl.pat, ledgers: [] });
    if (h.id === 'INV') for (const c of INV_CATS) {
      const s = sub['INV_' + c.key];
      if (s && (s.cy || s.py)) rows.push({ code: 'INV_' + c.key, label: c.label, cy: s.cy, py: s.py, ledgers: [] });
    }
    for (const c of INV_CATS) if (c.target === h.id) {
      const s = sub['INV_' + c.key];
      if (s && (s.cy || s.py)) rows.push({ code: 'CL_' + c.key, label: 'Less: Closing stock – ' + c.label.toLowerCase(), cy: -s.cy, py: -s.py, ledgers: [] });
    }
    notes.push({ no: noteNo[h.id], id: h.id, title: headName(h.id, fw), rows, total: { cy: res.cy.H[h.id], py: res.py.H[h.id] } });
  }

  /* --- checks --- */
  const checks = [];
  const fmtA = x => x.toLocaleString('en-IN', { maximumFractionDigits: 2 });
  for (const p of PERIODS) {
    if (p === 'py' && !opt.hasPY) continue;
    const P = p.toUpperCase();
    checks.push(Math.abs(res[p].tb) < 0.5
      ? { lvl: 'ok', title: `Trial balance agrees (${P})`, detail: 'Total debits equal total credits.' }
      : { lvl: 'error', title: `Trial balance does not agree (${P})`, detail: `Difference of ₹${fmtA(res[p].tb)} (${res[p].tb > 0 ? 'excess debit' : 'excess credit'}). Fix the source TB before finalising.` });
  }
  checks.push(unmapped.length
    ? { lvl: 'error', title: `${unmapped.length} ledger(s) not mapped`, detail: `Map every ledger to a line of ${fwName} in the Mapping step.`, items: unmapped.map(l => l.name) }
    : { lvl: 'ok', title: 'All ledgers mapped', detail: `${ledgers.length} ledgers mapped to ${fwName} lines.` });
  for (const p of PERIODS) {
    if (p === 'py' && !opt.hasPY) continue;
    const d = round2(res[p].totL - res[p].totA), P = p.toUpperCase();
    checks.push(Math.abs(d) < 0.5
      ? { lvl: 'ok', title: `Balance Sheet tallies (${P})`, detail: `Equity and liabilities = Assets = ₹${fmtA(round2(res[p].totA))}.` }
      : { lvl: 'error', title: `Balance Sheet does not tally (${P})`, detail: `Difference ₹${fmtA(d)}. Usually caused by an unbalanced TB or unmapped ledgers.` });
  }
  const rd = { cy: round2(totLR.cy - totAR.cy), py: round2(totLR.py - totAR.py) };
  if (u.div > 1 && (Math.abs(rd.cy) > 1e-9 || Math.abs(rd.py) > 1e-9))
    checks.push({ lvl: 'warn', title: 'Rounding difference on Balance Sheet totals', detail: `Rounded totals differ by ${rd.cy} (CY) / ${rd.py} (PY) in ${u.label}. Adjust the largest line by the casting difference before issue.` });
  if (opt.hasPY) {
    const diffs = INV_CATS.map(c => ({ c, d: round2(v(c.openCode, 'cy') - v('INV_' + c.key, 'py')) })).filter(x => Math.abs(x.d) >= 0.5);
    checks.push(diffs.length
      ? { lvl: 'warn', title: 'Opening stock (CY) ≠ closing stock (PY)', detail: 'Opening stock ledgers in the current-year TB should equal last year\'s closing stock.', items: diffs.map(x => `${x.c.label}: difference ₹${fmtA(x.d)}`) }
      : { lvl: 'ok', title: 'Opening stock agrees with previous-year closing stock', detail: 'All inventory categories reconcile.' });
    const fund = x => APPR ? x.H.SC + x.H.RS : x.H.RS;
    const so = fund(res.cy) - res.cy.pl.pat, spc = fund(res.py), ds = round2(so - spc);   // CY reserves before CY profit vs PY closing reserves
    checks.push(Math.abs(ds) < 0.5
      ? { lvl: 'ok', title: 'Opening reserves agree with previous-year closing reserves', detail: `₹${fmtA(round2(so))} carried forward.` }
      : { lvl: 'warn', title: 'Opening reserves ≠ previous-year closing reserves', detail: `CY reserves before current-year profit ₹${fmtA(round2(so))} vs PY closing reserves ₹${fmtA(round2(spc))} (difference ₹${fmtA(ds)}). Check prior-period adjustments, appropriations or capital introduced / withdrawn.` });
  }
  const contra = [];
  for (const code in sub) {
    if (!LINE[code] || HEAD[LINE[code].head].stmt !== 'BS' || CONTRA_OK.has(code)) continue;
    for (const l of sub[code].ledgers) if (l.cy < -0.5) contra.push(`${l.name} — ${LINE[code].label} (₹${fmtA(round2(-l.cy))} opposite balance)`);
  }
  checks.push(contra.length
    ? { lvl: 'warn', title: `${contra.length} ledger(s) with opposite balances`, detail: `${fwName.replace('the ', '')} does not permit netting a debtor\'s credit balance or a creditor\'s debit balance against the head. Regroup these (e.g. debtor credit balance → Advances from customers).`, items: contra }
    : { lvl: 'ok', title: 'No opposite balances in Balance Sheet heads', detail: 'Every ledger carries the natural balance of its head.' });
  if (Math.abs(res.cy.H.TP) > 0.5 && Math.abs(v('TP_MSME', 'cy')) < 0.5)
    checks.push({ lvl: 'info', title: 'No MSME trade payables identified', detail: 'Dues to micro and small enterprises are shown separately (MSMED Act, 2006). Confirm supplier status before finalising.' });
  if (!NC) {
    const turnover = res.cy.H.REV;
    const big = turnover >= 1e9; // ₹100 crore
    const okUnits = big ? ['lakhs', 'millions', 'crores'] : ['rupees', 'hundreds', 'thousands', 'lakhs', 'millions'];
    checks.push(okUnits.includes(opt.unit || 'rupees')
      ? { lvl: 'ok', title: 'Rounding unit permitted by Schedule III', detail: `Turnover ${big ? 'is ₹100 crore or more' : 'is below ₹100 crore'}; ${u.label} is a permitted unit.` }
      : { lvl: 'warn', title: 'Rounding unit not permitted for this turnover', detail: big ? 'Turnover ≥ ₹100 crore: round to lakhs, millions or crores (or decimals thereof).' : 'Turnover < ₹100 crore: round to hundreds, thousands, lakhs or millions (or decimals thereof); crores is not permitted.' });
    if (!(sh.cy > 0)) checks.push({ lvl: 'info', title: 'EPS not computed', detail: 'Enter the weighted average number of equity shares in Company details (AS 20).' });
  } else {
    if (Math.abs(res.cy.H.SC) < 0.5) checks.push({ lvl: 'info', title: 'No owners\' capital accounts mapped', detail: 'Map the partners\' / proprietor\'s capital ledgers to "Capital accounts" so that Owners\' funds are presented.' });
    if (!APPR) checks.push({ lvl: 'info', title: 'Appropriation of profit', detail: 'Profit for the year is carried to Reserves and surplus. To appropriate it to the partners\' capital accounts, choose that option in Entity details and enter the profit-sharing ratio.' });
    else if (!partners.length) checks.push({ lvl: 'warn', title: 'No partners entered', detail: 'Profit is added to the capital accounts as one amount. Enter each partner and profit-sharing ratio in Entity details to show the appropriation by partner.' });
    else { const tot = partners.reduce((a, x) => a + (+x.share || 0), 0);
      checks.push(Math.abs(tot - 100) < 0.005 ? { lvl: 'ok', title: 'Profit-sharing ratio totals 100%', detail: `${partners.length} partner(s). Same ratio applied to both years; edit for a mid-year change.` }
        : { lvl: 'error', title: 'Profit-sharing ratio does not total 100%', detail: `Ratios entered add up to ${tot}%.` }); }
  }

  return { res, face, notes, checks, unmapped, sub, noteNo, unit: u, fw, plLabels: PLL, appr: APPR ? apprRows : null, apprOn: APPR };
}
function rsum(arr, u) { const f = Math.pow(10, u.dec); return Math.round(arr.reduce((a, b) => a + (b || 0), 0) * f) / f; }

/* ---------- 7. Fixed assets: Companies Act and Income-tax depreciation, deferred tax working ---------- */
const DAYMS = 86400000;
const pdate = x => { const [y, m, d] = String(x).split('-').map(Number); return Date.UTC(y, (m || 1) - 1, d || 1); };
function faPeriod(fyEnd) {
  const to = pdate(fyEnd), d = new Date(to);
  const from = Date.UTC(d.getUTCFullYear() - 1, d.getUTCMonth(), d.getUTCDate() + 1);
  return { from, to, days: Math.round((to - from) / DAYMS) + 1 };
}
const clampDays = (v, P) => Math.max(0, Math.min(P.days, v));
const daysFrom = (date, P) => { const t = pdate(date); return isNaN(t) ? 0 : clampDays(Math.round((P.to - t) / DAYMS) + 1, P); };   // put to use on `date` .. year end (inclusive)
const daysTill = (date, P) => { const t = pdate(date); return isNaN(t) ? P.days : clampDays(Math.round((t - P.from) / DAYMS), P); };   // 1 Apr .. day before sale
/** WDV rate (Schedule II: rate that writes the cost down to the residual value over the useful life). */
const wdvRate = c => (+c.rateCA > 0) ? c.rateCA / 100 : 1 - Math.pow(((+c.resid > 0) ? c.resid : 5) / 100, 1 / (+c.life || 1));
/** Companies Act depreciation on an asset base for `frac` of the year. */
function caDep(c, cost, acc, frac) {
  cost = +cost || 0; acc = +acc || 0;
  const resid = cost * (+c.resid || 0) / 100;
  if (c.method === 'WDV') return Math.max(0, (cost - acc) * wdvRate(c) * frac);
  const annual = (cost - resid) / (+c.life || 1);
  return Math.max(0, Math.min(annual * frac, cost - resid - acc));                 // never below residual value
}
/** Income-tax Act, 1961 - blocks of assets and depreciation rates (Appendix I to the Income-tax Rules, as amended). */
const IT_BLOCKS = [
  ['BLDG_RES', 'Buildings – residential (other than hotels / boarding houses)', 5], ['BLDG', 'Buildings – other than residential', 10],
  ['BLDG_TEMP', 'Purely temporary erections (wooden structures)', 40], ['FURN', 'Furniture and fittings (incl. electrical fittings)', 10],
  ['PM', 'Plant and machinery – general', 15], ['COMP', 'Computers including computer software', 40],
  ['CAR', 'Motor cars (other than those used on hire)', 15], ['COMM', 'Motor buses, lorries and taxis used on hire', 30],
  ['INTANG', 'Intangible assets (know-how, patents, copyrights, trademarks, licences, franchises)', 25],
  ['PM_ENERGY', 'Plant and machinery – energy saving / renewable energy devices', 40], ['PM_POLL', 'Plant and machinery – pollution control equipment', 40],
  ['SHIP', 'Ships (other than those ordinarily operated on inland waters)', 20],
].map(([key, name, rate]) => ({ key, name, rate }));
const IT_BLOCK = Object.fromEntries(IT_BLOCKS.map(b => [b.key, b]));
/** Typical Schedule II life and suggested Income-tax block from the asset name (all editable in the tool). */
function faDefaults(name, intangible) {
  const n = String(name || '').toLowerCase(), r = (life, block, resid) => ({ life, block, itRate: IT_BLOCK[block].rate, resid });
  if (/goodwill|patent|trade ?mark|copyright|know.?how|franchise|licen[cs]e fee/.test(n)) return r(10, 'INTANG', 0);
  if (/software|website|app\b/.test(n)) return r(5, 'COMP', 0);
  if (intangible) return r(5, 'INTANG', 0);
  if (/building|premises|factory|flat|shed|godown/.test(n)) return r(60, 'BLDG', 5);
  if (/computer|laptop|desktop|server|printer|tablet|mobile|ipad/.test(n)) return r(/server/.test(n) ? 6 : 3, 'COMP', 5);
  if (/motor|car\b|vehicle|scooter|bike|truck|tempo/.test(n)) return r(8, 'CAR', 5);
  if (/furniture|fixture|fitting|electrical|installation|air.?condition|\bac\b/.test(n)) return r(10, 'FURN', 5);
  return r(15, 'PM', 5);                                                              // plant and machinery / equipment
}
const itBlockOf = c => (c.block && IT_BLOCK[c.block]) ? c.block : 'own:' + c.id;      // no block chosen = the class is its own block (not pooled)
/** Companies Act schedule laid out block by block: heading per block, its classes, and a block total when it holds more than one class */
function caLayout(F) {
  const out = [];
  (F.caGroups || []).forEach(g => {
    if (!g.real) { g.classes.forEach(k => out.push({ type: 'cls', k, indent: false })); return; }
    out.push({ type: 'head', name: g.name });
    g.classes.forEach(k => out.push({ type: 'cls', k, indent: true }));
    if (g.classes.length > 1) out.push({ type: 'sub', name: 'Total – ' + g.name, tot: g.tot, count: g.classes.length });
  });
  return out;
}
/** fa = { classes:[{id,name,method,life,resid,rateCA,itRate,grossOpen,accOpen,itOpen}], adds:[{cls,date,amount}],
           disp:[{cls,date,cost,accOpen,sale}], other:[{desc,cy,py}], rate }  -  Dr / amounts are plain positives. */
function computeFA(fa, fyEnd) {
  const P = faPeriod(fyEnd), sum = (a, f) => a.reduce((t, x) => t + (+f(x) || 0), 0), out = [];
  for (const c of (fa.classes || [])) {
    const adds = (fa.adds || []).filter(a => a.cls === c.id), disps = (fa.disp || []).filter(d => d.cls === c.id);
    const gO = +c.grossOpen || 0, aO = +c.accOpen || 0, dCost = sum(disps, d => d.cost), dAcc = sum(disps, d => d.accOpen);
    const addRows = adds.map(a => { const days = daysFrom(a.date, P); return Object.assign({}, a, { days, dep: caDep(c, a.amount, 0, days / P.days) }); });
    const dispRows = disps.map(d => { const days = daysTill(d.date, P), dep = caDep(c, d.cost, d.accOpen, days / P.days);
      return Object.assign({}, d, { days, dep, profit: (+d.sale || 0) - ((+d.cost || 0) - (+d.accOpen || 0) - dep) }); });
    const gAdd = sum(adds, a => a.amount), depCont = caDep(c, gO - dCost, aO - dAcc, 1), depAdd = sum(addRows, x => x.dep), depDisp = sum(dispRows, x => x.dep);
    const dep = depCont + depAdd + depDisp, aDisp = dAcc + depDisp, gC = gO + gAdd - dCost, aC = aO + dep - aDisp;
    out.push({ id: c.id, name: c.name, method: c.method, life: c.life, resid: c.resid, wdvRate: c.method === 'WDV' ? wdvRate(c) : null, ca: {
      gO, gAdd, gDisp: dCost, gC, aO, dep, depCont, depAdd, depDisp, aDisp, aC, nbC: gC - aC, nbO: gO - aO, profit: sum(dispRows, x => x.profit) }, addRows, dispRows });
  }
  // Income-tax Act: depreciation is allowed on the WDV of a BLOCK of assets, so classes in the same block are pooled
  const byBlock = new Map(), slot = key => { if (!byBlock.has(key)) byBlock.set(key, { classes: [], bookOpen: 0, bookClose: 0, addRows: [], dispRows: [], first: null }); return byBlock.get(key); };
  const blockOfRow = (row, c) => (row.block && IT_BLOCK[row.block]) ? row.block : itBlockOf(c);          // an entry may be put in another block than its asset class
  (fa.classes || []).forEach((c, i) => {
    const k = out[i], key0 = itBlockOf(c), g = slot(key0);
    if (!g.first) g.first = c;
    g.classes.push(k.name); g.bookOpen += k.ca.nbO; g.bookClose += k.ca.nbC;
    for (const r of k.addRows) { const kk = blockOfRow(r, c), gg = slot(kk); if (!gg.first) gg.first = c; gg.addRows.push(r); if (kk !== key0) { g.bookClose -= +r.amount || 0; gg.bookClose += +r.amount || 0; if (!gg.classes.includes(k.name)) gg.classes.push(k.name); } }
    for (const r of k.dispRows) { const kk = blockOfRow(r, c), gg = slot(kk); if (!gg.first) gg.first = c; gg.dispRows.push(r); if (kk !== key0 && !gg.classes.includes(k.name)) gg.classes.push(k.name); }
  });
  const blocks = [];
  for (const [key, g] of byBlock) {
    const bi = (fa.blockIn || {})[key] || {}, info = IT_BLOCK[key], has = v => v !== '' && v != null && !isNaN(+v);
    const rate = has(bi.rate) ? +bi.rate : (info ? info.rate : (+(g.first && g.first.itRate) || 0)), r = rate / 100;
    const open = has(bi.open) ? +bi.open : g.bookOpen, addRows = g.addRows, dispRows = g.dispRows;
    const sale = sum(dispRows, d => d.sale);
    const addF = sum(addRows.filter(x => x.days >= 180), x => x.amount), addH = sum(addRows.filter(x => x.days < 180), x => x.amount);
    const pool = open + addF + addH - sale, base = open + addF - sale;
    let depF = 0, depH = 0, stcg = 0;
    if (pool < 0) stcg = -pool;                                               // block ceases: short-term capital gain u/s 50
    else if (base >= 0) { depF = r * base; depH = r / 2 * addH; }
    else depH = r / 2 * Math.max(addH + base, 0);                             // sale exceeds opening + full-rate additions: eats into the <180-day pool
    const calc = depF + depH, ov = has(bi.ov) ? +bi.ov : null, extra = +bi.addDep || 0;
    const dep = pool < 0 ? 0 : (ov != null ? ov : calc) + extra;              // override replaces the calculated normal depreciation; additional depreciation is added
    blocks.push({ key, name: info ? info.name : g.classes.join(', '), pooled: g.classes.length > 1, classes: g.classes, bookOpen: g.bookOpen, open, openIsBook: !has(bi.open), bookClose: g.bookClose,
      rate, addF, addH, sale, depF, depH, calc, extra, ov, dep, close: Math.max(pool - dep, 0), stcg, nAdds: addRows.length });
  }
  const T = (f) => sum(out, x => f(x));
  const tot = { gO: T(x => x.ca.gO), gAdd: T(x => x.ca.gAdd), gDisp: T(x => x.ca.gDisp), gC: T(x => x.ca.gC), aO: T(x => x.ca.aO), dep: T(x => x.ca.dep),
    aDisp: T(x => x.ca.aDisp), aC: T(x => x.ca.aC), nbC: T(x => x.ca.nbC), nbO: T(x => x.ca.nbO), profit: T(x => x.ca.profit),
    itOpen: sum(blocks, b => b.open), itAddF: sum(blocks, b => b.addF), itAddH: sum(blocks, b => b.addH), itSale: sum(blocks, b => b.sale), itDep: sum(blocks, b => b.dep), itClose: sum(blocks, b => b.close), stcg: sum(blocks, b => b.stcg) };
  const CAK = ['gO', 'gAdd', 'gDisp', 'gC', 'aO', 'dep', 'aDisp', 'aC', 'nbC', 'nbO'];
  const gmap = new Map();   // Companies Act schedule: classes grouped by the block of the class itself
  (fa.classes || []).forEach((c, i) => { const key = itBlockOf(c); if (!gmap.has(key)) gmap.set(key, []); gmap.get(key).push(out[i]); });
  const caGroups = [...gmap].map(([key, ks]) => { const t = {}; CAK.forEach(f => { t[f] = sum(ks, k => k.ca[f]); });
    return { key, name: IT_BLOCK[key] ? IT_BLOCK[key].name : ks[0].name, real: !!IT_BLOCK[key], classes: ks, tot: t }; });
  return { P, classes: out, blocks, caGroups, tot };
}
/** Deferred tax (AS 22): timing differences x tax rate. ctx = balances in the books {cyDtl, pyDtl, cyDta, pyDta} (credit-positive DTL, debit-positive DTA). */
function computeDT(fa, F, ctx) {
  const rate = (+fa.rate || 0) / 100, oth = fa.other || [], sum = (a, f) => a.reduce((t, x) => t + (+f(x) || 0), 0);
  const depClose = sum(F.classes, c => c.ca.nbC) - sum(F.blocks, b => b.close), depOpen = sum(F.classes, c => c.ca.nbO) - sum(F.blocks, b => b.open);
  const othClose = sum(oth, o => o.cy), othOpen = sum(oth, o => o.py);
  const close = (depClose + othClose) * rate, open = (depOpen + othOpen) * rate;      // + = net DTL, - = net DTA
  const booksOpen = (ctx.pyDtl || 0) - (ctx.pyDta || 0), booksClose = (ctx.cyDtl || 0) - (ctx.cyDta || 0);
  return { rate, depClose, depOpen, othClose, othOpen, close, open, booksOpen, booksClose, adj: close - booksClose, charge: close - booksOpen };
}

/* ---------- 8. Schedule III (Division I) financial ratios ---------- */
/** res = compute().res, sub = compute().sub, x = { prinCy, prinPy } (principal repayments of borrowings, for DSCR). Averages use the opening (= previous-year closing) balance;
    previous-year ratios use the closing balance only because the year before is not in the data. */
function computeRatios(res, sub, x) {
  x = x || {};
  const sv = (c, p) => (sub[c] ? sub[c][p] : 0), g = (H, ids) => ids.reduce((a, k) => a + (H[k] || 0), 0);
  const CA = H => g(H, ['CINV', 'INV', 'TR', 'CCE', 'STLA', 'OCA']), CL = H => g(H, ['STB', 'TP', 'OCL', 'SP']);
  const EQ = H => H.SC + H.RS + H.SW, DEBT = H => H.LTB + H.STB;
  const div = (a, b) => (b && isFinite(a / b)) ? a / b : null;
  const per = p => {
    const H = res[p].H, pl = res[p].pl, O = p === 'cy' ? res.py.H : H;            // opening balances
    const avg = id => (H[id] + O[id]) / 2, avgFn = f => (f(H) + f(O)) / 2;
    const fc = H.FC, pat = pl.pat, cogs = H.COMC + H.PSIT + H.CHG, purchases = sv('PUR_RM', p) + sv('PUR_SIT', p);
    const inv = H.CINV + H.NCI, invO = O.CINV + O.NCI, invInc = sv('OI_DIV', p) + sv('OI_GAIN', p), prin = +(p === 'cy' ? x.prinCy : x.prinPy) || 0;
    return {
      cr: [CA(H), CL(H)], de: [DEBT(H), EQ(H)], dscr: [pat + H.DEP + fc, fc + prin], roe: [pat, avgFn(EQ)],
      it: [cogs, avg('INV')], trt: [H.REV, avg('TR')], tpt: [purchases, avg('TP')], nct: [H.REV, CA(H) - CL(H)],
      npr: [pat, H.REV], roce: [pl.pbt + fc, EQ(H) + DEBT(H) + H.DTL], roi: [invInc, (inv + invO) / 2] };
  };
  const C = per('cy'), P = per('py');
  const def = [
    ['cr', 'Current ratio', 'Current assets', 'Current liabilities', 'x'],
    ['de', 'Debt-equity ratio', 'Total debt (long and short-term borrowings)', "Shareholders' equity", 'x'],
    ['dscr', 'Debt service coverage ratio', 'Earnings available for debt service (profit after tax + depreciation + finance costs)', 'Debt service (finance costs + principal repayments)', 'x'],
    ['roe', 'Return on equity ratio', 'Net profit after tax', "Average shareholders' equity", '%'],
    ['it', 'Inventory turnover ratio', 'Cost of goods sold', 'Average inventory', 'x'],
    ['trt', 'Trade receivables turnover ratio', 'Revenue from operations', 'Average trade receivables', 'x'],
    ['tpt', 'Trade payables turnover ratio', 'Purchases of goods and services', 'Average trade payables', 'x'],
    ['nct', 'Net capital turnover ratio', 'Revenue from operations', 'Working capital (current assets − current liabilities)', 'x'],
    ['npr', 'Net profit ratio', 'Net profit after tax', 'Revenue from operations', '%'],
    ['roce', 'Return on capital employed', 'Earnings before interest and tax', 'Capital employed (equity + debt + deferred tax liability)', '%'],
    ['roi', 'Return on investment', 'Income from investments (dividend, gains)', 'Average investments', '%']];
  return def.map(([k, name, nl, dl, unit], i) => {
    const f = v => { const q = div(v[0], v[1]); return q == null ? null : (unit === '%' ? q * 100 : q); };
    const cy = f(C[k]), py = f(P[k]);
    return { no: i + 1, key: k, name, numLabel: nl, denLabel: dl, unit, cy, py, num: C[k][0], den: C[k][1],
      variance: (cy != null && py != null && Math.abs(py) > 1e-9) ? (cy - py) / Math.abs(py) * 100 : null };
  });
}

/* ---------- 9. Cash flow statement (AS 3, indirect method) ---------- */
/** Built from the two balance sheets and the P&L. Every Balance Sheet head is allocated to exactly one section, so the statement
    reconciles to the movement in cash and cash equivalents (check = 0). Needs the previous-year balances (movements). */
function computeCashFlow(res, sub, opt) {
  opt = opt || {};
  const cur = opt.cur || 'cy', prev = opt.prev || 'py', ex = opt.excludeDeposits ? 1 : 0;   // ex = 1: deposits with maturity over 3 months are NOT cash equivalents          // current year vs previous year, or previous year vs the start of the previous year
  const H = res[cur].H, G = res[prev].H, pl = res[cur].pl;
  const sv = (c, p) => (sub[c] ? sub[c][p] : 0), dl = c => sv(c, cur) - sv(c, prev), d = id => H[id] - G[id];
  const taxLed = p => ((sub.STLA_GOVT && sub.STLA_GOVT.ledgers) || []).filter(l => /advance tax|self.?assess|\btds\b|\btcs\b|income.?tax|tax refund/i.test(l.name)).reduce((a, l) => a + l[p], 0);
  const dTaxA = taxLed(cur) - taxLed(prev), tax = pl.pbt - pl.pat, rows = [];
  const grp = label => rows.push({ key: 'g' + rows.length, label, t: 'group' });
  const lab = label => rows.push({ key: 'l' + rows.length, label, t: 'sub' });
  const ln = (key, label, v, t) => { rows.push({ key, label, v, t: t || 'line' }); return v; };
  const sum = (...a) => a.reduce((x, y) => x + y, 0);
  grp('A. Cash flow from operating activities');
  const pbt = ln('pbt', 'Net profit before tax', pl.pbt);
  lab('Adjustments for:');
  const adj = sum(ln('dep', 'Depreciation and amortisation', H.DEP), ln('fc', 'Finance costs', H.FC), ln('int', 'Interest income', -sv('OI_INT', cur)),
    ln('div', 'Dividend income', -sv('OI_DIV', cur)), ln('gain', '(Profit) / loss on sale of investments / assets', -sv('OI_GAIN', cur)));
  const opb = ln('opb', 'Operating profit before working capital changes', pbt + adj, 'subtotal');
  lab('Adjustments for changes in working capital:');
  const wc = sum(ln('winv', '(Increase) / decrease in inventories', -d('INV')), ln('wtr', '(Increase) / decrease in trade receivables', -d('TR')),
    ln('wstla', '(Increase) / decrease in short-term loans and advances', -(d('STLA') - dTaxA)), ln('wltla', '(Increase) / decrease in long-term loans and advances', -(d('LTLA') - dl('LTLA_CAP'))),
    ln('woca', '(Increase) / decrease in other current assets', -(d('OCA') - dl('OCA_INT'))), ln('wonca', '(Increase) / decrease in other non-current assets', -(d('ONCA') - dl('ONCA_FD'))),
    ln('wtp', 'Increase / (decrease) in trade payables', d('TP')), ln('wocl', 'Increase / (decrease) in other current liabilities', d('OCL') - dl('OCL_CAP') - dl('OCL_INT')),
    ln('wprov', 'Increase / (decrease) in provisions', d('SP') - dl('SP_TAX') + d('LTP')), ln('woltl', 'Increase / (decrease) in other long-term liabilities', d('OLTL')));
  const cgo = ln('cgo', 'Cash generated from operations', opb + wc, 'subtotal');
  const taxp = ln('taxp', 'Income taxes paid (net of refunds)', -tax + dl('SP_TAX') + d('DTL') - d('DTA') - dTaxA);
  const A = ln('A', 'Net cash from / (used in) operating activities (A)', cgo + taxp, 'total');
  grp('B. Cash flow from investing activities');
  const B = ln('B', 'Net cash from / (used in) investing activities (B)', sum(
    ln('capex', 'Purchase of property, plant and equipment, intangibles and capital work-in-progress (net)', -(d('PPE') + d('INTANG') + d('CWIP') + d('IAUD') + H.DEP)),
    ln('capadv', 'Capital advances and creditors for capital goods (net)', -dl('LTLA_CAP') + dl('OCL_CAP')),
    ln('inv', 'Purchase of investments (net)', -(d('NCI') + d('CINV'))), ln('gainr', 'Profit on sale of investments / assets realised', sv('OI_GAIN', cur)),
    ln('dep2', ex ? 'Bank deposits with original maturity over three months (net)' : 'Bank deposits with maturity over twelve months (net)', -(ex * dl('CCE_OBB') + dl('ONCA_FD'))),
    ln('intr', 'Interest received', sv('OI_INT', cur) - dl('OCA_INT')), ln('divr', 'Dividend received', sv('OI_DIV', cur))), 'total');
  grp('C. Cash flow from financing activities');
  const C = ln('C', 'Net cash from / (used in) financing activities (C)', sum(
    ln('sc', 'Proceeds from issue of share capital and securities premium', d('SC') + dl('RS_SEC') + d('SW') + d('SAM')),
    ln('bor', 'Proceeds from / (repayment of) borrowings (net)', d('LTB') + d('STB')),
    ln('fcp', 'Finance costs paid', -H.FC + dl('OCL_INT')),
    ln('divp', 'Dividends paid and other movements in reserves', (H.RS - pl.pat) - G.RS - dl('RS_SEC'))), 'total');
  const net = ln('net', 'Net increase / (decrease) in cash and cash equivalents (A + B + C)', A + B + C, 'grand');
  const open = ln('open', 'Cash and cash equivalents at the beginning of the year', G.CCE - ex * sv('CCE_OBB', prev));
  const close = ln('close', 'Cash and cash equivalents at the end of the year', H.CCE - ex * sv('CCE_OBB', cur), 'grand');
  if (ex) {                                                       // reconcile to the Balance Sheet figure
    ln('obb', 'Add: bank deposits (maturity over three months) shown in cash and cash equivalents on the Balance Sheet', sv('CCE_OBB', cur));
    ln('bscash', 'Cash and cash equivalents as per Balance Sheet', H.CCE, 'grand');
  }
  const noPrior = prev === 'p0' ? !res.p0.hasP0 : (Math.abs(res[prev].totA) < 0.5 && Math.abs(res[prev].totL) < 0.5);
  return { rows, A, B, C, net, open, close, check: net - (close - open), bsDiff: (close + ex * sv('CCE_OBB', cur)) - H.CCE, excludeDeposits: !!ex, noPrior };
}

const api = { HEADS, HEAD, LINES, LINE, INV_CATS, UNITS, GROUPS, RULES, CONTRA_OK, groupInfo, autoMap, parseAmount, detectColumns, buildTB,
  isTallyExport, buildTallyTB, computeFA, computeDT, caLayout, faDefaults, IT_BLOCKS, IT_BLOCK, itBlockOf, computeRatios, computeCashFlow, wdvRate, linesFor, headsFor, xlate, headName, isNCE, compute, rnd, round2 };
if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.FSEngine = api;
})(typeof window !== 'undefined' ? window : globalThis);
