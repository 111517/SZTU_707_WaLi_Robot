import { useEffect, useState } from 'react';
import type { RosbridgeConnection } from '../../utils/RosbridgeConnection';
import { DeviceStatusCard } from './DeviceStatusCard';

interface Props { connection: RosbridgeConnection | null }

const API_SERVICES = [
  { path: '/api/arm/request', label: '机械臂' },
  { path: '/api/gpt/request', label: 'GPT' },
  { path: '/api/voice/request', label: '语音' },
  { path: '/api/vui/request', label: 'VUI' },
  { path: '/api/sport/request', label: '运动' },
  { path: '/api/slam_operate/request', label: 'SLAM操作' },
  { path: '/api/gas_sensor/request', label: '气体传感器' },
  { path: '/api/gesture/request', label: '手势' },
  { path: '/api/pet/request', label: '宠物' },
  { path: '/api/audiohub/request', label: 'AudioHub' },
  { path: '/api/videohub/request', label: 'VideoHub' },
  { path: '/api/motion_switcher/request', label: '运动切换' },
  { path: '/api/obstacles_avoid/request', label: '避障' },
  { path: '/api/rm_con/request', label: '遥控' },
  { path: '/api/uwbswitch/request', label: 'UWB开关' },
  { path: '/api/programming_actuator/request', label: '编程执行器' },
  { path: '/api/sport_lease/request', label: 'Sport租约' },
  { path: '/api/assistant_recorder/request', label: '录音助手' },
  { path: '/api/fourg_agent/request', label: 'FourG Agent' },
  { path: '/api/config/request', label: '配置' },
  { path: '/api/bashrunner/request', label: 'BashRunner' },
  { path: '/api/robot_state/request', label: '机器人状态' },
];

export function ApiServicesPanel({ connection }: Props) {
  const [activePaths, setActivePaths] = useState<Set<string>>(new Set());

  const onlineCount = activePaths.size;
  const total = API_SERVICES.length;
  const status: 'online' | 'idle' | 'offline' =
    onlineCount >= total * 0.5 ? 'online' : onlineCount > 0 ? 'idle' : 'offline';

  useEffect(() => {
    if (!connection?.isConnected()) { setActivePaths(new Set()); return; }

    const refresh = () => {
      const topics = connection.getProviderTopics();
      const active = new Set<string>();
      for (const svc of API_SERVICES) {
        if (topics.some(t => t.name === svc.path)) active.add(svc.path);
      }
      setActivePaths(active);
    };
    refresh();
    const unsub = connection.onTopicsChange(() => refresh());
    return () => { unsub(); };
  }, [connection]);

  return (
    <DeviceStatusCard
      title={`API 服务 (${onlineCount}/${total})`}
      icon="🔌"
      status={status}
      metrics={API_SERVICES.map(svc => ({
        label: svc.label,
        value: activePaths.has(svc.path) ? '活跃' : '离线',
        warn: !activePaths.has(svc.path),
      }))}
    />
  );
}
