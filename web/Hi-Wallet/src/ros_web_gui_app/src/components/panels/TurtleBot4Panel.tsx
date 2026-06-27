import { useEffect, useState, useRef } from 'react';
import type { RosbridgeConnection } from '../../utils/RosbridgeConnection';
import { DeviceStatusCard } from './DeviceStatusCard';

interface Props { connection: RosbridgeConnection | null }

interface TB4State {
  // Battery
  batteryVoltage: number | null;
  batteryCurrent: number | null;
  batteryPercent: number | null;
  // Diagnostics
  diagLevel: string;
  diagMessage: string;
  // Dock
  dockVisible: boolean;
  dockStatus: string;
  // Wheel
  wheelLeft: number | null;
  wheelRight: number | null;
  // HMI
  hmiButtons: number[];
  hmiDisplay: string;
  hmiLed: string;
  // AMCL
  amclX: number | null;
  amclY: number | null;
  amclYaw: number | null;
  // Hazard
  hazardCount: number;
  // OAK-D NN
  nnDetections: number;
  // Interface buttons
  ifaceButtons: number;
}

const numberOrNull = (v: unknown): number | null =>
  typeof v === 'number' && Number.isFinite(v) ? v : null;

export function TurtleBot4Panel({ connection }: Props) {
  const [state, setState] = useState<TB4State>({
    batteryVoltage: null, batteryCurrent: null, batteryPercent: null,
    diagLevel: '-', diagMessage: '',
    dockVisible: false, dockStatus: '-',
    wheelLeft: null, wheelRight: null,
    hmiButtons: [], hmiDisplay: '', hmiLed: '',
    amclX: null, amclY: null, amclYaw: null,
    hazardCount: 0,
    nnDetections: 0,
    ifaceButtons: 0,
  });
  const connRef = useRef(connection);
  useEffect(() => { connRef.current = connection; }, [connection]);

  useEffect(() => {
    const conn = connRef.current;
    if (!conn?.isConnected()) return;

    let subscribed: string[] = [];
    const allTopics = conn.getProviderTopics();

    const findAndSub = (candidates: string[], cb: (msg: Record<string, unknown>) => void) => {
      const t = allTopics.find(tp => candidates.some(c => tp.name === c));
      if (t) { conn.subscribe(t.name, t.type, cb as (msg: unknown) => void); subscribed.push(t.name); }
    };

    // Battery — Create 3 遵循 ROS 标准：percentage ∈ [0.0, 1.0]
    findAndSub(['/battery_state'], (msg) => {
      const rawPct = numberOrNull(msg.percentage);
      const normalizedPct = rawPct != null
        ? (rawPct <= 1.0 ? rawPct * 100 : rawPct)
        : null;
      setState(prev => ({
        ...prev,
        batteryVoltage: numberOrNull(msg.voltage) ?? prev.batteryVoltage,
        batteryCurrent: numberOrNull(msg.current) ?? prev.batteryCurrent,
        batteryPercent: normalizedPct ?? prev.batteryPercent,
      }));
    });

    // Diagnostics
    findAndSub(['/diagnostics'], (msg) => {
      const statusArr = (msg as any).status;
      if (Array.isArray(statusArr) && statusArr.length > 0) {
        const levels = ['OK', 'WARN', 'ERROR', 'STALE'];
        let worstLevel = 0;
        let worstMsg = '';
        for (const s of statusArr) {
          const lv = typeof s.level === 'number' ? s.level : 0;
          if (lv > worstLevel) { worstLevel = lv; worstMsg = String(s.message || s.name || ''); }
        }
        setState(prev => ({
          ...prev,
          diagLevel: levels[worstLevel] || 'OK',
          diagMessage: worstMsg,
        }));
      }
    });

    // Dock status
    findAndSub(['/dock_status'], (msg) => {
      setState(prev => ({
        ...prev,
        dockVisible: Boolean((msg as any).is_docked),
        dockStatus: (msg as any).is_docked ? '已停靠' : '未停靠',
      }));
    });

    // Wheel status
    findAndSub(['/wheel_status'], (msg) => {
      setState(prev => ({
        ...prev,
        wheelLeft: numberOrNull((msg as any).encoders?.left || (msg as any).left),
        wheelRight: numberOrNull((msg as any).encoders?.right || (msg as any).right),
      }));
    });

    // HMI buttons
    findAndSub(['/hmi/buttons'], (msg) => {
      const b = (msg as any).data ?? msg;
      setState(prev => ({ ...prev, hmiButtons: Array.isArray(b) ? b : typeof b === 'number' ? [b] : [] }));
    });

    // HMI display
    findAndSub(['/hmi/display'], (msg) => {
      const d = (msg as any).data ?? msg;
      setState(prev => ({ ...prev, hmiDisplay: typeof d === 'string' ? d : String(d || '') }));
    });

    // HMI LED
    findAndSub(['/hmi/led'], (msg) => {
      const l = (msg as any).data ?? msg;
      setState(prev => ({ ...prev, hmiLed: typeof l === 'string' ? l : JSON.stringify(l || '') }));
    });

    // AMCL pose
    findAndSub(['/amcl_pose'], (msg) => {
      const pose = (msg as any).pose?.pose || (msg as any).pose;
      if (pose) {
        const q = pose.orientation || {};
        const siny = 2 * ((q.w || 0) * (q.z || 0) + (q.x || 0) * (q.y || 0));
        const cosy = 1 - 2 * ((q.y || 0) * (q.y || 0) + (q.z || 0) * (q.z || 0));
        setState(prev => ({
          ...prev,
          amclX: numberOrNull(pose.position?.x),
          amclY: numberOrNull(pose.position?.y),
          amclYaw: Math.atan2(siny, cosy),
        }));
      }
    });

    // Hazard detection
    findAndSub(['/hazard_detection'], (msg) => {
      const detections = (msg as any).detections;
      setState(prev => ({ ...prev, hazardCount: Array.isArray(detections) ? detections.length : 0 }));
    });

    // OAK-D NN detections
    findAndSub(['/oakd/nn/detections'], (msg) => {
      const dets = (msg as any).detections || (msg as any).data;
      setState(prev => ({ ...prev, nnDetections: Array.isArray(dets) ? dets.length : 0 }));
    });

    // Interface buttons
    findAndSub(['/interface_buttons'], (msg) => {
      setState(prev => ({ ...prev, ifaceButtons: typeof (msg as any).data === 'number' ? (msg as any).data : 0 }));
    });

    return () => {
      subscribed.forEach(t => { try { conn.unsubscribe(t); } catch {} });
    };
  }, [connection]);

  const online = state.batteryVoltage != null || state.diagLevel !== '-';
  const status: 'online' | 'idle' | 'offline' = online ? 'online' : connection ? 'idle' : 'offline';

  const metrics = [
    { label: '电量', value: state.batteryPercent != null ? `${state.batteryPercent.toFixed(0)}%` : '-', warn: state.batteryPercent != null && state.batteryPercent < 20 },
    { label: '电压', value: state.batteryVoltage != null ? `${state.batteryVoltage.toFixed(1)}V` : '-' },
    { label: '电流', value: state.batteryCurrent != null ? `${state.batteryCurrent.toFixed(1)}A` : '-' },
    { label: '停靠状态', value: state.dockStatus, warn: !state.dockVisible },
    { label: 'AMCL定位', value: state.amclX != null && state.amclY != null ? `${state.amclX.toFixed(2)}, ${state.amclY.toFixed(2)}` : '-' },
    { label: 'AMCL航向', value: state.amclYaw != null ? `${(state.amclYaw * 180 / Math.PI).toFixed(1)}°` : '-' },
  ];

  return <DeviceStatusCard title="TurtleBot4 状态" icon="🐢" status={status} metrics={metrics} />;
}
