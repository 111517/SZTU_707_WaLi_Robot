import { useEffect, useState } from 'react';
import './AIChatFAB.css';

interface Props {
  connected: boolean;
  hasNewMessage: boolean;
  onClick: () => void;
}

export function AIChatFAB({ connected, hasNewMessage, onClick }: Props) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // delay entrance for smooth page load
    const t = setTimeout(() => setVisible(true), 600);
    return () => clearTimeout(t);
  }, []);

  const statusClass = connected ? 'ai-fab--connected' : 'ai-fab--connecting';

  return (
    <button
      className={`ai-fab ${statusClass} ${visible ? 'ai-fab--visible' : ''}`}
      onClick={onClick}
      aria-label="打开 AI 助手"
      title={connected ? 'GO2 AI 已连接' : 'GO2 AI 连接中'}
    >
      {/* Robot face */}
      <div className="ai-fab-face">
        <div className="ai-fab-eyes">
          <span className="ai-fab-eye" />
          <span className="ai-fab-eye" />
        </div>
        <span className="ai-fab-mouth" />
      </div>
      {/* New message dot */}
      {hasNewMessage && !connected && (
        <span className="ai-fab-dot" />
      )}
      {hasNewMessage && connected && (
        <span className="ai-fab-dot ai-fab-dot--amber" />
      )}
    </button>
  );
}
