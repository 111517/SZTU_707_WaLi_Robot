import type { RobotFleetEntry } from '../../types/FleetTypes';
import './RobotCard.css';

interface RobotCardProps {
  robot: RobotFleetEntry;
  selected?: boolean;
  onSelect: () => void;
  onReconnect: () => void;
  onRemove: () => void;
}

const STATUS_CLASS: Record<string, string> = {
  online: 'badge-online',
  idle: 'badge-idle',
  busy: 'badge-task',
  offline: 'badge-idle',
};

const STATUS_LABEL: Record<string, string> = {
  online: '在线',
  idle: '待机',
  busy: '执行中',
  offline: '离线',
};

export function RobotCard({ robot, selected, onSelect, onReconnect, onRemove }: RobotCardProps) {
  return (
    <div
      className={`robot-card ${selected ? 'selected' : ''}`}
      onClick={onSelect}
    >
      <div className="robot-header">
        <div className="robot-icon" style={{ background: getRobotColor(robot.type) }}>
          <RobotIcon type={robot.type} />
        </div>
        <div className="robot-info">
          <div className="robot-name">{robot.name}</div>
          <div className="robot-type">{getRobotTypeLabel(robot.type)}</div>
        </div>
        <div className={`status-badge ${STATUS_CLASS[robot.status] || 'badge-idle'}`}>
          {robot.status === 'busy' && <span className="badge-dot" />}
          {STATUS_LABEL[robot.status] || robot.status}
        </div>
      </div>

      <div className="robot-metrics">
        <div className="metric-item">
          <div className="metric-val">{robot.batteryPercent !== null ? `${robot.batteryPercent}%` : '-'}</div>
          <div className="metric-lbl">电量</div>
        </div>
        <div className="metric-item">
          <div className="metric-val">{robot.topicCount}</div>
          <div className="metric-lbl">话题数</div>
        </div>
        <div className="metric-item">
          <div className="metric-val" style={{ color: robot.status === 'online' ? 'var(--green)' : 'var(--text3)' }}>
            {robot.ip}:{robot.port}
          </div>
          <div className="metric-lbl">地址</div>
        </div>
      </div>

      <div className="robot-footer">
        {robot.status !== 'online' ? (
          <button className="action-btn primary" onClick={(e) => { e.stopPropagation(); onReconnect(); }}>
            重新连接
          </button>
        ) : (
          <button className="action-btn primary" onClick={(e) => { e.stopPropagation(); onSelect(); }}>
            选中
          </button>
        )}
        <button className="action-btn" onClick={(e) => { e.stopPropagation(); onRemove(); }}>
          移除
        </button>
      </div>
    </div>
  );
}

function RobotIcon({ type }: { type: string }) {
  return (
    <svg viewBox="0 0 24 24">
      {type === 'tb4' ? (
        <>
          <rect x="5" y="11" width="14" height="10" rx="2" />
          <path strokeLinecap="round" d="M8 11V8a4 4 0 018 0v3M12 15v2" />
          <circle cx="9" cy="16" r="1" fill="white" stroke="none" />
          <circle cx="15" cy="16" r="1" fill="white" stroke="none" />
        </>
      ) : type === 'uav' ? (
        <>
          <circle cx="12" cy="12" r="2.5" />
          <path strokeLinecap="round"
            d="M6 6l1.5 1.5M18 6l-1.5 1.5M6 18l1.5-1.5M18 18l-1.5-1.5M4 6a2 2 0 114 0 2 2 0 01-4 0zM16 6a2 2 0 114 0 2 2 0 01-4 0zM4 18a2 2 0 114 0 2 2 0 01-4 0zM16 18a2 2 0 114 0 2 2 0 01-4 0z" />
        </>
      ) : (
        <path strokeLinecap="round"
          d="M6 12c0-.8.4-1.5 1.2-2L9 9h6l1.8 1c.8.5 1.2 1.2 1.2 2M9 9c0-1.5.8-2.5 3-2.5S15 7.5 15 9M9 17l-2 2M15 17l2 2M9 17h6M9 17c0 1.2.8 2 3 2s3-.8 3-2" />
      )}
    </svg>
  );
}

function getRobotColor(type: string): string {
  switch (type) {
    case 'tb4': return 'var(--tb4)';
    case 'go2': return 'var(--go2)';
    case 'uav': return 'var(--drone)';
    default: return 'var(--accent)';
  }
}

function getRobotTypeLabel(type: string): string {
  switch (type) {
    case 'tb4': return '差速轮式 · ROS2 Humble';
    case 'go2': return '四足步行 · ROS2 Humble';
    case 'uav': return '四旋翼 · PX4';
    default: return '通用机器人';
  }
}
