import { useMemo } from 'react';
import { StatCard } from '../panels/StatCard';
import { RobotCard } from '../panels/RobotCard';
import { LogFeed } from '../panels/LogFeed';
import { ViewportPanel } from '../panels/ViewportPanel';
import { RobotCorePanel } from '../panels/RobotCorePanel';
import { SlamLidarPanel } from '../panels/SlamLidarPanel';
import { TurtleBot4Panel } from '../panels/TurtleBot4Panel';
import { TB4ControlPanel } from '../TB4ControlPanel';
import { CameraVideoPanel } from '../panels/CameraVideoPanel';
import { AudioVoicePanel } from '../panels/AudioVoicePanel';
import { AIGPTPanel } from '../panels/AIGPTPanel';
import { SensorsPanel } from '../panels/SensorsPanel';
import { MotionControlPanel } from '../panels/MotionControlPanel';
import { NetworkPanel } from '../panels/NetworkPanel';
import { ApiServicesPanel } from '../panels/ApiServicesPanel';
import type { RobotFleetEntry } from '../../types/FleetTypes';

interface DashboardPageProps {
  robots: RobotFleetEntry[];
  selectedRobotId: string | null;
  onSelectRobot: (id: string) => void;
  onReconnectRobot: (id: string) => void;
  onAddRobot: () => void;
  onRemoveRobot: (id: string) => void;
}

const WELCOME_LOG = [
  { msg: 'RobotCore 系统就绪，等待机器人连接', robot: '系统', robotColor: 'var(--text2)', dotColor: 'var(--green)', tagBg: 'var(--surface2)', tagColor: 'var(--text2)' },
];

const TB4_CAMERA_URL = import.meta.env.VITE_TB4_CAMERA_URL || '';
const GO2_CAMERA_URL = import.meta.env.VITE_GO2_CAMERA_URL || '';

export function DashboardPage({ robots, selectedRobotId, onSelectRobot, onReconnectRobot, onAddRobot, onRemoveRobot }: DashboardPageProps) {
  const onlineCount = robots.filter((r) => r.status === 'online').length;
  const totalCount = robots.length;
  const alertCount = robots.filter((r) => r.status !== 'online').length;

  const selectedRobot = selectedRobotId
    ? robots.find((r) => r.id === selectedRobotId && r.status === 'online') ?? null
    : robots.find((r) => r.status === 'online' && r.connection?.isConnected()) ?? null;
  const activeConn = selectedRobot?.connection ?? null;
  const totalTopics = robots.reduce((s, r) => s + r.topicCount, 0);

  const logEntries = useMemo(() => {
    if (robots.length === 0) return WELCOME_LOG;
    return robots.map((r) => ({
      msg: `${r.name} · ${r.ip}:${r.port} · ${r.topicCount} 个话题 · ${r.status === 'online' ? '已连接' : r.status === 'idle' ? '待机中' : '离线'}`,
      robot: r.name,
      robotColor: getRobotColor(r.type),
      dotColor: r.status === 'online' ? 'var(--green)' : r.status === 'idle' ? 'var(--amber)' : 'var(--border2)',
      tagBg: r.status === 'online' ? 'var(--green-bg)' : 'var(--surface2)',
      tagColor: r.status === 'online' ? 'var(--green)' : 'var(--text3)',
    }));
  }, [robots]);

  return (
    <div className="page-enter">
      {alertCount > 0 && (
        <div className="alert-banner" style={{ marginBottom: 16 }}>
          <svg viewBox="0 0 24 24" style={{ width: 16, height: 16, fill: 'none', stroke: 'currentColor', strokeWidth: 2, flexShrink: 0 }}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span><strong>提示：</strong>{alertCount} 个机器人未在线，请检查连接状态。</span>
        </div>
      )}

      <div className="grid-4" style={{ marginBottom: 16 }}>
        <StatCard label="在线机器人" value={onlineCount} suffix={`/ ${totalCount}`} delta={totalCount === 0 ? undefined : onlineCount === totalCount ? '▲ 全部在线' : `▲ ${onlineCount} 在线`} valueColor={onlineCount > 0 ? 'var(--green)' : undefined} />
        <StatCard label="活跃话题" value={totalTopics} delta="ROS2 Topic 统计" />
        <StatCard label="当前选中" value={selectedRobot ? selectedRobot.name : '无'} valueColor={selectedRobot ? 'var(--accent)' : 'var(--text3)'} delta={selectedRobot ? `${selectedRobot.ip}:${selectedRobot.port}` : '点击机器人卡片选中'} />
        <StatCard label="告警" value={alertCount} valueColor={alertCount > 0 ? 'var(--amber)' : 'var(--green)'} delta={alertCount > 0 ? `▲ ${alertCount} 项` : '无告警'} deltaNeg={alertCount > 0} />
      </div>

      {robots.length > 0 ? (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: 16, marginBottom: 16, alignItems: 'stretch' }}>
          <ViewportPanel robots={robots} compact={true} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, overflow: 'auto' }}>
            {selectedRobot?.type === 'tb4' ? (
              <>
                <TurtleBot4Panel connection={activeConn} />
                {activeConn && <TB4ControlPanel connection={activeConn} />}
                <CameraVideoPanel
                  connection={activeConn}
                  videoSrc={TB4_CAMERA_URL}
                />
              </>
            ) : (
              <>
                <RobotCorePanel connection={activeConn} />
                <CameraVideoPanel
                  connection={activeConn}
                  videoSrc={GO2_CAMERA_URL}
                />
              </>
            )}
          </div>
        </div>
      ) : totalCount > 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: 32, marginBottom: 16 }}>
          <div className="card-sub" style={{ fontSize: 14 }}>点击机器人卡片选中并在线以查看 3D 视图</div>
        </div>
      ) : (
        <div className="card" style={{ textAlign: 'center', padding: 48, marginBottom: 16 }}>
          <div className="card-sub" style={{ fontSize: 14, marginBottom: 16 }}>
            暂无已保存的机器人 · 请添加机器人以查看 3D 视图和状态面板
          </div>
          <button className="action-btn primary" onClick={onAddRobot} style={{ padding: '10px 24px', fontSize: 14, borderRadius: 20 }}>
            + 连接机器人
          </button>
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'row' }}>
        <div className="sec-hdr" style={{ flex: 1, marginBottom: 14, display: 'flex', alignItems: 'center', justifyContent: 'start' }}>
          <span className="sec-title">
            机器人舰队
            {totalCount > 0 && <span style={{ fontWeight: 400, color: 'var(--text3)', fontSize: 11, marginLeft: 8 }}>(自动保存至本地)</span>}
          </span>
          <button className="action-btn primary" onClick={onAddRobot} style={{ borderRadius: 16, padding: '3px 10px', fontSize: 11, lineHeight: 1.6, width: 80 }}>
            + 添加
          </button>
        </div>
        <div style={{ flex: 4 }}></div>
      </div>

      {totalCount > 0 && (
        <div className="grid-3" style={{ marginBottom: 16 }}>
          {robots.map((robot) => (
            <RobotCard
              key={robot.id}
              robot={robot}
              selected={robot.id === selectedRobotId}
              onSelect={() => onSelectRobot(robot.id)}
              onReconnect={() => onReconnectRobot(robot.id)}
              onRemove={() => onRemoveRobot(robot.id)}
            />
          ))}
        </div>
      )}

      {activeConn && (
        <>
          <div className="sec-hdr" style={{ marginBottom: 14 }}>
            <span className="sec-title">设备状态面板</span>
          </div>
          {selectedRobot?.type === 'tb4' ? null : (
            <div className="grid-3" style={{ marginBottom: 16 }}>
              <SlamLidarPanel connection={activeConn} />
              <AudioVoicePanel connection={activeConn} />
              <AIGPTPanel connection={activeConn} />
              <SensorsPanel connection={activeConn} />
              <MotionControlPanel connection={activeConn} />
              <NetworkPanel connection={activeConn} />
              <ApiServicesPanel connection={activeConn} />
            </div>
          )}
        </>
      )}

      <LogFeed feed={logEntries} />
    </div>
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
