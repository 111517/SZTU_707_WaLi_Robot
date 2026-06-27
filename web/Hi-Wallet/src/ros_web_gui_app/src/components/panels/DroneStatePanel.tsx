import { useEffect, useState } from 'react';
import type { RosbridgeConnection } from '../../utils/RosbridgeConnection';
import { DeviceStatusCard } from './DeviceStatusCard';

interface Props { connection: RosbridgeConnection | null }

export function DroneStatePanel({ connection }: Props) {
  const [armed, setArmed] = useState(false);
  const [mode, setMode] = useState('-');
  const [connected, setConnected] = useState(false);
  const [landed, setLanded] = useState('-');
  const [extendedState, setExtendedState] = useState('-');

  const status: 'online' | 'idle' | 'offline' = connected ? (armed ? 'online' : 'idle') : 'offline';

  useEffect(() => {
    if (!connection?.isConnected()) {
      setArmed(false); setMode('-'); setConnected(false); setLanded('-'); setExtendedState('-');
      return;
    }

    let subbed: string[] = [];
    const refresh = () => {
      subbed.forEach(t => { try { connection.unsubscribe(t); } catch {} });
      subbed = [];

      const allTopics = connection.getProviderTopics();
      const findAndSub = (candidates: string[], cb: (msg: Record<string, unknown>) => void) => {
        const t = allTopics.find(tp => candidates.some(c => tp.name === c));
        if (t) { connection.subscribe(t.name, t.type, cb as (msg: unknown) => void); subbed.push(t.name); }
      };

      findAndSub(['/mavros/state'], (msg) => {
        setConnected((msg as Record<string, unknown>).connected === true);
        setArmed((msg as Record<string, unknown>).armed === true);
        setMode(String((msg as Record<string, unknown>).mode ?? '-'));
      });

      findAndSub(['/mavros/extended_state'], (msg) => {
        const landedState = (msg as Record<string, unknown>).landed_state;
        const stateMap: Record<number, string> = { 0: '未定义', 1: '地面', 2: '起飞中', 3: '空中', 4: '降落中' };
        setLanded(stateMap[landedState as number] ?? String(landedState ?? '-'));
        setExtendedState(String((msg as Record<string, unknown>).vtol_state ?? '-'));
      });
    };
    refresh();
    const unsub = connection.onTopicsChange(() => refresh());
    return () => { unsub(); subbed.forEach(t => { try { connection.unsubscribe(t); } catch {} }); };
  }, [connection]);

  return (
    <DeviceStatusCard title="飞控状态" icon="✈️" status={status} metrics={[
      { label: '连接', value: connected ? '已连接' : '断开', warn: !connected },
      { label: '解锁', value: armed ? '已解锁' : '未解锁', warn: !armed },
      { label: '模式', value: mode },
      { label: '起降状态', value: landed },
      { label: 'VTOL状态', value: extendedState !== '-' ? extendedState : 'N/A' },
    ]} />
  );
}
