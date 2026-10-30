/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import fs from 'fs';
import path from 'path';
import { 
  ClientEntity, 
  GeneratedReport, 
  ReviewFinding, 
  RunSnapshot, 
  UploadedDocument 
} from '../types/workbench.js';

interface SessionData {
  clients: ClientEntity[];
  documents: UploadedDocument[];
  runs: RunSnapshot[];
  reports: GeneratedReport[];
  findings: ReviewFinding[];
}

const BASE_SESSIONS_DIR = path.resolve(process.cwd(), 'data', 'sessions');

if (!fs.existsSync(BASE_SESSIONS_DIR)) {
  fs.mkdirSync(BASE_SESSIONS_DIR, { recursive: true });
}

export class SessionStore {
  readonly sessionId: string;
  readonly sessionDir: string;
  readonly uploadsDir: string;
  readonly reportsDir: string;
  private readonly dbFilePath: string;
  private data: SessionData;

  constructor(sessionId: string) {
    // Sanitize session ID to prevent path traversal
    this.sessionId = sessionId.replace(/[^a-zA-Z0-9_-]/g, '');
    this.sessionDir = path.join(BASE_SESSIONS_DIR, this.sessionId);
    this.uploadsDir = path.join(this.sessionDir, 'uploads');
    this.reportsDir = path.join(this.sessionDir, 'reports');
    this.dbFilePath = path.join(this.sessionDir, 'store.json');

    for (const dir of [this.sessionDir, this.uploadsDir, this.reportsDir]) {
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
    }

    this.data = this.load();
  }

  private load(): SessionData {
    if (fs.existsSync(this.dbFilePath)) {
      try {
        const raw = fs.readFileSync(this.dbFilePath, 'utf-8');
        return JSON.parse(raw);
      } catch (err) {
        console.error(`Failed to parse session db file for ${this.sessionId}:`, err);
      }
    }

    const initial: SessionData = {
      clients: [],
      documents: [],
      runs: [],
      reports: [],
      findings: [],
    };
    this.save(initial);
    return initial;
  }

  private save(state?: SessionData): void {
    const toSave = state || this.data;
    fs.writeFileSync(this.dbFilePath, JSON.stringify(toSave, null, 2), 'utf-8');
  }

  // CLIENTS
  getClients(): ClientEntity[] {
    return this.data.clients;
  }

  getClient(id: string): ClientEntity | undefined {
    return this.data.clients.find(c => c.id === id);
  }

  saveClient(client: ClientEntity): ClientEntity {
    const index = this.data.clients.findIndex(c => c.id === client.id);
    if (index >= 0) {
      this.data.clients[index] = { ...client, updatedAt: new Date().toISOString() };
    } else {
      this.data.clients.push(client);
    }
    this.save();
    return client;
  }

  deleteClient(id: string): boolean {
    const index = this.data.clients.findIndex(c => c.id === id);
    if (index >= 0) {
      this.data.clients.splice(index, 1);
      // clean associated records
      this.data.documents = this.data.documents.filter(d => d.clientId !== id);
      this.data.runs = this.data.runs.filter(r => r.clientId !== id);
      this.data.reports = this.data.reports.filter(r => r.clientId !== id);
      this.data.findings = this.data.findings.filter(f => f.clientId !== id);
      this.save();
      return true;
    }
    return false;
  }

  // DOCUMENTS
  getDocuments(clientId: string): UploadedDocument[] {
    return this.data.documents.filter(d => d.clientId === clientId);
  }

  getDocument(docId: string): UploadedDocument | undefined {
    return this.data.documents.find(d => d.id === docId);
  }

  addDocuments(docs: UploadedDocument[]): void {
    this.data.documents.push(...docs);
    this.save();
  }

  updateDocument(docId: string, updates: Partial<UploadedDocument>): UploadedDocument | undefined {
    const doc = this.data.documents.find(d => d.id === docId);
    if (doc) {
      Object.assign(doc, updates);
      this.save();
      return doc;
    }
    return undefined;
  }

  deleteDocument(docId: string): boolean {
    const index = this.data.documents.findIndex(d => d.id === docId);
    if (index >= 0) {
      const doc = this.data.documents[index];
      // remove file from disk if present
      const fullPath = path.join(this.uploadsDir, doc.storedFileName);
      if (fs.existsSync(fullPath)) {
        try { fs.unlinkSync(fullPath); } catch (e) {}
      }
      this.data.documents.splice(index, 1);
      this.save();
      return true;
    }
    return false;
  }

  // RUNS
  getRuns(clientId: string): RunSnapshot[] {
    return this.data.runs
      .filter(r => r.clientId === clientId)
      .sort((a, b) => b.runNumber - a.runNumber);
  }

  getRun(runId: string): RunSnapshot | undefined {
    return this.data.runs.find(r => r.id === runId);
  }

  saveRun(run: RunSnapshot): RunSnapshot {
    const index = this.data.runs.findIndex(r => r.id === run.id);
    if (index >= 0) {
      this.data.runs[index] = run;
    } else {
      this.data.runs.push(run);
    }
    this.save();
    return run;
  }

  // REPORTS
  getReports(clientId?: string): GeneratedReport[] {
    const list = clientId 
      ? this.data.reports.filter(r => r.clientId === clientId)
      : this.data.reports;
    return list.sort((a, b) => new Date(b.generatedAt).getTime() - new Date(a.generatedAt).getTime());
  }

  getReport(reportId: string): GeneratedReport | undefined {
    return this.data.reports.find(r => r.id === reportId);
  }

  saveReport(report: GeneratedReport): GeneratedReport {
    this.data.reports.push(report);
    this.save();
    return report;
  }

  // FINDINGS (Internal to generated excel, not shown in UI)
  getFindings(clientId: string, runId?: string): ReviewFinding[] {
    if (runId) {
      return this.data.findings.filter(f => f.clientId === clientId && f.runId === runId);
    }
    return this.data.findings.filter(f => f.clientId === clientId);
  }

  saveFindings(newFindings: ReviewFinding[]): void {
    const runIds = new Set(newFindings.map(f => f.runId));
    this.data.findings = this.data.findings.filter(f => !runIds.has(f.runId));
    this.data.findings.push(...newFindings);
    this.save();
  }

  clearAllData(): void {
    this.data = {
      clients: [],
      documents: [],
      runs: [],
      reports: [],
      findings: [],
    };
    this.save();
  }
}

// In-memory cache of session instances
const sessionInstances = new Map<string, SessionStore>();

export function getSessionStore(sessionId: string): SessionStore {
  const cleanId = (sessionId || 'default').replace(/[^a-zA-Z0-9_-]/g, '');
  if (!sessionInstances.has(cleanId)) {
    sessionInstances.set(cleanId, new SessionStore(cleanId));
  }
  return sessionInstances.get(cleanId)!;
}
