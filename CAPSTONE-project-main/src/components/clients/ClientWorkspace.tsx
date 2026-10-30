/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useRef, useState } from 'react';
import { 
  AlertCircle, 
  ArrowLeft, 
  Building2, 
  CheckCircle2, 
  Clock, 
  Download, 
  Eye, 
  EyeOff, 
  FileSpreadsheet, 
  FileText, 
  Play, 
  RotateCw, 
  Trash2, 
  Upload 
} from 'lucide-react';
import { apiFetch, useWorkbench } from '../../context/WorkbenchContext.js';
import { AmrgLogo } from '../common/AmrgLogo.js';
import { ClientEntity, GeneratedReport, RunSnapshot, UploadedDocument } from '../../types/workbench.js';

interface ClientWorkspaceProps {
  clientId: string;
  onBack: () => void;
}

export const ClientWorkspace: React.FC<ClientWorkspaceProps> = ({
  clientId,
  onBack,
}) => {
  const { showToast, refreshReports } = useWorkbench();
  const [client, setClient] = useState<ClientEntity | null>(null);
  const [documents, setDocuments] = useState<UploadedDocument[]>([]);
  const [runs, setRuns] = useState<RunSnapshot[]>([]);
  const [reports, setReports] = useState<GeneratedReport[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [isRunningReview, setIsRunningReview] = useState(false);
  const [runProgressMessage, setRunProgressMessage] = useState('');
  const [deleteConfirmDocId, setDeleteConfirmDocId] = useState<string | null>(null);
  
  // Inline editing state for client info
  const [isEditingInfo, setIsEditingInfo] = useState(false);
  const [editForm, setEditForm] = useState({
    name: '',
    entityType: '',
    jurisdiction: '',
    tradeLicenceNumber: '',
    registrationNumber: '',
    vatTrn: '',
    ctTrn: '',
    financialYearEnd: '',
  });

  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadClientWorkspace = async () => {
    try {
      setIsLoading(true);
      const res = await apiFetch(`/api/clients/${clientId}`);
      if (!res.ok) {
        showToast('Client workspace not found', 'error');
        onBack();
        return;
      }
      const data = await res.json();
      setClient(data.client);
      setDocuments(data.documents || []);
      setRuns(data.runs || []);
      setReports(data.reports || []);

      setEditForm({
        name: data.client.name || '',
        entityType: data.client.entityType || '',
        jurisdiction: data.client.jurisdiction || '',
        tradeLicenceNumber: data.client.tradeLicenceNumber || '',
        registrationNumber: data.client.registrationNumber || '',
        vatTrn: data.client.vatTrn || '',
        ctTrn: data.client.ctTrn || '',
        financialYearEnd: data.client.financialYearEnd || '',
      });
    } catch (err) {
      console.error('Failed to load client workspace:', err);
      showToast('Error loading workspace', 'error');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadClientWorkspace();
  }, [clientId]);

  // Handle Document Uploads
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i]);
    }

    try {
      setIsUploading(true);
      const sessionId = localStorage.getItem('amrg_session_id') || '';
      const res = await fetch(`/api/clients/${clientId}/documents`, {
        method: 'POST',
        headers: {
          'X-AMRG-Session': sessionId,
        },
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || 'Failed to upload documents');
      }

      showToast(`Uploaded ${files.length} document(s) successfully`, 'success');
      loadClientWorkspace();
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Upload failed', 'error');
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  // Toggle Document Exclusion
  const handleToggleExclude = async (docId: string) => {
    try {
      const res = await apiFetch(`/api/clients/${clientId}/documents/${docId}/exclude`, {
        method: 'POST',
      });
      if (res.ok) {
        showToast('Document exclusion status updated', 'info');
        loadClientWorkspace();
      }
    } catch (err) {
      showToast('Failed to update document exclusion', 'error');
    }
  };

  // Permanent Document Deletion
  const handleDeleteDocument = async (docId: string) => {
    try {
      const res = await apiFetch(`/api/clients/${clientId}/documents/${docId}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        showToast('Document permanently removed', 'info');
        setDeleteConfirmDocId(null);
        loadClientWorkspace();
      }
    } catch (err) {
      showToast('Failed to remove document', 'error');
    }
  };

  // Execute Review Run
  const handleRunReview = async () => {
    if (documents.filter(d => !d.isExcluded).length === 0) {
      showToast('Please upload at least one active document before running the review.', 'error');
      return;
    }

    try {
      setIsRunningReview(true);
      setRunProgressMessage('Loading approved published skill and processing evidence snapshot...');
      
      const res = await apiFetch(`/api/clients/${clientId}/run`, {
        method: 'POST',
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || 'Review execution failed.');
      }

      const data = await res.json();
      showToast(`Excel Report ${data.report.versionLabel} generated successfully!`, 'success');
      refreshReports();
      loadClientWorkspace();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Review run failed.';
      showToast(msg, 'error');
      loadClientWorkspace();
    } finally {
      setIsRunningReview(false);
      setRunProgressMessage('');
    }
  };

  // Download Report (.xlsx)
  const handleDownloadReport = (report: GeneratedReport) => {
    const sessionId = localStorage.getItem('amrg_session_id') || '';
    const downloadUrl = `/api/clients/${clientId}/reports/${report.id}/download?session_id=${sessionId}`;
    
    const a = document.createElement('a');
    a.href = downloadUrl;
    a.download = report.fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  // Save client edits
  const handleSaveClientInfo = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await apiFetch(`/api/clients/${clientId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editForm),
      });
      if (res.ok) {
        const updated = await res.json();
        setClient(updated);
        setIsEditingInfo(false);
        showToast('Client details updated', 'success');
      }
    } catch (err) {
      showToast('Failed to update client information', 'error');
    }
  };

  if (isLoading || !client) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="flex items-center gap-3 text-slate-500 text-sm">
          <RotateCw className="w-5 h-5 animate-spin text-[#0A7C3B]" />
          <span>Loading client onboarding workspace...</span>
        </div>
      </div>
    );
  }

  const activeDocsCount = documents.filter(d => !d.isExcluded).length;
  const latestReport = reports.length > 0 ? reports[0] : null;

  return (
    <div className="space-y-6">
      {/* Top Header & Breadcrumb */}
      <div className="flex items-center justify-between">
        <button
          onClick={onBack}
          className="inline-flex items-center gap-2 text-xs font-medium text-slate-600 hover:text-slate-900 transition-colors cursor-pointer py-1 px-2 rounded-md hover:bg-slate-100"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Clients</span>
        </button>

        <div className="flex items-center gap-3">
          {client.currentRunStatus === 'Processing' || isRunningReview ? (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-800">
              <RotateCw className="w-3.5 h-3.5 animate-spin" />
              Processing Review
            </span>
          ) : client.currentRunStatus === 'Completed' ? (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800">
              <CheckCircle2 className="w-3.5 h-3.5" />
              {runs[0]?.versionLabel || 'Completed'}
            </span>
          ) : client.currentRunStatus === 'Failed' ? (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-800">
              <AlertCircle className="w-3.5 h-3.5" />
              Run Failed
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-700">
              <Clock className="w-3.5 h-3.5" />
              Ready for Review
            </span>
          )}
        </div>
      </div>

      {/* Client Identity & Scope Banner */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-xs">
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-4">
            <div className="p-3 bg-[#0A7C3B]/10 text-[#0A7C3B] rounded-xl mt-1">
              <Building2 className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-xl font-bold text-slate-900">{client.name}</h1>
                <span className="px-2.5 py-0.5 text-xs font-medium bg-slate-100 text-slate-700 rounded-md">
                  {client.entityType}
                </span>
                <span className="px-2.5 py-0.5 text-xs font-medium bg-slate-100 text-slate-700 rounded-md">
                  {client.jurisdiction}
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1">
                Workspace ID: <span className="font-mono">{client.id}</span> • Registered FY End: {client.financialYearEnd || '31 December'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <AmrgLogo size="sm" showSubtitle={false} className="hidden sm:flex border border-slate-200/80 rounded-xl px-2.5 py-1 bg-slate-50/70" />
            <button
              onClick={() => setIsEditingInfo(!isEditingInfo)}
              className="text-xs text-[#0A7C3B] hover:text-[#08632f] font-medium px-3 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors cursor-pointer"
            >
              {isEditingInfo ? 'Cancel' : 'Edit Details'}
            </button>
          </div>
        </div>

        {/* Detailed Fields */}
        {!isEditingInfo ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6 pt-6 border-t border-slate-100 text-xs">
            <div>
              <span className="text-slate-400 block font-medium">Trade Licence No.</span>
              <span className="text-slate-800 font-semibold mt-0.5 block">
                {client.tradeLicenceNumber || 'Not specified'}
              </span>
            </div>
            <div>
              <span className="text-slate-400 block font-medium">Registration / Est. No.</span>
              <span className="text-slate-800 font-semibold mt-0.5 block">
                {client.registrationNumber || 'Not specified'}
              </span>
            </div>
            <div>
              <span className="text-slate-400 block font-medium">VAT TRN</span>
              <span className="text-slate-800 font-semibold mt-0.5 block">
                {client.vatTrn || 'Pending threshold testing'}
              </span>
            </div>
            <div>
              <span className="text-slate-400 block font-medium">Corporate Tax TRN</span>
              <span className="text-slate-800 font-semibold mt-0.5 block">
                {client.ctTrn || 'Registration Ack on file'}
              </span>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSaveClientInfo} className="mt-6 pt-6 border-t border-slate-100 space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="block text-[11px] font-semibold text-slate-600 mb-1">Legal Name</label>
                <input
                  type="text"
                  required
                  value={editForm.name}
                  onChange={e => setEditForm({ ...editForm, name: e.target.value })}
                  className="w-full px-3 py-1.5 text-xs border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-slate-600 mb-1">Entity Form</label>
                <input
                  type="text"
                  value={editForm.entityType}
                  onChange={e => setEditForm({ ...editForm, entityType: e.target.value })}
                  className="w-full px-3 py-1.5 text-xs border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-slate-600 mb-1">Jurisdiction</label>
                <input
                  type="text"
                  value={editForm.jurisdiction}
                  onChange={e => setEditForm({ ...editForm, jurisdiction: e.target.value })}
                  className="w-full px-3 py-1.5 text-xs border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-slate-600 mb-1">Trade Licence No.</label>
                <input
                  type="text"
                  value={editForm.tradeLicenceNumber}
                  onChange={e => setEditForm({ ...editForm, tradeLicenceNumber: e.target.value })}
                  className="w-full px-3 py-1.5 text-xs border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-slate-600 mb-1">Registration No.</label>
                <input
                  type="text"
                  value={editForm.registrationNumber}
                  onChange={e => setEditForm({ ...editForm, registrationNumber: e.target.value })}
                  className="w-full px-3 py-1.5 text-xs border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-slate-600 mb-1">Financial Year End</label>
                <input
                  type="text"
                  value={editForm.financialYearEnd}
                  onChange={e => setEditForm({ ...editForm, financialYearEnd: e.target.value })}
                  className="w-full px-3 py-1.5 text-xs border border-slate-300 rounded-md"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setIsEditingInfo(false)}
                className="px-3 py-1 text-xs text-slate-600 hover:text-slate-800"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-1 text-xs text-white bg-[#0A7C3B] hover:bg-[#08632f] rounded-md"
              >
                Save Changes
              </button>
            </div>
          </form>
        )}
      </div>

      {/* Rerun Notification Banner if Documents Changed */}
      {client.documentsChangedSinceLastRun && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-amber-600 shrink-0" />
            <div>
              <h4 className="text-sm font-semibold text-amber-900">
                Documents changed — rerun available
              </h4>
              <p className="text-xs text-amber-700">
                Evidence files have been added, removed, or excluded since the last run. Rerun the review to generate a new Excel deliverable version.
              </p>
            </div>
          </div>
          <button
            onClick={handleRunReview}
            disabled={isRunningReview || activeDocsCount === 0}
            className="inline-flex items-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white text-xs font-semibold rounded-lg shadow-xs transition-colors cursor-pointer disabled:bg-slate-300"
          >
            <RotateCw className={`w-3.5 h-3.5 ${isRunningReview ? 'animate-spin' : ''}`} />
            <span>Rerun Checks</span>
          </button>
        </div>
      )}

      {/* Main Action Card: Run Review & Latest Deliverable */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-xs">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div>
            <h2 className="text-base font-bold text-slate-900">
              UAE Onboarding Compliance Review
            </h2>
            <p className="text-xs text-slate-500 mt-1 max-w-2xl">
              Applies the approved AMRG UAE Onboarding Review Skill v2.4, evaluates cross-document consistency, verifies statutory deadlines, and compiles the official 12-sheet Excel deliverable.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleRunReview}
              disabled={isRunningReview || activeDocsCount === 0}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-[#0A7C3B] hover:bg-[#08632f] disabled:bg-slate-300 text-white text-sm font-semibold rounded-lg shadow-sm transition-colors cursor-pointer"
            >
              {isRunningReview ? (
                <>
                  <RotateCw className="w-4 h-4 animate-spin" />
                  <span>Processing...</span>
                </>
              ) : runs.length === 0 ? (
                <>
                  <Play className="w-4 h-4 fill-white" />
                  <span>Run Review</span>
                </>
              ) : (
                <>
                  <RotateCw className="w-4 h-4" />
                  <span>Rerun Review (New Version)</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Progress state */}
        {isRunningReview && (
          <div className="mt-4 p-4 bg-emerald-50 border border-emerald-200 rounded-lg">
            <div className="flex items-center gap-3 text-xs text-emerald-900 font-medium">
              <RotateCw className="w-4 h-4 animate-spin text-[#0A7C3B]" />
              <span>{runProgressMessage || 'Applying onboarding review rules...'}</span>
            </div>
          </div>
        )}

        {/* Error message display if failed */}
        {client.currentRunStatus === 'Failed' && client.lastRunError && (
          <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
              <div>
                <h4 className="text-xs font-bold text-red-900">Review Execution Halted</h4>
                <p className="text-xs text-red-700 mt-0.5">{client.lastRunError}</p>
              </div>
            </div>
          </div>
        )}

        {/* Latest Excel Deliverable Card */}
        {latestReport && (
          <div className="mt-6 p-4 rounded-xl border border-emerald-200 bg-emerald-50/40 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-[#0A7C3B] text-white rounded-lg">
                <FileSpreadsheet className="w-6 h-6" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h4 className="text-sm font-bold text-slate-900">{latestReport.fileName}</h4>
                  <span className="px-2 py-0.5 text-[11px] font-bold bg-[#0A7C3B] text-white rounded-md">
                    {latestReport.versionLabel.toUpperCase()} DELIVERABLE
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  Generated {new Date(latestReport.generatedAt).toLocaleString()} • Snapshot of {latestReport.includedDocumentsCount} documents • {(latestReport.fileSizeBytes / 1024).toFixed(1)} KB
                </p>
              </div>
            </div>

            <button
              onClick={() => handleDownloadReport(latestReport)}
              className="inline-flex items-center gap-2 px-4 py-2 bg-[#0A7C3B] hover:bg-[#08632f] text-white text-xs font-semibold rounded-lg shadow-xs transition-colors cursor-pointer shrink-0"
            >
              <Download className="w-4 h-4" />
              <span>Download Excel Deliverable</span>
            </button>
          </div>
        )}
      </div>

      {/* Evidence Documents Intake & Inventory */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs">
        <div className="p-6 border-b border-slate-100 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <h3 className="text-base font-bold text-slate-900">Evidence Document Inventory</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Upload PDF, DOCX, XLSX, PPT, PPTX, CSV, or ZIP files. All documents are stored in private server storage.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <input
              type="file"
              ref={fileInputRef}
              multiple
              onChange={handleFileUpload}
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              className="inline-flex items-center gap-2 px-4 py-2 bg-slate-900 hover:bg-slate-800 disabled:bg-slate-300 text-white text-xs font-medium rounded-lg shadow-xs transition-colors cursor-pointer"
            >
              <Upload className="w-4 h-4" />
              <span>{isUploading ? 'Uploading...' : 'Upload Documents'}</span>
            </button>
          </div>
        </div>

        {/* Documents Table */}
        {documents.length === 0 ? (
          <div className="p-12 text-center">
            <FileText className="w-10 h-10 text-slate-300 mx-auto mb-3" />
            <h4 className="text-sm font-semibold text-slate-700">No evidence documents uploaded yet</h4>
            <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
              Upload client constitutional documents, trade licences, tax acknowledgments, or agreements to commence onboarding checks.
            </p>
            <button
              onClick={() => fileInputRef.current?.click()}
              className="mt-4 inline-flex items-center gap-2 px-4 py-2 bg-[#0A7C3B] hover:bg-[#08632f] text-white text-xs font-medium rounded-lg shadow-xs transition-colors cursor-pointer"
            >
              <Upload className="w-4 h-4" />
              <span>Select Files or ZIP</span>
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-600">
              <thead className="bg-slate-50 text-[11px] font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-100">
                <tr>
                  <th className="px-6 py-3">File Name</th>
                  <th className="px-6 py-3">Category</th>
                  <th className="px-6 py-3">Size</th>
                  <th className="px-6 py-3">Uploaded</th>
                  <th className="px-6 py-3">Status in Review</th>
                  <th className="px-6 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-normal">
                {documents.map(doc => (
                  <tr 
                    key={doc.id}
                    className={`hover:bg-slate-50/70 transition-colors ${doc.isExcluded ? 'opacity-60 bg-slate-50/40' : ''}`}
                  >
                    <td className="px-6 py-4 font-medium text-slate-900 flex items-center gap-3">
                      <FileText className="w-4 h-4 text-slate-400 shrink-0" />
                      <span className="truncate max-w-xs sm:max-w-md" title={doc.originalName}>
                        {doc.originalName}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 text-slate-700">
                        {doc.category || 'Other'}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-slate-500">
                      {(doc.fileSize / 1024).toFixed(1)} KB
                    </td>
                    <td className="px-6 py-4 text-slate-500">
                      {new Date(doc.uploadedAt).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-4">
                      {doc.isExcluded ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-500">
                          <EyeOff className="w-3.5 h-3.5" />
                          Excluded from Review
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#0A7C3B]">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          Included in Snapshot
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-right space-x-2">
                      <button
                        onClick={() => handleToggleExclude(doc.id)}
                        className="text-xs text-slate-500 hover:text-slate-800 p-1 rounded transition-colors cursor-pointer"
                        title={doc.isExcluded ? 'Include in review' : 'Exclude from review'}
                      >
                        {doc.isExcluded ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                      </button>

                      {deleteConfirmDocId === doc.id ? (
                        <div className="inline-flex items-center gap-1.5 bg-red-50 p-1 rounded">
                          <span className="text-[10px] text-red-700">Delete?</span>
                          <button
                            onClick={() => handleDeleteDocument(doc.id)}
                            className="px-1.5 py-0.5 text-[10px] font-semibold bg-red-600 text-white rounded"
                          >
                            Yes
                          </button>
                          <button
                            onClick={() => setDeleteConfirmDocId(null)}
                            className="px-1.5 py-0.5 text-[10px] text-slate-600 hover:text-slate-800"
                          >
                            No
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setDeleteConfirmDocId(doc.id)}
                          className="text-xs text-red-500 hover:text-red-700 p-1 rounded transition-colors cursor-pointer"
                          title="Permanently remove file"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Generated Report Versions History */}
      {reports.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs">
          <div className="p-6 border-b border-slate-100">
            <h3 className="text-base font-bold text-slate-900">Generated Excel Deliverable Versions</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Every review run generates a distinct, immutable Excel deliverable preserving the exact snapshot of evidence evaluated.
            </p>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-600">
              <thead className="bg-slate-50 text-[11px] font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-100">
                <tr>
                  <th className="px-6 py-3">Version</th>
                  <th className="px-6 py-3">File Name</th>
                  <th className="px-6 py-3">Generated Date</th>
                  <th className="px-6 py-3">Processed Snapshot</th>
                  <th className="px-6 py-3">Applied Skill</th>
                  <th className="px-6 py-3 text-right">Deliverable</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-normal">
                {reports.map((rep, idx) => (
                  <tr key={rep.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="px-6 py-4 font-bold text-slate-900">
                      <span className={`px-2.5 py-1 rounded-md text-xs font-bold ${
                        idx === 0 
                          ? 'bg-[#0A7C3B] text-white' 
                          : 'bg-slate-100 text-slate-700'
                      }`}>
                        {rep.versionLabel.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-6 py-4 font-medium text-slate-800">
                      {rep.fileName}
                    </td>
                    <td className="px-6 py-4 text-slate-500">
                      {new Date(rep.generatedAt).toLocaleString()}
                    </td>
                    <td className="px-6 py-4">
                      <span className="font-semibold text-slate-700">
                        {rep.includedDocumentsCount} documents
                      </span>
                      {rep.includedDocumentNames && rep.includedDocumentNames.length > 0 && (
                        <p className="text-[11px] text-slate-400 mt-0.5 truncate max-w-xs">
                          {rep.includedDocumentNames.slice(0, 3).join(', ')}
                          {rep.includedDocumentNames.length > 3 && ` +${rep.includedDocumentNames.length - 3} more`}
                        </p>
                      )}
                    </td>
                    <td className="px-6 py-4 text-slate-500">
                      <span className="text-[11px] font-mono">{rep.skillVersion}</span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={() => handleDownloadReport(rep)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#0A7C3B] hover:bg-[#08632f] text-white text-xs font-semibold rounded-lg shadow-xs transition-colors cursor-pointer"
                      >
                        <Download className="w-3.5 h-3.5" />
                        <span>Download .xlsx</span>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
