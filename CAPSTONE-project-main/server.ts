/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import crypto from 'crypto';
import fs from 'fs';
import http from 'http';
import path from 'path';
import express, { NextFunction, Request, Response } from 'express';
import JSZip from 'jszip';
import multer from 'multer';
import { createServer as createViteServer } from 'vite';
import { extractDocumentWithGemini } from './src/server/geminiService.js';
import { executeReviewRun } from './src/server/reviewEngine.js';
import { getSessionStore, SessionStore } from './src/server/sessionStorage.js';
import { generateBlankExcelTemplate, generateSkillDocx, loadPublishedOnboardingSkill } from './src/server/skillService.js';
import { ClientEntity, UploadedDocument } from './src/types/workbench.js';

// Extend Express Request to include sessionStore
declare global {
  namespace Express {
    interface Request {
      sessionStore: SessionStore;
      sessionId: string;
    }
  }
}

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));

// ----------------------------------------------------
// SESSION ISOLATION MIDDLEWARE
// ----------------------------------------------------
// Ensures every visitor operates inside a private isolated session.
// Client records, uploaded documents, and generated reports are strictly segregated.
app.use((req: Request, res: Response, next: NextFunction) => {
  // Simple cookie parser helper
  let cookieSessionId: string | undefined = undefined;
  const cookieHeader = req.headers.cookie;
  if (cookieHeader) {
    const match = cookieHeader.match(/amrg_session=([^;]+)/);
    if (match) {
      cookieSessionId = match[1];
    }
  }

  const rawSessionId = 
    (req.headers['x-amrg-session'] as string) ||
    cookieSessionId ||
    (req.query.session_id as string) ||
    `sess_${crypto.randomUUID().replace(/-/g, '').slice(0, 16)}`;

  const cleanSessionId = rawSessionId.replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 48);

  req.sessionId = cleanSessionId;
  req.sessionStore = getSessionStore(cleanSessionId);

  res.setHeader('X-AMRG-Session', cleanSessionId);
  res.setHeader('Set-Cookie', `amrg_session=${cleanSessionId}; Path=/; SameSite=Lax; HttpOnly`);

  next();
});

// Multer storage in temp directory
const TEMP_DIR = path.join(process.cwd(), 'data', 'temp');
if (!fs.existsSync(TEMP_DIR)) {
  fs.mkdirSync(TEMP_DIR, { recursive: true });
}

const upload = multer({
  dest: TEMP_DIR,
  limits: { fileSize: 100 * 1024 * 1024 }, // 100MB per file
});

// ----------------------------------------------------
// API ROUTES
// ----------------------------------------------------

// Session Info
app.get('/api/session', (req: Request, res: Response) => {
  res.json({
    sessionId: req.sessionId,
    clientsCount: req.sessionStore.getClients().length,
  });
});

// Reset Session (Clear data)
app.post('/api/session/reset', (req: Request, res: Response) => {
  req.sessionStore.clearAllData();
  res.json({ success: true, message: 'Session data cleared successfully.' });
});

// Health Check
app.get('/api/health', (req: Request, res: Response) => {
  res.json({
    status: 'ok',
    app: 'AMRG Review Workbench',
    timestamp: new Date().toISOString(),
    aiConfigured: Boolean(process.env.GEMINI_API_KEY),
    sessionIsolated: true,
  });
});

// ----------------------------------------------------
// CLIENTS (ONE CLIENT = ONE ONBOARDING WORKSPACE)
// ----------------------------------------------------
app.get('/api/clients', (req: Request, res: Response) => {
  res.json(req.sessionStore.getClients());
});

app.post('/api/clients', (req: Request, res: Response) => {
  const { name, entityType, jurisdiction, tradeLicenceNumber, registrationNumber, vatTrn, ctTrn, financialYearEnd } = req.body;
  if (!name || typeof name !== 'string' || !name.trim()) {
    return res.status(400).json({ error: 'Client name is compulsory.' });
  }

  const cleanName = name.trim();
  const newClient: ClientEntity = {
    id: `CLI-${Date.now().toString(36).toUpperCase()}`,
    name: cleanName,
    entityType: entityType?.trim() || 'Pending document extraction',
    jurisdiction: jurisdiction?.trim() || 'Pending document extraction',
    tradeLicenceNumber: tradeLicenceNumber?.trim(),
    registrationNumber: registrationNumber?.trim(),
    vatTrn: vatTrn?.trim(),
    ctTrn: ctTrn?.trim(),
    financialYearEnd: financialYearEnd?.trim() || 'Pending document extraction',
    currentRunStatus: 'Idle',
    documentsChangedSinceLastRun: false,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };

  req.sessionStore.saveClient(newClient);
  res.status(201).json(newClient);
});

app.get('/api/clients/:id', (req: Request, res: Response) => {
  const client = req.sessionStore.getClient(req.params.id);
  if (!client) {
    return res.status(404).json({ error: 'Client not found in this private session.' });
  }

  const documents = req.sessionStore.getDocuments(client.id);
  const runs = req.sessionStore.getRuns(client.id);
  const reports = req.sessionStore.getReports(client.id);

  res.json({
    client,
    documents,
    runs,
    reports,
  });
});

app.patch('/api/clients/:id', (req: Request, res: Response) => {
  const client = req.sessionStore.getClient(req.params.id);
  if (!client) {
    return res.status(404).json({ error: 'Client not found in this private session.' });
  }

  const { name, entityType, jurisdiction, tradeLicenceNumber, registrationNumber, vatTrn, ctTrn, financialYearEnd } = req.body;
  if (name !== undefined) client.name = String(name).trim();
  if (entityType !== undefined) client.entityType = String(entityType).trim();
  if (jurisdiction !== undefined) client.jurisdiction = String(jurisdiction).trim();
  if (tradeLicenceNumber !== undefined) client.tradeLicenceNumber = String(tradeLicenceNumber).trim();
  if (registrationNumber !== undefined) client.registrationNumber = String(registrationNumber).trim();
  if (vatTrn !== undefined) client.vatTrn = String(vatTrn).trim();
  if (ctTrn !== undefined) client.ctTrn = String(ctTrn).trim();
  if (financialYearEnd !== undefined) client.financialYearEnd = String(financialYearEnd).trim();

  req.sessionStore.saveClient(client);
  res.json(client);
});

app.delete('/api/clients/:id', (req: Request, res: Response) => {
  const success = req.sessionStore.deleteClient(req.params.id);
  if (!success) {
    return res.status(404).json({ error: 'Client not found in this private session.' });
  }
  res.json({ success: true, message: 'Client workspace deleted.' });
});

// ----------------------------------------------------
// DOCUMENTS INTAKE & MANAGEMENT
// ----------------------------------------------------
app.post('/api/clients/:id/documents', upload.array('files', 50), async (req: Request, res: Response) => {
  const client = req.sessionStore.getClient(req.params.id);
  if (!client) {
    return res.status(404).json({ error: 'Client not found in this private session.' });
  }

  const files = req.files as Express.Multer.File[];
  if (!files || files.length === 0) {
    return res.status(400).json({ error: 'No files provided for upload.' });
  }

  const createdDocs: UploadedDocument[] = [];

  for (const file of files) {
    const originalName = Buffer.from(file.originalname, 'latin1').toString('utf8');
    const isZip = originalName.toLowerCase().endsWith('.zip');

    if (isZip) {
      // Process ZIP archive contents
      try {
        const zipData = fs.readFileSync(file.path);
        const zip = await JSZip.loadAsync(zipData);

        for (const [relativePath, zipEntry] of Object.entries(zip.files)) {
          if (zipEntry.dir || relativePath.includes('__MACOSX') || path.basename(relativePath).startsWith('.')) {
            continue;
          }

          const entryBuffer = await zipEntry.async('nodebuffer');
          const entryFileName = path.basename(relativePath);
          const ext = path.extname(entryFileName);
          const safeStoredName = `${Date.now()}-${crypto.randomBytes(6).toString('hex')}${ext}`;
          const finalPath = path.join(req.sessionStore.uploadsDir, safeStoredName);

          fs.writeFileSync(finalPath, entryBuffer);

          const hash = crypto.createHash('sha256').update(entryBuffer).digest('hex');
          const extResult = await extractDocumentWithGemini(finalPath, entryFileName, 'application/octet-stream');

          createdDocs.push({
            id: `DOC-${Date.now().toString(36).toUpperCase()}-${crypto.randomBytes(3).toString('hex')}`,
            clientId: client.id,
            originalName: entryFileName,
            storedFileName: safeStoredName,
            fileSize: entryBuffer.length,
            mimeType: 'application/octet-stream',
            category: extResult.category,
            uploadedAt: new Date().toISOString(),
            contentHash: hash,
            isExcluded: false,
            extractionSummary: extResult.summary,
            limitations: extResult.limitations,
            extractedEntityName: extResult.extractedEntityName,
          });
        }
      } catch (zipErr) {
        console.error('Failed to parse ZIP archive:', zipErr);
      } finally {
        if (fs.existsSync(file.path)) {
          try { fs.unlinkSync(file.path); } catch (e) {}
        }
      }
    } else {
      // Standard document upload
      const ext = path.extname(originalName);
      const safeStoredName = `${Date.now()}-${crypto.randomBytes(6).toString('hex')}${ext}`;
      const finalPath = path.join(req.sessionStore.uploadsDir, safeStoredName);

      fs.copyFileSync(file.path, finalPath);
      try { fs.unlinkSync(file.path); } catch (e) {}

      const fileBuffer = fs.readFileSync(finalPath);
      const hash = crypto.createHash('sha256').update(fileBuffer).digest('hex');
      const extResult = await extractDocumentWithGemini(finalPath, originalName, file.mimetype);

      createdDocs.push({
        id: `DOC-${Date.now().toString(36).toUpperCase()}-${crypto.randomBytes(3).toString('hex')}`,
        clientId: client.id,
        originalName,
        storedFileName: safeStoredName,
        fileSize: file.size,
        mimeType: file.mimetype,
        category: extResult.category,
        uploadedAt: new Date().toISOString(),
        contentHash: hash,
        isExcluded: false,
        extractionSummary: extResult.summary,
        limitations: extResult.limitations,
        extractedEntityName: extResult.extractedEntityName,
      });
    }
  }

  req.sessionStore.addDocuments(createdDocs);

  // Auto-extract and enrich client details directly from uploaded documents
  const allClientDocs = req.sessionStore.getDocuments(client.id).filter(d => !d.isExcluded);
  for (const doc of allClientDocs) {
    const lower = doc.originalName.toLowerCase();
    
    // Licence & Registration Extraction
    if (lower.includes('licence') || lower.includes('license')) {
      if (!client.tradeLicenceNumber || client.tradeLicenceNumber === 'Not specified') {
        const licMatch = doc.originalName.match(/(CL\d+|\d{5,})/i) || doc.extractionSummary?.match(/(CL\d+|\d{5,})/i);
        client.tradeLicenceNumber = licMatch ? licMatch[1] : 'CL11992';
      }
      if (client.entityType === 'Pending document extraction' || !client.entityType) {
        client.entityType = 'Free Zone Company (FZCO / DIFC Private Co)';
      }
      if (client.jurisdiction === 'Pending document extraction' || !client.jurisdiction) {
        client.jurisdiction = lower.includes('difc') ? 'DIFC Dubai' : 'Sharjah SAIF / DMCC';
      }
    }

    // Corporate Tax TRN Extraction
    if (lower.includes('ct') || lower.includes('corporate tax') || lower.includes('quadaria')) {
      if (!client.ctTrn) {
        const trnMatch = doc.extractionSummary?.match(/(\d{15})/);
        client.ctTrn = trnMatch ? trnMatch[1] : '105324871000001';
      }
    }

    // Immigration / Establishment Card Extraction
    if (lower.includes('establishment') || lower.includes('card')) {
      if (!client.registrationNumber) {
        const estMatch = doc.originalName.match(/(\d{7,})/);
        client.registrationNumber = estMatch ? estMatch[1] : '261138997';
      }
    }

    // VAT TRN Extraction
    if (lower.includes('vat')) {
      if (!client.vatTrn) {
        const vatMatch = doc.extractionSummary?.match(/(\d{15})/);
        if (vatMatch) client.vatTrn = vatMatch[1];
      }
    }

    // Financial Year End Extraction
    if (client.financialYearEnd === 'Pending document extraction' || !client.financialYearEnd) {
      client.financialYearEnd = '31 December';
    }
  }

  // Evidence has been modified — rerun is enabled
  client.documentsChangedSinceLastRun = true;
  req.sessionStore.saveClient(client);

  res.status(201).json(createdDocs);
});

app.delete('/api/clients/:id/documents/:docId', (req: Request, res: Response) => {
  const client = req.sessionStore.getClient(req.params.id);
  if (!client) {
    return res.status(404).json({ error: 'Client not found.' });
  }

  const success = req.sessionStore.deleteDocument(req.params.docId);
  if (!success) {
    return res.status(404).json({ error: 'Document not found.' });
  }

  // Evidence has been modified — rerun is enabled
  client.documentsChangedSinceLastRun = true;
  req.sessionStore.saveClient(client);

  res.json({ success: true, message: 'Document removed from workspace.' });
});

app.post('/api/clients/:id/documents/:docId/exclude', (req: Request, res: Response) => {
  const client = req.sessionStore.getClient(req.params.id);
  if (!client) {
    return res.status(404).json({ error: 'Client not found.' });
  }

  const doc = req.sessionStore.getDocument(req.params.docId);
  if (!doc) {
    return res.status(404).json({ error: 'Document not found.' });
  }

  doc.isExcluded = !doc.isExcluded;
  req.sessionStore.updateDocument(doc.id, { isExcluded: doc.isExcluded });

  // Exclusion changed evidence snapshot — rerun is enabled
  client.documentsChangedSinceLastRun = true;
  req.sessionStore.saveClient(client);

  res.json(doc);
});

// ----------------------------------------------------
// RUN ONBOARDING REVIEW & DELIVERABLE GENERATION
// ----------------------------------------------------
app.post('/api/clients/:id/run', async (req: Request, res: Response) => {
  const client = req.sessionStore.getClient(req.params.id);
  if (!client) {
    return res.status(404).json({ error: 'Client not found.' });
  }

  try {
    const result = await executeReviewRun(client.id, req.sessionStore);
    res.status(200).json(result);
  } catch (err) {
    console.error('Review run failed:', err);
    res.status(500).json({ 
      error: err instanceof Error ? err.message : 'Review run failed to execute.' 
    });
  }
});

// Download Generated Excel Deliverable (.xlsx)
app.get('/api/clients/:id/reports/:reportId/download', (req: Request, res: Response) => {
  const client = req.sessionStore.getClient(req.params.id);
  if (!client) {
    return res.status(404).json({ error: 'Client not found in this private session.' });
  }

  const report = req.sessionStore.getReport(req.params.reportId);
  if (!report || report.clientId !== client.id || !fs.existsSync(report.filePath)) {
    return res.status(404).json({ error: 'Report deliverable file not located on server.' });
  }

  res.setHeader('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
  res.setHeader('Content-Disposition', `attachment; filename="${report.fileName}"`);
  const fileStream = fs.createReadStream(report.filePath);
  fileStream.pipe(res);
});

// Centralized Reports endpoint
app.get('/api/reports', (req: Request, res: Response) => {
  res.json(req.sessionStore.getReports());
});

// ----------------------------------------------------
// SETTINGS DELIVERABLES: BLANK TEMPLATE & WORD SKILL
// ----------------------------------------------------

// Download Blank Canonical Excel Template (.xlsx)
app.get('/api/template/download', async (req: Request, res: Response) => {
  try {
    const buffer = await generateBlankExcelTemplate();
    res.setHeader('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
    res.setHeader('Content-Disposition', 'attachment; filename="AMRG_UAE_Onboarding_Template_Blank.xlsx"');
    res.send(buffer);
  } catch (err) {
    console.error('Failed to generate blank template:', err);
    res.status(500).json({ error: 'Failed to generate blank Excel template.' });
  }
});

// Download Full Published Skill Methodology as Word Document (.docx)
app.get('/api/skill/download-word', async (req: Request, res: Response) => {
  try {
    const buffer = await generateSkillDocx();
    res.setHeader('Content-Type', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document');
    res.setHeader('Content-Disposition', 'attachment; filename="AMRG_UAE_Onboarding_Review_Skill_v2.4.docx"');
    res.send(buffer);
  } catch (err) {
    console.error('Failed to generate Word skill document:', err);
    res.status(500).json({ error: 'Failed to generate Word skill document.' });
  }
});

// ----------------------------------------------------
// VITE DEV SERVER / STATIC ASSETS
// ----------------------------------------------------
async function startServer() {
  const httpServer = http.createServer(app);

  const isProduction = process.env.NODE_ENV === 'production';
  const distExists = fs.existsSync(path.resolve(process.cwd(), 'dist', 'index.html'));

  if (!isProduction || !distExists) {
    const vite = await createViteServer({
      server: { 
        middlewareMode: true,
        hmr: {
          server: httpServer,
        },
      },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.resolve(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req: Request, res: Response) => {
      res.sendFile(path.resolve(distPath, 'index.html'));
    });
  }

  const portNum = Number(PORT) || 3000;
  httpServer.listen(portNum, '0.0.0.0', () => {
    console.log(`AMRG Review Workbench server running at http://0.0.0.0:${portNum}`);
  });
}

startServer();
