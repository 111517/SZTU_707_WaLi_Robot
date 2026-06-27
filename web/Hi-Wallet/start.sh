#!/bin/bash
# ============================================================
# Go2 Web Dashboard — One-click Startup
# ============================================================
# Starts the ROS2 backend + web frontend server.
#
# Prerequisites:
#   - ROS 2 Humble installed
#   - unitree_ros2 SDK installed at ~/unitree_ros2
#   - This workspace built with: colcon build
#   - Go2 robot powered on and accessible (for live data)
#
# Usage:
#   chmod +x start.sh
#   ./start.sh [--no-web] [--rosbridge-port 9090]
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROSBRIDGE_PORT="${ROSBRIDGE_PORT:-9090}"
WEB_PORT="${WEB_PORT:-3000}"
START_WEB=true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-web) START_WEB=false; shift ;;
    --rosbridge-port) ROSBRIDGE_PORT="$2"; shift 2 ;;
    --web-port) WEB_PORT="$2"; shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

echo "========================================"
echo " Go2 Web Dashboard"
echo " ROS Bridge : ws://0.0.0.0:${ROSBRIDGE_PORT}"
echo " Web UI    : http://0.0.0.0:${WEB_PORT}"
echo "========================================"

# --- Source ROS2 + unitree SDK ---
echo "[1/4] Sourcing ROS2 environment..."
if [ -f /opt/ros/humble/setup.bash ]; then
  source /opt/ros/humble/setup.bash
else
  echo "ERROR: /opt/ros/humble/setup.bash not found. Is ROS2 Humble installed?"
  exit 1
fi

UNITREE_SETUP="${HOME}/unitree_ros2/setup.sh"
if [ -f "${UNITREE_SETUP}" ]; then
  source "${UNITREE_SETUP}"
  echo "       unitree_ros2 SDK sourced."
else
  echo "WARNING: ${UNITREE_SETUP} not found."
  echo "         unitree_go message types may not be available."
  echo "         Install from: https://github.com/unitreerobotics/unitree_ros2"
fi

# --- Source this workspace ---
echo "[2/4] Sourcing workspace..."
if [ -f "${SCRIPT_DIR}/install/setup.bash" ]; then
  source "${SCRIPT_DIR}/install/setup.bash"
else
  echo "ERROR: ${SCRIPT_DIR}/install/setup.bash not found."
  echo "       Please build the workspace first: cd ${SCRIPT_DIR} && colcon build"
  exit 1
fi

# --- Launch ROS2 backend ---
echo "[3/4] Launching ROS2 backend (bridge + TF + rosbridge)..."
export ROSBRIDGE_PORT
export GO2_URDF_PATH="${SCRIPT_DIR}/install/go2_description/share/go2_description/urdf/go2_description.urdf"
ros2 launch go2_web_bridge dashboard.launch.py \
  rosbridge_port:=${ROSBRIDGE_PORT} &

ROS_PID=$!
echo "       Backend PID: ${ROS_PID}"

# Give rosbridge a moment to start
sleep 2

# --- Serve web frontend ---
if $START_WEB; then
  WEB_DIR="${SCRIPT_DIR}/src/ros_web_gui_app/dist"
  if [ -d "${WEB_DIR}" ]; then
    echo "[4/4] Serving web frontend on port ${WEB_PORT}..."
    echo "       Open http://localhost:${WEB_PORT} in your browser"
    echo ""
    echo "  Press Ctrl+C to stop all services."
    echo ""
    python3 "${SCRIPT_DIR}/serve.py" ${WEB_PORT} "${WEB_DIR}" &
    WEB_PID=$!
  else
    echo "[4/4] WARNING: Web frontend not built. Skipping."
    echo "       Build with: cd src/ros_web_gui_app && npm run build"
    WEB_PID=""
  fi
else
  echo "[4/4] Web server skipped (--no-web)."
  echo ""
  echo "  Press Ctrl+C to stop all services."
  echo ""
  WEB_PID=""
fi

# --- Cleanup on exit ---
cleanup() {
  echo ""
  echo "Shutting down..."
  kill ${ROS_PID} 2>/dev/null || true
  [ -n "${WEB_PID}" ] && kill ${WEB_PID} 2>/dev/null || true
  wait
  echo "Done."
}
trap cleanup EXIT INT TERM

# Wait for ROS process (the launch file runs until interrupted)
wait ${ROS_PID}
