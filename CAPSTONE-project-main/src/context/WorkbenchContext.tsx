/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { createContext, useContext, useEffect, useState } from 'react';
import { ClientEntity, GeneratedReport } from '../types/workbench.js';

interface Toast {
  id: string;
  type: 'success' | 'error' | 'info';
  message: string;
}

interface WorkbenchContextType {
  sessionId: string;
  clients: ClientEntity[];
  reports: GeneratedReport[];
  activeClientId: string | null;
  setActiveClientId: (id: string | null) => void;
  refreshClients: () => Promise<void>;
  refreshReports: () => Promise<void>;
  createClient: (data: Partial<ClientEntity>) => Promise<ClientEntity>;
  deleteClient: (id: string) => Promise<boolean>;
  updateClient: (id: string, updates: Partial<ClientEntity>) => Promise<ClientEntity>;
  resetSession: () => Promise<void>;
  toasts: Toast[];
  showToast: (message: string, type?: 'success' | 'error' | 'info') => void;
  dismissToast: (id: string) => void;
  isAiConfigured: boolean;
}

const WorkbenchContext = createContext<WorkbenchContextType | undefined>(undefined);

// Helper for session-authenticated fetch
export function apiFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const sessionId = localStorage.getItem('amrg_session_id') || '';
  const headers = new Headers(options.headers || {});
  if (sessionId) {
    headers.set('X-AMRG-Session', sessionId);
  }
  return fetch(url, { ...options, headers });
}

export const WorkbenchProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [sessionId, setSessionId] = useState<string>(() => {
    return localStorage.getItem('amrg_session_id') || '';
  });
  const [clients, setClients] = useState<ClientEntity[]>([]);
  const [reports, setReports] = useState<GeneratedReport[]>([]);
  const [activeClientId, setActiveClientId] = useState<string | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [isAiConfigured, setIsAiConfigured] = useState<boolean>(true);

  const showToast = (message: string, type: 'success' | 'error' | 'info' = 'info') => {
    const id = Date.now().toString();
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => dismissToast(id), 5000);
  };

  const dismissToast = (id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };

  // Initialize session
  useEffect(() => {
    apiFetch('/api/session')
      .then(res => res.json())
      .then(data => {
        if (data.sessionId) {
          setSessionId(data.sessionId);
          localStorage.setItem('amrg_session_id', data.sessionId);
        }
      })
      .catch(console.error);

    apiFetch('/api/health')
      .then(res => res.json())
      .then(data => {
        setIsAiConfigured(data.aiConfigured !== false);
      })
      .catch(console.error);
  }, []);

  const refreshClients = async () => {
    try {
      const res = await apiFetch('/api/clients');
      if (res.ok) {
        const data = await res.json();
        setClients(data);
      }
    } catch (err) {
      console.error('Failed to fetch clients:', err);
    }
  };

  const refreshReports = async () => {
    try {
      const res = await apiFetch('/api/reports');
      if (res.ok) {
        const data = await res.json();
        setReports(data);
      }
    } catch (err) {
      console.error('Failed to fetch reports:', err);
    }
  };

  useEffect(() => {
    refreshClients();
    refreshReports();
  }, [sessionId]);

  const createClient = async (data: Partial<ClientEntity>): Promise<ClientEntity> => {
    const res = await apiFetch('/api/clients', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || 'Failed to create client workspace');
    }

    const newClient = await res.json();
    setClients(prev => [...prev, newClient]);
    showToast(`Client workspace created: ${newClient.name}`, 'success');
    return newClient;
  };

  const deleteClient = async (id: string): Promise<boolean> => {
    const res = await apiFetch(`/api/clients/${id}`, {
      method: 'DELETE',
    });

    if (res.ok) {
      setClients(prev => prev.filter(c => c.id !== id));
      if (activeClientId === id) {
        setActiveClientId(null);
      }
      showToast('Client workspace deleted', 'info');
      refreshReports();
      return true;
    }
    return false;
  };

  const updateClient = async (id: string, updates: Partial<ClientEntity>): Promise<ClientEntity> => {
    const res = await apiFetch(`/api/clients/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    });

    if (!res.ok) {
      throw new Error('Failed to update client details');
    }

    const updated = await res.json();
    setClients(prev => prev.map(c => (c.id === id ? updated : c)));
    showToast('Client details updated', 'success');
    return updated;
  };

  const resetSession = async (): Promise<void> => {
    try {
      await apiFetch('/api/session/reset', { method: 'POST' });
      setClients([]);
      setReports([]);
      setActiveClientId(null);
      showToast('Session cleared. Starting with fresh clean workspace.', 'info');
    } catch (err) {
      console.error('Failed to reset session:', err);
    }
  };

  return (
    <WorkbenchContext.Provider
      value={{
        sessionId,
        clients,
        reports,
        activeClientId,
        setActiveClientId,
        refreshClients,
        refreshReports,
        createClient,
        deleteClient,
        updateClient,
        resetSession,
        toasts,
        showToast,
        dismissToast,
        isAiConfigured,
      }}
    >
      {children}
    </WorkbenchContext.Provider>
  );
};

export const useWorkbench = () => {
  const context = useContext(WorkbenchContext);
  if (!context) {
    throw new Error('useWorkbench must be used within a WorkbenchProvider');
  }
  return context;
};
