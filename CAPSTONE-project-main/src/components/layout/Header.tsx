/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { 
  Building2, 
  FileSpreadsheet, 
  LayoutDashboard, 
  Plus, 
  Settings 
} from 'lucide-react';
import { AmrgLogo } from '../common/AmrgLogo.js';

interface HeaderProps {
  currentTab: string;
  onSelectTab: (tab: string) => void;
  onOpenNewClient: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  currentTab,
  onSelectTab,
  onOpenNewClient,
}) => {
  const navTabs = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'clients', label: 'Clients', icon: Building2 },
    { id: 'reports', label: 'Reports', icon: FileSpreadsheet },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-40 shadow-xs">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Brand & Identity */}
          <div className="flex items-center gap-6">
            <div 
              onClick={() => onSelectTab('dashboard')}
              className="cursor-pointer transition-opacity hover:opacity-90 flex items-center"
            >
              <AmrgLogo size="md" />
            </div>

            {/* Navigation Tabs (Dashboard, Clients, Reports, Settings) */}
            <nav className="hidden md:flex items-center space-x-1 ml-4 border-l border-slate-200 pl-4">
              {navTabs.map(tab => {
                const Icon = tab.icon;
                const isActive = currentTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    onClick={() => onSelectTab(tab.id)}
                    className={`flex items-center gap-2 px-3.5 py-2 text-sm font-medium rounded-md transition-colors ${
                      isActive
                        ? 'bg-[#0A7C3B]/10 text-[#0A7C3B] font-semibold'
                        : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                    }`}
                  >
                    <Icon className="w-4 h-4" />
                    <span>{tab.label}</span>
                  </button>
                );
              })}
            </nav>
          </div>

          {/* Action Button */}
          <div className="flex items-center gap-3">
            <button
              onClick={onOpenNewClient}
              className="inline-flex items-center gap-2 px-4 py-2 bg-[#0A7C3B] hover:bg-[#08632f] text-white text-sm font-medium rounded-lg shadow-xs transition-colors cursor-pointer"
            >
              <Plus className="w-4 h-4" />
              <span>New Client</span>
            </button>
          </div>
        </div>
      </div>

      {/* Mobile Navigation Bar */}
      <div className="md:hidden flex items-center justify-around border-t border-slate-100 py-2 bg-slate-50">
        {navTabs.map(tab => {
          const Icon = tab.icon;
          const isActive = currentTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => onSelectTab(tab.id)}
              className={`flex flex-col items-center gap-1 py-1 px-3 text-xs font-medium ${
                isActive ? 'text-[#0A7C3B] font-bold' : 'text-slate-500'
              }`}
            >
              <Icon className="w-4 h-4" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>
    </header>
  );
};
