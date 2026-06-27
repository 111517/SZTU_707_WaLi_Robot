import { useEffect, useState } from 'react';
import type { RosbridgeConnection } from '../../utils/RosbridgeConnection';
import { DeviceStatusCard } from './DeviceStatusCard';

interface Props { connection: RosbridgeConnection | null }

const LIDAR_TOPICS = [
  '/point_cloud2', '/utlidar/lidar_state', '/utlidar/cloud_deskewed',
  '/utlidar/robot_odom', '/utlidar/imu', '/utlidar/grid_map', '/utlidar/cloud',
];
const SLAM_TOPICS = [
  '/odom', '/slam_info', '/slam_key_info',
  '/uslam/frontend/odom', '/uslam/localization/odom',
];

export function SlamLidarPanel({ connection }: Props) {
  const [lidarActive, setLidarActive] = useState<string[]>([]);
  const [slamActive, setSlamActive] = useState<string[]>([]);
  const [slamInfo, setSlamInfo] = useState('-');
  const [lidarState, setLidarState] = useState('-');

  const total = LIDAR_TOPICS.length + SLAM_TOPICS.length;
  const active = lidarActive.length + slamActive.length;
  const status: 'online' | 'idle' | 'offline' = active >= total * 0.6 ? 'online' : active > 0 ? 'idle' : 'offline';

  useEffect(() => {
    if (!connection?.isConnected()) {
      setLidarActive([]); setSlamActive([]); setSlamInfo('-'); setLidarState('-');
      return;
    }

    let subbed: string[] = [];
    const refresh = () => {
      subbed.forEach(t => { try { connection.unsubscribe(t); } catch {} });
      subbed = [];

      const allTopics = connection.getProviderTopics();
      setLidarActive(LIDAR_TOPICS.filter(t => allTopics.some(pt => pt.name === t)));
      setSlamActive(SLAM_TOPICS.filter(t => allTopics.some(pt => pt.name === t)));

      const sub = (tName: string, cb: (msg: Record<string, unknown>) => void) => {
        const t = allTopics.find(tp => tp.name === tName);
        if (t) { connection.subscribe(t.name, t.type, cb as (msg: unknown) => void); subbed.push(t.name); }
      };
      sub('/utlidar/lidar_state', (msg) => setLidarState(typeof msg.data === 'string' ? msg.data : 'active'));
      sub('/slam_info', (msg) => setSlamInfo(typeof msg.data === 'string' ? msg.data : 'active'));
    };
    refresh();
    const unsub = connection.onTopicsChange(() => refresh());
    return () => { unsub(); subbed.forEach(t => { try { connection.unsubscribe(t); } catch {} }); };
  }, [connection]);

  const on = (t: string) => lidarActive.includes(t) || slamActive.includes(t);

  const metrics = [
    { label: 'LiDAR点云', value: on('/point_cloud2') || on('/utlidar/cloud_deskewed') ? '活跃' : '离线', warn: !(on('/point_cloud2') || on('/utlidar/cloud_deskewed')) },
    { label: 'LiDAR里程计', value: on('/utlidar/robot_odom') ? '活跃' : '离线', warn: !on('/utlidar/robot_odom') },
    { label: 'LiDAR栅格图', value: on('/utlidar/grid_map') ? '活跃' : '离线' },
    { label: 'LiDAR状态', value: lidarState },
    { label: '里程计(odom)', value: on('/odom') ? '活跃' : '离线' },
    { label: 'SLAM里程计', value: on('/uslam/frontend/odom') ? '活跃' : '离线' },
    { label: 'SLAM定位', value: on('/uslam/localization/odom') ? '活跃' : '离线' },
    { label: 'SLAM信息', value: slamInfo },
    { label: '活跃话题', value: `${active}/${total}` },
  ];

  return <DeviceStatusCard title="SLAM / LiDAR" icon="🔭" status={status} metrics={metrics} />;
}
