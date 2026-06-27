import { useCallback, useState } from 'react';
import { type ChatMessage, parseMarkdown, formatTime } from '../../utils/openclawApi';
import './AIChatMessage.css';

interface Props {
  message: ChatMessage;
  isStreaming: boolean;
  isLastAi: boolean;
  assistantLabel: string;
  onRetry?: () => void;
  onRegenerate?: () => void;
}

export function AIChatMessage({ message, isStreaming, isLastAi, assistantLabel, onRetry, onRegenerate }: Props) {
  const isUser = message.role === 'user';
  const showRegenerate = isLastAi && !isStreaming && !message.isError && onRegenerate && message.content.length > 0;
  const showRetry = message.isError && onRetry;
  const [thinkingOpen, setThinkingOpen] = useState(true); // default open during streaming

  const handleCopy = useCallback(() => {
    const text = message.reasoning
      ? `[思考过程]\n${message.reasoning}\n\n${message.content}`
      : message.content;
    navigator.clipboard.writeText(text).catch(() => {
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    });
  }, [message.content, message.reasoning]);

  // Handle copy button clicks in rendered markdown
  const handleBubbleClick = useCallback((e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    if (target.classList.contains('ai-copy-btn')) {
      const code = target.getAttribute('data-code') || '';
      navigator.clipboard.writeText(code).catch(() => {});
      target.textContent = '✓';
      setTimeout(() => { target.textContent = '📋'; }, 1500);
    }
  }, []);

  const hasReasoning = !!message.reasoning;
  const isThinking = isLastAi && isStreaming && !message.content && hasReasoning;

  return (
    <div className={`ai-message ${isUser ? 'ai-message--user' : 'ai-message--ai'}`}>
      {!isUser && <div className="ai-message-label">{assistantLabel} &gt;</div>}

      {/* ── Thinking / Reasoning block ─────────────── */}
      {hasReasoning && (
        <details
          className={`ai-thinking ${isThinking ? 'ai-thinking--active' : ''}`}
          open={thinkingOpen}
          onToggle={e => setThinkingOpen((e.target as HTMLDetailsElement).open)}
        >
          <summary className="ai-thinking-summary">
            <span className="ai-thinking-indicator" />
            <span>{isThinking ? '思考中...' : '已完成思考'}</span>
            <span className="ai-thinking-chevron">▾</span>
          </summary>
          <div className="ai-thinking-content">
            {message.reasoning}
          </div>
        </details>
      )}

      <div className="ai-message-row">
        {!isUser && (
          <div className="ai-message-actions">
            <button className="ai-msg-btn" onClick={handleCopy} title="复制" aria-label="复制消息">
              📋
            </button>
            {showRetry && (
              <button className="ai-msg-btn ai-msg-btn--retry" onClick={onRetry} title="重试" aria-label="重试">
                🔄
              </button>
            )}
            {showRegenerate && (
              <button className="ai-msg-btn" onClick={onRegenerate} title="重新生成" aria-label="重新生成">
                ↻
              </button>
            )}
          </div>
        )}

        <div
          className={`ai-message-bubble ${isUser ? 'ai-message-bubble--user' : 'ai-message-bubble--ai'} ${message.isError ? 'ai-message-bubble--error' : ''}`}
          {...(isUser ? {} : { onClick: handleBubbleClick })}
        >
          {isUser ? (
            message.content
          ) : message.content ? (
            <span dangerouslySetInnerHTML={{ __html: parseMarkdown(message.content) }} />
          ) : hasReasoning ? (
            <span className="ai-waiting-text">...</span>
          ) : null}
        </div>

        {isUser && (
          <div className="ai-message-actions ai-message-actions--user">
            <button className="ai-msg-btn" onClick={handleCopy} title="复制" aria-label="复制消息">
              📋
            </button>
          </div>
        )}
      </div>

      <div className={`ai-message-time ${isUser ? 'ai-message-time--user' : ''}`}>
        {formatTime(message.timestamp)}
        {message.tokenUsage && !isUser && (
          <span className="ai-token-info" title={`prompt: ${message.tokenUsage.prompt.toLocaleString()}, completion: ${message.tokenUsage.completion.toLocaleString()}`}>
            · {message.tokenUsage.total.toLocaleString()} tokens
          </span>
        )}
        {isLastAi && isStreaming && message.content && (
          <span className="ai-streaming-cursor" />
        )}
      </div>
    </div>
  );
}
