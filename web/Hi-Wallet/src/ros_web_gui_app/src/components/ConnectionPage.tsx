import { useState, useEffect } from 'react';
import './ConnectionPage.css';
import { loadConnectionPreferences, saveConnectionPreferences } from '../utils/connectionPreferences';
import type { RobotType } from '../types/FleetTypes';

interface ConnectionPageProps {
  onConnect: (url: string, type: RobotType) => Promise<boolean>;
  onCancel?: () => void;
}

export function ConnectionPage({ onConnect, onCancel }: ConnectionPageProps) {
  const [ip, setIp] = useState(() => {
    const preferences = loadConnectionPreferences();
    if (preferences?.ip) return preferences.ip;
    const hostname = window.location.hostname;
    return hostname || 'localhost';
  });
  const [port, setPort] = useState(() => {
    const preferences = loadConnectionPreferences();
    return preferences?.port || '9090';
  });
  const [robotType, setRobotType] = useState<RobotType>(() => {
    const prefs = loadConnectionPreferences();
    return (prefs?.robotType as RobotType) || 'go2';
  });
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    saveConnectionPreferences({ ip, port, robotType });
  }, [ip, port, robotType]);

  const handleConnect = async () => {
    if (!ip || !port) {
      setError('请输入IP和端口');
      return;
    }

    setConnecting(true);
    setError(null);

    try {
      const url = `ws://${ip}:${port}`;
      const success = await onConnect(url, robotType);
      if (!success) {
        setError('连接失败，请检查IP和端口是否正确');
      } else {
        saveConnectionPreferences({ ip, port, robotType });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '连接失败');
    } finally {
      setConnecting(false);
    }
  };

  return (
    <div className="connection-page">
      <div className="connection-card">
        <div className="connection-logo">
          <div className="connection-logo-icon">
            <svg viewBox="0 0 24 24" style={{ width: 20, height: 20, fill: 'none', stroke: 'white', strokeWidth: 1.8 }}>
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" />
            </svg>
          </div>
          <div>
            <div className="connection-logo-name">RobotCore</div>
            <div className="connection-logo-sub">连接机器人</div>
          </div>
        </div>

        <div className="connection-form-group">
          <label htmlFor="ip" className="connection-label">IP 地址</label>
          <input
            id="ip"
            className="connection-input"
            type="text"
            value={ip}
            onChange={(e) => setIp(e.target.value)}
            placeholder="localhost"
            disabled={connecting}
          />
        </div>

        <div className="connection-form-group">
          <label htmlFor="port" className="connection-label">端口</label>
          <input
            id="port"
            className="connection-input"
            type="text"
            value={port}
            onChange={(e) => setPort(e.target.value)}
            placeholder="9090"
            disabled={connecting}
          />
        </div>

        <div className="connection-form-group">
          <label htmlFor="robotType" className="connection-label">机器人类型</label>
          <select
            id="robotType"
            className="connection-input"
            value={robotType}
            onChange={(e) => setRobotType(e.target.value as RobotType)}
            disabled={connecting}
          >
            <option value="go2">Go2 四足机器人</option>
            <option value="tb4">TurtleBot4 差速机器人</option>
            <option value="uav">UAV 无人机</option>
            <option value="custom">自定义</option>
          </select>
        </div>

        {error && <div className="connection-error">{error}</div>}

        <div className="connection-actions">
          <button
            className="connection-btn primary"
            onClick={handleConnect}
            disabled={connecting}
          >
            {connecting ? '连接中...' : '连接'}
          </button>
          {onCancel && (
            <button
              className="connection-btn secondary"
              onClick={onCancel}
              disabled={connecting}
            >
              取消
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
