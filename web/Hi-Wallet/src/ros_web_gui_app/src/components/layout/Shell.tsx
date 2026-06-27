import type { ReactNode } from 'react';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import type { PageId } from '../../types/FleetTypes';
import './Shell.css';

interface ShellProps {
  activePage: PageId;
  pageTitle: string;
  tabs?: { id: string; label: string }[];
  activeTab?: string;
  onTabChange?: (tabId: string) => void;
  onNavigate: (page: PageId) => void;
  onSelectRobot: (robotId: string) => void;
  onRefresh?: () => void;
  onFullscreen?: () => void;
  children: ReactNode;
}

export function Shell({
  activePage,
  pageTitle,
  tabs,
  activeTab,
  onTabChange,
  onNavigate,
  onSelectRobot,
  onRefresh,
  onFullscreen,
  children,
}: ShellProps) {
  return (
    <div className="shell">
      <Sidebar
        activePage={activePage}
        onNavigate={onNavigate}
        onSelectRobot={onSelectRobot}
      />
      <div className="main">
        <TopBar
          title={pageTitle}
          tabs={tabs}
          activeTab={activeTab}
          onTabChange={onTabChange}
          onRefresh={onRefresh}
          onFullscreen={onFullscreen}
        />
        <div className="content">
          {children}
        </div>
      </div>
    </div>
  );
}
