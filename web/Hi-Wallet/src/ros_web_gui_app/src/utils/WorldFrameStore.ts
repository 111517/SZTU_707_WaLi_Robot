export interface WorldOffset {
  x: number;
  y: number;
  theta: number; // radians
}

type ChangeCallback = (robotId: string, offset: WorldOffset) => void;

const STORAGE_KEY = 'go2_world_frame_offsets';

/**
 * Singleton store for per-robot world coordinate calibration offsets.
 * Persisted to localStorage.
 *
 * Each robot's offset represents: world_pose = odom_pose + offset
 * (or equivalently: map->odom transform = offset)
 */
export class WorldFrameStore {
  private static instance: WorldFrameStore | null = null;
  private offsets: Map<string, WorldOffset> = new Map();
  private listeners: Set<ChangeCallback> = new Set();

  private constructor() {
    this.load();
  }

  static getInstance(): WorldFrameStore {
    if (!WorldFrameStore.instance) {
      WorldFrameStore.instance = new WorldFrameStore();
    }
    return WorldFrameStore.instance;
  }

  getOffset(robotId: string): WorldOffset {
    return this.offsets.get(robotId) ?? { x: 0, y: 0, theta: 0 };
  }

  setOffset(robotId: string, offset: WorldOffset): void {
    this.offsets.set(robotId, { ...offset });
    this.save();
    for (const fn of this.listeners) {
      fn(robotId, offset);
    }
  }

  removeOffset(robotId: string): void {
    this.offsets.delete(robotId);
    this.save();
  }

  onChange(callback: ChangeCallback): () => void {
    this.listeners.add(callback);
    return () => this.listeners.delete(callback);
  }

  private load(): void {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const data = JSON.parse(raw) as Record<string, WorldOffset>;
        for (const [id, offset] of Object.entries(data)) {
          this.offsets.set(id, offset);
        }
      }
    } catch {
      // corrupted data, reset
      this.offsets.clear();
    }
  }

  private save(): void {
    const data: Record<string, WorldOffset> = {};
    for (const [id, offset] of this.offsets.entries()) {
      data[id] = offset;
    }
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch {
      console.warn('[WorldFrameStore] Failed to save to localStorage');
    }
  }
}
