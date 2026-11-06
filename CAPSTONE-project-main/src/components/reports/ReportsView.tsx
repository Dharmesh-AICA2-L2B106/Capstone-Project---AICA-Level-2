/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from 'react';
import { 
  Download, 
  FileSpreadsheet, 
  Search 
} from 'lucide-react';
import { AmrgLogo } from '../common/AmrgLogo.js';
import { useWorkbench } from '../../context/WorkbenchContext.js';
import { GeneratedReport } from '../../types/workbench.js';

export const ReportsView: React.FC = () => {
  const { reports } = useWorkbench();
  const [searchTerm, setSearchTerm] = useState('');

  const filteredReports = reports.filter(r =>
    r.clientName.toLowerCase().includes(searchTerm.toLowerCase()) ||
    r.fileName.toLowerCase().includes(searchTerm.toLowerCase()) ||
    r.versionLabel.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleDownload = (report: GeneratedReport) => {
    const sessionId = localStorage.getItem('amrg_session_id') || '';
    const downloadUrl = `/api/clients/${report.clientId}/reports/${report.id}/download?session_id=${sessionId}`;
    
    const a = document.createElement('a');
    a.href = downloadUrl;
    a.download = report.fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  return (
    <div className="space-y-6">
      {/* Header bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
        <div className="flex items-center gap-4">
          <AmrgLogo size="md" showSubtitle={false} className="shrink-0" />
          <div className="border-l border-slate-200 pl-4">
            <h1 className="text-xl font-bold text-slate-900">Generated Excel Deliverables</h1>
            <p className="text-xs text-slate-500 mt-0.5">
              Official 3-sheet Excel workbooks generated across your client onboarding workspaces.
            </p>
          </div>
        </div>

        <button
          onClick={() => { window.location.href = '/api/template/download'; }}
          className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-[#0A7C3B] border border-[#0A7C3B]/30 hover:bg-[#0A7C3B]/5 rounded-xl transition-colors cursor-pointer shrink-0"
        >
          <Download className="w-3.5 h-3.5" />
          <span>Download Blank Template</span>
        </button>
      </div>

      {/* Search Input */}
      <div className="bg-white p-3 rounded-xl border border-slate-200 shadow-xs flex items-center gap-3">
        <Search className="w-4 h-4 text-slate-400 ml-1" />
        <input
          type="text"
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
          placeholder="Search reports by client name or filename..."
          className="w-full text-xs text-slate-700 bg-transparent focus:outline-hidden"
        />
      </div>

      {/* Reports Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs">
        {reports.length === 0 ? (
          <div className="p-16 text-center">
            <FileSpreadsheet className="w-12 h-12 text-slate-300 mx-auto mb-3" />
            <h3 className="text-sm font-semibold text-slate-800">No Excel reports generated yet</h3>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
              Execute a review run inside a client workspace to compile the approved 12-sheet Excel deliverable.
            </p>
          </div>
        ) : filteredReports.length === 0 ? (
          <div className="p-12 text-center text-xs text-slate-500">
            No reports match "{searchTerm}".
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-600">
              <thead className="bg-slate-50 text-[11px] font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-100">
                <tr>
                  <th className="px-6 py-3.5">Client & Version</th>
                  <th className="px-6 py-3.5">Deliverable File Name</th>
                  <th className="px-6 py-3.5">Generated Date</th>
                  <th className="px-6 py-3.5">Evidence Snapshot</th>
                  <th className="px-6 py-3.5">Applied Skill</th>
                  <th className="px-6 py-3.5 text-right">Download</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-normal">
                {filteredReports.map(rep => (
                  <tr key={rep.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="px-6 py-4">
                      <div className="font-bold text-slate-900 text-sm">{rep.clientName}</div>
                      <span className="inline-block px-2 py-0.5 mt-1 text-[11px] font-bold bg-[#0A7C3B] text-white rounded">
                        {rep.versionLabel.toUpperCase()}
                      </span>
                    </td>

                    <td className="px-6 py-4 font-medium text-slate-800">
                      {rep.fileName}
                      <p className="text-[11px] text-slate-400 mt-0.5">
                        {(rep.fileSizeBytes / 1024).toFixed(1)} KB • Microsoft Excel (.xlsx)
                      </p>
                    </td>

                    <td className="px-6 py-4 text-slate-500">
                      {new Date(rep.generatedAt).toLocaleString()}
                    </td>

                    <td className="px-6 py-4">
                      <span className="font-semibold text-slate-700">
                        {rep.includedDocumentsCount} documents
                      </span>
                      {rep.includedDocumentNames && rep.includedDocumentNames.length > 0 && (
                        <p className="text-[11px] text-slate-400 mt-0.5 truncate max-w-xs" title={rep.includedDocumentNames.join(', ')}>
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
                        onClick={() => handleDownload(rep)}
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
        )}
      </div>
    </div>
  );
};
