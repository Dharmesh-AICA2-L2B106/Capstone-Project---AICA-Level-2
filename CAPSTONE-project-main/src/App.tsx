/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from 'react';
import { ClientsListView } from './components/clients/ClientsListView.js';
import { ClientWorkspace } from './components/clients/ClientWorkspace.js';
import { CreateClientModal } from './components/clients/CreateClientModal.js';
import { DashboardView } from './components/dashboard/DashboardView.js';
import { Header } from './components/layout/Header.js';
import { AmrgLogo } from './components/common/AmrgLogo.js';
import { ReportsView } from './components/reports/ReportsView.js';
import { SettingsView } from './components/settings/SettingsView.js';
import { useWorkbench, WorkbenchProvider } from './context/WorkbenchContext.js';

function MainApp() {
  const [currentTab, setCurrentTab] = useState('dashboard');
  const [showNewClientModal, setShowNewClientModal] = useState(false);
  const { 
    activeClientId, 
    setActiveClientId, 
    toasts, 
    dismissToast 
  } = useWorkbench();

  const handleOpenClient = (id: string) => {
    setActiveClientId(id);
    setCurrentTab('clients');
  };

  const handleBackFromWorkspace = () => {
    setActiveClientId(null);
  };

  const handleClientCreated = (newId: string) => {
    setActiveClientId(newId);
    setCurrentTab('clients');
  };

  return (
    <div className="min-h-screen bg-[#F8FAFC] text-slate-800 flex flex-col font-sans antialiased">
      {/* Global AMRG Header */}
      <Header
        currentTab={currentTab}
        onSelectTab={tab => {
          setCurrentTab(tab);
          if (tab !== 'clients') {
            setActiveClientId(null);
          }
        }}
        onOpenNewClient={() => setShowNewClientModal(true)}
      />

      {/* Main Viewport */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {currentTab === 'dashboard' && (
          <DashboardView
            onOpenClient={handleOpenClient}
            onOpenNewClient={() => setShowNewClientModal(true)}
            onNavigateToTab={tab => {
              setCurrentTab(tab);
              if (tab !== 'clients') {
                setActiveClientId(null);
              }
            }}
          />
        )}

        {currentTab === 'clients' && (
          <>
            {activeClientId ? (
              <ClientWorkspace
                clientId={activeClientId}
                onBack={handleBackFromWorkspace}
              />
            ) : (
              <ClientsListView
                onOpenClient={handleOpenClient}
                onOpenNewClient={() => setShowNewClientModal(true)}
              />
            )}
          </>
        )}

        {currentTab === 'reports' && <ReportsView />}

        {currentTab === 'settings' && <SettingsView />}
      </main>

      {/* Grounded AMRG Global Footer */}
      <footer className="border-t border-slate-200 bg-white py-6 mt-auto">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-4">
          <AmrgLogo size="sm" showSubtitle={true} />
          
          <div className="text-center sm:text-right">
            <p className="text-[11px] text-slate-500 font-medium">
              AMRG Global UAE Corporate, Tax & Advisory Practice • Dubai • Abu Dhabi • DIFC
            </p>
            <p className="text-[10px] text-slate-400 mt-0.5">
              Approved UAE Onboarding Review Skill v2.4 • Confidential Client Deliverables
            </p>
          </div>
        </div>
      </footer>

      {/* Create Client Modal */}
      <CreateClientModal
        isOpen={showNewClientModal}
        onClose={() => setShowNewClientModal(false)}
        onSuccess={handleClientCreated}
      />

      {/* Global Toast Notifications */}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm pointer-events-none">
        {toasts.map(toast => (
          <div
            key={toast.id}
            onClick={() => dismissToast(toast.id)}
            className={`pointer-events-auto px-4 py-3 rounded-lg shadow-lg text-xs font-medium cursor-pointer transition-all border ${
              toast.type === 'success'
                ? 'bg-slate-900 text-white border-emerald-600'
                : toast.type === 'error'
                ? 'bg-red-900 text-white border-red-700'
                : 'bg-slate-800 text-white border-slate-700'
            }`}
          >
            {toast.message}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function App() {
  return (
    <WorkbenchProvider>
      <MainApp />
    </WorkbenchProvider>
  );
}
