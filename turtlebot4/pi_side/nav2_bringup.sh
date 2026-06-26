#!/bin/bash
# TurtleBot4 Nav2 Bringup (运行在树莓派上)
# 前提：turtlebot4.service 已在运行（底盘驱动、传感器、robot_state_publisher）

source /etc/turtlebot4/setup.bash

BASE_DIR="/home/ubuntu/tb4_nav2"
MAP_PATH="$BASE_DIR/map/707.yaml"
LOG_DIR="$BASE_DIR/logs"
mkdir -p "$LOG_DIR"

# 捕获退出信号，确保子进程被清理（防重入）
_CLEANUP_DONE=false
cleanup() {
    if $_CLEANUP_DONE; then
        return
    fi
    _CLEANUP_DONE=true
    echo "🛑 停止所有导航进程..."
    pkill -P $$ 2>/dev/null || true
    pkill -f "localization.launch.py" 2>/dev/null || true
    pkill -f "nav2.launch.py" 2>/dev/null || true
    pkill -f "/nav2_" 2>/dev/null || true
    pkill -f "/amcl" 2>/dev/null || true
    pkill -f "/map_server" 2>/dev/null || true
    sleep 1
    echo "✅ 导航进程已停止"
}
trap cleanup EXIT INT TERM

# 启动前清理上一次可能残留的节点
echo "🧹 清理残留进程..."
cleanup
_CLEANUP_DONE=false

echo "🧭 启动 AMCL 定位..."
ros2 launch turtlebot4_navigation localization.launch.py map:="$MAP_PATH" \
    > "$LOG_DIR/amcl.log" 2>&1 &
AMCL_LAUNCH_PID=$!

echo "⏳ 等待 AMCL 就绪..."
AMCL_WARN_SEC=300
amcl_start=$(date +%s)
amcl_last_warn=0
amcl_i=0
while true; do
    if ros2 topic list 2>/dev/null | grep -q "^/amcl_pose$"; then
        echo "✅ AMCL 已就绪"
        break
    fi
    amcl_i=$((amcl_i + 1))
    amcl_elapsed=$(($(date +%s) - amcl_start))
    if [ "$amcl_elapsed" -gt "$AMCL_WARN_SEC" ] && [ "$((amcl_elapsed - amcl_last_warn))" -gt 60 ]; then
        echo "⚠️ 等待 AMCL 已超过 ${amcl_elapsed}s，请检查底盘是否正常启动"
        amcl_last_warn=$amcl_elapsed
    fi
    sleep 2
done

echo "⏳ 等待地图发布..."
map_start=$(date +%s)
map_last_warn=0
while true; do
    if ros2 topic list 2>/dev/null | grep -q "^/map$"; then
        echo "✅ 地图已发布"
        break
    fi
    map_elapsed=$(($(date +%s) - map_start))
    if [ "$map_elapsed" -gt 60 ] && [ "$((map_elapsed - map_last_warn))" -gt 30 ]; then
        echo "⚠️ 等待地图发布已超过 ${map_elapsed}s..."
        map_last_warn=$map_elapsed
    fi
    sleep 2
done

echo "🧭 启动 Nav2 导航..."
ros2 launch turtlebot4_navigation nav2.launch.py \
    > "$LOG_DIR/nav2.log" 2>&1 &
NAV2_LAUNCH_PID=$!

echo "⏳ 等待 Nav2 就绪..."
NAV2_WARN_SEC=300
nav2_start=$(date +%s)
nav2_last_warn=0
nav2_i=0
while true; do
    if ros2 topic list 2>/dev/null | grep -q "^/local_plan$"; then
        echo "✅ Nav2 已就绪，可以接收导航指令"
        break
    fi
    nav2_i=$((nav2_i + 1))
    nav2_elapsed=$(($(date +%s) - nav2_start))
    if [ "$nav2_elapsed" -gt "$NAV2_WARN_SEC" ] && [ "$((nav2_elapsed - nav2_last_warn))" -gt 60 ]; then
        echo "⚠️ 等待 Nav2 已超过 ${nav2_elapsed}s，请检查底盘/turtlebot4.service 是否正常"
        nav2_last_warn=$nav2_elapsed
    fi
    sleep 2
done

ros2 param set /_do_not_use/motion_control safety_override full && echo "✅ safety_override=full"

echo "✅ 全部就绪 — AMCL launch PID=$AMCL_LAUNCH_PID, Nav2 launch PID=$NAV2_LAUNCH_PID"
wait
