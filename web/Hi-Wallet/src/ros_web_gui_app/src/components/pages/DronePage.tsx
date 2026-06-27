import { useEffect, useState } from 'react';
import { DroneStatePanel } from '../panels/DroneStatePanel';
import { DroneBatteryPanel } from '../panels/DroneBatteryPanel';
import { DroneGPSPanel } from '../panels/DroneGPSPanel';
import { DroneFlightPanel } from '../panels/DroneFlightPanel';
import { DroneSystemPanel } from '../panels/DroneSystemPanel';
import { StatCard } from '../panels/StatCard';
import type { RobotFleetEntry } from '../../types/FleetTypes';

interface DronePageProps {
  robots: RobotFleetEntry[];
}

export function DronePage({ robots }: DronePageProps) {
  const drone = robots.find(r => r.type === 'uav' && r.status === 'online');
  const conn = drone?.connection ?? robots.find(r => r.status === 'online')?.connection ?? null;
  const [topicCount, setTopicCount] = useState(conn?.getProviderTopics().length ?? 0);

  useEffect(() => {
    if (!conn) { setTopicCount(0); return; }
    setTopicCount(conn.getProviderTopics().length);
    return conn.onTopicsChange(() => setTopicCount(conn.getProviderTopics().length));
  }, [conn]);

  if (!conn) {
    return (
      <div className="page-enter">
        <div className="card" style={{ textAlign: 'center', padding: 48 }}>
          <div className="card-sub" style={{ fontSize: 14 }}>
            暂无在线无人机 · 请先通过机器人舰队连接 UAV
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="page-enter">
      <div className="grid-4" style={{ marginBottom: 16 }}>
        <StatCard label="无人机" value={drone?.name ?? 'UAV'} suffix="" delta={drone?.ip ? `${drone.ip}:${drone.port}` : '已连接'} valueColor="var(--drone)" />
        <StatCard label="ROS 话题" value={topicCount} suffix="topics" delta="rosbridge" />
        <StatCard label="MAVROS" value="PX4" suffix="" delta="飞控连接中" valueColor="var(--green)" />
        <StatCard label="数据链路" value="WebSocket" suffix="" delta={conn.isConnected() ? '在线' : '断开'} valueColor={conn.isConnected() ? 'var(--green)' : 'var(--red)'} />
      </div>

      <div className="grid-3" style={{ marginBottom: 16 }}>
        <DroneStatePanel connection={conn} />
        <DroneBatteryPanel connection={conn} />
        <DroneGPSPanel connection={conn} />
      </div>

      <div className="grid-3" style={{ marginBottom: 16 }}>
        <DroneFlightPanel connection={conn} />
        <DroneSystemPanel connection={conn} />
      </div>
    </div>
  );
}
