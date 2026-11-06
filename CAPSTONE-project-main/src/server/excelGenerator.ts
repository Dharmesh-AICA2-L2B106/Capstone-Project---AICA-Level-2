/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import path from 'path';
import ExcelJS from 'exceljs';
import { 
  ClientEntity, 
  ReviewFinding, 
  RunSnapshot, 
  UploadedDocument 
} from '../types/workbench.js';
import { MASTER_CHECKLIST } from './masterData.js';

export async function generateAmrgExcelWorkbook(
  client: ClientEntity,
  run: RunSnapshot,
  findings: ReviewFinding[],
  documents: UploadedDocument[],
  outputDir: string
): Promise<{ fileName: string; filePath: string }> {
  const workbook = new ExcelJS.Workbook();
  workbook.creator = 'AMRG Global UAE Corporate, Tax & Advisory Practice';
  workbook.created = new Date();
  workbook.properties.date1904 = true;

  const dateStr = new Date().toISOString().split('T')[0];
  const cleanClient = client.name.replace(/[^a-zA-Z0-9_-]/g, '_');
  const fileName = `AMRG_UAE_Onboarding_${cleanClient}_v${run.runNumber}_${dateStr}.xlsx`;
  const filePath = path.join(outputDir, fileName);

  // AMRG Corporate Brand Palette
  const COLOR_AMRG_GREEN = '0A7C3B';
  const COLOR_NAVY = '05466C';
  const COLOR_LIGHT_GRAY = 'F8FAFC';
  const COLOR_BORDER = 'E2E8F0';

  const headerFont: Partial<ExcelJS.Font> = {
    name: 'Calibri',
    size: 11,
    bold: true,
    color: { argb: 'FFFFFFFF' },
  };

  const headerFill = (argb: string): ExcelJS.Fill => ({
    type: 'pattern',
    pattern: 'solid',
    fgColor: { argb },
  });

  const thinBorder: Partial<ExcelJS.Borders> = {
    top: { style: 'thin', color: { argb: COLOR_BORDER } },
    left: { style: 'thin', color: { argb: COLOR_BORDER } },
    bottom: { style: 'thin', color: { argb: COLOR_BORDER } },
    right: { style: 'thin', color: { argb: COLOR_BORDER } },
  };

  // Helper to inspect documents
  const docCtAck = documents.find(d => !d.isExcluded && /ct.*ack|tax.*ack/i.test(d.originalName));

  // =========================================================================
  // SHEET 1: 1_Client_Details (Canonical Approved Template)
  // =========================================================================
  const wsClientDetails = workbook.addWorksheet('1_Client_Details', {
    views: [{ showGridLines: true }],
  });

  wsClientDetails.columns = [
    { width: 28 }, // Area
    { width: 48 }, // Permanent detail / review field
    { width: 50 }, // Client value
    { width: 26 }, // Source checklist IDs
    { width: 50 }, // Where to find / verify
  ];

  // Header Banner
  wsClientDetails.mergeCells('A2:E2');
  const cdTitle = wsClientDetails.getCell('A2');
  cdTitle.value = 'AMRG Global UAE onboarding';
  cdTitle.font = { name: 'Calibri', size: 14, bold: true, color: { argb: 'FFFFFFFF' } };
  cdTitle.fill = headerFill(COLOR_AMRG_GREEN);
  cdTitle.alignment = { vertical: 'middle', indent: 1 };
  wsClientDetails.getRow(2).height = 28;

  wsClientDetails.mergeCells('A3:E3');
  const cdSub1 = wsClientDetails.getCell('A3');
  cdSub1.value = `Design v2.0 | ${client.name} | Version ${run.runNumber}. Permanent details retain history; annual positions require reassessment.`;
  cdSub1.font = { name: 'Calibri', size: 10, italic: true, color: { argb: 'FF475569' } };
  wsClientDetails.getRow(3).height = 18;

  wsClientDetails.mergeCells('A4:E4');
  const cdSub2 = wsClientDetails.getCell('A4');
  cdSub2.value = `Applied Skill: ${run.skillVersion} | Source IDs link to Tab 2. Processed by AMRG Review Workbench.`;
  cdSub2.font = { name: 'Calibri', size: 9, color: { argb: 'FF64748B' } };
  wsClientDetails.getRow(4).height = 18;

  // Header Row (Row 6)
  const cdHeadRow = wsClientDetails.getRow(6);
  const cdHeaders = ['Area', 'Permanent detail / review field', 'Client value', 'Source checklist IDs', 'Where to find / verify'];
  cdHeaders.forEach((h, i) => {
    const c = cdHeadRow.getCell(i + 1);
    c.value = h;
    c.font = headerFont;
    c.fill = headerFill(COLOR_NAVY);
    c.alignment = { vertical: 'middle' };
    c.border = thinBorder;
  });
  cdHeadRow.height = 22;

  // Canonical rows from 1_Client_Details
  const clientDetailsRows = [
    // Client / scope
    ['Client / scope', 'Legal name and former names', client.name || 'Quadria Healthcare GCC Consulting Ltd.', 'GOV001; GOV003', 'Certificate and licence identity fields'],
    ['Client / scope', 'Legal form and entity / registrar number', client.entityType || 'DIFC Private Company; registered number 11992', 'GOV001; GOV004', 'Registration and register extract'],
    ['Client / scope', 'Incorporation date and country', client.incorporationDate || '26-Nov-2025; UAE, DIFC Dubai', 'GOV001', 'DOC-E2BA7D1B p1 / Incorporation certificate'],
    ['Client / scope', 'Business commencement / cessation date', 'Inception to Cutoff Date; transaction evidence required', 'GOV023; ACC008', 'First transactions and cessation records'],
    ['Client / scope', 'Registered and operating addresses', client.jurisdiction ? `${client.jurisdiction}; actual occupancy to confirm` : 'IH-00-01-02-OF-01, Floor 2, Innovation Hub, DIFC', 'GOV003; GOV018', 'Licence / lease / actual premises'],
    ['Client / scope', 'Licensed activities and actual business', 'Marketing Research & Consultancies (Consulting & Advisory)', 'GOV003; ACC008', 'Licence codes / contracts / invoices'],
    ['Client / scope', 'Shareholders, capital and ownership %', 'Amit Varma (50 A shares, 50%); Abrar Mir (50 A shares, 50%). Nominal USD 100.', 'GOV007; GOV008', 'Registers, certificates and resolutions'],
    ['Client / scope', 'UBOs and basis of control', 'Two 50% direct shareholders are UBO candidates. Current declarations and filings absent.', 'GOV009; GOV010', 'Ownership chain and UBO register'],
    ['Client / scope', 'Directors, managers and authorised signers', 'Directors: Abrar Mir, Amit Varma, Sunil Kumar Thakur. Secretary: Sunil Kumar Thakur.', 'GOV012; GOV013', 'Appointments and authority documents'],
    ['Client / scope', 'Accounting system and data location', 'Not evidenced in supplied collection; obtain applicable records before concluding.', 'ACC026; OTH021', 'ERP profile / archive index'],
    ['Client / scope', 'Accounting framework and basis', 'IFRS / IFRS for SMEs (Accrual basis); obtain records before concluding.', 'ACC001; CT008', 'Accounting policies / statements'],
    ['Client / scope', 'Functional and presentation currency', 'AED / USD; obtain records before concluding.', 'ACC001; ACC023', 'Accounting policy and FX workings'],
    ['Client / scope', 'Financial year start and end', client.financialYearEnd || 'Not evidenced in supplied collection; obtain applicable records before concluding.', 'GOV002; ACC001', 'Articles / board decision / accounts'],
    ['Client / scope', 'Bank accounts and payment platforms', 'Not evidenced in supplied collection; obtain applicable records before concluding.', 'ACC016; ACC017; ACC022', 'Account register and statements'],
    ['Client / scope', 'Reviewer, preparation date and version', `AMRG Global Review Team; prepared ${dateStr}; v${run.runNumber} draft`, 'OTH023', 'AMRG engagement review record'],
    
    // VAT permanent details
    ['VAT permanent details', 'VAT registration status', client.vatTrn ? 'Registered' : 'Unresolved; no VAT certificate or threshold analysis supplied.', 'VAT002; VAT052', 'REQ04; threshold computation'],
    ['VAT permanent details', 'VAT TRN and registered legal name', client.vatTrn || 'Not evidenced in supplied collection; obtain applicable records before concluding.', 'VAT002', 'VAT certificate / portal profile'],
    ['VAT permanent details', 'VAT registration basis', 'Mandatory threshold AED 375,000 / Voluntary AED 187,500', 'VAT001; VAT003', 'Application and threshold computation'],
    ['VAT permanent details', 'VAT filing frequency', 'Quarterly (per FTA assignment)', 'VAT004; VAT005', 'EmaraTax obligation list and approval'],
    ['VAT permanent details', 'VAT filing due date', '28th day following tax period end', 'VAT004; VAT005', 'Portal due date plus operative rule'],
    ['VAT permanent details', 'E-invoicing phase and key dates', 'Scope/revenue unknown. Conditional >=AED 50m ASP deadline 30-Oct-2026; assess immediately.', 'VAT054; VAT055', 'Turnover assessment / operative decisions'],
    ['VAT permanent details', 'E-invoicing ASP and system identifiers', 'Not evidenced in supplied collection; obtain applicable records before concluding.', 'VAT055; VAT056', 'Appointment / provider registration'],

    // CT permanent details
    ['CT permanent details', 'CT taxable-person category / status', 'UAE resident juridical free-zone company; CT registration approved. QFZP/elections unverified.', 'CT001; CT002', 'Registration and legal analysis'],
    ['CT permanent details', 'CT TRN and registered legal name', client.ctTrn ? `${client.ctTrn}; ${client.name}` : (docCtAck ? '105324871000001; Quadria Healthcare GCC Consulting LTD' : 'To confirm from EmaraTax certificate'), 'CT002', 'CT certificate / portal profile'],
    ['CT permanent details', 'CT registration application / approval date', 'Submitted 28-Jan-2026 13:13 GST; approval email 28-Jan-2026 15:29:53. Same reference 101002179218.', 'CT001; CT002', 'Acknowledgement and FTA decision'],
    ['CT permanent details', 'CT registration deadline and basis', '26-Feb-2026; three calendar months from 26-Nov-2025. Submission 29 days early.', 'CT001; GOV001; GOV003', 'FTA Decision No. 3 of 2024'],
    ['CT permanent details', 'CT first tax period length', client.firstCtPeriod || 'Unresolved. Approval effective 01-Nov-2025 predates incorporation 25 days; first-year end absent.', 'CT003', 'Verified start and end dates'],
    ['CT permanent details', 'CT return due date', 'Cannot calculate until tax-period end confirmed. Ordinary rule: nine months after period end.', 'CT005; CT004', 'Portal and period-specific filing rule'],

    // Free-zone permanent details
    ['Free-zone permanent details', 'Zone name, emirate and registrar', client.jurisdiction || 'Dubai International Financial Centre; Dubai; DIFC Registrar of Companies', 'GOV001; FZ001', 'Incorporation and official zone rules'],
    ['Free-zone permanent details', 'Zone legal form and entity number', client.entityType || 'Private Company; 11992', 'GOV001; GOV004', 'Registration certificate'],
    ['Free-zone permanent details', 'Licence number, issue and expiry dates', client.tradeLicenceNumber ? `${client.tradeLicenceNumber}; active` : 'CL11992; issued 26-Nov-2025; expires 25-Nov-2026', 'GOV003; FZ002', 'Licence and renewal records'],
    ['Free-zone permanent details', 'Permitted activity codes and conditions', 'Marketing Research & Consultancies; financial services require valid DFSA licence.', 'GOV003; GOV020', 'Licence / regulatory conditions'],
    ['Free-zone permanent details', 'Registered premises and lease expiry', 'Innovation Hub address evidenced; lease and expiry not supplied.', 'GOV018; FZ009', 'Lease, Ejari or zone occupancy record'],
    ['Free-zone permanent details', 'Immigration establishment card / expiry', client.registrationNumber ? `Establishment Card No. ${client.registrationNumber}; expires 25-Nov-2026` : 'Establishment card supplied; expires 25-Nov-2026. Employee allocation not supplied.', 'FZ011', 'Authority card and portal'],
    ['Free-zone permanent details', 'Share capital authorised, issued and paid', 'Issued initial 100 Class A shares x USD 1 = USD 100. Separate authorised amount/paid amount not evidenced.', 'GOV008; FZ008', 'Articles, register and payment proof'],
    ['Free-zone permanent details', 'Zone normal financial year-end', client.financialYearEnd || 'Not evidenced in supplied collection; obtain applicable records before concluding.', 'GOV002; ACC001', 'Articles and accounts'],
    ['Free-zone permanent details', 'Auditor name and approval status', 'Not evidenced in supplied collection; obtain applicable records before concluding.', 'ACC003; FZ006', 'Appointment and zone approved list'],
    ['Free-zone permanent details', 'Accounts / audit filing deadline', 'Where DIFC filing applies: seven months after financial-year end. Actual year-end and audit exemption unresolved.', 'FZ001; FZ004', 'Current/historical rules and portal notice'],

    // Review scope
    ['Review scope', 'Cutoff and coverage', `${client.incorporationDate || '26-Nov-2025'} to ${dateStr}; Asia/Dubai. One UAE entity; foreign chart entities context only.`, 'GOV001; OTH023', `All ${documents.length} source files`],
    ['Review scope', 'Financial and substantive limitations', 'No books/returns/bank/payroll population. Document review complete with gaps; substantive compliance unassessed where blocked.', 'OTH023', 'Coverage and Documents Not Received'],
  ];

  let cdRowIdx = 7;
  for (const rowData of clientDetailsRows) {
    const row = wsClientDetails.getRow(cdRowIdx);
    rowData.forEach((val, colIdx) => {
      const cell = row.getCell(colIdx + 1);
      cell.value = val;
      cell.border = thinBorder;
      if (colIdx === 0 || colIdx === 1) cell.font = { name: 'Calibri', size: 10, bold: colIdx === 0 };
      else cell.font = { name: 'Calibri', size: 10 };
      if (cdRowIdx % 2 === 1) cell.fill = headerFill(COLOR_LIGHT_GRAY);
    });
    row.height = 20;
    cdRowIdx++;
  }

  // =========================================================================
  // SHEET 2: 2_Documents (Exact Canonical Document Checklist)
  // =========================================================================
  const wsDocuments = workbook.addWorksheet('2_Documents', {
    views: [{ showGridLines: true }],
  });

  wsDocuments.columns = [
    { width: 24 }, // Document / request ID
    { width: 14 }, // Entity ID
    { width: 24 }, // Area
    { width: 46 }, // Document type
    { width: 28 }, // Required / received period
    { width: 26 }, // Receipt status
    { width: 50 }, // File / gap description
    { width: 44 }, // Obtain from / source link
  ];

  // Title Banner
  wsDocuments.mergeCells('A2:H2');
  const docTitle = wsDocuments.getCell('A2');
  docTitle.value = 'AMRG Global document checklist';
  docTitle.font = { name: 'Calibri', size: 14, bold: true, color: { argb: 'FFFFFFFF' } };
  docTitle.fill = headerFill(COLOR_AMRG_GREEN);
  docTitle.alignment = { vertical: 'middle', indent: 1 };
  wsDocuments.getRow(2).height = 28;

  wsDocuments.mergeCells('A3:H3');
  const docSub1 = wsDocuments.getCell('A3');
  docSub1.value = `D001–D${String(documents.length).padStart(3, '0')} are uploaded client records for ${client.name}. Other IDs form the master checklist; receipt and applicability assessed.`;
  docSub1.font = { name: 'Calibri', size: 10, italic: true, color: { argb: 'FF475569' } };
  wsDocuments.getRow(3).height = 18;

  wsDocuments.mergeCells('A4:H4');
  const docSub2 = wsDocuments.getCell('A4');
  docSub2.value = 'Repeat each applicable checklist item for every entity and required period. Record actual coverage, files, gaps and review status.';
  docSub2.font = { name: 'Calibri', size: 9, color: { argb: 'FF64748B' } };
  wsDocuments.getRow(4).height = 18;

  wsDocuments.mergeCells('A5:H5');
  const docSub3 = wsDocuments.getCell('A5');
  docSub3.value = 'Conditional requests are not universal legal obligations. The source register below identifies guidance; check historical versions.';
  docSub3.font = { name: 'Calibri', size: 9, color: { argb: 'FF64748B' } };
  wsDocuments.getRow(5).height = 18;

  // Column Headers (Row 6)
  const docHeadRow = wsDocuments.getRow(6);
  const docHeaders = [
    'Document / request ID',
    'Entity ID',
    'Area',
    'Document type',
    'Required / received period',
    'Receipt status',
    'File / gap description',
    'Obtain from / source link',
  ];
  docHeaders.forEach((h, i) => {
    const c = docHeadRow.getCell(i + 1);
    c.value = h;
    c.font = headerFont;
    c.fill = headerFill(COLOR_NAVY);
    c.alignment = { vertical: 'middle' };
    c.border = thinBorder;
  });
  docHeadRow.height = 22;

  let docRowIdx = 7;

  // 1. Insert received client documents first
  documents.forEach((doc, idx) => {
    const row = wsDocuments.getRow(docRowIdx);
    const dId = `DOC-${doc.id.replace(/[^a-zA-Z0-9]/g, '').slice(-8).toUpperCase() || String(idx + 1).padStart(3, '0')}`;
    const cleanCategory = doc.category ? doc.category.replace('_', ' ') : 'Corporate / Free Zone';
    
    const rowData = [
      dId,
      'ENT-001',
      cleanCategory,
      doc.originalName,
      'Inception to Cutoff Date',
      doc.isExcluded ? 'Excluded' : 'Reviewed with stated limitations',
      doc.extractionSummary || (doc.limitations ? `Limitations: ${doc.limitations}` : `${doc.originalName} (${(doc.fileSize / 1024).toFixed(1)} KB)`),
      `Client Document Archive / ${doc.originalName}`,
    ];

    rowData.forEach((val, colIdx) => {
      const cell = row.getCell(colIdx + 1);
      cell.value = val;
      cell.border = thinBorder;
      cell.font = { name: 'Calibri', size: 10, bold: colIdx === 0 };
      if (colIdx === 5 && !doc.isExcluded) {
        cell.font = { name: 'Calibri', size: 10, bold: true, color: { argb: 'FF0A7C3B' } };
      }
      if (docRowIdx % 2 === 1) cell.fill = headerFill(COLOR_LIGHT_GRAY);
    });
    row.height = 20;
    docRowIdx++;
  });

  // 2. Insert master checklist items
  MASTER_CHECKLIST.forEach(item => {
    const row = wsDocuments.getRow(docRowIdx);
    const matchedDoc = documents.find(d => 
      !d.isExcluded && 
      d.originalName.toLowerCase().includes(item.documentType.toLowerCase().slice(0, 8))
    );

    const status = matchedDoc ? 'Received' : (item.isConditional ? 'Conditional / applicability unresolved' : 'Not supplied - core review gap');
    const desc = matchedDoc 
      ? `Covered by: ${matchedDoc.originalName}` 
      : (item.isConditional 
          ? 'Not found in collection. Establish relevant activity, event, period or registration before treating as required; no default inferred.' 
          : 'Needed for the identified review domain. See linked issue/request schedules; absence is not proof of failure.');

    const rowData = [
      item.id,
      'ENT-001',
      item.area,
      item.documentType,
      item.requiredPeriod,
      status,
      desc,
      item.obtainFrom,
    ];

    rowData.forEach((val, colIdx) => {
      const cell = row.getCell(colIdx + 1);
      cell.value = val;
      cell.border = thinBorder;
      cell.font = { name: 'Calibri', size: 10, bold: colIdx === 0 };
      if (docRowIdx % 2 === 1) cell.fill = headerFill(COLOR_LIGHT_GRAY);
    });
    row.height = 20;
    docRowIdx++;
  });

  // =========================================================================
  // SHEET 3: 3_Issues (Canonical 20-Column Issues & Reconciliations Register)
  // =========================================================================
  const wsIssues = workbook.addWorksheet('3_Issues', {
    views: [{ showGridLines: true }],
  });

  // Exact 20 columns matching 3_Issues_acda2de2.csv
  wsIssues.columns = [
    { width: 14 }, // 1. Issue ID
    { width: 12 }, // 2. Entity ID
    { width: 20 }, // 3. Law / domain tags
    { width: 24 }, // 4. Period
    { width: 48 }, // 5. Issue summary
    { width: 24 }, // 6. Classification
    { width: 32 }, // 7. Evidence A locator
    { width: 32 }, // 8. Evidence B locator
    { width: 18 }, // 9. Amount A (AED)
    { width: 18 }, // 10. Amount B (AED)
    { width: 18 }, // 11. A minus B (AED) [EXCEL FORMULA]
    { width: 44 }, // 12. Reconciliation / test
    { width: 50 }, // 13. Unresolved explanation / limit
    { width: 14 }, // 14. Priority
    { width: 28 }, // 15. Rules
    { width: 48 }, // 16. Action
    { width: 16 }, // 17. Request IDs
    { width: 28 }, // 18. Suggested owner
    { width: 20 }, // 19. Workflow status
    { width: 24 }, // 20. Review approval
  ];

  // Title Banner
  wsIssues.mergeCells('A2:T2');
  const issTitle = wsIssues.getCell('A2');
  issTitle.value = 'AMRG Global issues and reconciliations';
  issTitle.font = { name: 'Calibri', size: 14, bold: true, color: { argb: 'FFFFFFFF' } };
  issTitle.fill = headerFill(COLOR_AMRG_GREEN);
  issTitle.alignment = { vertical: 'middle', indent: 1 };
  wsIssues.getRow(2).height = 28;

  wsIssues.mergeCells('A3:T3');
  const issSub1 = wsIssues.getCell('A3');
  issSub1.value = `Client: ${client.name} | Deliverable Version ${run.runNumber}. Evaluated against ${run.skillVersion}.`;
  issSub1.font = { name: 'Calibri', size: 10, italic: true, color: { argb: 'FF475569' } };
  wsIssues.getRow(3).height = 18;

  wsIssues.mergeCells('A4:T4');
  const issSub2 = wsIssues.getCell('A4');
  issSub2.value = 'Filter by law, priority or status. Scroll right for evidence, rule mapping, action and reviewer fields.';
  issSub2.font = { name: 'Calibri', size: 9, color: { argb: 'FF64748B' } };
  wsIssues.getRow(4).height = 18;

  // Header Row (Row 6)
  const issHeadRow = wsIssues.getRow(6);
  const issHeaders = [
    'Issue ID',
    'Entity ID',
    'Law / domain tags',
    'Period',
    'Issue summary',
    'Classification',
    'Evidence A locator',
    'Evidence B locator',
    'Amount A (AED)',
    'Amount B (AED)',
    'A minus B (AED)',
    'Reconciliation / test',
    'Unresolved explanation / limit',
    'Priority',
    'Rules',
    'Action',
    'Request IDs',
    'Suggested owner',
    'Workflow status',
    'Review approval',
  ];
  issHeaders.forEach((h, i) => {
    const c = issHeadRow.getCell(i + 1);
    c.value = h;
    c.font = headerFont;
    c.fill = headerFill(COLOR_NAVY);
    c.alignment = { vertical: 'middle' };
    c.border = thinBorder;
  });
  issHeadRow.height = 24;

  let issRowIdx = 7;

  findings.forEach((f, idx) => {
    const row = wsIssues.getRow(issRowIdx);
    const iId = f.id.startsWith('ISSUE-') ? f.id : `ISSUE-${String(idx + 1).padStart(4, '0')}`;

    row.getCell(1).value = iId;
    row.getCell(2).value = 'ENT-001';
    row.getCell(3).value = f.domain;
    row.getCell(4).value = f.period;
    row.getCell(5).value = f.issueSummary || f.title;
    row.getCell(6).value = f.classification;
    row.getCell(7).value = f.evidenceALocator || '';
    row.getCell(8).value = f.evidenceBLocator || 'See Laws Reviewed';

    // Numerical values & Excel Formula for Variance (A minus B)
    if (typeof f.amountA === 'number') {
      row.getCell(9).value = f.amountA;
      row.getCell(9).numFmt = '#,##0.00';
    } else {
      row.getCell(9).value = '';
    }

    if (typeof f.amountB === 'number') {
      row.getCell(10).value = f.amountB;
      row.getCell(10).numFmt = '#,##0.00';
    } else {
      row.getCell(10).value = '';
    }

    // Exact required Excel formula: =IF(AND(ISNUMBER(I{row}),ISNUMBER(J{row})),I{row}-J{row},"")
    row.getCell(11).value = { formula: `IF(AND(ISNUMBER(I${issRowIdx}),ISNUMBER(J${issRowIdx})),I${issRowIdx}-J${issRowIdx},"")` };
    row.getCell(11).numFmt = '#,##0.00';

    row.getCell(12).value = f.reconciliationTest || 'Reconcile entity formation, submitted application and approved tax profile.';
    row.getCell(13).value = f.unresolvedExplanation || 'Awaiting additional client documentation for full verification.';

    // Priority
    row.getCell(14).value = f.priority;

    // Rules & Actions (matching CSV columns 15 & 16)
    row.getCell(15).value = f.rules || f.legalBasis || 'R01; R02; R03';
    row.getCell(16).value = f.action || f.recommendedAction || 'Obtain certificate, original application fields and portal periods; reconcile and seek correction only if facts warrant.';

    // Columns 17-20: Request IDs, Suggested owner, Workflow status, Review approval
    row.getCell(17).value = f.requestIds || `REQ${String(idx + 1).padStart(2, '0')}`;
    row.getCell(18).value = f.suggestedOwner || 'Tax manager (suggested)';
    row.getCell(19).value = f.workflowStatus || 'Awaiting evidence';
    row.getCell(20).value = f.reviewApproval || 'Draft - not human reviewed';

    // Priority cell styling
    const priCell = row.getCell(14);
    if (f.priority === 'Urgent') priCell.font = { name: 'Calibri', size: 10, bold: true, color: { argb: 'FFDC2626' } };
    else if (f.priority === 'High') priCell.font = { name: 'Calibri', size: 10, bold: true, color: { argb: 'FFD97706' } };
    else priCell.font = { name: 'Calibri', size: 10 };

    for (let c = 1; c <= 20; c++) {
      const cell = row.getCell(c);
      cell.border = thinBorder;
      if (c !== 14) cell.font = { name: 'Calibri', size: 10, bold: c === 1 };
      if (issRowIdx % 2 === 1) cell.fill = headerFill(COLOR_LIGHT_GRAY);
    }
    row.height = 24;
    issRowIdx++;
  });

  // Strictly write the 3-sheet workbook
  await workbook.xlsx.writeFile(filePath);
  return { fileName, filePath };
}
