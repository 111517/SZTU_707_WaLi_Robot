import { useEffect, useRef, useState } from 'react';
import { AIChatMessage } from './AIChatMessage';
import { AIChatSettings } from './AIChatSettings';
import {
  type ChatSettings,
  type Conversation,
  OPENCLAW_GO2_BASE_URL,
  OPENCLAW_TB4_BASE_URL,
  estimateContextTokens,
  getOpenClawTokenForBaseUrl,
} from '../../utils/openclawApi';
import './AIChatDialog.css';

interface Props {
  conversations: Conversation[];
  activeConversationId: string | null;
  messages: Conversation['messages'];
  isStreaming: boolean;
  settings: ChatSettings;
  onSend: (text: string) => void;
  onStop: () => void;
  onRetry: () => void;
  onRegenerate: () => void;
  onCreateConversation: (baseUrl?: string) => void;
  onDeleteConversation: (id: string) => void;
  onSwitchConversation: (id: string) => void;
  onUpdateSettings: (s: ChatSettings) => void;
  onClose: () => void;
  connected: boolean;
}

export function AIChatDialog({
  conversations,
  activeConversationId,
  messages,
  isStreaming,
  settings,
  onSend,
  onStop,
  onRetry,
  onRegenerate,
  onCreateConversation,
  onDeleteConversation,
  onSwitchConversation,
  onUpdateSettings,
  onClose,
  connected,
}: Props) {
  const [input, setInput] = useState('');
  const [showSettings, setShowSettings] = useState(false);
  const [showSidebar, setShowSidebar] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const draftRef = useRef<Record<string, string>>({});
  const presetActiveRef = useRef<Record<string, string>>({});
  const prevBaseUrlRef = useRef<string>(settings.baseUrl);

  // filter conversations for current preset (legacy convs without baseUrl go to Go2)
  const presetConversations = conversations.filter(c =>
    c.baseUrl === settings.baseUrl || (!c.baseUrl && settings.baseUrl === OPENCLAW_GO2_BASE_URL)
  );

  // auto-scroll on new messages or conversation switch
  useEffect(() => {
    if (bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [messages, activeConversationId]);

  // switch conversation set when preset (baseUrl) changes
  useEffect(() => {
    const prev = prevBaseUrlRef.current;
    const curr = settings.baseUrl;
    if (prev === curr) return;
    prevBaseUrlRef.current = curr;

    // save current active conversation for previous preset
    if (activeConversationId) {
      presetActiveRef.current[prev] = activeConversationId;
    }

    // find the most recent conversation for the new preset
    const currConvs = conversations.filter(c => c.baseUrl === curr || (!c.baseUrl && curr === OPENCLAW_GO2_BASE_URL));
    if (currConvs.length > 0) {
      // restore last active, or pick the most recent
      const savedId = presetActiveRef.current[curr];
      const target = savedId && currConvs.find(c => c.id === savedId)
        ? savedId
        : currConvs.sort((a, b) => b.updatedAt - a.updatedAt)[0].id;
      onSwitchConversation(target);
    } else {
      // no conversations yet for this preset — create one
      onCreateConversation(curr);
    }
  }, [settings.baseUrl]); // eslint-disable-line react-hooks/exhaustive-deps

  // track current active conversation for current preset
  useEffect(() => {
    if (activeConversationId && settings.baseUrl) {
      presetActiveRef.current[settings.baseUrl] = activeConversationId;
    }
  }, [activeConversationId, settings.baseUrl]);

  // focus on open
  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  // restore draft on conversation switch
  useEffect(() => {
    const draft = draftRef.current[activeConversationId || ''] || '';
    setInput(draft);
    textareaRef.current?.focus();
  }, [activeConversationId]);

  // ESC / keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;

      // Esc hierarchy
      if (e.key === 'Escape') {
        if (showSettings) { setShowSettings(false); return; }
        if (showSidebar) { setShowSidebar(false); return; }
        if (input.trim()) {
          draftRef.current[activeConversationId || ''] = input;
        }
        onClose();
        return;
      }

      // Ctrl+N / Cmd+N — new conversation
      if (mod && e.key === 'n') {
        e.preventDefault();
        if (input.trim()) draftRef.current[activeConversationId || ''] = input;
        onCreateConversation(settings.baseUrl);
        return;
      }

      // Ctrl+W / Cmd+W — close dialog
      if (mod && e.key === 'w') {
        e.preventDefault();
        if (input.trim()) draftRef.current[activeConversationId || ''] = input;
        onClose();
        return;
      }

      // Ctrl+Shift+K — delete current conversation
      if (mod && e.shiftKey && e.key === 'K') {
        e.preventDefault();
        if (activeConversationId) onDeleteConversation(activeConversationId);
        return;
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose, showSettings, showSidebar, input, activeConversationId, onCreateConversation, onDeleteConversation, settings.baseUrl]);

  // auto-resize textarea
  const adjustHeight = () => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = 'auto';
      ta.style.height = Math.min(ta.scrollHeight, 120) + 'px';
    }
  };

  const handleInput = (value: string) => {
    setInput(value);
    draftRef.current[activeConversationId || ''] = value;
    setTimeout(adjustHeight, 0);
  };

  const handleSend = () => {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput('');
    draftRef.current[activeConversationId || ''] = '';
    onSend(text);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
    // Shift+Enter adds newline (default behavior)
  };

  const connectionColor = connected ? '#16a34a' : '#d97706';
  const connectionText = connected ? '已连接' : '连接中';
  const sortedConversations = [...presetConversations].sort((a, b) => b.updatedAt - a.updatedAt);
  const lastAiMsg = [...messages].reverse().find(m => m.role === 'assistant');
  const contextTokens = estimateContextTokens(messages);
  const assistantLabel = settings.baseUrl === OPENCLAW_TB4_BASE_URL ? 'TB4' : 'GO2';

  return (
    <div className="ai-dialog-overlay" onClick={onClose}>
      <div
        className="ai-dialog"
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="AI 助手对话框"
      >
        {/* Connection status bar */}
        <div
          className="ai-dialog-connection-bar"
          style={{ background: `linear-gradient(90deg, ${connectionColor}, ${connectionColor}88)` }}
        />

        {/* ── Sidebar ─────────────────────────────── */}
        {showSidebar && (
          <div className="ai-sidebar">
            <div className="ai-sidebar-header">
              <span className="ai-sidebar-title">对话列表</span>
              <button className="ai-header-btn" onClick={() => setShowSidebar(false)} aria-label="关闭列表">✕</button>
            </div>
            <button className="ai-new-chat-btn" onClick={() => { onCreateConversation(settings.baseUrl); setShowSidebar(false); }}>
              + 新建对话 <kbd>⌘N</kbd>
            </button>
            <div className="ai-sidebar-list">
              {sortedConversations.map(conv => (
                <div
                  key={conv.id}
                  className={`ai-sidebar-item ${conv.id === activeConversationId ? 'ai-sidebar-item--active' : ''}`}
                  onClick={() => { onSwitchConversation(conv.id); setShowSidebar(false); }}
                >
                  <span className="ai-sidebar-item-title">{conv.title}</span>
                  <span className="ai-sidebar-item-time">
                    {new Date(conv.updatedAt).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })}
                  </span>
                  <button
                    className="ai-sidebar-delete"
                    onClick={e => { e.stopPropagation(); onDeleteConversation(conv.id); }}
                    aria-label="删除对话"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Main column ─────────────────────────── */}
        <div className="ai-dialog-main">

          {/* ── Header ──────────────────────────────── */}
          <div className="ai-dialog-header">
            <div className="ai-dialog-header-left">
              <button
                className="ai-header-btn"
                onClick={() => setShowSidebar(!showSidebar)}
                aria-label="对话列表"
                title="对话列表"
              >
                ☰
              </button>
              <span className="ai-dialog-title">
                <button
                  className={`ai-preset-toggle ${settings.baseUrl === OPENCLAW_TB4_BASE_URL ? 'ai-preset-toggle--tb4' : ''}`}
                  onClick={() => {
                    const isGo2 = settings.baseUrl === OPENCLAW_GO2_BASE_URL;
                    const nextBaseUrl = isGo2 ? OPENCLAW_TB4_BASE_URL : OPENCLAW_GO2_BASE_URL;
                    const next = {
                      baseUrl: nextBaseUrl,
                      token: getOpenClawTokenForBaseUrl(nextBaseUrl),
                    };
                    onUpdateSettings({ ...settings, ...next });
                  }}
                  title="点击切换机器"
                >
                  <span className="ai-preset-toggle-label">GO2</span>
                  <span className="ai-preset-toggle-switch" />
                  <span className="ai-preset-toggle-label">TB4</span>
                </button>
              </span>
              <span className="ai-dialog-status">
                <span className="ai-status-dot" style={{ background: connectionColor }} />
                {connectionText}
              </span>
            </div>
            <div className="ai-dialog-header-right">
              <button className="ai-header-btn" onClick={() => setShowSettings(!showSettings)} aria-label="设置" title="设置">⚙️</button>
              <button className="ai-header-btn" onClick={() => onCreateConversation(settings.baseUrl)} aria-label="新建对话" title="新建对话 (⌘N)">+</button>
              <button className="ai-header-btn ai-header-close" onClick={onClose} aria-label="关闭 (⌘W)">✕</button>
            </div>
          </div>

          {/* ── Body ────────────────────────────────── */}
          <div className="ai-dialog-body" ref={bodyRef}>
            {showSettings ? (
              <AIChatSettings settings={settings} onSave={onUpdateSettings} onClose={() => setShowSettings(false)} contextTokens={contextTokens} />
            ) : messages.length === 0 ? (
              <div className="ai-empty-state">
                <div className="ai-empty-icon">🐕</div>
                <div className="ai-empty-text">向 {assistantLabel} 发送指令开始对话</div>
              </div>
            ) : (
              <>
                {messages.map((msg, i) => (
                  <AIChatMessage
                    key={msg.id}
                    message={msg}
                    isStreaming={isStreaming && i === messages.length - 1 && msg.role === 'assistant'}
                    isLastAi={msg.id === lastAiMsg?.id}
                    assistantLabel={assistantLabel}
                    onRetry={msg.isError ? onRetry : undefined}
                    onRegenerate={!isStreaming && msg.id === lastAiMsg?.id ? onRegenerate : undefined}
                  />
                ))}
                {isStreaming && messages[messages.length - 1]?.content === '' && (
                  <div className="ai-streaming-dots">
                    <span className="ai-dot" style={{ animationDelay: '0s' }} />
                    <span className="ai-dot" style={{ animationDelay: '0.2s' }} />
                    <span className="ai-dot" style={{ animationDelay: '0.4s' }} />
                  </div>
                )}
              </>
            )}
          </div>

          {/* ── Footer ──────────────────────────────── */}
          <div className="ai-dialog-footer">
            <textarea
              ref={textareaRef}
              className="ai-input"
              value={input}
              onChange={e => handleInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={isStreaming ? `${assistantLabel} 正在回复...` : `向 ${assistantLabel} 发送指令... (Enter 发送，Shift+Enter 换行)`}
              disabled={isStreaming}
              aria-label="输入消息"
              rows={1}
            />
            {isStreaming ? (
              <button className="ai-send-btn ai-send-stop" onClick={onStop} aria-label="停止生成 (Esc)">
                <span className="ai-stop-icon" />
              </button>
            ) : (
              <button
                className="ai-send-btn"
                onClick={handleSend}
                disabled={!input.trim()}
                aria-label="发送"
              >
                <span className="ai-send-arrow">→</span>
              </button>
            )}
          </div>

        </div>{/* /ai-dialog-main */}
      </div>
    </div>
  );
}
