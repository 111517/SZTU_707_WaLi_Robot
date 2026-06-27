// ── Types ───────────────────────────────────────────

export interface ChatSettings {
  baseUrl: string;
  token: string;
  model: string;
  systemPrompt: string;
  temperature: number;
  topP: number;
  maxTokens: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  reasoning?: string;  // thinking/reasoning chain (visible in collapsible block)
  timestamp: number;
  tokenUsage?: { prompt: number; completion: number; total: number };
  isError?: boolean;
}

export interface Conversation {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
  baseUrl?: string;  // which preset this conversation belongs to
}

// ── Defaults ────────────────────────────────────────

export const OPENCLAW_GO2_BASE_URL = '/api/ai';
export const OPENCLAW_TB4_BASE_URL = '/api/ai-tb4';

export function getOpenClawTokenForBaseUrl(baseUrl: string): string {
  if (baseUrl === OPENCLAW_TB4_BASE_URL) {
    return import.meta.env.VITE_OPENCLAW_TB4_TOKEN || '';
  }
  if (baseUrl === OPENCLAW_GO2_BASE_URL) {
    return import.meta.env.VITE_OPENCLAW_GO2_TOKEN || '';
  }
  return '';
}

const DEFAULT_SETTINGS: ChatSettings = {
  baseUrl: OPENCLAW_GO2_BASE_URL,
  token: getOpenClawTokenForBaseUrl(OPENCLAW_GO2_BASE_URL),
  model: 'openclaw/main',
  systemPrompt: '你是一个在飞书群里的 Go2 机器人助手，帮助用户控制机械狗、查询状态和回答问题。你的回复应该简洁直接，适合群聊场景。',
  temperature: 0.7,
  topP: 1,
  maxTokens: 4096,
};

// ── IDs ─────────────────────────────────────────────

export function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

// ── Settings persistence ────────────────────────────

const SETTINGS_KEY = 'ai_chat_settings';

export function loadSettings(): ChatSettings {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (raw) return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
  } catch { /* ignore */ }
  return { ...DEFAULT_SETTINGS };
}

export function saveSettings(settings: ChatSettings): void {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
}

// ── Conversation persistence ────────────────────────

const CONVERSATIONS_KEY = 'ai_chat_conversations';
const LEGACY_HISTORY_KEY = 'ai_chat_history';
const MAX_CONVERSATIONS = 50;

function autoTitle(text: string): string {
  const cleaned = text.replace(/\n/g, ' ').trim();
  return cleaned.length > 30 ? cleaned.slice(0, 30) + '…' : cleaned;
}

export function loadConversations(): Conversation[] {
  try {
    const raw = localStorage.getItem(CONVERSATIONS_KEY);
    if (raw) {
      const convs = JSON.parse(raw) as Conversation[];
      if (convs.length > 0) return convs;
    }
  } catch { /* ignore */ }

  // migrate legacy history
  try {
    const legacy = localStorage.getItem(LEGACY_HISTORY_KEY);
    if (legacy) {
      const messages = JSON.parse(legacy) as ChatMessage[];
      if (messages.length > 0) {
        const firstUser = messages.find(m => m.role === 'user');
        return [{
          id: generateId(),
          title: firstUser ? autoTitle(firstUser.content) : '历史对话',
          messages,
          createdAt: messages[0]?.timestamp || Date.now(),
          updatedAt: messages[messages.length - 1]?.timestamp || Date.now(),
        }];
      }
    }
  } catch { /* ignore */ }

  return [];
}

export function saveConversations(conversations: Conversation[]): void {
  try {
    const trimmed = conversations.slice(-MAX_CONVERSATIONS);
    localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(trimmed));
  } catch { /* ignore */ }
}

// ── Token estimation ────────────────────────────────
// Rough estimate: ~4 chars per token for CJK, ~4 chars for English
// This is approximate; real token counts come from the API

export function estimateTokens(text: string): number {
  let chars = 0;
  for (const ch of text) {
    // CJK characters count as ~1.5 tokens each
    chars += (ch.charCodeAt(0) > 0x4e00) ? 1.5 : 1;
  }
  return Math.ceil(chars / 3.5); // rough average
}

export function estimateContextTokens(messages: Array<{ role: string; content: string; reasoning?: string }>): number {
  let total = 0;
  for (const m of messages) {
    total += estimateTokens(m.role) + estimateTokens(m.content);
    if (m.reasoning) total += estimateTokens(m.reasoning);
  }
  return total;
}

// ── Fetch available models ──────────────────────────

export interface ModelInfo {
  id: string;
  name?: string;
  owned_by?: string;
}

export async function fetchModels(baseUrl: string, token: string, signal?: AbortSignal): Promise<ModelInfo[]> {
  const headers: Record<string, string> = {};
  if (token.trim()) {
    headers.Authorization = `Bearer ${token}`;
  }

  const res = await fetch(`${baseUrl}/v1/models`, {
    headers,
    signal,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  const list = data.data || data.models || data || [];
  return list.map((m: Record<string, unknown>) => ({
    id: (m.id as string) || '',
    name: (m.name as string) || undefined,
    owned_by: (m.owned_by as string) || undefined,
  })).filter((m: ModelInfo) => m.id);
}

// ── SSE Streaming ───────────────────────────────────

interface SSECallbacks {
  onToken: (text: string) => void;
  onReasoning?: (text: string) => void;
  onDone: (usage?: { prompt: number; completion: number; total: number }) => void;
  onError: (err: Error) => void;
}

export async function streamChat(
  settings: ChatSettings,
  messages: Array<{ role: string; content: string }>,
  callbacks: SSECallbacks,
  signal?: AbortSignal,
  conversationId?: string,
): Promise<void> {
  const { baseUrl, token, model, systemPrompt, temperature, topP, maxTokens } = settings;

  const payloadMessages = systemPrompt
    ? [{ role: 'system', content: systemPrompt }, ...messages]
    : messages;

  let response: Response;
  try {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (token.trim()) {
      headers.Authorization = `Bearer ${token}`;
    }

    response = await fetch(`${baseUrl}/v1/chat/completions`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        model,
        stream: true,
        messages: payloadMessages,
        temperature,
        top_p: topP,
        max_tokens: maxTokens,
        ...(conversationId ? {
          user: conversationId,
        } : {}),
      }),
      signal,
    });
  } catch (err) {
    callbacks.onError(err instanceof Error ? err : new Error('Network error'));
    return;
  }

  if (!response.ok) {
    const text = await response.text().catch(() => '');
    callbacks.onError(new Error(`API error ${response.status}: ${text}`));
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    callbacks.onError(new Error('ReadableStream not supported'));
    return;
  }

  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith('data:')) continue;

        const data = trimmed.slice(5).trim();
        if (data === '[DONE]') {
          callbacks.onDone();
          return;
        }

        try {
          const parsed = JSON.parse(data);
          const delta = parsed.choices?.[0]?.delta;

          // content
          if (delta?.content) callbacks.onToken(delta.content);

          // reasoning / thinking (deepseek-r1, claude thinking, o1, etc.)
          if (delta?.reasoning_content && callbacks.onReasoning) {
            callbacks.onReasoning(delta.reasoning_content);
          }
          // some gateways normalize to thinking_content
          if (delta?.thinking_content && callbacks.onReasoning) {
            callbacks.onReasoning(delta.thinking_content);
          }

          const finishReason = parsed.choices?.[0]?.finish_reason;
          if (finishReason) {
            const u = parsed.usage;
            callbacks.onDone(u ? { prompt: u.prompt_tokens, completion: u.completion_tokens, total: u.total_tokens } : undefined);
            return;
          }
        } catch { /* skip malformed chunks */ }
      }
    }
    callbacks.onDone();
  } catch (err) {
    if ((err as Error).name === 'AbortError') return;
    callbacks.onError(err instanceof Error ? err : new Error('Stream error'));
  } finally {
    reader.releaseLock();
  }
}

// ── Markdown ────────────────────────────────────────

export function parseMarkdown(text: string): string {
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // code blocks
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_m, lang, code) => {
    const langTag = lang ? `<span class="ai-code-lang">${lang}</span>` : '';
    const escapedCode = code.trim();
    return `<pre class="ai-code-block">${langTag}<button class="ai-copy-btn" data-code="${escapedCode.replace(/"/g, '&quot;')}" title="复制代码">📋</button><code>${escapedCode}</code></pre>`;
  });

  // inline code
  html = html.replace(/`([^`]+)`/g, '<code class="ai-inline-code">$1</code>');

  // bold
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

  // italic
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

  // unordered list
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');

  // links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

  // paragraphs
  html = html.replace(/\n\n/g, '</p><p>');
  html = html.replace(/\n/g, '<br/>');

  return `<p>${html}</p>`;
}

// ── Time formatting ─────────────────────────────────

export function formatTime(ts: number): string {
  const d = new Date(ts);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);

  if (diffMin < 1) return '刚刚';
  if (diffMin < 60) return `${diffMin}分钟前`;
  if (diffMin < 1440) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  }
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }) +
    ' ' + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}
