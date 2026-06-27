import * as THREE from 'three';
import { BaseLayer } from './BaseLayer';
import type { LayerConfig } from '../../types/LayerConfig';
import type { RosbridgeConnection } from '../../utils/RosbridgeConnection';
import { TF2JS } from '../../utils/tf2js';

interface PointField {
  name: string;
  offset: number;
  datatype: number;
  count: number;
}

interface PointCloud2 {
  header?: { frame_id?: string };
  height: number;
  width: number;
  fields: PointField[];
  is_bigendian: boolean;
  point_step: number;
  row_step: number;
  data: Uint8Array | number[] | ArrayBuffer;
  is_dense?: boolean;
}

export class PointCloudLayer extends BaseLayer {
  private points: THREE.Points | null = null;
  private tf2js: TF2JS;
  private targetFrame: string;
  private warnedTfFallback = false;

  constructor(scene: THREE.Object3D, config: LayerConfig, connection: RosbridgeConnection | null = null) {
    super(scene, config, connection);
    this.tf2js = TF2JS.getInstance();
    this.targetFrame = (config.targetFrame as string | undefined) || 'map';
    if (config.topic) {
      this.subscribe(config.topic, this.getMessageType());
    }
  }

  getMessageType(): string | null {
    return 'sensor_msgs/PointCloud2';
  }

  private readNumber(view: DataView, offset: number, datatype: number, littleEndian: boolean): number {
    switch (datatype) {
      case 1: // INT8
        return view.getInt8(offset);
      case 2: // UINT8
        return view.getUint8(offset);
      case 3: // INT16
        return view.getInt16(offset, littleEndian);
      case 4: // UINT16
        return view.getUint16(offset, littleEndian);
      case 5: // INT32
        return view.getInt32(offset, littleEndian);
      case 6: // UINT32
        return view.getUint32(offset, littleEndian);
      case 7: // FLOAT32
        return view.getFloat32(offset, littleEndian);
      case 8: // FLOAT64
        return view.getFloat64(offset, littleEndian);
      default:
        return NaN;
    }
  }

  private parsePointCloud2(msg: PointCloud2, maxPoints = 200000): Array<{ x: number; y: number; z: number; r?: number; g?: number; b?: number }> {
    if (!msg || !msg.fields || !msg.data) return [];

    const littleEndian = !msg.is_bigendian;
    const dataBuffer = (msg.data instanceof ArrayBuffer)
      ? new Uint8Array(msg.data)
      : (msg.data instanceof Uint8Array ? msg.data : new Uint8Array(msg.data as number[]));
    const dv = new DataView(dataBuffer.buffer, dataBuffer.byteOffset, dataBuffer.byteLength);

    let xField: PointField | undefined;
    let yField: PointField | undefined;
    let zField: PointField | undefined;
    let rgbField: PointField | undefined;
    let intensityField: PointField | undefined;

    for (const f of msg.fields) {
      if (f.name === 'x') xField = f;
      if (f.name === 'y') yField = f;
      if (f.name === 'z') zField = f;
      if (f.name === 'rgb' || f.name === 'r' || f.name === 'rgba') rgbField = f;
      if (f.name === 'intensity') intensityField = f;
    }

    if (!xField || !yField || !zField) return [];

    const pointCount = msg.width * msg.height;
    const step = Math.max(1, Math.floor(pointCount / maxPoints));
    const out: Array<{ x: number; y: number; z: number; r?: number; g?: number; b?: number }> = [];

    for (let i = 0; i < pointCount; i += step) {
      const row = Math.floor(i / msg.width);
      const col = i % msg.width;
      const base = row * msg.row_step + col * msg.point_step;
      if (base + msg.point_step > dataBuffer.byteLength) {
        continue;
      }
      const x = this.readNumber(dv, base + xField.offset, xField.datatype, littleEndian);
      const y = this.readNumber(dv, base + yField.offset, yField.datatype, littleEndian);
      const z = this.readNumber(dv, base + zField.offset, zField.datatype, littleEndian);
      if (!isFinite(x) || !isFinite(y) || !isFinite(z) || Number.isNaN(x) || Number.isNaN(y) || Number.isNaN(z)) continue;

      const p: { x: number; y: number; z: number; r?: number; g?: number; b?: number } = { x, y, z };

      if (rgbField) {
        const rgbOffset = base + rgbField.offset;
        // rgb is often float32 containing packed rgb as uint32 or separate channels
        try {
          const raw = dv.getUint32(rgbOffset, littleEndian);
          const r = (raw >> 16) & 0xff;
          const g = (raw >> 8) & 0xff;
          const b = raw & 0xff;
          p.r = r / 255;
          p.g = g / 255;
          p.b = b / 255;
        } catch {
          // ignore
        }
      }

      if (intensityField && p.r === undefined) {
        const intensity = this.readNumber(dv, base + intensityField.offset, intensityField.datatype, littleEndian);
        const c = Math.max(0, Math.min(1, (intensity as number) / 255));
        p.r = p.g = p.b = c;
      }

      out.push(p);
    }

    return out;
  }

  update(message: unknown): void {
    const msg = message as PointCloud2;
    if (!msg) return;
    const sourceFrame = msg.header?.frame_id || this.targetFrame;

    const pointsData = this.parsePointCloud2(msg, 200000);
    if (pointsData.length === 0) return;

    const rawPoints = pointsData.map((p) => ({ x: p.x, y: p.y, z: p.z }));
    let transformed = this.tf2js.transformPointsToFrame(rawPoints, sourceFrame, this.targetFrame);
    if (!transformed) {
      if (!this.warnedTfFallback && sourceFrame !== this.targetFrame) {
        console.warn(
          `[PointCloudLayer] TF unavailable from ${sourceFrame} to ${this.targetFrame}, rendering in source frame`
        );
        this.warnedTfFallback = true;
      }
      transformed = rawPoints.map((p) => new THREE.Vector3(p.x, p.y, p.z));
    }

    const positions = new Float32Array(transformed.length * 3);
    const colors = new Float32Array(transformed.length * 3);

    for (let i = 0; i < transformed.length; i++) {
      const v = transformed[i]!;
      positions[i * 3 + 0] = v.x;
      positions[i * 3 + 1] = v.y;
      positions[i * 3 + 2] = v.z;
      const col = pointsData[i];
      const r = (col.r !== undefined) ? col.r : 0.5;
      const g = (col.g !== undefined) ? col.g : 0.5;
      const b = (col.b !== undefined) ? col.b : 0.5;
      colors[i * 3 + 0] = r;
      colors[i * 3 + 1] = g;
      colors[i * 3 + 2] = b;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    const material = new THREE.PointsMaterial({ size: (this.config.pointSize as number) || 0.05, vertexColors: true });
    const pointsMesh = new THREE.Points(geometry, material);

    if (this.points) {
      this.scene.remove(this.points);
      this.points.geometry.dispose();
      (this.points.material as THREE.Material).dispose();
    }

    this.points = pointsMesh;
    this.object3D = pointsMesh;
    if (this.config.enabled) {
      this.scene.add(pointsMesh);
    }
  }

  setConfig(config: LayerConfig): void {
    super.setConfig(config);
    const cfg = config as LayerConfig & { targetFrame?: string; pointSize?: number };
    if (cfg.targetFrame) this.targetFrame = cfg.targetFrame;
  }

  dispose(): void {
    if (this.points) {
      this.scene.remove(this.points);
      this.points.geometry.dispose();
      (this.points.material as THREE.Material).dispose();
      this.points = null;
    }
    super.dispose();
  }
}
