import { useEffect, useState } from 'react';
import type { RosbridgeConnection } from '../../utils/RosbridgeConnection';
import { DeviceStatusCard } from './DeviceStatusCard';

interface Props { connection: RosbridgeConnection | null }

const numberOrNull = (v: unknown): number | null =>
  typeof v === 'number' && Number.isFinite(v) ? v : null;

export function DroneSystemPanel({ connection }: Props) {
  const [cpuLoad, setCpuLoad] = useState<number | null>(null);
  const [voltage, setVoltage] = useState<number | null>(null);
  const [dropRate, setDropRate] = useState<number | null>(null);
  const [errors, setErrors] = useState<number | null>(null);
  const [rssi, setRssi] = useState<number | null>(null);
  const [rcChannels, setRcChannels] = useState(0);

  useEffect(() => {
    if (!connection?.isConnected()) {
      setCpuLoad(null); setVoltage(null); setDropRate(null); setErrors(null); setRssi(null); setRcChannels(0);
      return;
    }

    let subbed: string[] = [];
    const refresh = () => {
      subbed.forEach(t => { try { connection.unsubscribe(t); } catch {} });
      subbed = [];
      const topics = connection.getProviderTopics();
      const findAndSub = (candidates: string[], cb: (msg: Record<string, unknown>) => void) => {
        const t = topics.find(tp => candidates.some(c => tp.name === c));
        if (t) { connection.subscribe(t.name, t.type, cb as (msg: unknown) => void); subbed.push(t.name); }
      };

      findAndSub(['/mavros/sys_status'], (msg) => {
        setCpuLoad(numberOrNull((msg as Record<string, unknown>).load));
        setVoltage(numberOrNull((msg as Record<string, unknown>).voltage));
        setDropRate(numberOrNull((msg as Record<string, unknown>).drop_rate));
        setErrors(numberOrNull((msg as Record<string, unknown>).errors_count1));
      });

      findAndSub(['/mavros/radio_status'], (msg) => {
        const r = numberOrNull((msg as Record<string, unknown>).rssi);
        setRssi(r);
      });

      findAndSub(['/mavros/rc/in'], (msg) => {
        const ch = (msg as Record<string, unknown>).channels;
        setRcChannels(Array.isArray(ch) ? ch.length : 0);
      });
    };
    refresh();
    const unsub = connection.onTopicsChange(() => refresh());
    return () => { unsub(); subbed.forEach(t => { try { connection.unsubscribe(t); } catch {} }); };
  }, [connection]);

  const online = [cpuLoad, voltage, rssi].filter(v => v != null).length;
  const status: 'online' | 'idle' | 'offline' = online >= 2 ? 'online' : online > 0 ? 'idle' : 'offline';

  return (
    <DeviceStatusCard title="系统 / 遥控" icon="📡" status={status} metrics={[
      { label: 'CPU负载', value: cpuLoad != null ? `${(cpuLoad * 100).toFixed(0)}%` : '-' },
      { label: '飞控电压', value: voltage != null ? `${(voltage / 1000).toFixed(1)}V` : '-' },
      { label: '丢包率', value: dropRate != null ? `${dropRate.toFixed(2)}%` : '-', warn: dropRate != null && dropRate > 1 },
      { label: '错误数', value: errors != null ? String(errors) : '-', warn: errors != null && errors > 0 },
      { label: 'RSSI', value: rssi != null ? `${rssi.toFixed(0)}dBm` : '-', warn: rssi != null && rssi < -80 },
      { label: 'RC通道', value: rcChannels > 0 ? `${rcChannels}ch` : '-' },
    ]} />
  );
}
