import * as THREE from 'three';
import { BaseLayer } from './BaseLayer';
import type { LayerConfig } from '../../types/LayerConfig';
import type { RosbridgeConnection } from '../../utils/RosbridgeConnection';
import { loadStaticMap } from '../../utils/StaticMapLoader';
import { paletteColorCached } from '../../utils/colorUtils';

interface OccupancyGrid {
  header: { frame_id: string };
  info: {
    resolution: number;
    width: number;
    height: number;
    origin: {
      position: { x: number; y: number; z: number };
      orientation: { x: number; y: number; z: number; w: number };
    };
  };
  data: number[] | Int8Array;
}

export class StaticMapLayer extends BaseLayer {
  private mesh: THREE.Mesh | null = null;
  private texture: THREE.DataTexture | null = null;
  private mapUrl: string;
  private colorMode: 'costmap' | 'map' | 'raw';
  private alpha: number;
  private height: number;
  private loaded: boolean = false;

  constructor(scene: THREE.Object3D, config: LayerConfig, connection: RosbridgeConnection | null = null) {
    super(scene, config, connection);
    this.mapUrl = (config.mapUrl as string) || '/maps/707.yaml';
    this.colorMode = (config.colorMode as 'costmap' | 'map' | 'raw') || 'map';
    this.alpha = (config.alpha as number) ?? 1.0;
    this.height = (config.height as number) ?? 0;
  }

  getMessageType(): null {
    // No ROS topic subscription — data loaded from local files
    return null;
  }

  override setConnection(_connection: RosbridgeConnection): void {
    // Static map doesn't need a ROS connection
  }

  /** Initiate async load. Call externally after construction. */
  async load(): Promise<void> {
    if (this.loaded) return;
    try {
      const map = await loadStaticMap(this.mapUrl);
      if (!this.object3D) {
        this.renderMap(map);
      }
      this.loaded = true;
    } catch (err) {
      console.error('[StaticMapLayer] Failed to load static map:', err);
    }
  }

  private renderMap(msg: OccupancyGrid): void {
    const { resolution, width, height, origin } = msg.info;
    const size = width * height;

    if (msg.data.length !== size) {
      console.warn('[StaticMapLayer] Data length mismatch', msg.data.length, size);
      return;
    }

    // Create texture
    const rgba = new Uint8ClampedArray(size * 4);
    const tempColor = { r: 0, g: 0, b: 0, a: 0 };
    for (let i = 0; i < size; i++) {
      const value = msg.data[i]! | 0;
      const offset = i * 4;
      if (value === -1) {
        rgba[offset + 0] = 0;
        rgba[offset + 1] = 0;
        rgba[offset + 2] = 0;
        rgba[offset + 3] = 0;
      } else {
        paletteColorCached(tempColor, value, this.colorMode);
        rgba[offset + 0] = tempColor.r;
        rgba[offset + 1] = tempColor.g;
        rgba[offset + 2] = tempColor.b;
        rgba[offset + 3] = Math.trunc(tempColor.a * this.alpha);
      }
    }

    const texture = new THREE.DataTexture(
      rgba, width, height,
      THREE.RGBAFormat, THREE.UnsignedByteType,
      THREE.UVMapping, THREE.ClampToEdgeWrapping, THREE.ClampToEdgeWrapping,
      THREE.NearestFilter, THREE.LinearFilter,
      1, THREE.LinearSRGBColorSpace,
    );
    texture.generateMipmaps = false;
    texture.needsUpdate = true;
    this.texture = texture;

    // Create geometry: unit plane, then scaled to real-world size
    const geometry = new THREE.PlaneGeometry(1, 1, 1, 1);
    geometry.translate(0.5, 0.5, 0); // anchor at bottom-left corner

    const transparent = this.alpha < 1.0;
    const material = new THREE.MeshBasicMaterial({
      map: texture,
      side: THREE.DoubleSide,
      alphaTest: 1e-4,
      depthWrite: !transparent,
      transparent,
      opacity: this.alpha,
    });

    const mesh = new THREE.Mesh(geometry, material);
    mesh.scale.set(width * resolution, height * resolution, 1);
    mesh.position.set(
      origin.position.x,
      origin.position.y,
      this.height,
    );
    // Default identity quaternion (no rotation)
    mesh.quaternion.set(0, 0, 0, 1);

    this.mesh = mesh;
    this.object3D = mesh;
    if (this.config.enabled) {
      this.scene.add(mesh);
    }
  }

  override setConfig(config: LayerConfig): void {
    super.setConfig(config);
    const oldAlpha = this.alpha;
    const oldColorMode = this.colorMode;
    this.alpha = (config.alpha as number) ?? 1.0;
    this.colorMode = (config.colorMode as 'costmap' | 'map' | 'raw') || 'map';
    this.height = (config.height as number) ?? 0;

    if (this.mesh) {
      // Update height
      this.mesh.position.z = this.height;

      // Update transparency
      const material = this.mesh.material as THREE.MeshBasicMaterial;
      const transparent = this.alpha < 1.0;
      material.transparent = transparent;
      material.opacity = this.alpha;
      material.depthWrite = !transparent;
    }

    if (this.mesh && (oldAlpha !== this.alpha || oldColorMode !== this.colorMode)) {
      // Would need to re-render texture for color mode change, but for
      // static map this is rarely changed at runtime.
    }

    // Show/hide based on enabled
    if (!config.enabled && this.mesh && this.scene.children.includes(this.mesh)) {
      this.scene.remove(this.mesh);
    } else if (config.enabled && this.mesh && !this.scene.children.includes(this.mesh)) {
      this.scene.add(this.mesh);
    }
  }

  update(_message: unknown): void {
    // No-op: static map doesn't receive live updates
  }

  dispose(): void {
    if (this.texture) {
      this.texture.dispose();
      this.texture = null;
    }
    if (this.mesh) {
      this.scene.remove(this.mesh);
      this.mesh.geometry.dispose();
      (this.mesh.material as THREE.Material).dispose();
      this.mesh = null;
    }
    this.object3D = null;
    this.loaded = false;
    super.dispose();
  }
}
