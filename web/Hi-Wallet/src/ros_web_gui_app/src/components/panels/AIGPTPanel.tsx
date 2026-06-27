import { useEffect, useState } from 'react';
import type { RosbridgeConnection } from '../../utils/RosbridgeConnection';
import { DeviceStatusCard } from './DeviceStatusCard';

interface Props { connection: RosbridgeConnection | null }

export function AIGPTPanel({ connection }: Props) {
  const [gptCmd, setGptCmd] = useState(false);
  const [gptState, setGptState] = useState('-');
  const [gptFeedback, setGptFeedback] = useState(false);
  const [gptService, setGptService] = useState(false);
  const [fourgAgent, setFourgAgent] = useState(false);

  const online = [gptCmd, gptFeedback, gptService, fourgAgent].filter(Boolean).length;
  const status: 'online' | 'idle' | 'offline' = online >= 2 ? 'online' : online > 0 ? 'idle' : 'offline';

  useEffect(() => {
    if (!connection?.isConnected()) {
      setGptCmd(false); setGptState('-'); setGptFeedback(false);
      setGptService(false); setFourgAgent(false);
      return;
    }

    let subbed: string[] = [];
    const refresh = () => {
      subbed.forEach(t => { try { connection.unsubscribe(t); } catch {} });
      subbed = [];

      const allTopics = connection.getProviderTopics();
      setGptCmd(allTopics.some(t => t.name === '/gpt_cmd'));
      setGptFeedback(allTopics.some(t => t.name === '/gptflowfeedback'));
      setGptService(allTopics.some(t => t.name.startsWith('/api/gpt')));
      setFourgAgent(allTopics.some(t => t.name.startsWith('/api/fourg_agent')));

      const findAndSub = (candidates: string[], cb: (msg: Record<string, unknown>) => void) => {
        const t = allTopics.find(tp => candidates.some(c => tp.name === c));
        if (t) { connection.subscribe(t.name, t.type, cb as (msg: unknown) => void); subbed.push(t.name); }
      };
      findAndSub(['/ai/gpt_state', '/gpt_state'], (msg) => {
        const d = (msg as Record<string, unknown>).data;
        setGptState(typeof d === 'string' ? d.slice(0, 40) : String(d ?? 'active'));
      });
    };
    refresh();
    const unsub = connection.onTopicsChange(() => refresh());
    return () => { unsub(); subbed.forEach(t => { try { connection.unsubscribe(t); } catch {} }); };
  }, [connection]);

  return (
    <DeviceStatusCard title="AI / GPT" icon="🧠" status={status} metrics={[
      { label: 'GPT命令', value: gptCmd ? '活跃' : '离线' },
      { label: 'GPT状态', value: gptState },
      { label: 'GPT反馈', value: gptFeedback ? '活跃' : '离线' },
      { label: 'GPT服务', value: gptService ? '活跃' : '离线', warn: !gptService },
      { label: 'FourG Agent', value: fourgAgent ? '活跃' : '离线' },
    ]} />
  );
}
