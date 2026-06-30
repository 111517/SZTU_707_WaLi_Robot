import * as THREE from 'three';
import { BaseLayer } from './BaseLayer';
import { GridLayer } from './GridLayer';
import { OccupancyGridLayer } from './OccupancyGridLayer';
import { LaserScanLayer } from './LaserScanLayer';
import { RobotLayer } from './RobotLayer';
import { PathLayer } from './PathLayer';
import { FootprintLayer } from './FootprintLayer';
import { TFLayer } from './TFLayer';
import { TopoLayer } from './TopoLayer';
import { ImageLayer } from './ImageLayer';
import { PointCloudLayer } from './PointCloudLayer';
import { StaticMapLayer } from './StaticMapLayer';
import type { LayerConfig, LayerConfigMap } from '../../types/LayerConfig';
import { RosbridgeConnection } from '../../utils/RosbridgeConnection';
import { TF2JS } from '../../utils/tf2js';

export class LayerManager {
  private container: THREE.Object3D;
  private connection: RosbridgeConnection;
  private robotId: string;
  private tf2js: TF2JS;
  private layers: Map<string, BaseLayer> = new Map();
  private layerConfigs: LayerConfigMap = {};

  constructor(container: THREE.Object3D, connection: RosbridgeConnection, robotId: string) {
    this.container = container;
    this.connection = connection;
    this.robotId = robotId;
    this.tf2js = new TF2JS();
  }

  /** Subscribe to /tf and /tf_static for this robot. Must be called after construction. */
  initialize(): void {
    this.tf2js.initialize(this.connection);
  }

  getTf2js(): TF2JS {
    return this.tf2js;
  }

  getRobotId(): string {
    return this.robotId;
  }

  setLayerConfigs(configs: LayerConfigMap): void {
    console.log(`[LayerManager ${this.robotId}] setLayerConfigs:`, Object.keys(configs), 'connection connected:', this.connection.isConnected());
    this.layerConfigs = configs;
    this.updateLayers();
  }

  getLayerConfigs(): LayerConfigMap {
    return { ...this.layerConfigs };
  }

  updateLayerConfig(layerId: string, config: Partial<LayerConfig>): void {
    if (this.layerConfigs[layerId]) {
      this.layerConfigs[layerId] = { ...this.layerConfigs[layerId]!, ...config };
      this.updateLayers();
    }
  }

  private updateLayers(): void {
    const currentLayerIds = new Set(this.layers.keys());
    const configLayerIds = new Set(Object.keys(this.layerConfigs));

    for (const layerId of currentLayerIds) {
      if (!configLayerIds.has(layerId)) {
        this.removeLayer(layerId);
      }
    }

    for (const [layerId, config] of Object.entries(this.layerConfigs)) {
      if (!this.layers.has(layerId)) {
        this.createLayer(layerId, config);
      } else {
        const layer = this.layers.get(layerId)!;
        const oldConnection = layer.getConnection();
        if (oldConnection !== this.connection) {
          layer.setConnection(this.connection);
        }
        layer.setConfig(config);
      }
    }
  }

  private createLayer(layerId: string, config: LayerConfig): void {
    let layer: BaseLayer;

    switch (config.id) {
      case 'grid':
        layer = new GridLayer(this.container, config, this.connection);
        break;
      case 'occupancy_grid':
      case 'local_costmap':
      case 'global_costmap':
        layer = new OccupancyGridLayer(this.container, config, this.connection);
        break;
      case 'laser_scan':
        layer = new LaserScanLayer(this.container, config, this.connection);
        break;
      case 'robot':
        layer = new RobotLayer(this.container, config, this.connection);
        break;
      case 'local_plan':
      case 'plan':
        layer = new PathLayer(this.container, config, this.connection);
        break;
      case 'footprint':
        layer = new FootprintLayer(this.container, config, this.connection);
        break;
      case 'tf':
        layer = new TFLayer(this.container, config, this.connection);
        break;
      case 'topology':
        layer = new TopoLayer(this.container, config, this.connection);
        break;
      case 'image':
        layer = new ImageLayer(this.container, config, this.connection);
        break;
      case 'point_cloud':
      case 'pointcloud':
        layer = new PointCloudLayer(this.container, config, this.connection);
        break;
      case 'static_map':
        layer = new StaticMapLayer(this.container, config, this.connection);
        // Trigger async load; the layer handles rendering when data arrives
        (layer as StaticMapLayer).load();
        break;
      default:
        console.warn(`[LayerManager ${this.robotId}] Unknown layer type: ${config.id}`);
        return;
    }

    // Inject this robot's TF2JS instance into the layer
    layer.setTf2js(this.tf2js);

    this.layers.set(layerId, layer);
  }

  private removeLayer(layerId: string): void {
    const layer = this.layers.get(layerId);
    if (layer) {
      layer.dispose();
      this.layers.delete(layerId);
    }
  }

  getLayer(layerId: string): BaseLayer | undefined {
    return this.layers.get(layerId);
  }

  dispose(): void {
    for (const layerId of this.layers.keys()) {
      this.removeLayer(layerId);
    }
    this.layers.clear();
    this.tf2js.disconnect();
  }
}

