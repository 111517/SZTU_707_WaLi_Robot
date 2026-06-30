import type { RosbridgeConnection } from '../utils/RosbridgeConnection';

export type RobotType = 'tb4' | 'go2' | 'uav' | 'custom';
export type RobotStatus = 'online' | 'idle' | 'offline' | 'busy';
export type PageId = 'dashboard' | 'mission' | 'telemetry' | 'settings';

export interface RobotFleetEntry {
  id: string;
  name: string;
  type: RobotType;
  ip: string;
  port: string;
  connection: RosbridgeConnection | null;
  status: RobotStatus;
  batteryPercent: number | null;
  telemetry: Record<string, unknown>;
  topicCount: number;
}

export interface FleetState {
  robots: RobotFleetEntry[];
  activeRobotId: string | null;
}

export type FleetAction =
  | { type: 'ADD_ROBOT'; robot: RobotFleetEntry }
  | { type: 'REMOVE_ROBOT'; id: string }
  | { type: 'SELECT_ROBOT'; id: string | null }
  | { type: 'UPDATE_ROBOT'; id: string; updates: Partial<RobotFleetEntry> }
  | { type: 'SET_ROBOTS'; robots: RobotFleetEntry[] };
