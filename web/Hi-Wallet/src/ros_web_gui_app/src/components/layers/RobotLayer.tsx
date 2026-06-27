import * as THREE from 'three';
import { LoadingManager, LoaderUtils } from 'three';
import URDFLoader from 'urdf-loader';
import { BaseLayer } from './BaseLayer';
import type { LayerConfig } from '../../types/LayerConfig';
import type { RosbridgeConnection } from '../../utils/RosbridgeConnection';
import { TF2JS } from '../../utils/tf2js';
import robotSvgUrl from '../../assets/robot.svg?url';

const GO2_STATIC_ROOT = '/go2_description';
const GO2_URDF_URL = `${GO2_STATIC_ROOT}/urdf/go2_description.urdf`;
const GO2_PACKAGE_MAP = {
  go2_description: GO2_STATIC_ROOT,
} as const;

const TB4_STATIC_ROOT = '/tb4_description';
const TB4_URDF_URL = `${TB4_STATIC_ROOT}/urdf/turtlebot4.urdf`;
const CREATE3_STATIC_ROOT = '/irobot_create_description';

export class RobotLayer extends BaseLayer {
  private robotGroup: THREE.Group | null = null;
  private urdfRobot: THREE.Group | null = null;
  private robotTf2js!: TF2JS;
  private baseFrame: string;
  private mapFrame: string;
  private jointFrameBindings: Array<{
    joint: THREE.Object3D;
    parentLink: string;
    childLink: string;
  }> = [];
  private transformChangeUnsubscribe: (() => void) | null = null;
  private updateInterval: ReturnType<typeof setInterval> | null = null;
  private iconMesh: THREE.Mesh | null = null;
  private isLoadingUrdf: boolean = false;
  private relocalizeMode: boolean = false;
  private relocalizePosition: { x: number; y: number; theta: number } | null = null;
  private lastResolvedMapFrame: string | null = null;

  constructor(scene: THREE.Object3D, config: LayerConfig, connection: RosbridgeConnection | null = null) {
    super(scene, config, connection);
    // Use injected TF2JS instance if available (multi-robot), otherwise singleton
    this.robotTf2js = this.robotTf2js ?? TF2JS.getInstance();
    this.baseFrame = (config.baseFrame as string | undefined) || 'base';
    this.mapFrame = (config.mapFrame as string | undefined) || 'map';
    this.createRobot();
    this.updateRobotTransform();
    this.transformChangeUnsubscribe = this.robotTf2js.onTransformChange(() => {
      this.updateRobotTransform();
    });
    this.updateInterval = setInterval(() => {
      this.updateRobotTransform();
    }, 100);
  }

  getMessageType(): string | null {
    return null;
  }

  override setTf2js(tf2js: TF2JS): void {
    super.setTf2js(tf2js);
    if (this.robotTf2js === tf2js) return;
    this.robotTf2js = tf2js;
    // Re-register transform change callback on the new TF2JS instance
    if (this.transformChangeUnsubscribe) {
      this.transformChangeUnsubscribe();
      this.transformChangeUnsubscribe = null;
    }
    this.transformChangeUnsubscribe = tf2js.onTransformChange(() => {
      this.updateRobotTransform();
    });
    this.updateRobotTransform();
  }

  setConnection(connection: RosbridgeConnection): void {
    this.connection = connection;
    this.updateRobotTransform();
  }

  private createSVGTexture(): Promise<THREE.Texture> {
    return new Promise<THREE.Texture>((resolve) => {
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.onload = () => {
        const canvas = document.createElement('canvas');
        const size = 1024;
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext('2d');
        if (ctx) {
          ctx.imageSmoothingEnabled = true;
          ctx.imageSmoothingQuality = 'high';
          ctx.clearRect(0, 0, size, size);
          ctx.drawImage(img, 0, 0, size, size);
        }
        const texture = new THREE.CanvasTexture(canvas);
        texture.flipY = false;
        texture.minFilter = THREE.LinearFilter;
        texture.magFilter = THREE.LinearFilter;
        texture.generateMipmaps = false;
        texture.anisotropy = 16;
        resolve(texture);
      };
      img.onerror = () => {
        const loader = new THREE.TextureLoader();
        const texture = loader.load(robotSvgUrl);
        texture.flipY = false;
        texture.minFilter = THREE.LinearFilter;
        texture.magFilter = THREE.LinearFilter;
        texture.generateMipmaps = false;
        texture.anisotropy = 16;
        resolve(texture);
      };
      img.src = robotSvgUrl;
    });
  }

  private createRobot(): void {
    const robotGroup = new THREE.Group();
    this.robotGroup = robotGroup;
    this.object3D = robotGroup;
    this.scene.add(robotGroup);

    this.loadUrdfModel().catch((error) => {
      console.error('[RobotLayer] Failed to load URDF model, falling back to SVG icon:', error);
      this.createSVGIcon();
    });
  }

  private get robotType(): string {
    return (this.config.robotType as string) || 'go2';
  }

  private async createCustomLoadingManager(): Promise<LoadingManager> {
    const manager = new LoadingManager();
    // Resolve package:// URLs for both Go2 and TurtleBot4
    manager.setURLModifier((url: string) => {
      if (url.startsWith('package://go2_description/')) {
        return url.replace('package://go2_description/', `${GO2_STATIC_ROOT}/`);
      }
      if (url.startsWith('package://turtlebot4_description/')) {
        return url.replace('package://turtlebot4_description/', `${TB4_STATIC_ROOT}/`);
      }
      if (url.startsWith('package://irobot_create_description/')) {
        return url.replace('package://irobot_create_description/', `${CREATE3_STATIC_ROOT}/`);
      }
      return url;
    });

    return manager;
  }

  private async loadUrdfModel(): Promise<void> {
    if (this.isLoadingUrdf) {
      return Promise.resolve();
    }

    this.isLoadingUrdf = true;

    try {
      // 优先尝试从 ROS 的 robot_description param 加载（通过 rosapi）
      if (this.connection && this.connection.isConnected()) {
        try {
          console.log('[RobotLayer] Attempting to load robot_description from ROS via rosapi');
          const resp = await this.connection.callService('/rosapi/get_param', 'rosapi/GetParam', { name: 'robot_description' });
          let urdfText: string | null = null;
          if (resp && typeof resp === 'object' && 'value' in resp) {
            const raw = (resp as any).value;
            if (typeof raw === 'string') {
              try {
                const parsed = JSON.parse(raw);
                urdfText = typeof parsed === 'string' ? parsed : raw;
              } catch (_e) {
                urdfText = raw;
              }
            }
          } else if (typeof resp === 'string') {
            urdfText = resp;
          }

          if (urdfText && urdfText.trim().length > 0) {
            console.log('[RobotLayer] Loaded robot_description from ROS, creating blob URL for URDF');
            const manager = await this.createCustomLoadingManager();
            const loader = new URDFLoader(manager);
            loader.packages = this.robotType === 'tb4'
              ? { turtlebot4_description: TB4_STATIC_ROOT, irobot_create_description: CREATE3_STATIC_ROOT }
              : GO2_PACKAGE_MAP;

            const blob = new Blob([urdfText], { type: 'application/xml' });
            const blobUrl = URL.createObjectURL(blob);
            try {
              await new Promise<void>((resolve, reject) => {
                loader.load(
                  blobUrl,
                  (robot: unknown) => {
                    const robotGroup = robot as THREE.Group;
                    this.isLoadingUrdf = false;
                    if (!this.robotGroup) {
                      reject(new Error('RobotGroup was disposed during loading'));
                      return;
                    }

                    if (this.iconMesh) {
                      this.robotGroup!.remove(this.iconMesh);
                      if (this.iconMesh.geometry) {
                        this.iconMesh.geometry.dispose();
                      }
                      if (this.iconMesh.material) {
                        const material = this.iconMesh.material as THREE.MeshBasicMaterial;
                        if (material.map) {
                          material.map.dispose();
                        }
                        material.dispose();
                      }
                      this.iconMesh = null;
                    }

                    if (this.urdfRobot) {
                      this.robotGroup!.remove(this.urdfRobot);
                      this.disposeObject3D(this.urdfRobot);
                      this.urdfRobot = null;
                    }
                    this.urdfRobot = robotGroup;
                    this.jointFrameBindings = this.buildJointFrameBindings(robotGroup);

                    robotGroup.position.set(0, 0, 0);
                    robotGroup.quaternion.set(0, 0, 0, 1);

                    robotGroup.traverse((child) => {
                      if (child instanceof THREE.Mesh) {
                        if (child.material) {
                          const fixMaterial = (mat: THREE.Material) => {
                            if (mat instanceof THREE.MeshStandardMaterial) {
                              mat.roughness = Math.min(mat.roughness, 0.7);
                              mat.needsUpdate = true;
                            } else if (mat instanceof THREE.MeshPhongMaterial) {
                              mat.needsUpdate = true;
                            }
                          };
                          if (Array.isArray(child.material)) {
                            child.material.forEach(fixMaterial);
                          } else {
                            fixMaterial(child.material);
                          }
                        }
                      }
                    });

                    this.robotGroup!.add(robotGroup);
                    this.updateRobotTransform();
                    resolve();
                  },
                  undefined,
                  (error) => {
                    this.isLoadingUrdf = false;
                    reject(error);
                  }
                );
              });
              return;
            } finally {
              URL.revokeObjectURL(blobUrl);
            }
          }
        } catch (error) {
          console.warn('[RobotLayer] Failed to load robot_description from ROS, will fall back to static:', error);
        }
      }

      // 如果没有从 ROS 成功加载，则回退到静态目录的 URDF 加载
      const isTb4 = this.robotType === 'tb4';
      const urdfUrl = isTb4 ? TB4_URDF_URL : GO2_URDF_URL;
      const pkgMap = isTb4
        ? ({ turtlebot4_description: TB4_STATIC_ROOT, irobot_create_description: CREATE3_STATIC_ROOT } as Record<string, string>)
        : GO2_PACKAGE_MAP;
      console.log(`[RobotLayer] loadUrdfModel - starting from static ${isTb4 ? 'TB4' : 'Go2'} directory`);
      const manager = await this.createCustomLoadingManager();
      const loader = new URDFLoader(manager);
      loader.packages = pkgMap;
      const workingPath = LoaderUtils.extractUrlBase(urdfUrl);
      if (workingPath) {
        (loader as typeof loader & { workingPath?: string }).workingPath = workingPath;
      }

      console.log('[RobotLayer] loadUrdfModel - loading URDF from path:', urdfUrl);
      await new Promise<void>((resolve, reject) => {
        loader.load(
          urdfUrl,
          (robot: unknown) => {
            const robotGroup = robot as THREE.Group;
            this.isLoadingUrdf = false;
            if (!this.robotGroup) {
              reject(new Error('RobotGroup was disposed during loading'));
              return;
            }

            if (this.iconMesh) {
              this.robotGroup!.remove(this.iconMesh);
              if (this.iconMesh.geometry) {
                this.iconMesh.geometry.dispose();
              }
              if (this.iconMesh.material) {
                const material = this.iconMesh.material as THREE.MeshBasicMaterial;
                if (material.map) {
                  material.map.dispose();
                }
                material.dispose();
              }
              this.iconMesh = null;
            }

            if (this.urdfRobot) {
              this.robotGroup!.remove(this.urdfRobot);
              this.disposeObject3D(this.urdfRobot);
              this.urdfRobot = null;
            }
            this.urdfRobot = robotGroup;
            this.jointFrameBindings = this.buildJointFrameBindings(robotGroup);
            
            robotGroup.position.set(0, 0, 0);
            robotGroup.quaternion.set(0, 0, 0, 1);
            
            robotGroup.traverse((child) => {
              if (child instanceof THREE.Mesh) {
                if (child.material) {
                  const fixMat = (mat: THREE.Material) => {
                    if (mat instanceof THREE.MeshStandardMaterial) {
                      mat.roughness = Math.min(mat.roughness, 0.7);
                      mat.needsUpdate = true;
                    } else if (mat instanceof THREE.MeshPhongMaterial) {
                      mat.needsUpdate = true;
                    }
                  };
                  if (Array.isArray(child.material)) {
                    child.material.forEach(fixMat);
                  } else {
                    fixMat(child.material);
                  }
                }
              }
            });

            this.robotGroup!.add(robotGroup);
            this.updateRobotTransform();
            resolve();
          },
          undefined,
          (error) => {
            this.isLoadingUrdf = false;
            reject(error);
          }
        );
      });
    } catch (error) {
      this.isLoadingUrdf = false;
      // 确保错误信息被正确传递
      if (error instanceof Error) {
        console.error('[RobotLayer] loadUrdfModel failed:', error.message);
        throw error;
      } else {
        const errorMsg = String(error);
        console.error('[RobotLayer] loadUrdfModel failed:', errorMsg);
        throw new Error(errorMsg);
      }
    }
  }

  public async reloadUrdf(): Promise<void> {
    if (this.urdfRobot && this.robotGroup) {
      this.robotGroup.remove(this.urdfRobot);
      this.disposeObject3D(this.urdfRobot);
      this.urdfRobot = null;
    }
    try {
      await this.loadUrdfModel();
    } catch (error) {
      console.error('[RobotLayer] Failed to reload URDF model:', error);
      this.createSVGIcon();
      throw error;
    }
  }

  private createSVGIcon(): void {
    if (!this.robotGroup) return;

    this.createSVGTexture().then((texture) => {
      if (!this.robotGroup) return;
      const geometry = new THREE.PlaneGeometry(0.2, 0.2);
      const material = new THREE.MeshBasicMaterial({
        map: texture,
        transparent: true,
        depthTest: true,
        depthWrite: false,
        side: THREE.DoubleSide,
        alphaTest: 0.1,
      });
      const iconMesh = new THREE.Mesh(geometry, material);
      iconMesh.position.set(0, 0, 0.001);
      iconMesh.rotation.set(0, 0, Math.PI / 4);
      this.iconMesh = iconMesh;
      this.robotGroup!.add(iconMesh);
    }).catch((error) => {
      console.error('[RobotLayer] Failed to load SVG texture:', error);
    });
  }

  private updateRobotTransform(): void {
    if (!this.robotGroup) {
      return;
    }

    if (this.relocalizeMode && this.relocalizePosition) {
      this.robotGroup.position.set(
        this.relocalizePosition.x,
        this.relocalizePosition.y,
        0
      );
      const quaternion = new THREE.Quaternion();
      quaternion.setFromEuler(new THREE.Euler(0, 0, this.relocalizePosition.theta, 'XYZ'));
      this.robotGroup.quaternion.copy(quaternion);
      return;
    }
 
    const preferredMapFrames = [this.mapFrame, 'odom'];
    // TB4 uses base_link/base_footprint; Go2 uses base. Try multiple base names.
    const baseFrameCandidates = [this.baseFrame, 'base_link', 'base_footprint', 'base'];
    let resolvedMapFrame: string | null = null;
    let transform = null as ReturnType<TF2JS['findTransform']>;

    outer:
    for (const mapFrame of preferredMapFrames) {
      if (!mapFrame) continue;
      for (const baseFrame of baseFrameCandidates) {
        if (!baseFrame) continue;
        transform = this.robotTf2js.findTransform(mapFrame, baseFrame);
        if (transform) {
          resolvedMapFrame = mapFrame;
          break outer;
        }
      }
    }

    if (transform) {
      // The transform gives us base_link's position and orientation in map frame
      this.robotGroup.position.set(
        transform.translation.x,
        transform.translation.y,
        transform.translation.z
      );
      this.robotGroup.quaternion.copy(transform.rotation);
      this.applyTfDrivenJointFrames();

      if (resolvedMapFrame && resolvedMapFrame !== this.mapFrame && this.lastResolvedMapFrame !== resolvedMapFrame) {
        console.warn('[RobotLayer] Falling back to frame for robot pose:', {
          configuredMapFrame: this.mapFrame,
          resolvedMapFrame,
          baseFrame: this.baseFrame,
        });
      }
      this.lastResolvedMapFrame = resolvedMapFrame;
    } else {
      this.lastResolvedMapFrame = null;
      console.warn('[RobotLayer] Transform not found:', {
        mapFrame: this.mapFrame,
        baseFrame: this.baseFrame,
        availableFrames: this.robotTf2js.getFrames()
      });
    }
  }

  private buildJointFrameBindings(robotGroup: THREE.Group): Array<{
    joint: THREE.Object3D;
    parentLink: string;
    childLink: string;
  }> {
    const robot = robotGroup as THREE.Group & {
      joints?: Record<string, THREE.Object3D & { urdfNode?: Element | null }>;
    };

    if (!robot.joints) {
      return [];
    }

    return Object.values(robot.joints)
      .map((joint) => {
        const parentLink = joint.urdfNode?.querySelector('parent')?.getAttribute('link') || '';
        const childLink = joint.urdfNode?.querySelector('child')?.getAttribute('link') || '';
        if (!parentLink || !childLink) {
          return null;
        }

        return {
          joint,
          parentLink,
          childLink,
        };
      })
      .filter((binding): binding is { joint: THREE.Object3D; parentLink: string; childLink: string } => binding !== null);
  }

  private applyTfDrivenJointFrames(): void {
    if (!this.robotGroup || !this.urdfRobot) {
      return;
    }

    for (const binding of this.jointFrameBindings) {
      const transform = this.robotTf2js.findTransform(binding.parentLink, binding.childLink);
      if (!transform) {
        continue;
      }

      binding.joint.position.set(transform.translation.x, transform.translation.y, transform.translation.z);
      binding.joint.quaternion.set(
        transform.rotation.x,
        transform.rotation.y,
        transform.rotation.z,
        transform.rotation.w
      );
    }

    this.urdfRobot.updateMatrixWorld(true);
  }
  
  public setRelocalizeMode(enabled: boolean, position: { x: number; y: number; theta: number } | null): void {
    this.relocalizeMode = enabled;
    this.relocalizePosition = position;
    if (this.relocalizeMode) {
      if (this.updateInterval) {
        clearInterval(this.updateInterval);
        this.updateInterval = null;
      }
      if (this.transformChangeUnsubscribe) {
        this.transformChangeUnsubscribe();
        this.transformChangeUnsubscribe = null;
      }
      if (this.robotGroup) {
        this.robotGroup.userData.isRobot = true;
        this.robotGroup.traverse((child) => {
          child.userData.isRobot = true;
        });
      }
    } else {
      if (!this.updateInterval) {
        this.updateInterval = setInterval(() => {
          this.updateRobotTransform();
        }, 100);
      }
      if (!this.transformChangeUnsubscribe) {
        this.transformChangeUnsubscribe = this.robotTf2js.onTransformChange(() => {
          this.updateRobotTransform();
        });
      }
      if (this.robotGroup) {
        this.robotGroup.userData.isRobot = false;
        this.robotGroup.traverse((child) => {
          child.userData.isRobot = false;
        });
      }
    }
    this.updateRobotTransform();
  }
  
  public setRelocalizePosition(position: { x: number; y: number; theta: number }): void {
    if (this.relocalizeMode) {
      this.relocalizePosition = position;
      this.updateRobotTransform();
    }
  }

  update(): void {
    // TF2JS 单例会自动处理消息更新，这里不需要处理
  }

  setConfig(config: LayerConfig): void {
    super.setConfig(config);
    const cfg = config as LayerConfig & { baseFrame?: string; mapFrame?: string };
    if (cfg.baseFrame) {
      this.baseFrame = cfg.baseFrame;
    }
    if (cfg.mapFrame) {
      this.mapFrame = cfg.mapFrame;
    }
    this.updateRobotTransform();
  }

  dispose(): void {
    if (this.updateInterval) {
      clearInterval(this.updateInterval);
      this.updateInterval = null;
    }
    if (this.transformChangeUnsubscribe) {
      this.transformChangeUnsubscribe();
      this.transformChangeUnsubscribe = null;
    }
    if (this.iconMesh) {
      if (this.iconMesh.geometry) {
        this.iconMesh.geometry.dispose();
      }
      if (this.iconMesh.material) {
        const material = this.iconMesh.material as THREE.MeshBasicMaterial;
        if (material.map) {
          material.map.dispose();
        }
        material.dispose();
      }
      this.iconMesh = null;
    }
    if (this.urdfRobot) {
      this.disposeObject3D(this.urdfRobot);
      this.urdfRobot = null;
    }
    if (this.robotGroup) {
      this.scene.remove(this.robotGroup);
      this.disposeObject3D(this.robotGroup);
      this.robotGroup = null;
    }
    super.dispose();
  }
}

