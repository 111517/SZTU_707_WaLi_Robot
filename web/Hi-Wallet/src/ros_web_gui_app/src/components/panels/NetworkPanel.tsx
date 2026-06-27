import { useEffect, useState } from 'react';
import type { RosbridgeConnection } from '../../utils/RosbridgeConnection';
import { DeviceStatusCard } from './DeviceStatusCard';

interface Props { connection: RosbridgeConnection | null }

const TOPICS = [
  '/webrtcreq', '/webrtcres', '/xfk_webrtcreq', '/xfk_webrtcres',
  '/client_count', '/connected_clients', '/public_network_status',
  '/rtc/state', '/rtc_status', '/gnss',
];

export function NetworkPanel({ connection }: Props) {
  const [activeTopics, setActiveTopics] = useState<string[]>([]);
  const [clientCount, setClientCount] = useState('-');
  const [rtcState, setRtcState] = useState('-');

  const status: 'online' | 'idle' | 'offline' =
    activeTopics.length >= 4 ? 'online' : activeTopics.length > 0 ? 'idle' : 'offline';

  useEffect(() => {
    if (!connection?.isConnected()) { setActiveTopics([]); setClientCount('-'); setRtcState('-'); return; }

    let subbed: string[] = [];
    const refresh = () => {
      subbed.forEach(t => { try { connection.unsubscribe(t); } catch {} });
      subbed = [];

      const allTopics = connection.getProviderTopics();
      setActiveTopics(TOPICS.filter(t => allTopics.some(pt => pt.name === t)));

      const findAndSub = (candidates: string[], cb: (msg: Record<string, unknown>) => void) => {
        const t = allTopics.find(tp => candidates.some(c => tp.name === c));
        if (t) { connection.subscribe(t.name, t.type, cb as (msg: unknown) => void); subbed.push(t.name); }
      };
      findAndSub(['/client_count'], (msg) => {
        setClientCount(String((msg as Record<string, unknown>).data ?? '1'));
      });
      findAndSub(['/rtc/state'], (msg) => {
        setRtcState(typeof (msg as Record<string, unknown>).data === 'string'
          ? String((msg as Record<string, unknown>).data) : 'connected');
      });
    };
    refresh();
    const unsub = connection.onTopicsChange(() => refresh());
    return () => { unsub(); subbed.forEach(t => { try { connection.unsubscribe(t); } catch {} }); };
  }, [connection]);

  const on = (t: string) => activeTopics.includes(t);

  return (
    <DeviceStatusCard title="网络 / WebRTC" icon="🌐" status={status} metrics={[
      { label: 'WebRTC请求', value: on('/webrtcreq') ? '活跃' : '离线' },
      { label: 'WebRTC响应', value: on('/webrtcres') ? '活跃' : '离线' },
      { label: '客户端数', value: clientCount },
      { label: 'RTC状态', value: rtcState },
      { label: '公网状态', value: on('/public_network_status') ? '活跃' : '离线' },
      { label: 'GNSS', value: on('/gnss') ? '活跃' : '离线' },
    ]} />
  );
}
