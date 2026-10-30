/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from 'react';
import { 
  BookOpen, 
  CheckCircle2, 
  Download, 
  FileSpreadsheet, 
  Lock, 
  RotateCw, 
  ShieldCheck, 
  Trash2 
} from 'lucide-react';
import { AmrgLogo } from '../common/AmrgLogo.js';
import { useWorkbench } from '../../context/WorkbenchContext.js';

export const SettingsView: React.FC = () => {
  const { sessionId, isAiConfigured, resetSession } = useWorkbench();
  const [isResetting, setIsResetting] = useState(false);
  const [showResetConfirm, setShowResetConfirm] = useState(false);

  const handleDownloadBlankTemplate = () => {
    window.location.href = '/api/template/download';
  };

  const handleDownloadWordSkill = () => {
    window.location.href = '/api/skill/download-word';
  };

  const handleResetSession = async () => {
    try {
      setIsResetting(true);
      await resetSession();
      setShowResetConfirm(false);
    } finally {
      setIsResetting(false);
    }
  };

  return (
    <div className="space-y-8 max-w-4xl mx-auto">
      <div className="flex items-center gap-4 bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
        <AmrgLogo size="md" showSubtitle={false} className="shrink-0" />
        <div className="border-l border-slate-200 pl-4">
          <h1 className="text-xl font-bold text-slate-900">Settings & Approved Deliverables</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Download the canonical AMRG Excel template, access the published onboarding skill methodology, and manage private session isolation.
          </p>
        </div>
      </div>

      {/* Deliverable Downloads Section */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-xs space-y-6">
        <div className="border-b border-slate-100 pb-4">
          <h2 className="text-base font-bold text-slate-900">Approved Practice Deliverables</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Download official AMRG Global UAE onboarding assets directly from private server storage.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {/* Approved Excel Output Template */}
          <div className="p-5 rounded-xl border border-slate-200 bg-slate-50/50 flex flex-col justify-between space-y-4">
            <div className="flex items-start gap-3">
              <div className="p-2.5 bg-emerald-100 text-[#0A7C3B] rounded-lg mt-0.5">
                <FileSpreadsheet className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-slate-900">Approved Excel Template</h3>
                <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                  Canonical 3-sheet AMRG workbook containing 1_Client_Details, 2_Documents checklist, and 3_Issues register with column K formula.
                </p>
              </div>
            </div>

            <button
              onClick={handleDownloadBlankTemplate}
              className="w-full inline-flex items-center justify-center gap-2 px-4 py-2 bg-[#0A7C3B] hover:bg-[#08632f] text-white text-xs font-semibold rounded-lg shadow-xs transition-colors cursor-pointer"
            >
              <Download className="w-4 h-4" />
              <span>Download Blank Template (.xlsx)</span>
            </button>
          </div>

          {/* Published Skill Word Document */}
          <div className="p-5 rounded-xl border border-slate-200 bg-slate-50/50 flex flex-col justify-between space-y-4">
            <div className="flex items-start gap-3">
              <div className="p-2.5 bg-blue-100 text-blue-700 rounded-lg mt-0.5">
                <BookOpen className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-slate-900">Published Skill Methodology</h3>
                <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                  Official published AMRG UAE Onboarding Review Skill v2.4 (October 2026). Complete review map, domain checks, and legal catalogue.
                </p>
              </div>
            </div>

            <button
              onClick={handleDownloadWordSkill}
              className="w-full inline-flex items-center justify-center gap-2 px-4 py-2 bg-blue-700 hover:bg-blue-800 text-white text-xs font-semibold rounded-lg shadow-xs transition-colors cursor-pointer"
            >
              <Download className="w-4 h-4" />
              <span>Download Skill Document (.docx)</span>
            </button>
          </div>
        </div>
      </div>

      {/* Session & Privacy Isolation */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-xs space-y-6">
        <div className="border-b border-slate-100 pb-4">
          <div className="flex items-center gap-2">
            <Lock className="w-4 h-4 text-[#0A7C3B]" />
            <h2 className="text-base font-bold text-slate-900">Private Session Isolation</h2>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Every visitor operates in an isolated private session. Uploaded client files and reports are strictly segregated and protected from public access.
          </p>
        </div>

        <div className="space-y-3 text-xs">
          <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg border border-slate-200">
            <div>
              <span className="font-semibold text-slate-700 block">Session Identifier</span>
              <span className="font-mono text-slate-500 text-[11px]">{sessionId || 'Active'}</span>
            </div>
            <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
              <CheckCircle2 className="w-3.5 h-3.5" />
              Isolated
            </span>
          </div>

          <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg border border-slate-200">
            <div>
              <span className="font-semibold text-slate-700 block">AI Backend Integration</span>
              <span className="text-slate-500 text-[11px]">Server-side multimodal Gemini API</span>
            </div>
            <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
              <CheckCircle2 className="w-3.5 h-3.5" />
              {isAiConfigured ? 'Connected' : 'Deterministic Mode'}
            </span>
          </div>

          <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg border border-slate-200">
            <div>
              <span className="font-semibold text-slate-700 block">Server-Side Skill Version</span>
              <span className="text-slate-500 text-[11px]">AMRG UAE Onboarding Review Skill v2.4 (Published October 2026)</span>
            </div>
            <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
              <ShieldCheck className="w-3.5 h-3.5" />
              Verified & Active
            </span>
          </div>
        </div>

        {/* Clear Session Action */}
        <div className="pt-4 border-t border-slate-100 flex items-center justify-between">
          <div>
            <h4 className="text-xs font-bold text-slate-900">Reset Private Session Data</h4>
            <p className="text-[11px] text-slate-500 mt-0.5">
              Clear all uploaded documents, client records, and generated Excel deliverables for this session.
            </p>
          </div>

          {showResetConfirm ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-red-700 font-medium">Are you sure?</span>
              <button
                onClick={handleResetSession}
                disabled={isResetting}
                className="px-3 py-1.5 text-xs font-semibold bg-red-600 hover:bg-red-700 text-white rounded-lg cursor-pointer"
              >
                {isResetting ? 'Clearing...' : 'Confirm Clear'}
              </button>
              <button
                onClick={() => setShowResetConfirm(false)}
                className="px-3 py-1.5 text-xs text-slate-600 hover:text-slate-800 cursor-pointer"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowResetConfirm(true)}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-red-600 hover:text-red-700 hover:bg-red-50 border border-red-200 rounded-lg transition-colors cursor-pointer"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Clear Session Data</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
