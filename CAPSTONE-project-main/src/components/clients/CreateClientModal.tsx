/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from 'react';
import { ArrowRight, FileText, Sparkles, X } from 'lucide-react';
import { AmrgLogo } from '../common/AmrgLogo.js';
import { useWorkbench } from '../../context/WorkbenchContext.js';

interface CreateClientModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (clientId: string) => void;
}

export const CreateClientModal: React.FC<CreateClientModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const { createClient } = useWorkbench();
  const [name, setName] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setErrorMessage('Company name is compulsory.');
      return;
    }

    try {
      setIsSubmitting(true);
      setErrorMessage('');
      const newClient = await createClient({
        name: name.trim(),
        entityType: 'To be extracted from documents',
        jurisdiction: 'To be extracted from documents',
        financialYearEnd: 'To be extracted from documents',
      });

      setName('');
      onSuccess(newClient.id);
      onClose();
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to create client workspace');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full border border-slate-200 overflow-hidden transform transition-all">
        {/* Modal Header with Official AMRG Global Logo */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-slate-100 bg-gradient-to-r from-slate-50 to-white">
          <div className="flex items-center gap-3">
            <AmrgLogo size="md" showSubtitle={true} />
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer"
            aria-label="Close modal"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form Body - Solely Client Company Name */}
        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          {errorMessage && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
              {errorMessage}
            </div>
          )}

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="block text-xs font-bold text-slate-800 uppercase tracking-wide">
                Company / Client Legal Name <span className="text-red-500">*</span>
              </label>
              <span className="text-[11px] font-medium text-[#0A7C3B] bg-[#0A7C3B]/10 px-2 py-0.5 rounded-full">
                Compulsory Field
              </span>
            </div>
            <input
              type="text"
              required
              placeholder="e.g. Quadria Healthcare GCC Consulting Ltd"
              value={name}
              onChange={e => setName(e.target.value)}
              className="w-full px-3.5 py-2.5 text-sm font-medium border border-slate-300 rounded-xl focus:outline-hidden focus:ring-2 focus:ring-[#0A7C3B] focus:border-[#0A7C3B] transition-all bg-slate-50/50 focus:bg-white"
              autoFocus
            />
          </div>

          {/* Intelligent Document Extraction Banner */}
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80 space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-800">
              <Sparkles className="w-4 h-4 text-[#0A7C3B]" />
              <span>Automated Document Extraction</span>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              Company name is the <strong>only compulsory detail</strong> needed to initialize the workspace. All other particulars will be automatically extracted directly from your uploaded evidence:
            </p>
            <ul className="text-[11px] text-slate-500 space-y-1 pt-1 list-disc list-inside">
              <li>Legal form & licensing authority jurisdiction</li>
              <li>Trade licence & commercial registration numbers</li>
              <li>VAT TRN & Corporate Tax TRN</li>
              <li>Financial year-end & reporting periods</li>
            </ul>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-4 py-2 text-xs font-medium text-slate-600 hover:text-slate-900 border border-slate-200 hover:bg-slate-100 rounded-xl transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || !name.trim()}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-[#0A7C3B] hover:bg-[#08632f] disabled:bg-slate-300 disabled:cursor-not-allowed text-white text-xs font-semibold rounded-xl shadow-md transition-all cursor-pointer"
            >
              <span>{isSubmitting ? 'Creating...' : 'Create Workspace'}</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
