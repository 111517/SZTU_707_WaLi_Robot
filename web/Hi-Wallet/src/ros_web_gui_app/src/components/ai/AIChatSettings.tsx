import { useEffect, useState } from 'react';
import {
  type ChatSettings,
  type ModelInfo,
  OPENCLAW_GO2_BASE_URL,
  OPENCLAW_TB4_BASE_URL,
  fetchModels,
  getOpenClawTokenForBaseUrl,
} from '../../utils/openclawApi';
import './AIChatSettings.css';

interface Props {
  settings: ChatSettings;
  onSave: (s: ChatSettings) => void;
  onClose: () => void;
  contextTokens?: number; // estimated context usage for current conversation
}

const PRESETS = [
  { label: 'Go2', baseUrl: OPENCLAW_GO2_BASE_URL },
  { label: 'Tb4', baseUrl: OPENCLAW_TB4_BASE_URL },
];

export function AIChatSettings({ settings, onSave, onClose, contextTokens }: Props) {
  const [baseUrl, setBaseUrl] = useState(settings.baseUrl);
  const [token, setToken] = useState(settings.token);
  const [model, setModel] = useState(settings.model);
  const [systemPrompt, setSystemPrompt] = useState(settings.systemPrompt);
  const [temperature, setTemperature] = useState(settings.temperature);
  const [topP, setTopP] = useState(settings.topP);
  const [maxTokens, setMaxTokens] = useState(settings.maxTokens);
  const [showToken, setShowToken] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<'idle' | 'success' | 'fail'>('idle');
  const [activePreset, setActivePreset] = useState(
    PRESETS.findIndex(p => p.baseUrl === settings.baseUrl)
  );
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);

  // fetch models on mount
  useEffect(() => {
    let cancelled = false;
    setModelsLoading(true);
    fetchModels(baseUrl, token)
      .then(list => { if (!cancelled) setModels(list); })
      .catch(() => { if (!cancelled) setModels([]); })
      .finally(() => { if (!cancelled) setModelsLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSave = () => {
    onSave({ baseUrl, token, model, systemPrompt, temperature, topP, maxTokens });
    onClose();
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult('idle');
    // also refresh model list
    setModelsLoading(true);
    try {
      const list = await fetchModels(baseUrl, token, AbortSignal.timeout(8000));
      setModels(list);
      setTestResult('success');
    } catch {
      setTestResult('fail');
    } finally {
      setTesting(false);
      setModelsLoading(false);
    }
  };

  const handlePreset = (idx: number) => {
    setActivePreset(idx);
    const preset = PRESETS[idx];
    const nextToken = getOpenClawTokenForBaseUrl(preset.baseUrl);
    if (preset.baseUrl) setBaseUrl(preset.baseUrl);
    setToken(nextToken);
    // refresh model list for the new preset
    setModelsLoading(true);
    fetchModels(preset.baseUrl, nextToken)
      .then(list => setModels(list))
      .catch(() => {})
      .finally(() => setModelsLoading(false));
  };

  const tempDisplay = temperature.toFixed(1);
  const topPDisplay = topP.toFixed(2);

  return (
    <div className="ai-settings">
      <div className="ai-settings-header">
        <button className="ai-settings-back" onClick={onClose} aria-label="返回">
          ←
        </button>
        <span className="ai-settings-title">模型设置</span>
      </div>

      <div className="ai-settings-body">
        {/* Presets */}
        <label className="ai-settings-label">快捷配置</label>
        <div className="ai-settings-presets">
          {PRESETS.map((p, i) => (
            <label key={p.label} className={`ai-preset ${i === activePreset ? 'ai-preset--active' : ''}`}>
              <input
                type="radio"
                name="ai_preset"
                checked={i === activePreset}
                onChange={() => handlePreset(i)}
              />
              <span>{p.label}</span>
            </label>
          ))}
        </div>

        {/* Gateway URL */}
        <label className="ai-settings-label">Gateway URL</label>
        <input
          className="ai-settings-input"
          type="text"
          value={baseUrl}
          onChange={e => { setBaseUrl(e.target.value); setActivePreset(-1); }}
          placeholder="http://<go2-ip>:18789"
        />

        {/* Token */}
        <label className="ai-settings-label">Token</label>
        <div className="ai-settings-token-row">
          <input
            className="ai-settings-input"
            type={showToken ? 'text' : 'password'}
            value={token}
            onChange={e => setToken(e.target.value)}
            placeholder="输入 token"
          />
          <button
            className="ai-settings-eye"
            onClick={() => setShowToken(!showToken)}
            aria-label={showToken ? '隐藏 token' : '显示 token'}
          >
            {showToken ? '🙈' : '👁'}
          </button>
        </div>

        {/* Model */}
        <label className="ai-settings-label">
          模型
          {modelsLoading && <span className="ai-settings-subtle"> 加载中...</span>}
          <button
            className="ai-settings-refresh"
            onClick={handleTest}
            disabled={testing}
            title="刷新模型列表 &amp; 测试连接"
          >
            ↻
          </button>
        </label>
        {models.length > 0 ? (
          <select
            className="ai-settings-select"
            value={model}
            onChange={e => setModel(e.target.value)}
          >
            {models.map(m => (
              <option key={m.id} value={m.id}>
                {m.id}{m.owned_by ? ` (${m.owned_by})` : ''}
              </option>
            ))}
            <option value={model} disabled>
              ── 自定义 ──
            </option>
          </select>
        ) : null}
        <input
          className="ai-settings-input"
          type="text"
          value={model}
          onChange={e => setModel(e.target.value)}
          placeholder="openclaw/main"
        />

        {/* Temperature */}
        <label className="ai-settings-label">
          Temperature <span className="ai-settings-value">{tempDisplay}</span>
        </label>
        <input
          className="ai-settings-range"
          type="range"
          min="0"
          max="2"
          step="0.1"
          value={temperature}
          onChange={e => setTemperature(parseFloat(e.target.value))}
        />
        <div className="ai-settings-range-labels">
          <span>精确 0</span>
          <span>平衡 1</span>
          <span>创造 2</span>
        </div>

        {/* Top P */}
        <label className="ai-settings-label">
          Top P <span className="ai-settings-value">{topPDisplay}</span>
        </label>
        <input
          className="ai-settings-range"
          type="range"
          min="0"
          max="1"
          step="0.05"
          value={topP}
          onChange={e => setTopP(parseFloat(e.target.value))}
        />

        {/* Max Tokens */}
        <label className="ai-settings-label">Max Tokens</label>
        <input
          className="ai-settings-input"
          type="number"
          min={256}
          max={32768}
          step={256}
          value={maxTokens}
          onChange={e => setMaxTokens(parseInt(e.target.value, 10) || 4096)}
        />

        {/* System Prompt */}
        <label className="ai-settings-label">System Prompt</label>
        <textarea
          className="ai-settings-textarea"
          value={systemPrompt}
          onChange={e => setSystemPrompt(e.target.value)}
          placeholder="可选：设置 AI 的系统提示词"
          rows={3}
        />

        {/* Context usage */}
        {contextTokens !== undefined && contextTokens > 0 && (
          <div className="ai-settings-context">
            <span className="ai-settings-label">上下文用量</span>
            <div className="ai-context-bar">
              <div
                className="ai-context-fill"
                style={{ width: `${Math.min((contextTokens / 32000) * 100, 100)}%` }}
              />
            </div>
            <span className="ai-context-text">
              ~{contextTokens.toLocaleString()} tokens
            </span>
          </div>
        )}
      </div>

      <div className="ai-settings-footer">
        <button
          className="action-btn ai-settings-test"
          onClick={handleTest}
          disabled={testing}
        >
          {testing ? '测试中...' : testResult === 'success' ? '✅ 连接成功' : testResult === 'fail' ? '❌ 连接失败' : '测试连接'}
        </button>
        <button className="action-btn primary" onClick={handleSave}>
          保存
        </button>
      </div>
    </div>
  );
}
