import { useState, useRef, useCallback, useEffect } from 'react';
import { RosbridgeConnection } from '../utils/RosbridgeConnection';

interface Props {
  connection: RosbridgeConnection;
}

const STEP = 0.05;
const MAX_LIN  = 0.5;
const MAX_ANG  = 1.5;

export function TB4ControlPanel({ connection }: Props) {
  const [linear, setLinear] = useState(0.15);
  const [angular, setAngular] = useState(0.5);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const publishVel = useCallback((lx: number, az: number) => {
    if (!connection.isConnected()) return;
    connection.publish('/cmd_vel', 'geometry_msgs/Twist', {
      linear:  { x: lx, y: 0, z: 0 },
      angular: { x: 0, y: 0, z: az },
    });
  }, [connection]);

  const stop = useCallback(() => {
    publishVel(0, 0);
    if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
    setActiveKey(null);
  }, [publishVel]);

  const startRepeat = useCallback((lx: number, az: number, key: string) => {
    stop();
    publishVel(lx, az);
    setActiveKey(key);
    intervalRef.current = setInterval(() => publishVel(lx, az), 100);
  }, [stop, publishVel]);

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.repeat) return;
      switch (e.key) {
        case 'w': case 'W': startRepeat(linear, 0, 'w'); break;
        case 's': case 'S': startRepeat(-linear, 0, 's'); break;
        case 'a': case 'A': startRepeat(0, angular, 'a'); break;
        case 'd': case 'D': startRepeat(0, -angular, 'd'); break;
      }
    };
    const up = () => stop();
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    return () => { window.removeEventListener('keydown', down); window.removeEventListener('keyup', up); };
  }, [linear, angular, startRepeat, stop]);

  const DpadBtn = (label: string, lx: number, az: number, key: string) => (
    <button
      className={`DpadBtn ${activeKey === key ? 'active' : ''}`}
      onMouseDown={() => startRepeat(lx, az, key)}
      onMouseUp={stop}
      onMouseLeave={stop}
      type="button"
    >
      {label}
    </button>
  );

  const isConnected = connection.isConnected();

  return (
    <div className="ManualControlPanel">
      <div className="ControlPanelHeader">
        <span className="ControlPanelIcon">🎮</span>
        <div className="ControlPanelTitle">
          <span>遥控</span>
          <span className="card-sub">cmd_vel / Twist</span>
        </div>
        <span
          className="status-dot"
          style={{
            background: isConnected ? 'var(--green)' : 'var(--border2)',
            marginLeft: 'auto',
          }}
        />
      </div>

      <div className="DpadGrid">
        <div />
        {DpadBtn('↑', linear, 0, 'w')}
        <div />

        {DpadBtn('←', 0, angular, 'a')}
        {DpadBtn('↓', -linear, 0, 's')}
        {DpadBtn('→', 0, -angular, 'd')}
      </div>

      <div className="ControlSliderRow" style={{ marginTop: 14 }}>
        <label>线速度</label>
        <input type="range" min={0.01} max={MAX_LIN} step={STEP} value={linear}
          onChange={e => setLinear(Number(e.target.value))} />
        <span className="slider-value">{linear.toFixed(2)}</span>
      </div>
      <div className="ControlSliderRow">
        <label>角速度</label>
        <input type="range" min={0.05} max={MAX_ANG} step={STEP} value={angular}
          onChange={e => setAngular(Number(e.target.value))} />
        <span className="slider-value">{angular.toFixed(2)}</span>
      </div>
      <div className="ControlHint">WASD 移动</div>
    </div>
  );
}
