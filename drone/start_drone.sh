#!/bin/bash
# UAV Full Startup v4 — rosbridge + web_video_server 移入 launch 文件
set -e
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
NC="\033[0m"
log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

log_info "Sourcing ROS2..."
source /opt/ros/humble/setup.bash
source /root/ros2_ws/install/setup.bash

# Kill leftovers
pkill -f realsense2_camera_node 2>/dev/null || true
pkill -f mavros_node 2>/dev/null || true
sleep 1

# === T265 firmware ===
log_info "Uploading T265 firmware..."
for attempt in 1 2 3; do
    if lsusb 2>/dev/null | grep -q "8087:0b37"; then
        log_info "T265 already in application mode"
        break
    fi
    log_info "  Attempt ${attempt}: rs-enumerate-devices..."
    timeout 15 rs-enumerate-devices 2>/dev/null || true
    sleep 1
    if lsusb 2>/dev/null | grep -q "8087:0b37"; then
        log_info "T265 firmware uploaded OK"
        break
    fi
    [ $attempt -eq 3 ] && log_error "T265 firmware upload FAILED"
done

# === Launch: MAVROS + Controller + rosbridge + web_video_server ===
log_info "Starting MAVROS + Controller + rosbridge + web_video_server..."
ros2 launch uav_controller uav_controller.launch.py \
    fcu_url:=serial:///dev/ttyTHS0:921600 \
    gcs_url:=udp://127.0.0.1:14555@ &
sleep 3

# === T265 camera ===
log_info "Starting realsense2_camera (pose_fps=200)..."
ros2 run realsense2_camera realsense2_camera_node \
    --ros-args -p pose_fps:=200 -r __ns:=/camera &

# === Wait for T265 Pose ===
log_info "Waiting for T265 Pose..."
log_warn ">>> SHAKE THE DRONE to init SLAM <<<"
WAIT=0
while [ $WAIT -lt 120 ]; do
    if ros2 topic info /camera/pose/sample 2>/dev/null | grep -q "Publisher count: 1"; then
        log_info "T265 Pose DETECTED after ${WAIT}s!"
        break
    fi
    sleep 3
    WAIT=$((WAIT + 3))
    [ $((WAIT % 15)) -eq 0 ] && [ $WAIT -gt 0 ] && log_warn "Still waiting... (${WAIT}s)"
done
[ $WAIT -ge 120 ] && log_error "Pose timeout (120s)."

log_info "=== Startup Complete ==="
log_info "  rosbridge:  ws://192.168.1.105:9090"
log_info "  video:      http://192.168.1.105:8080"
log_info "  MAVROS:     serial:///dev/ttyTHS0:921600"

wait
