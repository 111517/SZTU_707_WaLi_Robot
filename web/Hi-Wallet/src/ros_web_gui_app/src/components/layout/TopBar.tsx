import './TopBar.css';

interface TopBarProps {
  title: string;
  tabs?: { id: string; label: string }[];
  activeTab?: string;
  onTabChange?: (tabId: string) => void;
  statusText?: string;
  onRefresh?: () => void;
  onFullscreen?: () => void;
}

export function TopBar({
  title,
  tabs,
  activeTab,
  onTabChange,
  statusText = '系统运行中',
  onRefresh,
  onFullscreen,
}: TopBarProps) {
  return (
    <div className="topbar">
      <span className="topbar-title">{title}</span>
      {tabs && tabs.length > 0 && (
        <div className="topbar-tabs">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => onTabChange?.(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      )}
      <div className="topbar-actions">
        <div className="status-pill">
          <span className="status-dot" />
          {statusText}
        </div>
        {onRefresh && (
          <button className="icon-btn" title="刷新数据" onClick={onRefresh}>
            <svg viewBox="0 0 24 24">
              <path strokeLinecap="round"
                d="M4 4v5h5M20 20v-5h-5M4 9a9 9 0 0114.83-5.46M20 15a9 9 0 01-14.83 5.46" />
            </svg>
          </button>
        )}
        {onFullscreen && (
          <button className="icon-btn" title="全屏" onClick={onFullscreen}>
            <svg viewBox="0 0 24 24">
              <path strokeLinecap="round"
                d="M4 8V4m0 0h4M4 4l5 5M20 8V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5M20 16v4m0 0h-4m4 0l-5-5" />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}
