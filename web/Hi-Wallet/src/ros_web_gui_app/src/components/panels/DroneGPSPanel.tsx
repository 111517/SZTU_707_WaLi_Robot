import { useEffect, useState } from 'react';
import type { RosbridgeConnection } from '../../utils/RosbridgeConnection';
import { DeviceStatusCard } from './DeviceStatusCard';

interface Props { connection: RosbridgeConnection | null }

const numberOrNull = (v: unknown): number | null =>
  typeof v === 'number' && Number.isFinite(v) ? v : null;

export function DroneGPSPanel({ connection }: Props) {
  const [lat, setLat] = useState<number | null>(null);
  const [lon, setLon] = useState<number | null>(null);
  const [alt, setAlt] = useState<number | null>(null);
  const [relAlt, setRelAlt] = useState<number | null>(null);
  const [satellites, setSatellites] = useState<number | null>(null);
  const [fixType, setFixType] = useState('-');

  useEffect(() => {
    if (!connection?.isConnected()) {
      setLat(null); setLon(null); setAlt(null); setRelAlt(null); setSatellites(null); setFixType('-');
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

      findAndSub(['/mavros/global_position/global'], (msg) => {
        setLat(numberOrNull((msg as Record<string, unknown>).latitude));
        setLon(numberOrNull((msg as Record<string, unknown>).longitude));
        setAlt(numberOrNull((msg as Record<string, unknown>).altitude));
      });

      findAndSub(['/mavros/global_position/rel_alt'], (msg) => {
        setRelAlt(numberOrNull((msg as Record<string, unknown>).data));
      });

      findAndSub(['/mavros/global_position/raw/satellites'], (msg) => {
        const sats = (msg as Record<string, unknown>).data;
        setSatellites(numberOrNull(sats));
      });

      findAndSub(['/mavros/global_position/raw/fix'], (msg) => {
        const fix = (msg as Record<string, unknown>).status;
        const val = fix as number;
        if (val === -1 || val === 0) setFixType('无');
        else if (val === 1) setFixType('单点');
        else if (val === 2) setFixType('DGPS');
        else if (val === 4) setFixType('RTK固定');
        else if (val === 5) setFixType('RTK浮动');
        else setFixType(fix != null ? `类型${fix}` : '-');
      });
    };
    refresh();
    const unsub = connection.onTopicsChange(() => refresh());
    return () => { unsub(); subbed.forEach(t => { try { connection.unsubscribe(t); } catch {} }); };
  }, [connection]);

  const hasGPS = lat != null && lon != null;
  const status: 'online' | 'idle' | 'offline' = hasGPS ? 'online' : 'offline';

  return (
    <DeviceStatusCard title="GPS / 定位" icon="🛰️" status={status} metrics={[
      { label: '纬度', value: lat != null ? lat.toFixed(6) : '-' },
      { label: '经度', value: lon != null ? lon.toFixed(6) : '-' },
      { label: '高度(MSL)', value: alt != null ? `${alt.toFixed(1)}m` : '-' },
      { label: '相对高度', value: relAlt != null ? `${relAlt.toFixed(1)}m` : '-' },
      { label: '卫星数', value: satellites != null ? String(satellites) : '-', warn: satellites != null && satellites < 8 },
      { label: '定位类型', value: fixType },
    ]} />
  );
}
