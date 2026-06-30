import { useEffect, useState } from 'react';
import './LogFeed.css';

interface LogEntry {
  msg: string;
  robot: string;
  robotColor: string;
  dotColor: string;
  time?: string;
  tagBg?: string;
  tagColor?: string;
}

interface LogFeedProps {
  title?: string;
  feed: LogEntry[];
  maxItems?: number;
}

function getTimeStr() {
  const d = new Date();
  return d.getHours().toString().padStart(2, '0') + ':' +
    d.getMinutes().toString().padStart(2, '0');
}

export function LogFeed({ title = '实时日志', feed, maxItems = 7 }: LogFeedProps) {
  const [displayFeed, setDisplayFeed] = useState<LogEntry[]>([]);

  useEffect(() => {
    setDisplayFeed(feed.slice(0, maxItems));
  }, [feed, maxItems]);

  if (displayFeed.length === 0) {
    return (
      <div className="card">
        <div className="sec-hdr">
          <span className="sec-title">{title}</span>
        </div>
        <div className="log-empty">暂无日志</div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="sec-hdr">
        <span className="sec-title">{title}</span>
        <span className="sec-link">{displayFeed.length} 条</span>
      </div>
      <div className="log-scroll">
        <div className="log-feed">
          {displayFeed.map((entry, i) => (
            <div key={i} className="log-item">
              <span className="log-time">{entry.time || getTimeStr()}</span>
              <div className="log-dot" style={{ background: entry.dotColor }} />
              <span className="log-msg">{entry.msg}</span>
              <span
                className="log-tag"
                style={{
                  background: entry.tagBg || 'var(--surface2)',
                  color: entry.tagColor || entry.robotColor,
                }}
              >
                {entry.robot}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
