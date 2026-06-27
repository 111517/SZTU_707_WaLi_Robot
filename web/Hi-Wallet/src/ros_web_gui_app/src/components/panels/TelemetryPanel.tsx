interface TelemetryItem {
  label: string;
  value: string;
  unit?: string;
  warn?: boolean;
}

interface TelemetryPanelProps {
  title?: string;
  items: TelemetryItem[];
  columns?: number;
}

export function TelemetryPanel({ title = '实时状态', items, columns = 2 }: TelemetryPanelProps) {
  return (
    <div className="card">
      <div className="card-title" style={{ marginBottom: 14 }}>{title}</div>
      <div style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${columns}, 1fr)`,
        gap: 10,
      }}>
        {items.map((item, i) => (
          <div key={i} className="mini-stat">
            <div className="mini-stat-label">{item.label}</div>
            <div className="mini-stat-val" style={item.warn ? { color: 'var(--amber)' } : undefined}>
              {item.value}
            </div>
            {item.unit && <div className="mini-stat-unit">{item.unit}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
