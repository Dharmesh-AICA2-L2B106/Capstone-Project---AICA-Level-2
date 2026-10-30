/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

export interface ClientEntity {
  id: string; // e.g. CLI-MVR6XK
  name: string; // Compulsory client name
  entityType: string; // e.g. FZCO, LLC, Branch
  jurisdiction: string; // e.g. DMCC, Dubai Mainland, SAIF, DIFC
  registrationNumber?: string;
  tradeLicenceNumber?: string;
  incorporationDate?: string;
  vatTrn?: string;
  ctTrn?: string;
  financialYearEnd?: string; // e.g. 31 December
  firstCtPeriod?: string; // e.g. 1 Jan 2024 - 31 Dec 2024
  
  // Status and review snapshot tracking
  currentRunStatus: 'Idle' | 'Queued' | 'Processing' | 'Completed' | 'Failed';
  lastRunAt?: string;
  lastRunError?: string;
  documentsChangedSinceLastRun: boolean;
  activeRunId?: string;
  latestReportId?: string;

  createdAt: string;
  updatedAt: string;
}

export interface UploadedDocument {
  id: string;
  clientId: string;
  originalName: string;
  storedFileName: string;
  fileSize: number;
  mimeType: string;
  category: 'Corporate' | 'Licence' | 'Accounting' | 'VAT' | 'Corporate_Tax' | 'Banking' | 'Labour' | 'Other';
  uploadedAt: string;
  contentHash: string;
  isExcluded: boolean;
  pageCount?: number;
  extractionSummary?: string;
  limitations?: string;
  extractedEntityName?: string;
}

export interface SnapshotDocItem {
  id: string;
  originalName: string;
  fileSize: number;
  category: string;
}

export interface RunSnapshot {
  id: string; // e.g. RUN-001
  clientId: string;
  runNumber: number;
  versionLabel: string; // e.g. "Version 1"
  startedAt: string;
  completedAt?: string;
  status: 'Queued' | 'Processing' | 'Completed' | 'Failed';
  errorMessage?: string;
  skillId: string;
  skillVersion: string;
  snapshotDocuments: SnapshotDocItem[];
  totalDocumentsCount: number;
  reportId?: string;
}

export interface GeneratedReport {
  id: string; // e.g. REP-001
  clientId: string;
  clientName: string;
  runId: string;
  runNumber: number;
  versionLabel: string; // e.g. "v1", "v2"
  generatedAt: string;
  fileName: string;
  filePath: string;
  fileSizeBytes: number;
  includedDocumentsCount: number;
  includedDocumentNames: string[];
  skillVersion: string;
}

export type FindingClassification = 
  | 'Confirmed error'
  | 'Confirmed error / default' 
  | 'Potential issue' 
  | 'Discrepancy'
  | 'Document discrepancy' 
  | 'Missing evidence';

export type FindingPriority = 'Urgent' | 'High' | 'Medium' | 'Low';

export type FindingDomain = 
  | 'CT' 
  | 'VAT' 
  | 'Free Zone' 
  | 'Banking' 
  | 'Secretarial Services' 
  | 'Labour Laws' 
  | 'Other Laws' 
  | 'Accounting & Audit';

export interface ReviewFinding {
  id: string; // e.g. I001
  clientId: string;
  runId: string;
  domain: FindingDomain;
  checkId: string;
  period: string;
  title: string;
  issueSummary: string;
  classification: FindingClassification;
  priority: FindingPriority;
  
  // Reconciliations & Evidence
  evidenceALocator?: string;
  evidenceBLocator?: string;
  amountA?: number;
  amountB?: number;
  variance?: number;
  currency: string;
  reconciliationTest?: string;

  legalBasis?: string;
  rules?: string;
  action?: string;
  requestIds?: string;
  suggestedOwner?: string;
  workflowStatus?: string;
  reviewApproval?: string;
  unresolvedExplanation?: string;
  recommendedAction: string;
}

export interface MasterChecklistItem {
  id: string;
  area: string;
  documentType: string;
  requiredPeriod: string;
  obtainFrom: string;
  isConditional: boolean;
}
