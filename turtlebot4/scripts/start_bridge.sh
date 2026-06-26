#!/bin/bash
# Start the OpenClaw TurtleBot4 Nav2 Bridge
# Nav2/AMCL 在树莓派上运行，Jetson 只跑 bridge

set -e

source /opt/ros/humble/setup.bash
source /etc/turtlebot4_discovery/setup.bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

LOG_DIR="$PROJECT_DIR"
BRIDGE_PID_FILE="$LOG_DIR/bridge.pid"

# ─── 工具函数 ──────────────────────────────────────────────────────────────
wait_for_topic() {
    local topic_name="$1"
    local timeout="${2:-60}"
    local interval=2
    local elapsed=0
    echo "⏳ 等待话题 $topic_name 就绪..."
    while ! ros2 topic list 2>/dev/null | grep -q "$topic_name"; do
        if [ "$elapsed" -ge "$timeout" ]; then
            echo "❌ 超时：$topic_name 未在 ${timeout}s 内出现"
            return 1
        fi
        sleep "$interval"
        elapsed=$((elapsed + interval))
    done
    echo "✅ $topic_name 已就绪"
}

wait_for_action() {
    local action_name="$1"
    local timeout="${2:-90}"
    local interval=2
    local elapsed=0
    echo "⏳ 等待 action server $action_name 就绪..."
    while ! ros2 action list 2>/dev/null | grep -q "$action_name"; do
        if [ "$elapsed" -ge "$timeout" ]; then
            echo "❌ 超时：$action_name 未在 ${timeout}s 内就绪"
            return 1
        fi
        sleep "$interval"
        elapsed=$((elapsed + interval))
    done
    echo "✅ $action_name 已就绪"
}

# ─── Step 0：等待树莓派上线（/odom 话题说明 Create3 + Pi 桥接正常）────
echo "⏳ 等待树莓派 /odom 数据就绪..."
for i in $(seq 1 30); do
    if ros2 topic list 2>/dev/null | grep -q "/odom"; then
        echo "✅ 树莓派已在线，数据发现正常"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "❌ 超时：无法发现 /odom，请检查树莓派和机器人"
        exit 1
    fi
    echo "   等待 (${i}/30)..."
    sleep 2
done

# ─── Step 1：杀掉旧 bridge ────────────────────────────────────────────────
if [ -f "$BRIDGE_PID_FILE" ]; then
    OLD_PID=$(cat "$BRIDGE_PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "🛑 停止旧 bridge (PID $OLD_PID)..."
        kill "$OLD_PID" 2>/dev/null
        sleep 2
    fi
fi
pkill -f "openclaw_nav2_bridge.py" 2>/dev/null || true
sleep 1

# ─── Step 2：等待树莓派上的 map_server 就绪 ─────────────────────────────────
wait_for_topic "/map" 60
echo "✅ 树莓派 map_server 已就绪，准备启动 bridge（bridge 内部会等 Nav2）"

# ─── Step 3：启动 bridge ──────────────────────────────────────────────────
echo "🚀 启动 bridge..."
exec python3 src/openclaw_nav2_bridge.py > "$LOG_DIR/bridge.log" 2>&1
