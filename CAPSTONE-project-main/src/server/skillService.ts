/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import fs from 'fs';
import path from 'path';
import { 
  AlignmentType, 
  Document as DocxDocument, 
  HeadingLevel, 
  Packer, 
  Paragraph, 
  Table, 
  TableCell, 
  TableRow, 
  TextRun, 
  WidthType 
} from 'docx';
import ExcelJS from 'exceljs';
import { MASTER_CHECKLIST } from './masterData.js';

export const SKILL_ID = 'amrg-uae-onboarding-checks';
export const SKILL_VERSION = 'AMRG UAE Onboarding Review Skill v2.4 (Published October 2026)';
export const SKILL_FILE_PATH = path.join(process.cwd(), 'data', 'skills', 'AMRG_UAE_Onboarding_Skill_v2.4.md');

export interface LoadedSkill {
  skillId: string;
  skillVersion: string;
  markdownContent: string;
  characterCount: number;
  lineCount: number;
  loadedAt: string;
}

/**
 * Loads the complete published onboarding review skill from the server-side source.
 * Strict failure requirement: If the skill cannot be loaded or is corrupted,
 * the run must fail immediately.
 */
export function loadPublishedOnboardingSkill(): LoadedSkill {
  if (!fs.existsSync(SKILL_FILE_PATH)) {
    throw new Error(
      'Skill load failure: Unable to read approved skill methodology from server-side source. Run aborted.'
    );
  }

  const markdownContent = fs.readFileSync(SKILL_FILE_PATH, 'utf-8');
  if (!markdownContent || markdownContent.trim().length < 500) {
    throw new Error(
      'Skill load failure: Server-side skill document is empty or corrupted. Run aborted.'
    );
  }

  return {
    skillId: SKILL_ID,
    skillVersion: SKILL_VERSION,
    markdownContent,
    characterCount: markdownContent.length,
    lineCount: markdownContent.split('\n').length,
    loadedAt: new Date().toISOString(),
  };
}

/**
 * Generates an official AMRG Global Word document (.docx) from the approved skill markdown.
 */
export async function generateSkillDocx(): Promise<Buffer> {
  const skill = loadPublishedOnboardingSkill();
  const lines = skill.markdownContent.split('\n');

  const children: (Paragraph | Table)[] = [];

  // Header Title
  children.push(
    new Paragraph({
      text: 'AMRG Global — UAE Client Onboarding Review Methodology',
      heading: HeadingLevel.TITLE,
      alignment: AlignmentType.CENTER,
      spacing: { after: 200 },
    }),
    new Paragraph({
      children: [
        new TextRun({
          text: 'Official Published Skill v2.4 (Published October 2026)',
          bold: true,
          color: '0A7C3B',
          size: 24,
        }),
      ],
      alignment: AlignmentType.CENTER,
      spacing: { after: 400 },
    })
  );

  for (let i = 0; i < lines.length; i++) {
    const rawLine = lines[i].trim();
    if (!rawLine) continue;

    if (rawLine.startsWith('# ')) {
      children.push(
        new Paragraph({
          text: rawLine.replace(/^#\s+/, ''),
          heading: HeadingLevel.HEADING_1,
          spacing: { before: 300, after: 150 },
        })
      );
    } else if (rawLine.startsWith('## ')) {
      children.push(
        new Paragraph({
          text: rawLine.replace(/^##\s+/, ''),
          heading: HeadingLevel.HEADING_2,
          spacing: { before: 240, after: 120 },
        })
      );
    } else if (rawLine.startsWith('### ')) {
      children.push(
        new Paragraph({
          text: rawLine.replace(/^###\s+/, ''),
          heading: HeadingLevel.HEADING_3,
          spacing: { before: 180, after: 80 },
        })
      );
    } else if (rawLine.startsWith('- ') || rawLine.startsWith('* ')) {
      children.push(
        new Paragraph({
          children: [
            new TextRun({ text: '•  ', bold: true, color: '0A7C3B' }),
            new TextRun({ text: rawLine.replace(/^[-*]\s+/, '').replace(/\*\*/g, '') }),
          ],
          indent: { left: 400 },
          spacing: { after: 60 },
        })
      );
    } else if (rawLine.startsWith('|') && rawLine.endsWith('|')) {
      // Simple table row handler
      const cells = rawLine
        .split('|')
        .map(c => c.trim())
        .filter((_, idx, arr) => idx > 0 && idx < arr.length - 1);
      
      // Skip separator row like |---|---|
      if (cells.some(c => c.includes('---'))) continue;

      const isHeader = i > 0 && lines[i - 1]?.includes('---');
      const tableRow = new TableRow({
        children: cells.map(
          cellText =>
            new TableCell({
              children: [
                new Paragraph({
                  children: [
                    new TextRun({
                      text: cellText.replace(/\*\*/g, ''),
                      bold: isHeader,
                      size: 20,
                    }),
                  ],
                }),
              ],
              width: { size: Math.floor(9000 / cells.length), type: WidthType.DXA },
            })
        ),
      });

      children.push(
        new Table({
          rows: [tableRow],
          width: { size: 9000, type: WidthType.DXA },
        })
      );
    } else {
      children.push(
        new Paragraph({
          children: [
            new TextRun({
              text: rawLine.replace(/\*\*/g, ''),
              size: 22,
            }),
          ],
          spacing: { after: 120 },
        })
      );
    }
  }

  const doc = new DocxDocument({
    creator: 'AMRG Global UAE Corporate, Tax & Advisory Practice',
    title: 'AMRG UAE Onboarding Checks Detailed Skill v2.4',
    description: 'Published server-side methodology and review catalog for UAE client onboarding',
    sections: [
      {
        properties: {},
        children,
      },
    ],
  });

  return await Packer.toBuffer(doc);
}

/**
 * Generates a clean, blank copy of the approved canonical AMRG Excel template.
 */
export async function generateBlankExcelTemplate(): Promise<Buffer> {
  const workbook = new ExcelJS.Workbook();
  workbook.creator = 'AMRG Global UAE Corporate, Tax & Advisory Practice';
  workbook.created = new Date();

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

  // 1_Client_Details (Blank Template)
  const ws1 = workbook.addWorksheet('1_Client_Details', { views: [{ showGridLines: true }] });
  ws1.columns = [
    { width: 28 }, { width: 46 }, { width: 44 }, { width: 26 }, { width: 48 }
  ];
  ws1.mergeCells('A2:E2');
  const t1 = ws1.getCell('A2');
  t1.value = 'AMRG Global UAE onboarding — Blank Template';
  t1.font = { name: 'Calibri', size: 14, bold: true, color: { argb: 'FFFFFFFF' } };
  t1.fill = headerFill(COLOR_AMRG_GREEN);
  t1.alignment = { vertical: 'middle', indent: 1 };
  ws1.getRow(2).height = 28;

  ws1.mergeCells('A3:E3');
  ws1.getCell('A3').value = 'Approved Canonical Template v2.0 | Permanent details retain history; annual positions require reassessment.';
  ws1.getCell('A3').font = { name: 'Calibri', size: 10, italic: true, color: { argb: 'FF475569' } };

  const hRow1 = ws1.getRow(6);
  ['Area', 'Permanent detail / review field', 'Client value', 'Source checklist IDs', 'Where to find / verify'].forEach((h, i) => {
    const c = hRow1.getCell(i + 1);
    c.value = h;
    c.font = headerFont;
    c.fill = headerFill(COLOR_NAVY);
    c.border = thinBorder;
  });

  // 2_Documents (Blank Template with Master Checklist)
  const ws2 = workbook.addWorksheet('2_Documents', { views: [{ showGridLines: true }] });
  ws2.columns = [
    { width: 24 }, { width: 16 }, { width: 24 }, { width: 46 }, { width: 28 }, { width: 22 }, { width: 48 }, { width: 36 }
  ];
  ws2.mergeCells('A2:H2');
  const t2 = ws2.getCell('A2');
  t2.value = 'AMRG Global document checklist — Blank Template';
  t2.font = { name: 'Calibri', size: 14, bold: true, color: { argb: 'FFFFFFFF' } };
  t2.fill = headerFill(COLOR_AMRG_GREEN);
  ws2.getRow(2).height = 28;

  const hRow2 = ws2.getRow(6);
  ['Document / request ID', 'Entity ID', 'Area', 'Document type', 'Required / received period', 'Receipt status', 'File / gap description', 'Obtain from / source link'].forEach((h, i) => {
    const c = hRow2.getCell(i + 1);
    c.value = h;
    c.font = headerFont;
    c.fill = headerFill(COLOR_NAVY);
    c.border = thinBorder;
  });

  let rIdx2 = 7;
  MASTER_CHECKLIST.forEach(item => {
    const row = ws2.getRow(rIdx2);
    [item.id, 'To scope', item.area, item.documentType, item.requiredPeriod, 'Not assessed', 'To obtain / assess', item.obtainFrom].forEach((val, ci) => {
      const c = row.getCell(ci + 1);
      c.value = val;
      c.border = thinBorder;
      c.font = { name: 'Calibri', size: 10, bold: ci === 0 };
      if (rIdx2 % 2 === 1) c.fill = headerFill(COLOR_LIGHT_GRAY);
    });
    rIdx2++;
  });

  // 3_Issues (Blank Template with 20 columns and column K formula)
  const ws3 = workbook.addWorksheet('3_Issues', { views: [{ showGridLines: true }] });
  ws3.columns = [
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
  ws3.mergeCells('A2:T2');
  const t3 = ws3.getCell('A2');
  t3.value = 'AMRG Global issues and reconciliations — Blank Template';
  t3.font = { name: 'Calibri', size: 14, bold: true, color: { argb: 'FFFFFFFF' } };
  t3.fill = headerFill(COLOR_AMRG_GREEN);
  ws3.getRow(2).height = 28;

  const hRow3 = ws3.getRow(6);
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
    const c = hRow3.getCell(i + 1);
    c.value = h;
    c.font = headerFont;
    c.fill = headerFill(COLOR_NAVY);
    c.border = thinBorder;
  });

  // Add sample formula in row 7
  const blankRow3 = ws3.getRow(7);
  blankRow3.getCell(1).value = 'ISSUE-0001';
  blankRow3.getCell(2).value = 'ENT-001';
  blankRow3.getCell(3).value = 'VAT';
  blankRow3.getCell(4).value = 'FY2025';
  blankRow3.getCell(5).value = 'Sales differ between ledger and returns (Template formula demo)';
  blankRow3.getCell(6).value = 'Document discrepancy';
  blankRow3.getCell(7).value = 'Sales Ledger F2:F100';
  blankRow3.getCell(8).value = 'VAT 201 Box 1';
  blankRow3.getCell(9).value = 1000000;
  blankRow3.getCell(9).numFmt = '#,##0.00';
  blankRow3.getCell(10).value = 950000;
  blankRow3.getCell(10).numFmt = '#,##0.00';
  blankRow3.getCell(11).value = { formula: 'IF(AND(ISNUMBER(I7),ISNUMBER(J7)),I7-J7,"")' };
  blankRow3.getCell(11).numFmt = '#,##0.00';
  blankRow3.getCell(12).value = 'Compare same entity, period, currency and net-of-VAT basis';
  blankRow3.getCell(13).value = 'Timing and out-of-scope adjustments pending';
  blankRow3.getCell(14).value = 'High';
  blankRow3.getCell(15).value = 'R04; Federal Decree-Law No. 8 of 2017';
  blankRow3.getCell(16).value = 'Reconcile ledger with quarterly VAT filings';
  blankRow3.getCell(17).value = 'REQ01';
  blankRow3.getCell(18).value = 'VAT manager / finance (suggested)';
  blankRow3.getCell(19).value = 'Awaiting evidence';
  blankRow3.getCell(20).value = 'Draft - not human reviewed';
  for (let ci = 1; ci <= 20; ci++) {
    blankRow3.getCell(ci).border = thinBorder;
  }

  const buffer = await workbook.xlsx.writeBuffer();
  return Buffer.from(buffer);
}
