import { useEffect, useRef, useState } from 'react';
import type { RosbridgeConnection } from '../../utils/RosbridgeConnection';
import { DeviceStatusCard } from './DeviceStatusCard';

interface Props { connection: RosbridgeConnection | null }

interface LowStateData {
  batteryVoltage: number | null;
  batteryCurrent: number | null;
  batteryPercent: number | null;
  imu: { roll: number | null; pitch: number | null; yaw: number | null };
  footForce: number | null;
}

interface SportStateData {
  gaitType: number | null;
  bodyHeight: number | null;
  velocity: number[];
  yawSpeed: number | null;
}

const numberOrNull = (v: unknown): number | null =>
  typeof v === 'number' && Number.isFinite(v) ? v : null;

// Bridged standard topics (from unitree_bridge_node) — preferred
const BATTERY_STATE_TOPICS = ['/battery_state'];
const GAIT_TYPE_TOPICS = ['/robot/gait_type'];
const BODY_HEIGHT_TOPICS = ['/robot/body_height'];
const VELOCITY_X_TOPICS = ['/robot/velocity/x'];
const VELOCITY_Y_TOPICS = ['/robot/velocity/y'];
const VELOCITY_YAW_TOPICS = ['/robot/velocity/yaw'];
const IMU_TOPICS = ['/imu/data'];
const FOOT_FORCE_TOPICS = ['/robot/foot_force'];
const JOINT_TOPICS = ['/joint_states'];
const BATTERY_ALARM_TOPICS = ['/robot/battery_alarm', '/lf/battery_alarm'];
const SERVICE_STATE_TOPICS = ['/robot/service_state', '/servicestate'];

// Legacy custom-type topics (fallback)
const LOW_STATE_TOPICS = ['/lowstate', '/lf/lowstate'];
const SPORT_STATE_TOPICS = ['/go2_states', '/sportmodestate', '/lf/sportmodestate'];

export function RobotCorePanel({ connection }: Props) {
  const [lowState, setLowState] = useState<LowStateData | null>(null);
  const [sportState, setSportState] = useState<SportStateData | null>(null);
  const [batteryAlarm, setBatteryAlarm] = useState<string | null>(null);
  const [serviceState, setServiceState] = useState<string | null>(null);
  const [jointCount, setJointCount] = useState(0);
  const [topicStatus, setTopicStatus] = useState<string>('');
  const connRef = useRef(connection);

  // ── Velocity SMA (simple moving average) to de-bounce split-topic flicker ──
  const SMA_WINDOW = 4;  // 4 samples at ~10 Hz = 400 ms smoothing window
  const velBufRef = useRef({ vx: [] as number[], vy: [] as number[], vyaw: [] as number[] });
  const [smoothedVel, setSmoothedVel] = useState<{ vx: number; vy: number; vyaw: number } | null>(null);

  const pushAndSmooth = (buf: number[], val: number): number => {
    buf.push(val);
    while (buf.length > SMA_WINDOW) buf.shift();
    if (buf.length === 0) return 0;
    return buf.reduce((s, v) => s + v, 0) / buf.length;
  };

  const emitSmoothedVel = () => {
    const b = velBufRef.current;
    setSmoothedVel({
      vx: b.vx.length > 0 ? b.vx.reduce((s, v) => s + v, 0) / b.vx.length : 0,
      vy: b.vy.length > 0 ? b.vy.reduce((s, v) => s + v, 0) / b.vy.length : 0,
      vyaw: b.vyaw.length > 0 ? b.vyaw.reduce((s, v) => s + v, 0) / b.vyaw.length : 0,
    });
  };

  const status: 'online' | 'idle' | 'offline' = lowState || sportState ? 'online' : connection ? 'idle' : 'offline';

  useEffect(() => { connRef.current = connection; }, [connection]);

  useEffect(() => {
    const conn = connRef.current;
    if (!conn?.isConnected()) {
      setLowState(null); setSportState(null); setBatteryAlarm(null);
      setServiceState(null); setJointCount(0); setTopicStatus(''); setSmoothedVel(null);
      velBufRef.current = { vx: [], vy: [], vyaw: [] };
      return;
    }

    let subscribed: string[] = [];

    const doSubscribe = () => {
      subscribed.forEach(t => { try { conn.unsubscribe(t); } catch {} });
      subscribed = [];

      const allTopics = conn.getProviderTopics();
      if (allTopics.length === 0) {
        setTopicStatus('等待话题发现... 请确认 rosbridge 已连接');
        return;
      }

      const findAndSub = (candidates: string[], cb: (msg: Record<string, unknown>) => void) => {
        const t = allTopics.find(tp => candidates.some(c => tp.name === c));
        if (t) { conn.subscribe(t.name, t.type, cb as (msg: unknown) => void); subscribed.push(t.name); }
      };

      // ── Bridged standard subscriptions (primary) ──

      // sensor_msgs/BatteryState
      findAndSub(BATTERY_STATE_TOPICS, (msg) => {
        setLowState((prev) => ({
          ...(prev ?? { imu: { roll: null, pitch: null, yaw: null }, footForce: null }),
          batteryVoltage: numberOrNull(msg.voltage) ?? prev?.batteryVoltage ?? null,
          batteryCurrent: numberOrNull(msg.current) ?? prev?.batteryCurrent ?? null,
          batteryPercent: numberOrNull(msg.percentage) ?? prev?.batteryPercent ?? null,
        }));
      });

      // std_msgs/Int32 → gait_type
      findAndSub(GAIT_TYPE_TOPICS, (msg) => {
        setSportState((prev) => ({
          ...(prev ?? { gaitType: null, bodyHeight: null, velocity: [0, 0, 0], yawSpeed: null }),
          gaitType: numberOrNull((msg as Record<string, unknown>).data) ?? prev?.gaitType ?? null,
        }));
      });

      // std_msgs/Float32 → body_height
      findAndSub(BODY_HEIGHT_TOPICS, (msg) => {
        setSportState((prev) => ({
          ...(prev ?? { gaitType: null, bodyHeight: null, velocity: [0, 0, 0], yawSpeed: null }),
          bodyHeight: numberOrNull((msg as Record<string, unknown>).data) ?? prev?.bodyHeight ?? null,
        }));
      });

      // std_msgs/Float32 → velocity.x (SMA-smoothed)
      findAndSub(VELOCITY_X_TOPICS, (msg) => {
        const vx = numberOrNull((msg as Record<string, unknown>).data) ?? 0;
        pushAndSmooth(velBufRef.current.vx, vx);
        emitSmoothedVel();
        setSportState((prev) => {
          const base = prev ?? { gaitType: null, bodyHeight: null, velocity: [0, 0, 0], yawSpeed: null };
          const vel = [...base.velocity]; vel[0] = vx;
          return { ...base, velocity: vel };
        });
      });

      // std_msgs/Float32 → velocity.y (SMA-smoothed)
      findAndSub(VELOCITY_Y_TOPICS, (msg) => {
        const vy = numberOrNull((msg as Record<string, unknown>).data) ?? 0;
        pushAndSmooth(velBufRef.current.vy, vy);
        emitSmoothedVel();
        setSportState((prev) => {
          const base = prev ?? { gaitType: null, bodyHeight: null, velocity: [0, 0, 0], yawSpeed: null };
          const vel = [...base.velocity]; vel[1] = vy;
          return { ...base, velocity: vel };
        });
      });

      // std_msgs/Float32 → velocity.yaw / yaw_speed (SMA-smoothed)
      findAndSub(VELOCITY_YAW_TOPICS, (msg) => {
        const vyaw = numberOrNull((msg as Record<string, unknown>).data) ?? 0;
        pushAndSmooth(velBufRef.current.vyaw, vyaw);
        emitSmoothedVel();
        setSportState((prev) => ({
          ...(prev ?? { gaitType: null, bodyHeight: null, velocity: [0, 0, 0], yawSpeed: null }),
          yawSpeed: vyaw,
        }));
      });

      // sensor_msgs/Imu → orientation (quaternion → rpy)
      findAndSub(IMU_TOPICS, (msg) => {
        const q = (msg as Record<string, unknown>).orientation as Record<string, number> | undefined;
        let roll: number | null = null, pitch: number | null = null, yaw: number | null = null;
        if (q && q.x !== undefined && q.y !== undefined && q.z !== undefined && q.w !== undefined) {
          const x = q.x, y = q.y, z = q.z, w = q.w;
          const sinr_cosp = 2 * (w * x + y * z);
          const cosr_cosp = 1 - 2 * (x * x + y * y);
          roll = Math.atan2(sinr_cosp, cosr_cosp);
          const sinp = 2 * (w * y - z * x);
          pitch = Math.abs(sinp) >= 1 ? Math.sign(sinp) * Math.PI / 2 : Math.asin(sinp);
          const siny_cosp = 2 * (w * z + x * y);
          const cosy_cosp = 1 - 2 * (y * y + z * z);
          yaw = Math.atan2(siny_cosp, cosy_cosp);
        }
        setLowState((prev) => ({
          ...(prev ?? { batteryVoltage: null, batteryCurrent: null, batteryPercent: null, footForce: null }),
          imu: {
            roll: roll ?? prev?.imu.roll ?? null,
            pitch: pitch ?? prev?.imu.pitch ?? null,
            yaw: yaw ?? prev?.imu.yaw ?? null,
          },
        }));
      });

      // std_msgs/Float32 → foot_force
      findAndSub(FOOT_FORCE_TOPICS, (msg) => {
        setLowState((prev) => ({
          ...(prev ?? { batteryVoltage: null, batteryCurrent: null, batteryPercent: null, imu: { roll: null, pitch: null, yaw: null } }),
          footForce: numberOrNull((msg as Record<string, unknown>).data) ?? prev?.footForce ?? null,
        }));
      });

      // std_msgs/String → battery_alarm
      findAndSub(BATTERY_ALARM_TOPICS, (msg) => {
        const d = (msg as Record<string, unknown>).data;
        setBatteryAlarm(typeof d === 'string' ? d : String(d ?? ''));
      });

      // std_msgs/String → service_state
      findAndSub(SERVICE_STATE_TOPICS, (msg) => {
        const d = (msg as Record<string, unknown>).data;
        setServiceState(typeof d === 'string' ? d : String(d ?? ''));
      });

      // sensor_msgs/JointState → joint count
      findAndSub(JOINT_TOPICS, (msg) => {
        const names = (msg as Record<string, unknown>).name;
        setJointCount(Array.isArray(names) ? names.length : 0);
      });

      // ── Legacy custom-type fallbacks ──
      findAndSub(LOW_STATE_TOPICS, (msg) => {
        const imu = (msg.imu_state as Record<string, unknown>) ?? {};
        const rpy = Array.isArray(imu.rpy) ? imu.rpy : [];
        setLowState((prev) => ({
          batteryVoltage: numberOrNull(msg.power_v) ?? prev?.batteryVoltage ?? null,
          batteryCurrent: numberOrNull(msg.power_a) ?? prev?.batteryCurrent ?? null,
          batteryPercent: prev?.batteryPercent ?? null,
          imu: {
            roll: numberOrNull(rpy[0]) ?? prev?.imu.roll ?? null,
            pitch: numberOrNull(rpy[1]) ?? prev?.imu.pitch ?? null,
            yaw: numberOrNull(rpy[2]) ?? prev?.imu.yaw ?? null,
          },
          footForce: prev?.footForce ?? null,
        }));
      });

      findAndSub(SPORT_STATE_TOPICS, (msg) => {
        const rawV = Array.isArray(msg.velocity) ? msg.velocity.slice(0, 3) : [];
        const vx = numberOrNull(rawV[0]) ?? 0;
        const vy = numberOrNull(rawV[1]) ?? 0;
        const vyaw = numberOrNull(msg.yaw_speed) ?? 0;
        // Feed SMA buffers for smoothed display
        pushAndSmooth(velBufRef.current.vx, vx);
        pushAndSmooth(velBufRef.current.vy, vy);
        pushAndSmooth(velBufRef.current.vyaw, vyaw);
        emitSmoothedVel();
        setSportState((prev) => ({
          gaitType: numberOrNull(msg.gait_type) ?? prev?.gaitType ?? null,
          bodyHeight: numberOrNull(msg.body_height) ?? prev?.bodyHeight ?? null,
          velocity: [0, 1, 2].map((i) => numberOrNull(rawV[i]) ?? 0),
          yawSpeed: vyaw,
        }));
      });

      setTopicStatus(`已订阅 ${subscribed.length} 个话题`);
    };

    doSubscribe();

    const unsubTopics = conn.onTopicsChange(() => { doSubscribe(); });

    return () => {
      unsubTopics();
      subscribed.forEach(t => { try { conn.unsubscribe(t); } catch {} });
    };
  }, [connection]);

  const batteryV = lowState?.batteryVoltage;
  const batteryPct = lowState?.batteryPercent ?? (batteryV != null
    ? Math.min(100, Math.max(0, ((batteryV - 22) / (29.4 - 22)) * 100))
    : null);

  // Parse battery alarm JSON
  let batteryAlarmDisplay = '-';
  let batteryAlarmWarn = false;
  if (batteryAlarm) {
    try {
      const alarm = JSON.parse(batteryAlarm);
      if (alarm && typeof alarm === 'object') {
        const status = alarm.alarm_status ?? alarm.status ?? -1;
        const desc = alarm.description || '';
        batteryAlarmDisplay = status === 0 ? `正常${desc ? ` (${desc})` : ''}` : `告警! (code:${status})`;
        batteryAlarmWarn = status !== 0;
      }
    } catch { batteryAlarmDisplay = batteryAlarm.slice(0, 30); }
  }

  // Parse service state JSON
  let serviceDisplay = '-';
  if (serviceState) {
    try {
      const services = JSON.parse(serviceState);
      if (Array.isArray(services)) {
        const activeCount = services.filter((s: Record<string, unknown>) => s.status === 1 || s.protect === 0).length;
        serviceDisplay = `${services.length}个服务 · ${activeCount}活跃`;
      }
    } catch { serviceDisplay = serviceState.slice(0, 20); }
  }

  const metrics = [
    { label: '电量', value: batteryPct != null ? `${batteryPct.toFixed(0)}%` : '-', warn: batteryPct != null && batteryPct < 20 },
    { label: '电压', value: batteryV != null ? `${batteryV.toFixed(1)}V` : '-' },
    { label: '电流', value: lowState?.batteryCurrent != null ? `${lowState.batteryCurrent.toFixed(1)}A` : '-' },
    { label: '姿态 R/P/Y', value: lowState?.imu.roll != null && lowState?.imu.pitch != null && lowState?.imu.yaw != null ? `${(lowState.imu.roll * 180 / Math.PI).toFixed(1)}/${(lowState.imu.pitch * 180 / Math.PI).toFixed(1)}/${(lowState.imu.yaw * 180 / Math.PI).toFixed(1)}°` : '-' },
    { label: '步态', value: sportState?.gaitType != null ? String(sportState.gaitType) : '-' },
    { label: '身高', value: sportState?.bodyHeight != null ? `${sportState.bodyHeight.toFixed(3)}m` : '-' },
    { label: '速度 X/Y/Yaw', value: smoothedVel ? `${smoothedVel.vx.toFixed(2)}/${smoothedVel.vy.toFixed(2)}/${smoothedVel.vyaw.toFixed(2)}` : '-' },
    { label: '关节数', value: jointCount > 0 ? String(jointCount) : '-' },
    { label: '足端力', value: lowState?.footForce != null ? `${lowState.footForce.toFixed(1)}N` : '-' },
    { label: '电池报警', value: batteryAlarmDisplay, warn: batteryAlarmWarn },
    { label: '服务状态', value: serviceDisplay },
  ];

  if (topicStatus && !lowState && !sportState) {
    metrics.unshift({ label: '状态', value: topicStatus, warn: true });
  }

  return <DeviceStatusCard title="机器人核心状态" icon="🤖" status={status} metrics={metrics} />;
}
