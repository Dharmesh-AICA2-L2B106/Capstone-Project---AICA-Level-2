/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { MasterChecklistItem } from '../types/workbench.js';

export const MASTER_CHECKLIST: MasterChecklistItem[] = [
  // GOVERNANCE & CORPORATE (GOV)
  { id: 'GOV001', area: 'Corporate / Free Zone', documentType: 'Certificate of incorporation / registration', requiredPeriod: 'Inception to cutoff; all changes', obtainFrom: 'Registrar / company secretary', isConditional: false },
  { id: 'GOV002', area: 'Corporate / Free Zone', documentType: 'Memorandum and articles, including amendments', requiredPeriod: 'Inception to cutoff; all changes', obtainFrom: 'Company secretary / registrar', isConditional: false },
  { id: 'GOV003', area: 'Corporate / Free Zone', documentType: 'Current and historical trade licences', requiredPeriod: 'Inception to cutoff; all changes', obtainFrom: 'Licensing authority portal', isConditional: false },
  { id: 'GOV004', area: 'Corporate / Free Zone', documentType: 'Commercial register extract / incumbency certificate', requiredPeriod: 'Inception to cutoff; all changes', obtainFrom: 'Registrar / company secretary', isConditional: false },
  { id: 'GOV007', area: 'Corporate / Free Zone', documentType: 'Shareholder register and share certificates', requiredPeriod: 'Inception to cutoff; all changes', obtainFrom: 'Company secretary', isConditional: false },
  { id: 'GOV008', area: 'Corporate / Free Zone', documentType: 'Share allotment, transfer and capital-change records', requiredPeriod: 'Inception to cutoff; all changes', obtainFrom: 'Company secretary / finance', isConditional: false },
  { id: 'GOV009', area: 'Corporate / Free Zone', documentType: 'Ownership chart to natural-person controllers', requiredPeriod: 'Inception to cutoff; all changes', obtainFrom: 'Management / compliance', isConditional: false },
  { id: 'GOV010', area: 'Corporate / Free Zone', documentType: 'UBO register, declarations and filing receipts', requiredPeriod: 'Inception to cutoff; all changes', obtainFrom: 'Company secretary / registrar', isConditional: false },
  { id: 'GOV012', area: 'Corporate / Free Zone', documentType: 'Director, manager and secretary appointments / resignations', requiredPeriod: 'Inception to cutoff; all changes', obtainFrom: 'Company secretary', isConditional: false },
  { id: 'GOV013', area: 'Corporate / Free Zone', documentType: 'Authorised signatory powers and powers of attorney', requiredPeriod: 'Inception to cutoff; all changes', obtainFrom: 'Legal / board', isConditional: false },
  { id: 'GOV015', area: 'Corporate / Free Zone', documentType: 'Board and shareholder meeting minutes / resolutions', requiredPeriod: 'Inception to cutoff; all changes', obtainFrom: 'Company secretary', isConditional: false },
  { id: 'GOV016', area: 'Corporate / Free Zone', documentType: 'Annual returns / confirmation statements and receipts', requiredPeriod: 'Inception to cutoff; all changes', obtainFrom: 'Registrar portal', isConditional: false },
  { id: 'GOV018', area: 'Corporate / Free Zone', documentType: 'Registered office lease, Ejari / occupancy evidence', requiredPeriod: 'Inception to cutoff; all changes', obtainFrom: 'Landlord / facilities / portal', isConditional: false },

  // ACCOUNTING & BANKING (ACC)
  { id: 'ACC001', area: 'Accounting / Banking', documentType: 'Signed financial statements and notes', requiredPeriod: 'Each financial year and intervening period', obtainFrom: 'Finance / auditor', isConditional: false },
  { id: 'ACC002', area: 'Accounting / Banking', documentType: 'Auditor report and management letter', requiredPeriod: 'Each financial year and intervening period', obtainFrom: 'Auditor / management', isConditional: false },
  { id: 'ACC004', area: 'Accounting / Banking', documentType: 'Trial balance and chart of accounts', requiredPeriod: 'Each financial year and intervening period', obtainFrom: 'Finance / accounting system', isConditional: false },
  { id: 'ACC005', area: 'Accounting / Banking', documentType: 'Full general ledger and journal audit trail', requiredPeriod: 'Each financial year and intervening period', obtainFrom: 'Finance / ERP', isConditional: false },
  { id: 'ACC008', area: 'Accounting / Banking', documentType: 'Sales register and invoice sequence report', requiredPeriod: 'Each financial year and intervening period', obtainFrom: 'Sales / ERP', isConditional: false },
  { id: 'ACC009', area: 'Accounting / Banking', documentType: 'Purchase register and expense ledger', requiredPeriod: 'Each financial year and intervening period', obtainFrom: 'Procurement / ERP', isConditional: false },
  { id: 'ACC016', area: 'Accounting / Banking', documentType: 'All bank statements, including closed / foreign accounts', requiredPeriod: 'Each financial year and intervening period', obtainFrom: 'Bank / authorised treasury', isConditional: false },
  { id: 'ACC018', area: 'Accounting / Banking', documentType: 'Year-end and monthly bank reconciliations', requiredPeriod: 'Each financial year and intervening period', obtainFrom: 'Finance', isConditional: false },
  { id: 'ACC024', area: 'Accounting / Banking', documentType: 'Intercompany balances and confirmations', requiredPeriod: 'Each financial year and intervening period', obtainFrom: 'Group finance', isConditional: true },

  // VAT (VAT)
  { id: 'VAT001', area: 'VAT', documentType: 'VAT registration application and attachments', requiredPeriod: 'Pre-registration and effective date', obtainFrom: 'EmaraTax / previous adviser', isConditional: false },
  { id: 'VAT002', area: 'VAT', documentType: 'VAT certificate and registration decision', requiredPeriod: 'Every VAT period from effective date', obtainFrom: 'EmaraTax', isConditional: false },
  { id: 'VAT004', area: 'VAT', documentType: 'FTA-assigned VAT periods and filing dashboard', requiredPeriod: 'All active periods', obtainFrom: 'EmaraTax', isConditional: false },
  { id: 'VAT009', area: 'VAT', documentType: 'VAT201 returns and submission acknowledgements', requiredPeriod: 'Every quarterly/monthly VAT period', obtainFrom: 'EmaraTax / former adviser', isConditional: false },
  { id: 'VAT011', area: 'VAT', documentType: 'Sales-to-VAT and accounts-to-VAT reconciliations', requiredPeriod: 'Every VAT period', obtainFrom: 'Finance / tax adviser', isConditional: false },
  { id: 'VAT014', area: 'VAT', documentType: 'Tax payment receipts and FTA allocation ledger', requiredPeriod: 'Every VAT period', obtainFrom: 'EmaraTax / bank', isConditional: false },
  { id: 'VAT015', area: 'VAT', documentType: 'Sample sales tax invoices and credit notes', requiredPeriod: 'Selected test sample', obtainFrom: 'Sales / ERP', isConditional: false },
  { id: 'VAT050', area: 'VAT', documentType: 'Voluntary disclosures and error-discovery records', requiredPeriod: 'Historical filings', obtainFrom: 'Tax / EmaraTax', isConditional: true },

  // CORPORATE TAX (CT)
  { id: 'CT001', area: 'CT', documentType: 'CT registration application and attachments', requiredPeriod: 'Inception to CT commencement', obtainFrom: 'EmaraTax / former adviser', isConditional: false },
  { id: 'CT002', area: 'CT', documentType: 'CT registration certificate and FTA decision', requiredPeriod: 'From CT registration', obtainFrom: 'EmaraTax', isConditional: false },
  { id: 'CT003', area: 'CT', documentType: 'First CT period support and portal confirmation', requiredPeriod: 'First financial year in scope', obtainFrom: 'EmaraTax / articles / first accounts', isConditional: false },
  { id: 'CT005', area: 'CT', documentType: 'CT returns, all schedules and acknowledgements', requiredPeriod: 'Each applicable CT tax period', obtainFrom: 'EmaraTax / tax adviser', isConditional: false },
  { id: 'CT006', area: 'CT', documentType: 'Book-profit-to-taxable-income computation bridge', requiredPeriod: 'Each CT tax period', obtainFrom: 'Finance / tax adviser', isConditional: false },
  { id: 'CT007', area: 'CT', documentType: 'CT payment receipts and FTA statement of account', requiredPeriod: 'Each CT period', obtainFrom: 'EmaraTax / bank', isConditional: false },
  { id: 'CT011', area: 'CT', documentType: 'Small Business Relief eligibility and election evidence', requiredPeriod: 'Applicable years (revenue < AED 3M)', obtainFrom: 'Finance / tax adviser', isConditional: true },

  // FREE ZONE (FZ)
  { id: 'FZ002', area: 'Free Zone / CT', documentType: 'Renewal applications, receipts and renewed licences', requiredPeriod: 'Each licence year', obtainFrom: 'Zone portal', isConditional: false },
  { id: 'FZ004', area: 'Free Zone / CT', documentType: 'Audit / accounts filing receipts and authority queries', requiredPeriod: 'Each financial year', obtainFrom: 'Zone portal / auditor', isConditional: false },
  { id: 'FZ013', area: 'Free Zone / CT', documentType: 'QFZP condition assessment by tax period', requiredPeriod: 'Each CT period', obtainFrom: 'Tax / finance', isConditional: true },
  { id: 'FZ016', area: 'Free Zone / CT', documentType: 'Non-qualifying revenue and de minimis workings', requiredPeriod: 'Each CT period', obtainFrom: 'Tax / finance', isConditional: true },

  // OTHER / LABOUR / REGULATORY (OTH)
  { id: 'OTH001', area: 'Other / Labour', documentType: 'Employee register, employment contracts and amendments', requiredPeriod: 'All applicable historical periods', obtainFrom: 'HR / competent authority', isConditional: false },
  { id: 'OTH003', area: 'Other / Labour', documentType: 'Payroll, payslips and wage payment evidence', requiredPeriod: 'All applicable historical periods', obtainFrom: 'HR / finance', isConditional: false },
  { id: 'OTH004', area: 'Other / Labour', documentType: 'WPS submissions, acceptance and exemption evidence', requiredPeriod: 'All applicable historical periods', obtainFrom: 'HR / bank / authority', isConditional: false },
  { id: 'OTH009', area: 'Other / AML', documentType: 'AML scope assessment and supervisory registration', requiredPeriod: 'Applicable activities', obtainFrom: 'Compliance / supervisor', isConditional: true },
  { id: 'OTH014', area: 'Other / ESR', documentType: 'Historical ESR notifications, reports and exemptions', requiredPeriod: 'Historical periods on/before 31 Dec 2022', obtainFrom: 'MoF / FTA / former adviser', isConditional: true },
];

export const UAE_ONBOARDING_SKILL_META = {
  id: 'amrg-uae-onboarding-checks',
  name: 'AMRG UAE Onboarding Checks',
  version: '2.0.0',
  status: 'Published',
  publishedDate: '2026-10-27',
  author: 'AMRG Global Tax & Advisory Practice',
  jurisdictions: ['UAE Mainland', 'DMCC', 'ADGM', 'DIFC', 'JAFZA', 'DAFZ', 'HFZA', 'SAIF'],
  lawsCovered: [
    { code: 'CT', name: 'Federal Decree-Law No. 47 of 2022 on the Taxation of Corporations and Businesses' },
    { code: 'VAT', name: 'Federal Decree-Law No. 8 of 2017 on Value Added Tax and Amendments' },
    { code: 'CCL', name: 'Federal Decree-Law No. 32 of 2021 on Commercial Companies' },
    { code: 'FZ', name: 'Competent Free Zone Authority Regulations & Decisions' },
    { code: 'LABOUR', name: 'Federal Decree-Law No. 33 of 2021 on the Regulation of Labour Relations & WPS' },
    { code: 'AML', name: 'Federal Decree-Law No. 20 of 2018 on Anti-Money Laundering & Cabinet Decision 109/2023 (UBO)' }
  ]
};
