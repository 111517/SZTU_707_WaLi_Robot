interface StatCardProps {
  label: string;
  value: string | number;
  delta?: string;
  deltaNeg?: boolean;
  valueColor?: string;
  suffix?: string;
}

export function StatCard({ label, value, delta, deltaNeg, valueColor, suffix }: StatCardProps) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={valueColor ? { color: valueColor } : undefined}>
        {value}
        {suffix && (
          <span style={{ fontSize: 14, fontWeight: 400, color: 'var(--text3)' }}>
            {suffix}
          </span>
        )}
      </div>
      {delta && <div className={`stat-delta ${deltaNeg ? 'neg' : ''}`}>{delta}</div>}
    </div>
  );
}
