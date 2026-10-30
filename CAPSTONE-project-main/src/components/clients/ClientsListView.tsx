/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from 'react';
import { 
  AlertCircle, 
  ArrowRight, 
  Building2, 
  CheckCircle2, 
  Clock, 
  FileText, 
  Plus, 
  Search, 
  Trash2 
} from 'lucide-react';
import { AmrgLogo } from '../common/AmrgLogo.js';
import { useWorkbench } from '../../context/WorkbenchContext.js';

interface ClientsListViewProps {
  onOpenClient: (id: string) => void;
  onOpenNewClient: () => void;
}

export const ClientsListView: React.FC<ClientsListViewProps> = ({
  onOpenClient,
  onOpenNewClient,
}) => {
  const { clients, deleteClient } = useWorkbench();
  const [searchTerm, setSearchTerm] = useState('');
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  const filteredClients = clients.filter(c =>
    c.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    c.jurisdiction.toLowerCase().includes(searchTerm.toLowerCase()) ||
    c.entityType.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* Header bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
        <div className="flex items-center gap-4">
          <AmrgLogo size="md" showSubtitle={false} className="shrink-0" />
          <div className="border-l border-slate-200 pl-4">
            <h1 className="text-xl font-bold text-slate-900">Client Onboarding Workspaces</h1>
            <p className="text-xs text-slate-500 mt-0.5">
              Manage UAE onboarding workspaces, evidence files, and generated Excel deliverables.
            </p>
          </div>
        </div>

        <button
          onClick={onOpenNewClient}
          className="inline-flex items-center gap-2 px-4 py-2 bg-[#0A7C3B] hover:bg-[#08632f] text-white text-xs font-semibold rounded-xl shadow-xs transition-colors cursor-pointer shrink-0"
        >
          <Plus className="w-4 h-4" />
          <span>New Client</span>
        </button>
      </div>

      {/* Search Input */}
      <div className="bg-white p-3 rounded-xl border border-slate-200 shadow-xs flex items-center gap-3">
        <Search className="w-4 h-4 text-slate-400 ml-1" />
        <input
          type="text"
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
          placeholder="Search clients by name, jurisdiction, or entity type..."
          className="w-full text-xs text-slate-700 bg-transparent focus:outline-hidden"
        />
      </div>

      {/* Clients Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs">
        {clients.length === 0 ? (
          <div className="p-16 text-center">
            <Building2 className="w-12 h-12 text-slate-300 mx-auto mb-3" />
            <h3 className="text-sm font-semibold text-slate-800">No client workspaces yet</h3>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
              Create your first client onboarding workspace to upload documents and generate the approved Excel deliverable.
            </p>
            <button
              onClick={onOpenNewClient}
              className="mt-4 inline-flex items-center gap-2 px-4 py-2 bg-[#0A7C3B] hover:bg-[#08632f] text-white text-xs font-semibold rounded-lg shadow-xs transition-colors cursor-pointer"
            >
              <Plus className="w-4 h-4" />
              <span>Create Client Workspace</span>
            </button>
          </div>
        ) : filteredClients.length === 0 ? (
          <div className="p-12 text-center text-xs text-slate-500">
            No clients match "{searchTerm}".
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-600">
              <thead className="bg-slate-50 text-[11px] font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-100">
                <tr>
                  <th className="px-6 py-3.5">Client Legal Name</th>
                  <th className="px-6 py-3.5">Jurisdiction & Form</th>
                  <th className="px-6 py-3.5">Compliance Status</th>
                  <th className="px-6 py-3.5">Last Run Date</th>
                  <th className="px-6 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-normal">
                {filteredClients.map(client => {
                  const hasRun = client.lastRunAt;
                  const changed = client.documentsChangedSinceLastRun;

                  return (
                    <tr
                      key={client.id}
                      className="hover:bg-slate-50/70 transition-colors"
                    >
                      <td className="px-6 py-4">
                        <div 
                          onClick={() => onOpenClient(client.id)}
                          className="font-bold text-slate-900 text-sm hover:text-[#0A7C3B] cursor-pointer"
                        >
                          {client.name}
                        </div>
                        <p className="text-[11px] text-slate-400 mt-0.5">
                          ID: <span className="font-mono">{client.id}</span>
                        </p>
                      </td>

                      <td className="px-6 py-4">
                        <div className="font-medium text-slate-800">{client.jurisdiction}</div>
                        <div className="text-[11px] text-slate-400">{client.entityType}</div>
                      </td>

                      <td className="px-6 py-4">
                        {changed && hasRun ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                            <AlertCircle className="w-3.5 h-3.5" />
                            Documents changed — rerun available
                          </span>
                        ) : client.currentRunStatus === 'Completed' ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            Completed
                          </span>
                        ) : client.currentRunStatus === 'Failed' ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-red-50 text-red-700 border border-red-200">
                            <AlertCircle className="w-3.5 h-3.5" />
                            Run Failed
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-slate-100 text-slate-600">
                            <Clock className="w-3.5 h-3.5" />
                            No runs yet
                          </span>
                        )}
                      </td>

                      <td className="px-6 py-4 text-slate-500">
                        {client.lastRunAt 
                          ? new Date(client.lastRunAt).toLocaleDateString()
                          : 'Not yet run'}
                      </td>

                      <td className="px-6 py-4 text-right space-x-2">
                        <button
                          onClick={() => onOpenClient(client.id)}
                          className="inline-flex items-center gap-1 px-3 py-1.5 bg-slate-900 hover:bg-slate-800 text-white text-xs font-medium rounded-lg transition-colors cursor-pointer"
                        >
                          <span>Open Workspace</span>
                          <ArrowRight className="w-3.5 h-3.5" />
                        </button>

                        {deleteConfirmId === client.id ? (
                          <div className="inline-flex items-center gap-1 bg-red-50 p-1 rounded-lg">
                            <span className="text-[10px] text-red-700">Delete?</span>
                            <button
                              onClick={() => deleteClient(client.id)}
                              className="px-1.5 py-0.5 text-[10px] font-semibold bg-red-600 text-white rounded"
                            >
                              Yes
                            </button>
                            <button
                              onClick={() => setDeleteConfirmId(null)}
                              className="px-1.5 py-0.5 text-[10px] text-slate-600"
                            >
                              No
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => setDeleteConfirmId(client.id)}
                            className="p-1.5 text-slate-400 hover:text-red-600 transition-colors cursor-pointer rounded"
                            title="Delete workspace"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
