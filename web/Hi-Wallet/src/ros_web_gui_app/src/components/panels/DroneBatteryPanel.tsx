import { useEffect, useState } from 'react';
import type { RosbridgeConnection } from '../../utils/RosbridgeConnection';
import { DeviceStatusCard } from './DeviceStatusCard';

interface Props { connection: RosbridgeConnection | null }

const numberOrNull = (v: unknown): number | null =>
  typeof v === 'number' && Number.isFinite(v) ? v : null;

export function DroneBatteryPanel({ connection }: Props) {
  const [voltage, setVoltage] = useState<number | null>(null);
  const [current, setCurrent] = useState<number | null>(null);
  const [percent, setPercent] = useState<number | null>(null);

  useEffect(() => {
    if (!connection?.isConnected()) { setVoltage(null); setCurrent(null); setPercent(null); return; }

    let subbed: string[] = [];
    const refresh = () => {
      subbed.forEach(t => { try { connection.unsubscribe(t); } catch {} });
      subbed = [];
      const topics = connection.getProviderTopics();
      console.log('[DroneBattery] refresh: providerTopics count=', topics.length);
      const bt = topics.find(t => t.name === '/mavros/battery');
      console.log('[DroneBattery] /mavros/battery found:', !!bt, bt?.type);
      if (bt) {
        connection.subscribe(bt.name, bt.type, (msg) => {
          const m = msg as Record<string, unknown>;
          console.log('[DroneBattery] raw msg keys:', Object.keys(m), 'voltage=', m.voltage, 'current=', m.current, 'percentage=', m.percentage);
          setVoltage(numberOrNull(m.voltage));
          setCurrent(numberOrNull(m.current));
          setPercent(numberOrNull(m.percentage));
        });
        subbed.push(bt.name);
      }
    };
    refresh();
    const unsub = connection.onTopicsChange(() => refresh());
    return () => { unsub(); subbed.forEach(t => { try { connection.unsubscribe(t); } catch {} }); };
  }, [connection]);

  const status: 'online' | 'idle' | 'offline' = percent != null ? 'online' : 'offline';

  return (
    <DeviceStatusCard title="电池" icon="🔋" status={status} metrics={[
      { label: '电量', value: percent != null ? `${percent.toFixed(0)}%` : '-', warn: percent != null && percent < 20 },
      { label: '电压', value: voltage != null ? `${voltage.toFixed(1)}V` : '-' },
      { label: '电流', value: current != null ? `${current.toFixed(1)}A` : '-' },
    ]} />
  );
}
