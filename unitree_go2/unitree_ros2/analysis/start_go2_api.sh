#!/bin/bash
# Go2 HTTP + 飞书 Bot 自启动脚本
# 等待网络就绪后启动（v2：HTTP API + 飞书 Bot 双通道）

LOG="/tmp/go2_http.log"

echo "$(date) === Go2 控制服务启动 ===" >> $LOG
echo "$(date) 等待 eth0 就绪…" >> $LOG

# 等 eth0 拿到 IP（最多等 30 秒）
for i in $(seq 1 30); do
    IP=$(ip -4 addr show eth0 2>/dev/null | grep -oP 'inet \K[\d.]+')
    if [ -n "$IP" ]; then
        echo "$(date) eth0=$IP 就绪" >> $LOG
        break
    fi
    sleep 1
done

# 加载 ROS2
source /opt/ros/foxy/setup.bash
source /home/unitree/unitree_ros2/cyclonedds_ws/install/setup.bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI="file:///home/unitree/unitree_ros2/cyclonedds_ws/src/cyclonedds.xml"

cd /home/unitree/unitree_ros2/analysis

echo "$(date) 启动 HTTP API (端口 8001) …" >> $LOG
python3 go2_http_server.py --port 8001 --host 0.0.0.0 &
HTTP_PID=$!
sleep 3

echo "$(date) 启动飞书 Bot (端口 8002) …" >> $LOG
python3 go2_feishu_bot.py --port 8002 --host 0.0.0.0 --api-url http://localhost:8001 &
FEISHU_PID=$!

echo "$(date) 双服务就绪: HTTP API=8001, 飞书Bot=8002" >> $LOG

# 如果任意服务退出，记录日志但不退出
wait $HTTP_PID
echo "$(date) ⚠️ HTTP API 进程退出" >> $LOG