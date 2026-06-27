import { useCallback, useEffect, useRef, useState } from 'react';
import {
  type ChatMessage,
  type ChatSettings,
  type Conversation,
  OPENCLAW_GO2_BASE_URL,
  OPENCLAW_TB4_BASE_URL,
  loadSettings,
  saveSettings,
  loadConversations,
  saveConversations,
  generateId,
  getOpenClawTokenForBaseUrl,
  streamChat,
} from '../utils/openclawApi';

// ── Hook interface ──────────────────────────────────

export interface UseOpenClawChat {
  conversations: Conversation[];
  activeConversationId: string | null;
  activeMessages: ChatMessage[];
  isStreaming: boolean;
  settings: ChatSettings;
  createConversation: (baseUrl?: string) => void;
  deleteConversation: (id: string) => void;
  switchConversation: (id: string) => void;
  sendMessage: (text: string) => Promise<void>;
  retryLast: () => void;
  regenerate: () => void;
  stopStreaming: () => void;
  updateSettings: (s: ChatSettings) => void;
}

// ── Helpers ─────────────────────────────────────────

const ACTIVE_CONVERSATION_KEY = 'ai_chat_active_conversation_id';

function autoTitle(text: string): string {
  const cleaned = text.replace(/\n/g, ' ').trim();
  return cleaned.length > 30 ? cleaned.slice(0, 30) + '…' : cleaned;
}

function loadActiveConversationId(): string | null {
  try {
    return localStorage.getItem(ACTIVE_CONVERSATION_KEY);
  } catch {
    return null;
  }
}

function saveActiveConversationId(id: string): void {
  try {
    localStorage.setItem(ACTIVE_CONVERSATION_KEY, id);
  } catch { /* ignore */ }
}

function getConversationBaseUrl(conversation?: Conversation): string {
  return conversation?.baseUrl || OPENCLAW_GO2_BASE_URL;
}

function settingsForBaseUrl(settings: ChatSettings, baseUrl: string): ChatSettings {
  if (baseUrl === OPENCLAW_TB4_BASE_URL) {
    return {
      ...settings,
      baseUrl: OPENCLAW_TB4_BASE_URL,
      token: getOpenClawTokenForBaseUrl(OPENCLAW_TB4_BASE_URL),
    };
  }
  if (baseUrl === OPENCLAW_GO2_BASE_URL) {
    return {
      ...settings,
      baseUrl: OPENCLAW_GO2_BASE_URL,
      token: getOpenClawTokenForBaseUrl(OPENCLAW_GO2_BASE_URL),
    };
  }
  return { ...settings, baseUrl };
}

function syncSettingsForConversation(
  conversation: Conversation | undefined,
  currentSettings: ChatSettings,
): ChatSettings {
  return settingsForBaseUrl(currentSettings, getConversationBaseUrl(conversation));
}

function ensureActive(convs: Conversation[], activeId: string | null): { convs: Conversation[]; activeId: string } {
  if (activeId && convs.some(c => c.id === activeId)) {
    return { convs, activeId };
  }
  if (convs.length > 0) {
    return { convs, activeId: convs[0].id };
  }
  const c: Conversation = {
    id: generateId(),
    title: '新对话',
    messages: [],
    createdAt: Date.now(),
    updatedAt: Date.now(),
  };
  return { convs: [c], activeId: c.id };
}

// ── Hook ────────────────────────────────────────────

export function useOpenClawChat(): UseOpenClawChat {
  const initialStateRef = useRef<{
    conversations: Conversation[];
    activeConversationId: string;
    settings: ChatSettings;
  } | null>(null);

  if (!initialStateRef.current) {
    const loadedSettings = loadSettings();
    const initial = ensureActive(loadConversations(), loadActiveConversationId());
    const activeConversation = initial.convs.find(c => c.id === initial.activeId);
    initialStateRef.current = {
      conversations: initial.convs,
      activeConversationId: initial.activeId,
      settings: settingsForBaseUrl(loadedSettings, getConversationBaseUrl(activeConversation)),
    };
  }

  const [conversations, setConversations] = useState<Conversation[]>(initialStateRef.current.conversations);
  const [activeConversationId, setActiveConversationId] = useState<string>(initialStateRef.current.activeConversationId);
  const [isStreaming, setIsStreaming] = useState(false);
  const [settings, setSettings] = useState<ChatSettings>(initialStateRef.current.settings);

  const abortRef = useRef<AbortController | null>(null);
  const assistantIdRef = useRef<string | null>(null);
  const convsRef = useRef(initialStateRef.current.conversations);
  const activeIdRef = useRef(initialStateRef.current.activeConversationId);
  const settingsRef = useRef(initialStateRef.current.settings);

  // keep refs in sync
  useEffect(() => { convsRef.current = conversations; }, [conversations]);
  useEffect(() => { activeIdRef.current = activeConversationId; }, [activeConversationId]);
  useEffect(() => { settingsRef.current = settings; }, [settings]);

  // derive active messages
  const activeConversation = conversations.find(c => c.id === activeConversationId) || conversations[0];
  const activeMessages = activeConversation?.messages ?? [];

  // persist
  useEffect(() => { saveConversations(conversations); }, [conversations]);
  useEffect(() => { saveSettings(settings); }, [settings]);
  useEffect(() => { saveActiveConversationId(activeConversationId); }, [activeConversationId]);

  // helper: batch update one conversation
  const updateConv = useCallback((convId: string, fn: (c: Conversation) => Conversation) => {
    setConversations(prev => {
      const next = prev.map(c => c.id === convId ? fn(c) : c);
      convsRef.current = next;
      return next;
    });
  }, []);

  // ── Conversation CRUD ───────────────────────────

  const createConversation = useCallback((baseUrl?: string) => {
    const nextBaseUrl = baseUrl || settingsRef.current.baseUrl;
    const c: Conversation = {
      id: generateId(),
      title: '新对话',
      messages: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
      baseUrl: nextBaseUrl,
    };
    setConversations(prev => {
      const next = [c, ...prev];
      convsRef.current = next;
      return next;
    });
    setActiveConversationId(c.id);
    activeIdRef.current = c.id;
    const nextSettings = settingsForBaseUrl(settingsRef.current, nextBaseUrl);
    settingsRef.current = nextSettings;
    setSettings(nextSettings);
  }, []);

  const deleteConversation = useCallback((id: string) => {
    setConversations(prev => {
      const next = prev.filter(c => c.id !== id);
      if (next.length === 0) {
        const c: Conversation = {
          id: generateId(),
          title: '新对话',
          messages: [],
          createdAt: Date.now(),
          updatedAt: Date.now(),
          baseUrl: settingsRef.current.baseUrl,
        };
        setActiveConversationId(c.id);
        activeIdRef.current = c.id;
        convsRef.current = [c];
        return [c];
      }
      convsRef.current = next;
      if (id === activeIdRef.current) {
        const currentBaseUrl = settingsRef.current.baseUrl;
        const nextActive = next.find(c => getConversationBaseUrl(c) === currentBaseUrl) || next[0];
        setActiveConversationId(nextActive.id);
        activeIdRef.current = nextActive.id;
        const nextSettings = syncSettingsForConversation(nextActive, settingsRef.current);
        settingsRef.current = nextSettings;
        setSettings(nextSettings);
      }
      return next;
    });
  }, []);

  const switchConversation = useCallback((id: string) => {
    setActiveConversationId(id);
    activeIdRef.current = id;
    const nextSettings = syncSettingsForConversation(
      convsRef.current.find(c => c.id === id),
      settingsRef.current,
    );
    settingsRef.current = nextSettings;
    setSettings(nextSettings);
  }, []);

  // ── Send ────────────────────────────────────────

  const sendMessage = useCallback(async (text: string) => {
    const convId = activeIdRef.current;
    if (!convId) return;

    const userMsg: ChatMessage = {
      id: generateId(),
      role: 'user',
      content: text,
      timestamp: Date.now(),
    };

    const assistantId = generateId();
    assistantIdRef.current = assistantId;

    const assistantMsg: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      reasoning: '',
      timestamp: Date.now(),
    };

    // Get current conversation from ref (always fresh)
    const currentConv = convsRef.current.find(c => c.id === convId);
    const isFirstMessage = (currentConv?.messages.length ?? 0) === 0;

    // Add both messages
    updateConv(convId, c => ({
      ...c,
      baseUrl: c.baseUrl || settings.baseUrl,
      title: isFirstMessage ? autoTitle(text) : c.title,
      messages: [...c.messages, userMsg, assistantMsg],
      updatedAt: Date.now(),
    }));

    setIsStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;

    // Build API messages: all messages before the ones we just added, plus the new user message
    const prevMessages = currentConv?.messages ?? [];
    const apiMessages = [
      ...prevMessages.map(m => ({ role: m.role, content: m.content })),
      { role: 'user', content: text },
    ];

    await streamChat(settings, apiMessages, {
      onToken(content: string) {
        updateConv(convId, c => ({
          ...c,
          messages: c.messages.map(m =>
            m.id === assistantId ? { ...m, content: m.content + content } : m,
          ),
          updatedAt: Date.now(),
        }));
      },
      onReasoning(reasoning: string) {
        updateConv(convId, c => ({
          ...c,
          messages: c.messages.map(m =>
            m.id === assistantId ? { ...m, reasoning: (m.reasoning || '') + reasoning } : m,
          ),
          updatedAt: Date.now(),
        }));
      },
      onDone(usage) {
        updateConv(convId, c => ({
          ...c,
          messages: c.messages.map(m =>
            m.id === assistantId ? { ...m, tokenUsage: usage } : m,
          ),
          updatedAt: Date.now(),
        }));
        setIsStreaming(false);
        abortRef.current = null;
      },
      onError(err: Error) {
        updateConv(convId, c => ({
          ...c,
          messages: c.messages.map(m =>
            m.id === assistantId
              ? { ...m, content: `❌ ${err.message}`, isError: true }
              : m,
          ),
          updatedAt: Date.now(),
        }));
        setIsStreaming(false);
        abortRef.current = null;
      },
    }, controller.signal, convId);
  }, [settings, updateConv]);

  // ── Retry last ───────────────────────────────────

  const retryLast = useCallback(() => {
    if (isStreaming) return;
    const conv = convsRef.current.find(c => c.id === activeIdRef.current);
    if (!conv) return;

    // find last user message
    const lastUser = [...conv.messages].reverse().find(m => m.role === 'user');
    if (!lastUser) return;

    // remove messages after the last user message
    const userIdx = conv.messages.findIndex(m => m.id === lastUser.id);
    const cleaned = conv.messages.slice(0, userIdx + 1);

    updateConv(conv.id, c => ({ ...c, messages: cleaned, updatedAt: Date.now() }));
    sendMessage(lastUser.content);
  }, [isStreaming, sendMessage, updateConv]);

  // ── Regenerate ───────────────────────────────────

  const regenerate = useCallback(() => {
    if (isStreaming) return;
    const conv = convsRef.current.find(c => c.id === activeIdRef.current);
    if (!conv) return;

    // find last user message
    const lastUser = [...conv.messages].reverse().find(m => m.role === 'user');
    if (!lastUser) return;

    // remove last assistant message
    const lastAiIdx = [...conv.messages].reverse().findIndex(m => m.role === 'assistant');
    if (lastAiIdx < 0) return;
    const cleaned = conv.messages.slice(0, conv.messages.length - lastAiIdx - 1);

    updateConv(conv.id, c => ({ ...c, messages: cleaned, updatedAt: Date.now() }));
    sendMessage(lastUser.content);
  }, [isStreaming, sendMessage, updateConv]);

  // ── Stop ─────────────────────────────────────────

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setIsStreaming(false);
  }, []);

  const updateSettings = useCallback((s: ChatSettings) => {
    settingsRef.current = s;
    setSettings(s);
  }, []);

  return {
    conversations,
    activeConversationId,
    activeMessages,
    isStreaming,
    settings,
    createConversation,
    deleteConversation,
    switchConversation,
    sendMessage,
    retryLast,
    regenerate,
    stopStreaming,
    updateSettings,
  };
}
