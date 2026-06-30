import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { MouseEvent, PointerEvent } from 'react';
import type { RosbridgeConnection } from '../utils/RosbridgeConnection';
import './Go2ControlPanel.css';

interface Go2ControlPanelProps {
  connection: RosbridgeConnection;
  onClose: () => void;
}

const SPORT_REQUEST_TOPIC = '/api/sport/request';
const SPORT_REQUEST_TYPE = 'unitree_api/msg/Request';
const SPORT_STATE_TOPICS = ['/sportmodestate', 'lf/sportmodestate'];
const LOW_STATE_TOPICS = ['/lowstate', 'lf/lowstate', 'hf/lowstate'];
const WIRELESS_TOPICS = ['/wirelesscontroller'];

const SPORT_API_IDS = {
  stopMove: 1003,
  standUp: 1004,
  standDown: 1005,
  recoveryStand: 1006,
  move: 1008,
} as const;

type MoveVector = { x: number; y: number; z: number };
type MovePreset = 'slow' | 'normal' | 'fast';

type SpeedSettings = {
  forward: number;
  lateral: number;
  yaw: number;
  repeatMs: number;
};

type CustomRequest = {
  apiId: string;
  parameter: string;
};

function normalizeTopicName(topic: string): string {
  return topic.replace(/^\/+/, '');
}

function matchesTopicName(topicName: string, candidateName: string): boolean {
  const normalizedTopic = normalizeTopicName(topicName);
  const normalizedCandidate = normalizeTopicName(candidateName);

  return normalizedTopic === normalizedCandidate || normalizedTopic.endsWith(`/${normalizedCandidate}`) || normalizedTopic.endsWith(normalizedCandidate);
}

function findTopicMatch(candidates: readonly string[], providerTopics: string[]): string | null {
  for (const candidate of candidates) {
    const matched = providerTopics.find((topicName) => matchesTopicName(topicName, candidate));
    if (matched) {
      return matched;
    }
  }
  return null;
}

function formatNumber(value: number): string {
  return Number.isFinite(value) ? value.toFixed(2) : '0.00';
}

function safeJsonParse(text: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(text);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    // ignore
  }
  return null;
}

function parseNumberInput(value: string, fallback: number): number {
  const next = Number(value);
  return Number.isFinite(next) ? next : fallback;
}

function makeMoveParameter(vector: MoveVector): Record<string, unknown> {
  return { x: vector.x, y: vector.y, z: vector.z };
}

function makePostureTemplate(settings: { roll: number; pitch: number; yaw: number; bodyHeight: number }): Record<string, unknown> {
  return {
    euler: { roll: settings.roll, pitch: settings.pitch, yaw: settings.yaw },
    bodyHeight: settings.bodyHeight,
  };
}

export function Go2ControlPanel({ connection, onClose }: Go2ControlPanelProps) {
  const moveTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [providerTopics, setProviderTopics] = useState<string[]>(() => connection.getProviderTopics().map((topic) => topic.name));
  const [moveSettings, setMoveSettings] = useState<SpeedSettings>({
    forward: 0.35,
    lateral: 0.2,
    yaw: 0.45,
    repeatMs: 120,
  });
  const [postureSettings, setPostureSettings] = useState({
    roll: 0,
    pitch: 0,
    yaw: 0,
    bodyHeight: 0,
  });
  const [customRequest, setCustomRequest] = useState<CustomRequest>({
    apiId: String(SPORT_API_IDS.move),
    parameter: JSON.stringify(makeMoveParameter({ x: 0.35, y: 0, z: 0 }), null, 2),
  });
  const [lastPublished, setLastPublished] = useState<string>('暂无');

  useEffect(() => {
    const unsubscribe = connection.onTopicsChange((topics) => {
      setProviderTopics(topics.map((topic) => topic.name));
    });

    setProviderTopics(connection.getProviderTopics().map((topic) => topic.name));
    return unsubscribe;
  }, [connection]);

  useEffect(() => {
    return () => {
      if (moveTimerRef.current) {
        clearInterval(moveTimerRef.current);
        moveTimerRef.current = null;
      }
    };
  }, []);

  const publishRequest = useCallback((apiId: number, parameter: Record<string, unknown> = {}): void => {
    if (!connection.isConnected()) {
      return;
    }

    connection.publish(SPORT_REQUEST_TOPIC, SPORT_REQUEST_TYPE, {
      header: {
        identity: { api_id: apiId },
        lease: {},
      },
      parameter: JSON.stringify(parameter),
    });

    setLastPublished(`api_id=${apiId}`);
  }, [connection]);

  const stopMove = useCallback((): void => {
    if (moveTimerRef.current) {
      clearInterval(moveTimerRef.current);
      moveTimerRef.current = null;
    }
    publishRequest(SPORT_API_IDS.stopMove);
  }, [publishRequest]);

  const startMove = useCallback((vector: MoveVector): void => {
    if (!connection.isConnected()) {
      return;
    }

    stopMove();
    publishRequest(SPORT_API_IDS.move, vector);

    moveTimerRef.current = setInterval(() => {
      publishRequest(SPORT_API_IDS.move, vector);
    }, moveSettings.repeatMs);
  }, [connection, moveSettings.repeatMs, publishRequest, stopMove]);

  const bindMoveButton = useCallback((vector: MoveVector) => ({
    onPointerDown: (event: PointerEvent<HTMLButtonElement>) => {
      event.preventDefault();
      (event.currentTarget as HTMLButtonElement).setPointerCapture(event.pointerId);
      startMove(vector);
    },
    onPointerUp: (event: PointerEvent<HTMLButtonElement>) => {
      event.preventDefault();
      stopMove();
      try {
        (event.currentTarget as HTMLButtonElement).releasePointerCapture(event.pointerId);
      } catch {
        // ignore
      }
    },
    onPointerLeave: () => stopMove(),
    onPointerCancel: () => stopMove(),
    onContextMenu: (event: MouseEvent<HTMLButtonElement>) => {
      event.preventDefault();
    },
  }), [startMove, stopMove]);

  const topicStates = useMemo(() => ({
    request: findTopicMatch([SPORT_REQUEST_TOPIC], providerTopics),
    lowState: findTopicMatch(LOW_STATE_TOPICS, providerTopics),
    sportState: findTopicMatch(SPORT_STATE_TOPICS, providerTopics),
    wireless: findTopicMatch(WIRELESS_TOPICS, providerTopics),
  }), [providerTopics]);

  const applyPreset = (preset: MovePreset): void => {
    const nextSettings: SpeedSettings =
      preset === 'slow'
        ? { forward: 0.18, lateral: 0.12, yaw: 0.28, repeatMs: 160 }
        : preset === 'fast'
          ? { forward: 0.55, lateral: 0.32, yaw: 0.68, repeatMs: 90 }
          : { forward: 0.35, lateral: 0.2, yaw: 0.45, repeatMs: 120 };

    setMoveSettings(nextSettings);
    setCustomRequest({
      apiId: String(SPORT_API_IDS.move),
      parameter: JSON.stringify(makeMoveParameter({ x: nextSettings.forward, y: 0, z: 0 }), null, 2),
    });
  };

  const fillMoveTemplate = (): void => {
    setCustomRequest({
      apiId: String(SPORT_API_IDS.move),
      parameter: JSON.stringify(makeMoveParameter({ x: moveSettings.forward, y: moveSettings.lateral, z: 0 }), null, 2),
    });
  };

  const fillStandTemplate = (): void => {
    setCustomRequest({
      apiId: String(SPORT_API_IDS.standUp),
      parameter: JSON.stringify({}, null, 2),
    });
  };

  const fillPostureTemplate = (): void => {
    setCustomRequest({
      apiId: '',
      parameter: JSON.stringify(makePostureTemplate(postureSettings), null, 2),
    });
  };

  const sendCustomRequest = (): void => {
    const apiId = Number(customRequest.apiId);
    const parameter = safeJsonParse(customRequest.parameter);
    if (!Number.isFinite(apiId) || !parameter) {
      return;
    }

    publishRequest(apiId, parameter);
  };

  return (
    <div className="Go2ControlPanel">
      <div className="Go2ControlHeader">
        <div className="Go2ControlHeaderText">
          <span>Go2 遥控面板</span>
          <span className="Go2ControlHeaderSubtext">高层请求 + 速度参数 + 自定义模板</span>
        </div>
        <button
          className="Go2ControlCloseButton"
          onClick={() => {
            stopMove();
            onClose();
          }}
          type="button"
          aria-label="关闭 Go2 遥控面板"
          title="关闭"
        >
          ×
        </button>
      </div>

      <div className="Go2ControlBody">
        <div className="Go2ControlHint">
          通过 <span className="Go2ControlCode">/api/sport/request</span> 发送高层动作。已直接接入速度移动、站立、趴下、恢复和停止；其余文档动作保留在自定义请求里，方便你继续补映射。
        </div>

        <div className="Go2StatusStrip">
          <span className={`Go2StatusChip ${topicStates.request ? 'ok' : 'warn'}`}>请求通道 {topicStates.request ? '已发现' : '未发现'}</span>
          <span className={`Go2StatusChip ${topicStates.lowState ? 'ok' : 'warn'}`}>/lowstate {topicStates.lowState ? '已发现' : '未发现'}</span>
          <span className={`Go2StatusChip ${topicStates.sportState ? 'ok' : 'warn'}`}>/sportmodestate {topicStates.sportState ? '已发现' : '未发现'}</span>
          <span className={`Go2StatusChip ${topicStates.wireless ? 'ok' : 'warn'}`}>/wirelesscontroller {topicStates.wireless ? '已发现' : '未发现'}</span>
        </div>

        <div className="Go2ControlSection">
          <div className="Go2ControlSectionTitle">常用动作</div>
          <div className="Go2ActionGrid">
            <button className="Go2ActionButton" onClick={() => publishRequest(SPORT_API_IDS.standUp)} disabled={!connection.isConnected()} type="button">站立</button>
            <button className="Go2ActionButton Secondary" onClick={() => publishRequest(SPORT_API_IDS.standDown)} disabled={!connection.isConnected()} type="button">趴下</button>
            <button className="Go2ActionButton Secondary" onClick={() => publishRequest(SPORT_API_IDS.recoveryStand)} disabled={!connection.isConnected()} type="button">恢复站立</button>
            <button className="Go2ActionButton Danger" onClick={stopMove} disabled={!connection.isConnected()} type="button">停止移动</button>
          </div>
          <div className="Go2PresetRow">
            <button className="Go2MiniButton" onClick={() => applyPreset('slow')} disabled={!connection.isConnected()} type="button">慢速</button>
            <button className="Go2MiniButton" onClick={() => applyPreset('normal')} disabled={!connection.isConnected()} type="button">标准</button>
            <button className="Go2MiniButton" onClick={() => applyPreset('fast')} disabled={!connection.isConnected()} type="button">快速</button>
          </div>
        </div>

        <div className="Go2ControlSection">
          <div className="Go2ControlSectionTitle">速度参数</div>
          <div className="Go2SliderGrid">
            <label className="Go2SliderRow">
              <span>前进速度 m/s</span>
              <div className="Go2SliderValueRow">
                <input className="Go2RangeInput" min="0.05" max="0.8" step="0.01" type="range" value={moveSettings.forward} onChange={(event) => setMoveSettings((current) => ({ ...current, forward: parseNumberInput(event.target.value, current.forward) }))} />
                <input className="Go2NumberInput" min="0.05" max="0.8" step="0.01" type="number" value={moveSettings.forward} onChange={(event) => setMoveSettings((current) => ({ ...current, forward: parseNumberInput(event.target.value, current.forward) }))} />
              </div>
            </label>

            <label className="Go2SliderRow">
              <span>横移速度 m/s</span>
              <div className="Go2SliderValueRow">
                <input className="Go2RangeInput" min="0" max="0.5" step="0.01" type="range" value={moveSettings.lateral} onChange={(event) => setMoveSettings((current) => ({ ...current, lateral: parseNumberInput(event.target.value, current.lateral) }))} />
                <input className="Go2NumberInput" min="0" max="0.5" step="0.01" type="number" value={moveSettings.lateral} onChange={(event) => setMoveSettings((current) => ({ ...current, lateral: parseNumberInput(event.target.value, current.lateral) }))} />
              </div>
            </label>

            <label className="Go2SliderRow">
              <span>转向速度 rad/s</span>
              <div className="Go2SliderValueRow">
                <input className="Go2RangeInput" min="0.05" max="1" step="0.01" type="range" value={moveSettings.yaw} onChange={(event) => setMoveSettings((current) => ({ ...current, yaw: parseNumberInput(event.target.value, current.yaw) }))} />
                <input className="Go2NumberInput" min="0.05" max="1" step="0.01" type="number" value={moveSettings.yaw} onChange={(event) => setMoveSettings((current) => ({ ...current, yaw: parseNumberInput(event.target.value, current.yaw) }))} />
              </div>
            </label>

            <label className="Go2SliderRow">
              <span>重复发送间隔 ms</span>
              <div className="Go2SliderValueRow">
                <input className="Go2RangeInput" min="60" max="250" step="5" type="range" value={moveSettings.repeatMs} onChange={(event) => setMoveSettings((current) => ({ ...current, repeatMs: parseNumberInput(event.target.value, current.repeatMs) }))} />
                <input className="Go2NumberInput" min="60" max="250" step="5" type="number" value={moveSettings.repeatMs} onChange={(event) => setMoveSettings((current) => ({ ...current, repeatMs: parseNumberInput(event.target.value, current.repeatMs) }))} />
              </div>
            </label>
          </div>
          <div className="Go2ParamHint">
            当前前进 {formatNumber(moveSettings.forward)}，横移 {formatNumber(moveSettings.lateral)}，转向 {formatNumber(moveSettings.yaw)}，重复间隔 {moveSettings.repeatMs}ms。
          </div>
        </div>

        <div className="Go2ControlSection">
          <div className="Go2ControlSectionTitle">方向控制</div>
          <div className="Go2MoveGrid">
            <div />
            <button className="Go2MoveButton" title="前进" disabled={!connection.isConnected()} type="button" {...bindMoveButton({ x: moveSettings.forward, y: 0, z: 0 })}>↑</button>
            <div />
            <button className="Go2MoveButton" title="左移" disabled={!connection.isConnected()} type="button" {...bindMoveButton({ x: 0, y: moveSettings.lateral, z: 0 })}>←</button>
            <button className="Go2MoveButton Center" title="停止" disabled={!connection.isConnected()} type="button" onClick={stopMove}>■</button>
            <button className="Go2MoveButton" title="右移" disabled={!connection.isConnected()} type="button" {...bindMoveButton({ x: 0, y: -moveSettings.lateral, z: 0 })}>→</button>
            <div />
            <button className="Go2MoveButton" title="后退" disabled={!connection.isConnected()} type="button" {...bindMoveButton({ x: -moveSettings.forward, y: 0, z: 0 })}>↓</button>
            <div />
          </div>
          <div className="Go2TurnRow">
            <button className="Go2TurnButton" title="左转" disabled={!connection.isConnected()} type="button" {...bindMoveButton({ x: 0, y: 0, z: moveSettings.yaw })}>↶ 左转</button>
            <button className="Go2TurnButton" title="右转" disabled={!connection.isConnected()} type="button" {...bindMoveButton({ x: 0, y: 0, z: -moveSettings.yaw })}>右转 ↷</button>
          </div>
        </div>

        <div className="Go2ControlSection">
          <div className="Go2ControlSectionTitle">姿态模板</div>
          <div className="Go2SliderGrid">
            <label className="Go2SliderRow">
              <span>roll</span>
              <div className="Go2SliderValueRow">
                <input className="Go2RangeInput" min="-0.75" max="0.75" step="0.01" type="range" value={postureSettings.roll} onChange={(event) => setPostureSettings((current) => ({ ...current, roll: parseNumberInput(event.target.value, current.roll) }))} />
                <input className="Go2NumberInput" min="-0.75" max="0.75" step="0.01" type="number" value={postureSettings.roll} onChange={(event) => setPostureSettings((current) => ({ ...current, roll: parseNumberInput(event.target.value, current.roll) }))} />
              </div>
            </label>

            <label className="Go2SliderRow">
              <span>pitch</span>
              <div className="Go2SliderValueRow">
                <input className="Go2RangeInput" min="-0.75" max="0.75" step="0.01" type="range" value={postureSettings.pitch} onChange={(event) => setPostureSettings((current) => ({ ...current, pitch: parseNumberInput(event.target.value, current.pitch) }))} />
                <input className="Go2NumberInput" min="-0.75" max="0.75" step="0.01" type="number" value={postureSettings.pitch} onChange={(event) => setPostureSettings((current) => ({ ...current, pitch: parseNumberInput(event.target.value, current.pitch) }))} />
              </div>
            </label>

            <label className="Go2SliderRow">
              <span>yaw</span>
              <div className="Go2SliderValueRow">
                <input className="Go2RangeInput" min="-0.6" max="0.6" step="0.01" type="range" value={postureSettings.yaw} onChange={(event) => setPostureSettings((current) => ({ ...current, yaw: parseNumberInput(event.target.value, current.yaw) }))} />
                <input className="Go2NumberInput" min="-0.6" max="0.6" step="0.01" type="number" value={postureSettings.yaw} onChange={(event) => setPostureSettings((current) => ({ ...current, yaw: parseNumberInput(event.target.value, current.yaw) }))} />
              </div>
            </label>

            <label className="Go2SliderRow">
              <span>机身高度偏移 m</span>
              <div className="Go2SliderValueRow">
                <input className="Go2RangeInput" min="-0.18" max="0.03" step="0.005" type="range" value={postureSettings.bodyHeight} onChange={(event) => setPostureSettings((current) => ({ ...current, bodyHeight: parseNumberInput(event.target.value, current.bodyHeight) }))} />
                <input className="Go2NumberInput" min="-0.18" max="0.03" step="0.005" type="number" value={postureSettings.bodyHeight} onChange={(event) => setPostureSettings((current) => ({ ...current, bodyHeight: parseNumberInput(event.target.value, current.bodyHeight) }))} />
              </div>
            </label>
          </div>
          <div className="Go2PresetRow">
            <button className="Go2MiniButton" onClick={fillPostureTemplate} disabled={!connection.isConnected()} type="button">填入姿态模板</button>
            <button className="Go2MiniButton" onClick={() => setPostureSettings({ roll: 0, pitch: 0, yaw: 0, bodyHeight: 0 })} disabled={!connection.isConnected()} type="button">归零</button>
            <button className="Go2MiniButton" onClick={fillStandTemplate} disabled={!connection.isConnected()} type="button">填入站立模板</button>
          </div>
          <div className="Go2ParamHint">
            文档里的 <span className="Go2ControlCode">BalanceStand / Euler / BodyHeight</span> 参数可以先在这里准备成模板，再通过自定义请求发送。
          </div>
        </div>

        <div className="Go2ControlSection">
          <div className="Go2ControlSectionTitle">自定义请求</div>
          <div className="Go2CustomRequestGrid">
            <label className="Go2CustomField">
              <span>api_id</span>
              <input className="Go2NumberInput" type="number" value={customRequest.apiId} onChange={(event) => setCustomRequest((current) => ({ ...current, apiId: event.target.value }))} />
            </label>
            <label className="Go2CustomField Go2CustomFieldWide">
              <span>parameter JSON</span>
              <textarea className="Go2Textarea" rows={7} value={customRequest.parameter} onChange={(event) => setCustomRequest((current) => ({ ...current, parameter: event.target.value }))} />
            </label>
          </div>
          <div className="Go2PresetRow">
            <button className="Go2MiniButton" onClick={fillMoveTemplate} disabled={!connection.isConnected()} type="button">填入 Move 模板</button>
            <button className="Go2MiniButton" onClick={fillStandTemplate} disabled={!connection.isConnected()} type="button">填入站立模板</button>
            <button className="Go2MiniButton" onClick={() => setCustomRequest({ apiId: '', parameter: '{}' })} disabled={!connection.isConnected()} type="button">清空</button>
            <button className="Go2MiniButton Primary" onClick={sendCustomRequest} disabled={!connection.isConnected()} type="button">发送请求</button>
          </div>
          <div className="Go2ParamHint">
            当前已发送：{lastPublished}。如果后续确认了更多动作的 api_id，就能直接补成固定按钮。
          </div>
        </div>

        <div className="Go2ControlSection">
          <div className="Go2ControlSectionTitle">文档能力对照</div>
          <div className="Go2CapabilityList">
            <div className="Go2CapabilityRow ok"><span>已直接接入</span><span>velocity_move、stand_up、stand_down、recovery_stand、stop_move</span></div>
            <div className="Go2CapabilityRow warn"><span>可模板化</span><span>balance_stand、normal_stand、sit、rise_sit、stretch、wallow、content、pose、scrape、front_flip、front_jump、front_pounce</span></div>
            <div className="Go2CapabilityRow warn"><span>建议方式</span><span>先通过自定义请求发送，等机器人端确认稳定的 api_id 后再做成固定按钮。</span></div>
          </div>
        </div>
      </div>
    </div>
  );
}
