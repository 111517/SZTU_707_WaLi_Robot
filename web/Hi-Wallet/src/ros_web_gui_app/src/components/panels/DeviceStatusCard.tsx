import type { ReactNode } from 'react';

export interface DeviceStatusCardProps {
  title: string;
  icon: ReactNode;
  status: 'online' | 'idle' | 'offline' | 'warning' | 'busy';
  statusLabel?: string;
  metrics?: { label: string; value: string; warn?: boolean }[];
  children?: ReactNode;
}

const STATUS_CONFIG: Record<DeviceStatusCardProps['status'], { dot: string; label: string }> = {
  online:  { dot: 'var(--green)',  label: '活跃' },
  idle:    { dot: 'var(--amber)',  label: '待机' },
  offline: { dot: 'var(--border2)', label: '离线' },
  warning: { dot: 'var(--amber)',  label: '警告' },
  busy:    { dot: 'var(--accent)', label: '忙碌' },
};

export function DeviceStatusCard({ title, icon, status, statusLabel, metrics, children }: DeviceStatusCardProps) {
  const sc = STATUS_CONFIG[status];
  const label = statusLabel ?? sc.label;

  return (
    <div className="device-card">
      <div className="device-card-header">
        <span className="device-card-icon">{icon}</span>
        <div className="device-card-title">
          <span>{title}</span>
          <span className="card-sub" style={{ fontSize: 10 }}>{label}</span>
        </div>
        <span className="status-dot" style={{ background: sc.dot, marginLeft: 'auto' }} />
      </div>
      {metrics && metrics.length > 0 && (
        <div className="device-card-metrics">
          {metrics.map((m, i) => (
            <div key={i} className="device-card-row">
              <span className="device-card-key">{m.label}</span>
              <span className="device-card-val" style={m.warn ? { color: 'var(--amber)' } : undefined}>
                {m.value}
              </span>
            </div>
          ))}
        </div>
      )}
      {children}
    </div>
  );
}
