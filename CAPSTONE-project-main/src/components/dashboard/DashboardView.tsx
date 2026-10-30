/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { 
  AlertCircle, 
  ArrowRight, 
  BookOpen, 
  Building2, 
  CheckCircle2, 
  Clock, 
  Download, 
  FileSpreadsheet, 
  Plus, 
  ShieldCheck 
} from 'lucide-react';
import { AmrgLogo } from '../common/AmrgLogo.js';
import { useWorkbench } from '../../context/WorkbenchContext.js';

interface DashboardViewProps {
  onOpenClient: (id: string) => void;
  onOpenNewClient: () => void;
  onNavigateToTab: (tab: string) => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  onOpenClient,
  onOpenNewClient,
  onNavigateToTab,
}) => {
  const { clients, reports } = useWorkbench();

  const totalClients = clients.length;
  const completedRuns = clients.filter(c => c.currentRunStatus === 'Completed').length;
  const rerunsAvailable = clients.filter(c => c.documentsChangedSinceLastRun && c.lastRunAt).length;

  const handleDownloadBlankTemplate = () => {
    window.location.href = '/api/template/download';
  };

  const handleDownloadWordSkill = () => {
    window.location.href = '/api/skill/download-word';
  };

  return (
    <div className="space-y-8">
      {/* Welcome Banner with AMRG Global Brand Lockup */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 sm:p-7 shadow-xs flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
        <div className="flex items-start sm:items-center gap-5">
          <AmrgLogo size="xl" showSubtitle={false} className="shrink-0" />
          <div className="border-l border-slate-200 pl-5">
            <div className="flex items-center gap-2 text-xs font-semibold text-[#0A7C3B] uppercase tracking-wider">
              <ShieldCheck className="w-4 h-4" />
              <span>AMRG Global UAE Corporate, Tax & Advisory Practice</span>
            </div>
            <h1 className="text-2xl font-bold text-slate-900 mt-1">
              AMRG Review Workbench
            </h1>
            <p className="text-xs text-slate-600 mt-1.5 max-w-2xl leading-relaxed">
              Upload client corporate and statutory evidence, apply the published AMRG UAE onboarding skill, verify cross-document consistency, and produce the canonical 3-sheet Excel compliance deliverable.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <button
            onClick={onOpenNewClient}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-[#0A7C3B] hover:bg-[#08632f] text-white text-xs font-semibold rounded-lg shadow-xs transition-colors cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            <span>New Client Workspace</span>
          </button>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
        <div 
          onClick={() => onNavigateToTab('clients')}
          className="bg-white p-5 rounded-xl border border-slate-200 shadow-xs hover:border-slate-300 transition-colors cursor-pointer"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Client Workspaces
            </span>
            <div className="p-2 rounded-lg bg-slate-100 text-slate-600">
              <Building2 className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-slate-900">{totalClients}</span>
            <span className="text-xs text-slate-500">active {totalClients === 1 ? 'workspace' : 'workspaces'}</span>
          </div>
        </div>

        <div 
          onClick={() => onNavigateToTab('reports')}
          className="bg-white p-5 rounded-xl border border-slate-200 shadow-xs hover:border-slate-300 transition-colors cursor-pointer"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Generated Reports
            </span>
            <div className="p-2 rounded-lg bg-[#0A7C3B]/10 text-[#0A7C3B]">
              <FileSpreadsheet className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-slate-900">{reports.length}</span>
            <span className="text-xs text-slate-500">immutable Excel {reports.length === 1 ? 'deliverable' : 'deliverables'}</span>
          </div>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Completed Reviews
            </span>
            <div className="p-2 rounded-lg bg-emerald-100 text-emerald-700">
              <CheckCircle2 className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-slate-900">{completedRuns}</span>
            <span className="text-xs text-slate-500">
              {rerunsAvailable > 0 ? `(${rerunsAvailable} rerun available)` : 'up-to-date'}
            </span>
          </div>
        </div>
      </div>

      {/* Direct Deliverable Downloads Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-xs flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-emerald-50 text-[#0A7C3B] rounded-xl">
              <FileSpreadsheet className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900">Approved Excel Template</h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Download the canonical blank 12-sheet AMRG Global workbook template (.xlsx).
              </p>
            </div>
          </div>
          <button
            onClick={handleDownloadBlankTemplate}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-[#0A7C3B] border border-[#0A7C3B]/30 hover:bg-[#0A7C3B]/5 rounded-lg transition-colors cursor-pointer shrink-0"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Download Template</span>
          </button>
        </div>

        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-xs flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-blue-50 text-blue-700 rounded-xl">
              <BookOpen className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900">Published Skill Methodology</h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Download the complete AMRG UAE Onboarding Review Skill v2.4 as Word (.docx).
              </p>
            </div>
          </div>
          <button
            onClick={handleDownloadWordSkill}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-blue-700 border border-blue-200 hover:bg-blue-50 rounded-lg transition-colors cursor-pointer shrink-0"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Download Skill (.docx)</span>
          </button>
        </div>
      </div>

      {/* Recent Client Workspaces */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs">
        <div className="p-6 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold text-slate-900">Recent Onboarding Workspaces</h2>
            <p className="text-xs text-slate-500 mt-0.5">Active UAE client onboarding workspaces</p>
          </div>

          <button
            onClick={() => onNavigateToTab('clients')}
            className="text-xs font-semibold text-[#0A7C3B] hover:text-[#08632f] inline-flex items-center gap-1 cursor-pointer"
          >
            <span>View All Clients</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>

        {clients.length === 0 ? (
          <div className="p-12 text-center">
            <Building2 className="w-10 h-10 text-slate-300 mx-auto mb-2" />
            <p className="text-xs text-slate-500">No client workspaces created yet.</p>
            <button
              onClick={onOpenNewClient}
              className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#0A7C3B] text-white text-xs font-medium rounded-lg cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Create Client Workspace</span>
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-600">
              <thead className="bg-slate-50 text-[11px] font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-100">
                <tr>
                  <th className="px-6 py-3">Client</th>
                  <th className="px-6 py-3">Jurisdiction</th>
                  <th className="px-6 py-3">Review Status</th>
                  <th className="px-6 py-3">Last Run</th>
                  <th className="px-6 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-normal">
                {clients.slice(0, 5).map(c => (
                  <tr key={c.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="px-6 py-4 font-bold text-slate-900">
                      {c.name}
                    </td>
                    <td className="px-6 py-4 text-slate-700">
                      {c.jurisdiction} ({c.entityType})
                    </td>
                    <td className="px-6 py-4">
                      {c.documentsChangedSinceLastRun && c.lastRunAt ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-700">
                          <AlertCircle className="w-3.5 h-3.5" />
                          Rerun available
                        </span>
                      ) : c.currentRunStatus === 'Completed' ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          Completed
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-500">
                          <Clock className="w-3.5 h-3.5" />
                          Ready for review
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-slate-500">
                      {c.lastRunAt ? new Date(c.lastRunAt).toLocaleDateString() : '—'}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={() => onOpenClient(c.id)}
                        className="inline-flex items-center gap-1 text-xs font-semibold text-[#0A7C3B] hover:text-[#08632f] cursor-pointer"
                      >
                        <span>Open Workspace</span>
                        <ArrowRight className="w-3 h-3" />
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
