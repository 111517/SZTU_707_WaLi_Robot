#!/bin/bash
# ===========================================
# 一键启动 UAV 仿真（后台启动，前台留给你）
# ===========================================

PX4_DIR="$HOME/PX4-Autopilot"
ROS2_WS="$HOME/ros2_ws"

# 先杀残留
pkill -9 -f px4      2>/dev/null || true
pkill -9 -f gazebo   2>/dev/null || true
pkill -9 -f gzserver 2>/dev/null || true
pkill -9 -f gzclient 2>/dev/null || true
pkill -9 -f mavros   2>/dev/null || true
sleep 1

# 写入清理脚本
cat > /tmp/stop_sim.sh << 'CLEANUP'
#!/bin/bash
echo "正在关闭仿真..."
pkill -9 -f px4      2>/dev/null || true
pkill -9 -f gazebo   2>/dev/null || true
pkill -9 -f gzserver 2>/dev/null || true
pkill -9 -f gzclient 2>/dev/null || true
pkill -9 -f mavros   2>/dev/null || true
echo "已清理"
CLEANUP
chmod +x /tmp/stop_sim.sh

echo "========================================"
echo "  UAV 仿真环境启动"
echo "========================================"

# T1: PX4 + Gazebo
echo "[1/2] 启动 PX4 SITL + Gazebo..."
cd "$PX4_DIR"
nohup make px4_sitl gazebo-classic > /tmp/px4.log 2>&1 &
echo "  日志: /tmp/px4.log"

# 等 PX4 就绪
echo -n "  等待 PX4 就绪"
while ! ss -lnu 2>/dev/null | grep -q 14580; do
    echo -n "."
    sleep 2
done
echo " 就绪"

# T2: mavros + controller
echo "[2/2] 启动 mavros + uav_controller..."
source /opt/ros/humble/setup.bash
source "$ROS2_WS/install/setup.bash"
nohup ros2 launch uav_controller uav_controller.launch.py > /tmp/mavros.log 2>&1 &
echo "  日志: /tmp/mavros.log"

echo ""
echo "========================================"
echo "  就绪！"
echo ""
echo "  uav takeoff 0 0 2.5"
echo "  uav goto 5 3 2.5"
echo "  uav land"
echo "  uav ~/ros2_ws/mission_test.txt"
echo ""
echo "  停止: /tmp/stop_sim.sh"
echo "========================================"
