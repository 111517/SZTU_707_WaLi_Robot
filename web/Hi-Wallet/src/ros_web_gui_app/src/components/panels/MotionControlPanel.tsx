import { useEffect, useState } from 'react';
import type { RosbridgeConnection } from '../../utils/RosbridgeConnection';
import { DeviceStatusCard } from './DeviceStatusCard';

interface Props { connection: RosbridgeConnection | null }

const SERVICES = [
  { path: '/api/sport', label: 'Sport运动' },
  { path: '/api/motion_switcher', label: '运动切换' },
  { path: '/api/sport_lease', label: 'Sport租约' },
  { path: '/api/arm', label: '机械臂' },
  { path: '/api/obstacles_avoid', label: '避障' },
  { path: '/api/programming_actuator', label: '编程执行器' },
  { path: '/api/rm_con', label: '遥控' },
  { path: '/api/pet', label: 'Pet宠物' },
];

export function MotionControlPanel({ connection }: Props) {
  const [activeSvc, setActiveSvc] = useState<Set<string>>(new Set());

  const onlineCount = activeSvc.size;
  const status: 'online' | 'idle' | 'offline' = onlineCount >= 3 ? 'online' : onlineCount > 0 ? 'idle' : 'offline';

  useEffect(() => {
    if (!connection?.isConnected()) { setActiveSvc(new Set()); return; }

    const refresh = () => {
      const allTopics = connection.getProviderTopics();
      const active = new Set<string>();
      SERVICES.forEach(s => { if (allTopics.some(t => t.name.startsWith(s.path))) active.add(s.path); });
      setActiveSvc(active);
    };
    refresh();
    const unsub = connection.onTopicsChange(() => refresh());
    return () => { unsub(); };
  }, [connection]);

  return (
    <DeviceStatusCard title="运动 / 控制" icon="🕹️" status={status} metrics={
      SERVICES.map(s => ({
        label: s.label,
        value: activeSvc.has(s.path) ? '活跃' : '离线',
        warn: !activeSvc.has(s.path) && ['/api/sport', '/api/obstacles_avoid'].includes(s.path),
      }))
    } />
  );
}
