import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import type { TF2JS } from '../../utils/tf2js';
import { MapManager } from '../../utils/MapManager';
import { LayerManager } from '../layers/LayerManager';
import { StaticMapLayer } from '../layers/StaticMapLayer';
import { WorldFrameStore } from '../../utils/WorldFrameStore';
import { Go2ControlPanel } from '../Go2ControlPanel';
import { ImageDisplay } from '../ImageDisplay';
import { useImageLayers } from '../../hooks/useImageLayers';
import { saveImagePositions, type ImagePositionsMap } from '../../utils/layerConfigStorage';
import type { LayerConfigMap } from '../../types/LayerConfig';
import type { TopicInfo } from '../../types/TopicInfo';
import type { RobotFleetEntry } from '../../types/FleetTypes';
import './ViewportPanel.css';

type FixedFrame = 'odom' | 'map';

interface ViewportPanelProps {
  robots: RobotFleetEntry[];
  compact?: boolean;
}

const DEFAULT_FIXED_FRAME: FixedFrame = 'map';
/** Per-robot coordinate offset (no longer needed — calibration TF handles positioning). */
const ROBOT_OFFSETS: Record<string, { x: number; y: number; z: number }> = {};

// ── topic resolution helpers ────────────────────────────────────────

const normalizeTopicName = (topic: string): string => topic.replace(/^\/+/, '');

const matchesTopicName = (topicName: string, candidateName: string): boolean => {
  const normalizedTopic = normalizeTopicName(topicName);
  const normalizedCandidate = normalizeTopicName(candidateName);
  return normalizedTopic === normalizedCandidate ||
    normalizedTopic.endsWith(`/${normalizedCandidate}`) ||
    normalizedTopic.endsWith(normalizedCandidate);
};

const resolveTopic = (
  providerTopics: TopicInfo[],
  candidates: readonly string[],
  typeMatchers: readonly RegExp[] = []
): TopicInfo | null => {
  for (const candidate of candidates) {
    const byName = providerTopics.find((topic) => matchesTopicName(topic.name, candidate));
    if (byName) return byName;
  }
  for (const matcher of typeMatchers) {
    const byType = providerTopics.find((topic) => matcher.test(topic.type));
    if (byType) return byType;
  }
  return null;
};

function createLayerConfigs(fixedFrame: FixedFrame, providerTopics: TopicInfo[], robotType?: string): LayerConfigMap {
  const mapTopic = resolveTopic(providerTopics, ['/map'], [/OccupancyGrid$/i]);
  const laserTopic = resolveTopic(providerTopics, ['/scan', '/scan_filtered', '/utlidar/scan'], [/LaserScan$/i]);
  const pointCloudTopic = resolveTopic(providerTopics, ['/utlidar/cloud_deskewed', '/pointcloud', '/cloud'], [/PointCloud2$/i]);
  const pathTopic = resolveTopic(providerTopics, ['/plan'], [/Path$/i]);
  const localPathTopic = resolveTopic(providerTopics, ['/local_plan'], [/Path$/i]);
  const footprintTopic = resolveTopic(providerTopics, ['/local_costmap/published_footprint'], [/PolygonStamped$/i]);
  const imageTopic = resolveTopic(providerTopics, [
    '/camera/color/image_raw', '/camera/image_raw', '/image_raw',
    '/camera/front/image_raw', '/oakd/rgb/image_raw', '/oakd/rgb/preview/image_raw',
  ], [/Image$/i, /CompressedImage$/i]);

  // TB4 uses 'base_link' or 'base_footprint' as base frame; Go2 uses 'base'
  const baseFrame = robotType === 'tb4' ? 'base_link' : 'base';

  return {
    static_map: { id: 'static_map', name: 'Static Map', topic: null, messageType: null, enabled: true, mapUrl: '/maps/707.yaml' },
    grid: { id: 'grid', name: 'Grid', topic: '/map', messageType: 'nav_msgs/OccupancyGrid', enabled: true },
    occupancy_grid: { id: 'occupancy_grid', name: 'Map', topic: mapTopic?.name || '/map', messageType: mapTopic?.type || 'nav_msgs/OccupancyGrid', enabled: true, colorMode: 'map', height: 0, mapFrame: fixedFrame },
    laser_scan: { id: 'laser_scan', name: 'LaserScan', topic: laserTopic?.name || '/scan', messageType: laserTopic?.type || 'sensor_msgs/LaserScan', enabled: false, targetFrame: fixedFrame, baseFrame },
    point_cloud: { id: 'point_cloud', name: 'PointCloud2', topic: pointCloudTopic?.name || '/utlidar/cloud_deskewed', messageType: pointCloudTopic?.type || 'sensor_msgs/PointCloud2', enabled: true, pointSize: 0.05, targetFrame: fixedFrame },
    local_plan: { id: 'local_plan', name: 'Local Plan', topic: localPathTopic?.name || '/local_plan', messageType: localPathTopic?.type || 'nav_msgs/Path', enabled: false, color: 0x00ff00, lineWidth: 2 },
    plan: { id: 'plan', name: 'Global Plan', topic: pathTopic?.name || '/plan', messageType: pathTopic?.type || 'nav_msgs/Path', enabled: false, color: 0x4cc3ff, lineWidth: 2 },
    footprint: { id: 'footprint', name: 'Footprint', topic: footprintTopic?.name || '/local_costmap/published_footprint', messageType: footprintTopic?.type || 'geometry_msgs/PolygonStamped', enabled: false },
    front_camera: { id: 'image', name: 'Front Camera', topic: imageTopic?.name || '/camera/image_raw', messageType: imageTopic?.type || 'sensor_msgs/Image', enabled: false },
    robot: { id: 'robot', name: 'RobotModel', topic: null, messageType: null, enabled: true, baseFrame, mapFrame: fixedFrame, followZoomFactor: 0.3, robotType: robotType || 'go2' },
    tf: { id: 'tf', name: 'TF', topic: null, messageType: null, enabled: true, rootFrame: fixedFrame, showFrameNames: true },
  };
}

function formatResolvedTopic(topic: TopicInfo | null, fallback: string): string {
  if (!topic) return fallback;
  return `${topic.name} (${topic.type})`;
}

// ── per-robot entry ─────────────────────────────────────────────────

interface RobotViewEntry {
  robotId: string;
  group: THREE.Group;
  layerManager: LayerManager;
  tf2js: TF2JS;
}

export function ViewportPanel({ robots, compact = false }: ViewportPanelProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const robotEntriesRef = useRef<Map<string, RobotViewEntry>>(new Map());
  const layerConfigsRef = useRef<LayerConfigMap>({});
  const fixedFrameRef = useRef<FixedFrame>(DEFAULT_FIXED_FRAME);
  const focusRobotRef = useRef(true);
  const staticMapLayerRef = useRef<StaticMapLayer | null>(null);
  const imagePositionsRef = useRef<Map<string, { x: number; y: number; scale: number }>>(new Map());

  // Derive online robots with a valid connection
  const onlineRobots = useMemo(
    () => robots.filter((r) => r.status === 'online' && r.connection?.isConnected()),
    [robots]
  );
  // Primary connection for the status bar & single-robot panels
  const primaryConn = onlineRobots[0]?.connection ?? null;
  const primaryRobotId = onlineRobots[0]?.id ?? null;

  const [providerTopics, setProviderTopics] = useState<TopicInfo[]>(() => primaryConn?.getProviderTopics() ?? []);
  const [fixedFrame, setFixedFrame] = useState<FixedFrame>(DEFAULT_FIXED_FRAME);
  const [layerConfigs, setLayerConfigs] = useState<LayerConfigMap>(() =>
    primaryConn ? createLayerConfigs(DEFAULT_FIXED_FRAME, primaryConn.getProviderTopics()) : {}
  );
  const [showGo2ControlPanel, setShowGo2ControlPanel] = useState(false);
  const [showDisplays, setShowDisplays] = useState(true);
  const [focusRobot, setFocusRobot] = useState(true);
  const [showCalibration, setShowCalibration] = useState(false);
  const [calibRobot, setCalibRobot] = useState<string>('');
  const [calibX, setCalibX] = useState('0');
  const [calibY, setCalibY] = useState('0');
  const [calibTheta, setCalibTheta] = useState('0');
  const [calibDeg, setCalibDeg] = useState(true); // true=degrees input
  const imageLayers = useImageLayers(layerConfigs, imagePositionsRef);

  useEffect(() => {
    layerConfigsRef.current = layerConfigs;
    fixedFrameRef.current = fixedFrame;
    focusRobotRef.current = focusRobot;
  }, [layerConfigs, fixedFrame, focusRobot]);

  // Rebuild layer configs when fixed frame or primary provider topics change
  useEffect(() => {
    if (!primaryConn) return;
    const nextConfigs = createLayerConfigs(fixedFrame, providerTopics, onlineRobots[0]?.type);
    setLayerConfigs((current) => {
      const merged: LayerConfigMap = {};
      for (const [layerId, config] of Object.entries(nextConfigs)) {
        merged[layerId] = { ...config, enabled: current[layerId]?.enabled ?? config.enabled };
      }
      return merged;
    });
  }, [fixedFrame, providerTopics, primaryConn]);

  // Track provider topics on the primary connection
  useEffect(() => {
    if (!primaryConn?.isConnected()) {
      setProviderTopics([]);
      return;
    }
    let cancelled = false;
    const unsubscribeTopics = primaryConn.onTopicsChange((topics) => {
      if (!cancelled) setProviderTopics(topics);
    });
    (async () => {
      try { await primaryConn.initializeMessageReaders(); } catch (e) { console.error('[ViewportPanel] init msg readers:', e); }
      if (!cancelled) setProviderTopics(primaryConn.getProviderTopics());
    })();
    return () => { cancelled = true; unsubscribeTopics(); };
  }, [primaryConn]);

  // ── Scene + camera + renderer setup (once) ────────────────────────
  useEffect(() => {
    if (!canvasRef.current || !containerRef.current) return;
    const canvas = canvasRef.current;
    const container = containerRef.current;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x121416);
    sceneRef.current = scene;

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);
    const hemiLight = new THREE.HemisphereLight(0xddeeff, 0x3a3a4a, 0.5);
    scene.add(hemiLight);
    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(5, 5, 10);
    scene.add(directionalLight);
    THREE.Object3D.DEFAULT_UP = new THREE.Vector3(0, 0, 1);

    // World coordinate axes (X=red, Y=green, Z=blue), length 2m
    scene.add(new THREE.AxesHelper(2));

    // Load static map asynchronously
    const staticMapLayer = new StaticMapLayer(scene, {
      id: 'static_map', name: 'Static Map', topic: null, messageType: null, enabled: true,
      mapUrl: '/maps/707.yaml',
    });
    staticMapLayerRef.current = staticMapLayer;
    staticMapLayer.load();

    const w = container.clientWidth;
    const h = container.clientHeight;
    const camera = new THREE.PerspectiveCamera(75, w / Math.max(h, 1), 0.1, 2000);
    camera.position.set(10, -10, 10);
    camera.up.set(0, 0, 1);
    camera.lookAt(0, 0, 0);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
    renderer.setClearColor(0x121416, 1);
    renderer.setSize(w, h);
    renderer.setPixelRatio(window.devicePixelRatio);
    rendererRef.current = renderer;

    const controls = new OrbitControls(camera, canvas);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.screenSpacePanning = true;
    controls.minDistance = 0.1;
    controls.maxDistance = 1000;
    controls.target.set(0, 0, 0);
    controls.enableRotate = true;
    controls.mouseButtons.LEFT = THREE.MOUSE.ROTATE;
    controls.mouseButtons.MIDDLE = THREE.MOUSE.PAN;
    controls.mouseButtons.RIGHT = THREE.MOUSE.DOLLY;
    (controls as any).zoomToCursor = true;
    controls.update();
    controlsRef.current = controls;

    const handleResize = () => {
      if (!camera || !renderer || !container) return;
      const nw = container.clientWidth;
      const nh = container.clientHeight;
      camera.aspect = nw / Math.max(nh, 1);
      camera.updateProjectionMatrix();
      renderer.setSize(nw, nh);
    };
    const ro = new ResizeObserver(handleResize);
    ro.observe(container);

    let animationFrameId = 0;
    const animate = () => {
      animationFrameId = window.requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      ro.disconnect();
      cancelAnimationFrame(animationFrameId);
      controls.dispose();
      renderer.dispose();
      // Clean up all robot entries
      robotEntriesRef.current.forEach((entry) => entry.layerManager.dispose());
      robotEntriesRef.current.clear();
      sceneRef.current = null;
      rendererRef.current = null;
      cameraRef.current = null;
      controlsRef.current = null;
    };
  }, []);

  // ── Push updated layer configs to all robot LayerManagers ─────────
  useEffect(() => {
    if (!layerConfigs || Object.keys(layerConfigs).length === 0) return;
    // Filter out scene-level layers (static_map) from per-robot configs
    const perRobotConfigs: LayerConfigMap = {};
    for (const [key, val] of Object.entries(layerConfigs)) {
      if (key !== 'static_map') perRobotConfigs[key] = val;
    }
    for (const [, entry] of robotEntriesRef.current) {
      entry.layerManager.setLayerConfigs(perRobotConfigs);
    }
  }, [layerConfigs]);

  // Sync static_map enabled toggle to scene-level layer
  useEffect(() => {
    const layer = staticMapLayerRef.current;
    if (!layer || !layerConfigs.static_map) return;
    layer.setConfig(layerConfigs.static_map);
  }, [layerConfigs]);

  // ── Per-robot LayerManager management ─────────────────────────────
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;

    const currentEntries = robotEntriesRef.current;
    const wantedIds = new Set(onlineRobots.map((r) => r.id));

    // Remove entries for robots that went offline
    for (const [id, entry] of currentEntries) {
      if (!wantedIds.has(id)) {
        entry.layerManager.dispose();
        scene.remove(entry.group);
        currentEntries.delete(id);
      }
    }

    // Initialize MapManager with the FIRST robot's connection (once)
    // Must happen BEFORE creating layers so OccGridLayer sees map data.
    const mapManager = MapManager.getInstance();
    if (onlineRobots.length > 0 && primaryConn?.isConnected()) {
      mapManager.initialize(primaryConn);
    }

    // Add entries for new online robots
    for (const robot of onlineRobots) {
      if (currentEntries.has(robot.id)) continue;

      const group = new THREE.Group();
      group.name = `robot-group-${robot.id}`;

      // Apply per-type coordinate offset
      const offset = ROBOT_OFFSETS[robot.type];
      if (offset) {
        group.position.set(offset.x, offset.y, offset.z);
      }

      const layerManager = new LayerManager(group, robot.connection!, robot.id);
      layerManager.initialize();
      scene.add(group);

      // Build robot-specific layer configs from its own provider topics
      const robotTopics = robot.connection!.getProviderTopics();
      const robotConfigs = createLayerConfigs(fixedFrameRef.current, robotTopics, robot.type);
      layerManager.setLayerConfigs(robotConfigs);

      // Inject map→odom calibration transform for this robot
      const worldStore = WorldFrameStore.getInstance();
      const calibOffset = worldStore.getOffset(robot.id);
      if (calibOffset.x !== 0 || calibOffset.y !== 0 || calibOffset.theta !== 0) {
        layerManager.getTf2js().addTransforms([{
          header: { frame_id: 'map', stamp: { sec: 0, nsec: 0 } },
          child_frame_id: 'odom',
          transform: {
            translation: { x: calibOffset.x, y: calibOffset.y, z: 0 },
            rotation: { x: 0, y: 0, z: Math.sin(calibOffset.theta / 2), w: Math.cos(calibOffset.theta / 2) },
          },
        }]);
      }

      currentEntries.set(robot.id, {
        robotId: robot.id,
        group,
        layerManager,
        tf2js: layerManager.getTf2js(),
      });
    }

    return () => {
      mapManager.disconnect();
    };
  }, [onlineRobots, primaryConn]);


  // ── Robot follow (camera tracks primary robot's TF) ───────────────
  useEffect(() => {
    const controls = controlsRef.current;
    const scene = sceneRef.current;
    if (!scene || !controls) return;

    const updateFollow = () => {
      if (!focusRobotRef.current) return;
      // Try to follow the primary robot
      for (const [id, entry] of robotEntriesRef.current) {
        if (id === primaryRobotId) {
          const tf2js = entry.tf2js;
          const mapFrame = fixedFrameRef.current;
          const transform = tf2js.findTransform(mapFrame, 'base')
            || tf2js.findTransform(mapFrame, 'base_link')
            || tf2js.findTransform(mapFrame, 'base_footprint');
          if (transform) {
            controls.target.set(
              transform.translation.x + entry.group.position.x,
              transform.translation.y + entry.group.position.y,
              transform.translation.z + entry.group.position.z
            );
          }
          break;
        }
      }
    };

    // Subscribe to all robots' TF changes
    const unsubs: (() => void)[] = [];
    for (const [, entry] of robotEntriesRef.current) {
      unsubs.push(entry.tf2js.onTransformChange(() => updateFollow()));
    }
    updateFollow();

    return () => unsubs.forEach((fn) => fn());
  }, [primaryRobotId]);

  // ── Display rows ──────────────────────────────────────────────────
  const displayRows = useMemo(() => {
    return [
      { id: 'static_map', label: 'Static Map' },
      { id: 'grid', label: 'Grid' },
      { id: 'occupancy_grid', label: 'Map' },
      { id: 'point_cloud', label: 'PointCloud2' },
      { id: 'laser_scan', label: 'LaserScan' },
      { id: 'plan', label: 'Global Plan' },
      { id: 'local_plan', label: 'Local Plan' },
      { id: 'footprint', label: 'Footprint' },
      { id: 'front_camera', label: 'Front Camera' },
      { id: 'robot', label: 'RobotModel' },
      { id: 'tf', label: 'TF' },
    ].map((row) => {
      const config = layerConfigs[row.id];
      const resolvedTopic = config?.topic
        ? providerTopics.find((topic) => matchesTopicName(topic.name, config.topic || '')) ?? null
        : null;
      const topicLabel = row.id === 'robot'
        ? 'robot_description + TF'
        : row.id === 'static_map'
          ? '本地文件: /maps/707.yaml'
          : config?.topic
            ? formatResolvedTopic(resolvedTopic, config.topic)
            : '无 topic';
      return { ...row, enabled: config?.enabled ?? false, topicLabel };
    });
  }, [layerConfigs, providerTopics]);

  const toggleLayer = useCallback((layerId: string) => {
    setLayerConfigs((current) => {
      const next = { ...current };
      const config = next[layerId];
      if (config) next[layerId] = { ...config, enabled: !config.enabled };
      return next;
    });
  }, []);

  const handleResetView = useCallback(() => {
    const controls = controlsRef.current;
    const camera = cameraRef.current;
    if (!controls || !camera) return;
    controls.target.set(0, 0, 0);
    camera.position.set(10, -10, 10);
    camera.lookAt(0, 0, 0);
    controls.update();
  }, []);

  const applyCalibration = useCallback(() => {
    if (!calibRobot) return;
    const x = parseFloat(calibX) || 0;
    const y = parseFloat(calibY) || 0;
    const thetaRad = calibDeg ? (parseFloat(calibTheta) || 0) * (Math.PI / 180) : (parseFloat(calibTheta) || 0);

    // Save to store
    const store = WorldFrameStore.getInstance();
    store.setOffset(calibRobot, { x, y, theta: thetaRad });

    // Inject map→odom TF into the robot's TF2JS
    const entry = robotEntriesRef.current.get(calibRobot);
    if (entry) {
      entry.tf2js.addTransforms([{
        header: { frame_id: 'map', stamp: { sec: 0, nsec: 0 } },
        child_frame_id: 'odom',
        transform: {
          translation: { x, y, z: 0 },
          rotation: { x: 0, y: 0, z: Math.sin(thetaRad / 2), w: Math.cos(thetaRad / 2) },
        },
      }]);
    }
  }, [calibRobot, calibX, calibY, calibTheta, calibDeg]);

  const openCalibration = useCallback((robotId: string) => {
    const store = WorldFrameStore.getInstance();
    const off = store.getOffset(robotId);
    setCalibRobot(robotId);
    setCalibX(off.x.toFixed(3));
    setCalibY(off.y.toFixed(3));
    setCalibTheta(calibDeg ? (off.theta * 180 / Math.PI).toFixed(1) : off.theta.toFixed(4));
    setShowCalibration(true);
  }, [calibDeg]);

  const imageLayerEntries = useMemo(() => {
    return Array.from(imageLayers.entries()).filter(([layerId]) => layerConfigs[layerId]?.enabled);
  }, [imageLayers, layerConfigs]);

  return (
    <div className={`viewport-panel ${compact ? 'compact' : ''}`}>
      <div className="viewport-toolbar">
        <div className="viewport-title-block">
          <div className="viewport-title">Go2 RViz</div>
          <div className="viewport-subtitle">
            {onlineRobots.length > 0
              ? `${onlineRobots.length} robot${onlineRobots.length > 1 ? 's' : ''}: ${onlineRobots.map(r => r.name).join(', ')}`
              : 'ROS 话题显示与控制'}
          </div>
        </div>
        <div className="viewport-toolbar-actions">
          <button className="viewport-btn" onClick={() => setFixedFrame((prev) => (prev === 'odom' ? 'map' : 'odom'))}>
            固定帧: {fixedFrame}
          </button>
          <button className={`viewport-btn ${showDisplays ? 'active' : ''}`} onClick={() => setShowDisplays((prev) => !prev)}>Displays</button>
          <button className={`viewport-btn ${focusRobot ? 'active' : ''}`} onClick={() => { focusRobotRef.current = !focusRobotRef.current; setFocusRobot((prev) => !prev); }}>跟随</button>
          <button className="viewport-btn" onClick={handleResetView}>重置视角</button>
          <button className={`viewport-btn ${showCalibration ? 'active' : ''}`} onClick={() => {
            if (!showCalibration && onlineRobots.length > 0) openCalibration(onlineRobots[0]!.id);
            else setShowCalibration(false);
          }}>标定</button>
          <button className={`viewport-btn ${showGo2ControlPanel ? 'active' : ''}`} onClick={() => setShowGo2ControlPanel((prev) => !prev)}>Go2 遥控</button>
        </div>
      </div>

      {showDisplays && (
        <div className="viewport-displays-panel">
          <div className="viewport-displays-header">Displays</div>
          <div className="viewport-displays-list">
            {displayRows.map((row) => (
              <button
                key={row.id}
                className={`viewport-display-row ${row.enabled ? 'enabled' : ''}`}
                onClick={() => toggleLayer(row.id)}
                type="button"
              >
                <div className="viewport-display-row-top">
                  <span className="viewport-display-row-name">{row.label}</span>
                  <span className="viewport-display-row-state">{row.enabled ? 'ON' : 'OFF'}</span>
                </div>
                <div className="viewport-display-row-topic">{row.topicLabel}</div>
              </button>
            ))}
          </div>
          <div className="viewport-displays-footer">
            {onlineRobots.length} robot(s) · 固定帧: {fixedFrame}
          </div>
        </div>
      )}

      {showGo2ControlPanel && primaryConn && (
        <Go2ControlPanel connection={primaryConn} onClose={() => setShowGo2ControlPanel(false)} />
      )}

      {showCalibration && (
        <div className="viewport-calibration-panel">
          <div className="viewport-calibration-header">
            标定
            <button className="viewport-calibration-close" onClick={() => setShowCalibration(false)}>×</button>
          </div>
          <div className="viewport-calibration-body">
            <div className="viewport-calibration-row">
              <label>机器人</label>
              <select value={calibRobot} onChange={(e) => {
                const id = e.target.value;
                setCalibRobot(id);
                const store = WorldFrameStore.getInstance();
                const off = store.getOffset(id);
                setCalibX(off.x.toFixed(3));
                setCalibY(off.y.toFixed(3));
                setCalibTheta(calibDeg ? (off.theta * 180 / Math.PI).toFixed(1) : off.theta.toFixed(4));
              }}>
                {onlineRobots.map(r => (
                  <option key={r.id} value={r.id}>{r.name} ({r.id})</option>
                ))}
              </select>
            </div>
            <div className="viewport-calibration-row">
              <label>X (m)</label>
              <input type="number" step="0.01" value={calibX} onChange={(e) => setCalibX(e.target.value)} />
            </div>
            <div className="viewport-calibration-row">
              <label>Y (m)</label>
              <input type="number" step="0.01" value={calibY} onChange={(e) => setCalibY(e.target.value)} />
            </div>
            <div className="viewport-calibration-row">
              <label>θ ({calibDeg ? '°' : 'rad'})
                <button className="viewport-calibration-unit-toggle" onClick={() => {
                  const v = parseFloat(calibTheta) || 0;
                  if (calibDeg) setCalibTheta((v * Math.PI / 180).toFixed(4));
                  else setCalibTheta((v * 180 / Math.PI).toFixed(1));
                  setCalibDeg(!calibDeg);
                }}>↻</button>
              </label>
              <input type="number" step={calibDeg ? '0.1' : '0.01'} value={calibTheta} onChange={(e) => setCalibTheta(e.target.value)} />
            </div>
            <button className="viewport-calibration-apply" onClick={applyCalibration}>
              应用标定
            </button>
          </div>
        </div>
      )}

      <div className="viewport-status-bar">
        <span>Robots: {onlineRobots.length} connected</span>
        <span>Topics: {providerTopics.length}</span>
        <span>Fixed frame: {fixedFrame}</span>
      </div>

      <div className="viewport-canvas-container" ref={containerRef}>
        <canvas ref={canvasRef} className="viewport-canvas" />
      </div>

      {imageLayerEntries.map(([layerId, imageData]) => {
        const config = layerConfigs[layerId];
        const position = imagePositionsRef.current.get(layerId) || { x: 24, y: 96, scale: 1 };
        return (
          <ImageDisplay
            key={layerId}
            imageData={imageData}
            name={config?.name || layerId}
            position={position}
            onPositionChange={(newPos) => {
              imagePositionsRef.current.set(layerId, newPos);
              const positionsMap: ImagePositionsMap = {};
              imagePositionsRef.current.forEach((pos, id) => { positionsMap[id] = pos; });
              saveImagePositions(positionsMap);
            }}
          />
        );
      })}
    </div>
  );
}
