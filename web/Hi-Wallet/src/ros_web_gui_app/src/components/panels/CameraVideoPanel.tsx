import { useEffect, useState, useRef, useCallback } from 'react';
import type { RosbridgeConnection } from '../../utils/RosbridgeConnection';
import { DeviceStatusCard } from './DeviceStatusCard';

interface Props { connection: RosbridgeConnection | null; videoSrc?: string }

const CAMERA_TOPICS = [
  '/camera/image_raw', '/camera/camera_info',
  '/camera/color/image_raw', '/camera/color/camera_info',
  '/camera/depth/image_rect_raw', '/camera/depth/camera_info',
  '/frontvideostream', '/videohub/inner',
];

export function CameraVideoPanel({ connection, videoSrc }: Props) {
  const [activeTopics, setActiveTopics] = useState<string[]>([]);
  const [fps, setFps] = useState('-');
  const [lightbox, setLightbox] = useState(false);
  const [imgError, setImgError] = useState(false);
  const [retryKey, setRetryKey] = useState(0);
  const lightboxRef = useRef<HTMLDivElement>(null);

  const topicCount = activeTopics.length;
  const status: 'online' | 'idle' | 'offline' =
    topicCount >= 3 ? 'online' : topicCount > 0 ? 'idle' : 'offline';

  useEffect(() => {
    if (!connection?.isConnected()) { setActiveTopics([]); setFps('-'); return; }

    let subbed: string[] = [];
    let fpsTimer: ReturnType<typeof setInterval> | null = null;

    const refresh = () => {
      subbed.forEach(t => { try { connection.unsubscribe(t); } catch {} });
      subbed = [];
      if (fpsTimer) clearInterval(fpsTimer);

      const allTopics = connection.getProviderTopics();
      const active = CAMERA_TOPICS.filter(t => allTopics.some(pt => pt.name === t));
      setActiveTopics(active);

      const imgTopic = allTopics.find(t =>
        t.name === '/camera/image_raw' || t.name === '/camera/color/image_raw');
      if (imgTopic) {
        let lastTs = 0;
        let count = 0;
        connection.subscribe(imgTopic.name, imgTopic.type, () => {
          const now = Date.now();
          if (now - lastTs > 2000) { setFps(`${count} fps`); count = 0; lastTs = now; }
          count++;
        });
        subbed.push(imgTopic.name);
      }
    };
    refresh();
    return connection.onTopicsChange(() => refresh());
  }, [connection]);

  // --- Lightbox: close on Escape ---
  useEffect(() => {
    if (!lightbox) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setLightbox(false); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [lightbox]);

  const openLightbox = useCallback(() => {
    if (!videoSrc) return;
    // 每次打开 lightbox 时重置缩略图错误状态，触发重试
    if (imgError) {
      setImgError(false);
      setRetryKey((k) => k + 1);
    }
    setLightbox(true);
  }, [videoSrc, imgError]);

  const retryThumb = useCallback(() => {
    setImgError(false);
    setRetryKey((k) => k + 1);
  }, []);

  const metrics = [
    { label: '帧率', value: fps },
  ];

  return (
    <>
      <DeviceStatusCard title="摄像头 / 视频" icon="📷" status={status} metrics={metrics}>
        {videoSrc && (
          <div className="cam-thumb" onClick={imgError ? retryThumb : openLightbox} title={imgError ? '点击重试' : '点击放大'}>
            {imgError ? (
              <div className="cam-thumb-error">
                <span className="cam-thumb-error-icon">📷</span>
                <span className="cam-thumb-error-text">视频流加载失败</span>
                <span className="cam-thumb-error-hint">点击重试</span>
              </div>
            ) : (
              <>
                <img
                  key={retryKey}
                  src={videoSrc}
                  alt="Camera stream"
                  onError={() => setImgError(true)}
                  onLoad={() => setImgError(false)}
                />
                <div className="cam-thumb-hint">🔍 点击放大</div>
              </>
            )}
          </div>
        )}
      </DeviceStatusCard>

      {/* ---- Lightbox Modal ---- */}
      {lightbox && videoSrc && (
        <div
          ref={lightboxRef}
          className="cam-lightbox"
          onClick={(e) => { if (e.target === lightboxRef.current) setLightbox(false); }}
        >
          <button className="cam-lightbox-close" onClick={() => setLightbox(false)}>✕</button>
          <img src={videoSrc} alt="Camera full" className="cam-lightbox-img" />
        </div>
      )}
    </>
  );
}
