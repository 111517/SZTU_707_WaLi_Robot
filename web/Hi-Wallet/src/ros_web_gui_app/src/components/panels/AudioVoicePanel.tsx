import { useEffect, useState } from 'react';
import type { RosbridgeConnection } from '../../utils/RosbridgeConnection';
import { DeviceStatusCard } from './DeviceStatusCard';

interface Props { connection: RosbridgeConnection | null }

const TOPICS = ['/audio_msg', '/audioreceiver', '/audiosender', '/audiohub/player/state'];
const SERVICES = ['/api/audiohub', '/api/voice', '/api/vui', '/api/assistant_recorder'];

export function AudioVoicePanel({ connection }: Props) {
  const [activeTopics, setActiveTopics] = useState<string[]>([]);
  const [activeServices, setActiveServices] = useState<string[]>([]);

  const status: 'online' | 'idle' | 'offline' =
    activeServices.length >= 2 ? 'online' : activeTopics.length > 0 ? 'idle' : 'offline';

  useEffect(() => {
    if (!connection?.isConnected()) { setActiveTopics([]); setActiveServices([]); return; }

    const refresh = () => {
      const serverTopics = connection.getProviderTopics();
      setActiveTopics(TOPICS.filter(t => serverTopics.some(pt => pt.name === t)));
      setActiveServices(SERVICES.filter(s => serverTopics.some(pt => pt.name.startsWith(s))));
    };
    refresh();
    const unsub = connection.onTopicsChange(() => refresh());
    return () => { unsub(); };
  }, [connection]);

  const onT = (t: string) => activeTopics.includes(t);
  const onS = (s: string) => activeServices.includes(s);

  return (
    <DeviceStatusCard title="音频 / 语音" icon="🎤" status={status} metrics={[
      { label: '音频消息', value: onT('/audio_msg') ? '活跃' : '离线' },
      { label: '音频接收', value: onT('/audioreceiver') ? '活跃' : '离线' },
      { label: '音频发送', value: onT('/audiosender') ? '活跃' : '离线' },
      { label: 'AudioHub', value: onS('/api/audiohub') ? '活跃' : '离线' },
      { label: '语音识别', value: onS('/api/voice') ? '活跃' : '离线', warn: !onS('/api/voice') },
      { label: 'VUI', value: onS('/api/vui') ? '活跃' : '离线' },
      { label: '录音助手', value: onS('/api/assistant_recorder') ? '活跃' : '离线' },
    ]} />
  );
}
