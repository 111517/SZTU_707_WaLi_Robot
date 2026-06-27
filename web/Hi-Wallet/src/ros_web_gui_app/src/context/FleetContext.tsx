import { useReducer, useCallback, useEffect, useRef, type ReactNode } from 'react';
import type { FleetState, FleetAction, RobotFleetEntry, RobotStatus, RobotType } from '../types/FleetTypes';
import { RosbridgeConnection } from '../utils/RosbridgeConnection';
import { FleetContext } from './useFleet';

const STORAGE_KEY = 'robotcore_fleet';
const NEXT_ID_KEY = 'robotcore_next_id';

interface SavedRobot {
  id: string;
  name: string;
  type: RobotType;
  ip: string;
  port: string;
}

function loadSavedFleet(): { robots: RobotFleetEntry[]; nextId: number } {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const nextId = parseInt(localStorage.getItem(NEXT_ID_KEY) || '1', 10);
    if (!raw) return { robots: [], nextId };
    const saved: SavedRobot[] = JSON.parse(raw);
    const robots: RobotFleetEntry[] = saved.map((s) => ({
      id: s.id,
      name: s.name,
      type: s.type,
      ip: s.ip,
      port: s.port,
      connection: null,
      status: 'offline' as RobotStatus,
      batteryPercent: null,
      telemetry: {},
      topicCount: 0,
    }));
    return { robots, nextId };
  } catch {
    return { robots: [], nextId: 1 };
  }
}

function saveFleet(robots: RobotFleetEntry[]): void {
  const configs: SavedRobot[] = robots.map((r) => ({
    id: r.id, name: r.name, type: r.type, ip: r.ip, port: r.port,
  }));
  localStorage.setItem(STORAGE_KEY, JSON.stringify(configs));
}

function fleetReducer(state: FleetState, action: FleetAction): FleetState {
  switch (action.type) {
    case 'ADD_ROBOT':
      return { ...state, robots: [...state.robots, action.robot] };
    case 'REMOVE_ROBOT': {
      const robot = state.robots.find((r) => r.id === action.id);
      robot?.connection?.disconnect();
      return {
        ...state,
        robots: state.robots.filter((r) => r.id !== action.id),
        activeRobotId: state.activeRobotId === action.id ? null : state.activeRobotId,
      };
    }
    case 'SELECT_ROBOT':
      return { ...state, activeRobotId: action.id };
    case 'UPDATE_ROBOT':
      return {
        ...state,
        robots: state.robots.map((r) =>
          r.id === action.id ? { ...r, ...action.updates } : r
        ),
      };
    case 'SET_ROBOTS':
      return { ...state, robots: action.robots };
    default:
      return state;
  }
}

const { robots: savedRobots, nextId: savedNextId } = loadSavedFleet();
let nextRobotId = savedNextId;

const initialState: FleetState = {
  robots: savedRobots,
  activeRobotId: null,
};

export function FleetProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(fleetReducer, initialState);
  const stateRef = useRef(state);
  stateRef.current = state;

  useEffect(() => {
    saveFleet(state.robots);
    localStorage.setItem(NEXT_ID_KEY, String(nextRobotId));
  }, [state.robots]);

  const addRobot = useCallback(async (name: string, type: RobotType, ip: string, port: string) => {
    const id = `robot-${nextRobotId++}`;
    localStorage.setItem(NEXT_ID_KEY, String(nextRobotId));
    const conn = new RosbridgeConnection();
    const url = `ws://${ip}:${port}`;

    let status: RobotStatus = 'offline';
    let topicCount = 0;

    try {
      const success = await conn.connect(url);
      if (success) {
        await conn.initializeMessageReaders();
        status = 'online';
        topicCount = conn.getProviderTopics().length;
      }
    } catch {
      status = 'offline';
    }

    const robot: RobotFleetEntry = {
      id, name, type, ip, port,
      connection: status === 'online' ? conn : null,
      status,
      batteryPercent: null,
      telemetry: {},
      topicCount,
    };

    dispatch({ type: 'ADD_ROBOT', robot });
    return robot;
  }, []);

  const reconnectRobot = useCallback(async (id: string) => {
    const robot = stateRef.current.robots.find((r) => r.id === id);
    if (!robot) return false;
    robot.connection?.disconnect();
    const conn = new RosbridgeConnection();
    const url = `ws://${robot.ip}:${robot.port}`;

    try {
      const success = await conn.connect(url);
      if (success) {
        await conn.initializeMessageReaders();
        dispatch({ type: 'UPDATE_ROBOT', id, updates: {
          connection: conn,
          status: 'online',
          topicCount: conn.getProviderTopics().length,
        }});
        return true;
      }
    } catch { /* offline */ }
    dispatch({ type: 'UPDATE_ROBOT', id, updates: { status: 'offline' } });
    return false;
  }, []);

  const removeRobot = useCallback((id: string) => {
    dispatch({ type: 'REMOVE_ROBOT', id });
  }, []);

  const selectRobot = useCallback((id: string | null) => {
    dispatch({ type: 'SELECT_ROBOT', id });
  }, []);

  const updateRobot = useCallback((id: string, updates: Partial<RobotFleetEntry>) => {
    dispatch({ type: 'UPDATE_ROBOT', id, updates });
  }, []);

  const activeRobot = state.activeRobotId
    ? state.robots.find((r) => r.id === state.activeRobotId) ?? null
    : null;

  useEffect(() => {
    if (savedRobots.length === 0) return;
    const first = savedRobots[0];
    let cancelled = false;
    const tryConnect = async () => {
      const conn = new RosbridgeConnection();
      try {
        const ok = await conn.connect(`ws://${first.ip}:${first.port}`);
        if (cancelled) { conn.disconnect(); return; }
        if (ok) {
          await conn.initializeMessageReaders();
          dispatch({ type: 'UPDATE_ROBOT', id: first.id, updates: {
            connection: conn, status: 'online',
            topicCount: conn.getProviderTopics().length,
          }});
          dispatch({ type: 'SELECT_ROBOT', id: first.id });
        }
      } catch { /* offline - robot entry already shows as offline */ }
    };
    void tryConnect();
    return () => { cancelled = true; };
  }, []);

  return (
    <FleetContext.Provider
      value={{
        robots: state.robots,
        activeRobotId: state.activeRobotId,
        activeRobot,
        addRobot,
        removeRobot,
        selectRobot,
        updateRobot,
        reconnectRobot,
      }}
    >
      {children}
    </FleetContext.Provider>
  );
}
