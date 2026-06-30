import { useFleet } from '../../context/useFleet';
import type { PageId } from '../../types/FleetTypes';
import type { RobotType } from '../../types/FleetTypes';
import './Sidebar.css';

interface SidebarProps {
  activePage: PageId;
  onNavigate: (page: PageId) => void;
  onSelectRobot: (robotId: string) => void;
}

export function Sidebar({ activePage, onNavigate, onSelectRobot }: SidebarProps) {
  const { robots, activeRobot } = useFleet();

  return (
    <nav className="sidebar">
      <div className="sidebar-logo">
        <div className="logo-icon">
          <svg viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" />
          </svg>
        </div>
        <div>
          <div className="logo-name">RobotCore</div>
          <div className="logo-sub">Multi-Robot Hub</div>
        </div>
      </div>

      <div className="sidebar-section">
        <div className="sidebar-label">主菜单</div>
        <NavItem
          icon="dashboard"
          label="系统总览"
          active={activePage === 'dashboard'}
          onClick={() => onNavigate('dashboard')}
        />
        <NavItem
          icon="mission"
          label="任务规划"
          active={activePage === 'mission'}
          onClick={() => onNavigate('mission')}
        />
        <NavItem
          icon="telemetry"
          label="遥测数据"
          active={activePage === 'telemetry'}
          onClick={() => onNavigate('telemetry')}
        />
        <NavItem
          icon="settings"
          label="系统设置"
          active={activePage === 'settings'}
          onClick={() => onNavigate('settings')}
        />
      </div>

      <div className="sidebar-section" style={{ marginTop: 10 }}>
        <div className="sidebar-label">机器人</div>
        {robots.length === 0 && (
          <div className="sidebar-empty">暂无机器人连接</div>
        )}
        {robots.map((robot) => (
          <div
            key={robot.id}
            className={`nav-item ${robot.id === activeRobot?.id ? 'active' : ''}`}
            onClick={() => onSelectRobot(robot.id)}
          >
            <svg viewBox="0 0 24 24">
              {getRobotIcon(robot.type)}
            </svg>
            {robot.name}
            <span className={`robot-dot ${robot.status}`} />
          </div>
        ))}
      </div>

      <div className="sidebar-footer">
        <div className="user-row">
          <div className="avatar">OP</div>
          <div>
            <div className="user-name">操作员</div>
            <div className="user-role">系统管理员</div>
          </div>
        </div>
      </div>
    </nav>
  );
}

function NavItem({ icon, label, active, onClick }: {
  icon: string;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <div className={`nav-item ${active ? 'active' : ''}`} onClick={onClick}>
      {getNavIcon(icon)}
      {label}
    </div>
  );
}

function getNavIcon(name: string) {
  switch (name) {
    case 'dashboard':
      return (
        <svg viewBox="0 0 24 24">
          <rect x="3" y="3" width="7" height="7" rx="1.5" />
          <rect x="14" y="3" width="7" height="7" rx="1.5" />
          <rect x="3" y="14" width="7" height="7" rx="1.5" />
          <rect x="14" y="14" width="7" height="7" rx="1.5" />
        </svg>
      );
    case 'mission':
      return (
        <svg viewBox="0 0 24 24">
          <path strokeLinecap="round"
            d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        </svg>
      );
    case 'telemetry':
      return (
        <svg viewBox="0 0 24 24">
          <path strokeLinecap="round"
            d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
      );
    case 'settings':
      return (
        <svg viewBox="0 0 24 24">
          <path strokeLinecap="round"
            d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      );
    default:
      return null;
  }
}

function getRobotIcon(type: RobotType) {
  switch (type) {
    case 'tb4':
      return (
        <>
          <rect x="5" y="11" width="14" height="10" rx="2" />
          <path strokeLinecap="round" d="M8 11V8a4 4 0 018 0v3M12 15v2" />
          <circle cx="9" cy="16" r="1" fill="currentColor" stroke="none" />
          <circle cx="15" cy="16" r="1" fill="currentColor" stroke="none" />
        </>
      );
    case 'go2':
      return (
        <path strokeLinecap="round"
          d="M6 12c0-.8.4-1.5 1.2-2L9 9h6l1.8 1c.8.5 1.2 1.2 1.2 2M9 9c0-1.5.8-2.5 3-2.5S15 7.5 15 9M9 17l-2 2M15 17l2 2M9 17h6M9 17c0 1.2.8 2 3 2s3-.8 3-2" />
      );
    case 'uav':
      return (
        <>
          <circle cx="12" cy="12" r="2.5" />
          <path strokeLinecap="round"
            d="M6 6l1.5 1.5M18 6l-1.5 1.5M6 18l1.5-1.5M18 18l-1.5-1.5M4 6a2 2 0 114 0 2 2 0 01-4 0zM16 6a2 2 0 114 0 2 2 0 01-4 0zM4 18a2 2 0 114 0 2 2 0 01-4 0zM16 18a2 2 0 114 0 2 2 0 01-4 0z" />
        </>
      );
    default:
      return (
        <rect x="6" y="4" width="12" height="16" rx="3" />
      );
  }
}
