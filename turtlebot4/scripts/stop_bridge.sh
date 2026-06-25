#!/bin/bash
# Stop all TurtleBot4 navigation processes started by start_bridge.sh
set -e

echo "🛑 停止 TurtleBot4 导航..."

# 1. Kill bridge
pkill -f "openclaw_nav2_bridge.py" 2>/dev/null && echo "  ✅ bridge 已停止" || echo "  ⏭ bridge 未在运行"

# 2. Clean up PID file
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
rm -f "$SCRIPT_DIR/../bridge.pid"

sleep 2
echo "✅ 所有导航进程已停止"
