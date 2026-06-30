import { useEffect, useState } from 'react';
import type { RosbridgeConnection } from '../../utils/RosbridgeConnection';
import { DeviceStatusCard } from './DeviceStatusCard';

interface Props { connection: RosbridgeConnection | null }

const numberOrNull = (v: unknown): number | null =>
  typeof v === 'number' && Number.isFinite(v) ? v : null;

export function DroneFlightPanel({ connection }: Props) {
  const [px, setPx] = useState<number | null>(null);
  const [py, setPy] = useState<number | null>(null);
  const [pz, setPz] = useState<number | null>(null);
  const [vx, setVx] = useState<number | null>(null);
  const [vy, setVy] = useState<number | null>(null);
  const [vz, setVz] = useState<number | null>(null);
  const [airspeed, setAirspeed] = useState<number | null>(null);
  const [heading, setHeading] = useState<number | null>(null);
  const [throttle, setThrottle] = useState<number | null>(null);

  useEffect(() => {
    if (!connection?.isConnected()) {
      setPx(null); setPy(null); setPz(null); setVx(null); setVy(null); setVz(null);
      setAirspeed(null); setHeading(null); setThrottle(null);
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

      findAndSub(['/mavros/local_position/pose'], (msg) => {
        const p = (msg as Record<string, unknown>).pose as Record<string, unknown> | undefined;
        if (p?.position) {
          const pos = p.position as Record<string, unknown>;
          setPx(numberOrNull(pos.x)); setPy(numberOrNull(pos.y)); setPz(numberOrNull(pos.z));
        }
        if (p?.orientation) {
          const q = p.orientation as Record<string, number>;
          const siny = 2 * (q.w * q.z + q.x * q.y);
          const cosy = 1 - 2 * (q.y * q.y + q.z * q.z);
          setHeading(Math.atan2(siny, cosy) * 180 / Math.PI);
        }
      });

      findAndSub(['/mavros/local_position/velocity_local'], (msg) => {
        const twist = (msg as Record<string, unknown>).twist as Record<string, unknown> | undefined;
        if (twist?.linear) {
          const lin = twist.linear as Record<string, unknown>;
          setVx(numberOrNull(lin.x)); setVy(numberOrNull(lin.y)); setVz(numberOrNull(lin.z));
        }
      });

      findAndSub(['/mavros/vfr_hud'], (msg) => {
        setAirspeed(numberOrNull((msg as Record<string, unknown>).airspeed));
        setThrottle(numberOrNull((msg as Record<string, unknown>).throttle));
      });
    };
    refresh();
    const unsub = connection.onTopicsChange(() => refresh());
    return () => { unsub(); subbed.forEach(t => { try { connection.unsubscribe(t); } catch {} }); };
  }, [connection]);

  const hasPose = px != null;
  const status: 'online' | 'idle' | 'offline' = hasPose ? 'online' : 'offline';

  return (
    <DeviceStatusCard title="飞行数据" icon="🛩️" status={status} metrics={[
      { label: '位置 X/Y/Z', value: hasPose ? `${px!.toFixed(1)}/${py!.toFixed(1)}/${pz!.toFixed(1)}m` : '-' },
      { label: '速度 X/Y/Z', value: vx != null ? `${vx.toFixed(1)}/${vy!.toFixed(1)}/${vz!.toFixed(1)}m/s` : '-' },
      { label: '航向', value: heading != null ? `${heading.toFixed(1)}°` : '-' },
      { label: '空速', value: airspeed != null ? `${airspeed.toFixed(1)}m/s` : '-' },
      { label: '油门', value: throttle != null ? `${throttle.toFixed(0)}%` : '-' },
    ]} />
  );
}
