import { useEffect, useState } from 'react';
import type { RosbridgeConnection } from '../../utils/RosbridgeConnection';
import { DeviceStatusCard } from './DeviceStatusCard';

interface Props { connection: RosbridgeConnection | null }

export function SensorsPanel({ connection }: Props) {
  const [gasTopic, setGasTopic] = useState(false);
  const [gasValue, setGasValue] = useState('-');
  const [gestureTopic, setGestureTopic] = useState(false);
  const [gestureResult, setGestureResult] = useState('-');
  const [uwbState, setUwbState] = useState(false);
  const [uwbSwitch, setUwbSwitch] = useState(false);
  const [uwbSwitchVal, setUwbSwitchVal] = useState('-');
  const [selfTest, setSelfTest] = useState(false);

  const online = [gasTopic, gestureTopic, uwbState, uwbSwitch, selfTest].filter(Boolean).length;
  const status: 'online' | 'idle' | 'offline' = online >= 3 ? 'online' : online > 0 ? 'idle' : 'offline';

  useEffect(() => {
    if (!connection?.isConnected()) {
      setGasTopic(false); setGasValue('-'); setGestureTopic(false);
      setGestureResult('-'); setUwbState(false); setUwbSwitch(false);
      setUwbSwitchVal('-'); setSelfTest(false);
      return;
    }

    let subbed: string[] = [];
    const refresh = () => {
      subbed.forEach(t => { try { connection.unsubscribe(t); } catch {} });
      subbed = [];

      const allTopics = connection.getProviderTopics();
      const hasTopic = (candidates: string[]) => allTopics.some(t => candidates.some(c => t.name === c));
      const findAndSub = (candidates: string[], cb: (msg: Record<string, unknown>) => void) => {
        const t = allTopics.find(tp => candidates.some(c => tp.name === c));
        if (t) { connection.subscribe(t.name, t.type, cb as (msg: unknown) => void); subbed.push(t.name); }
      };

      setGasTopic(hasTopic(['/gas_sensor', '/sensor/gas']));
      setGestureTopic(hasTopic(['/gesture/result']));
      setUwbState(hasTopic(['/uwbstate', '/uwb_state']));
      setUwbSwitch(hasTopic(['/uwbswitch', '/uwb_switch']));
      setSelfTest(hasTopic(['/selftest']));

      findAndSub(['/sensor/gas', '/gas_sensor'], (msg) => {
        const v = (msg as Record<string, unknown>).data;
        setGasValue(v != null ? String(v).slice(0, 20) : 'active');
      });
      findAndSub(['/gesture/result'], (msg) => {
        const d = (msg as Record<string, unknown>).data;
        setGestureResult(typeof d === 'string' ? d : 'detected');
      });
      findAndSub(['/uwb_switch', '/uwbswitch'], (msg) => {
        const d = (msg as Record<string, unknown>).data;
        setUwbSwitchVal(d != null ? String(d) : '1');
      });
    };
    refresh();
    const unsub = connection.onTopicsChange(() => refresh());
    return () => { unsub(); subbed.forEach(t => { try { connection.unsubscribe(t); } catch {} }); };
  }, [connection]);

  return (
    <DeviceStatusCard title="传感器" icon="🌡️" status={status} metrics={[
      { label: '气体传感器', value: gasValue },
      { label: '手势识别', value: gestureResult },
      { label: 'UWB状态', value: uwbState ? '活跃' : '离线' },
      { label: 'UWB开关', value: uwbSwitch ? (uwbSwitchVal !== '-' ? uwbSwitchVal : '活跃') : '离线' },
      { label: '自检', value: selfTest ? '可用' : '离线' },
    ]} />
  );
}
