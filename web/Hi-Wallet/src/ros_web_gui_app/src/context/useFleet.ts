import { createContext, useContext } from 'react';
import type { RobotFleetEntry, RobotType } from '../types/FleetTypes';

export interface FleetContextValue {
  robots: RobotFleetEntry[];
  activeRobotId: string | null;
  activeRobot: RobotFleetEntry | null;
  addRobot: (name: string, type: RobotType, ip: string, port: string) => Promise<RobotFleetEntry>;
  reconnectRobot: (id: string) => Promise<boolean>;
  removeRobot: (id: string) => void;
  selectRobot: (id: string | null) => void;
  updateRobot: (id: string, updates: Partial<RobotFleetEntry>) => void;
}

export const FleetContext = createContext<FleetContextValue | null>(null);

export function useFleet(): FleetContextValue {
  const ctx = useContext(FleetContext);
  if (!ctx) {
    throw new Error('useFleet must be used within a FleetProvider');
  }
  return ctx;
}
