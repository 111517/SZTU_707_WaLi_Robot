#!/bin/bash
# 安装 Go2 HTTP 服务为 systemd 服务（开机自启）

SERVICE_FILE="/etc/systemd/system/go2-http.service"

cat > /tmp/go2-http.service << 'EOF'
[Unit]
Description=Go2 HTTP Control API
After=network.target

[Service]
Type=simple
User=unitree
WorkingDirectory=/home/unitree/unitree_ros2/analysis
Environment="HOME=/home/unitree"
Environment="ROS_DOMAIN_ID=0"
Environment="RMW_IMPLEMENTATION=rmw_cyclonedds_cpp"
Environment="CYCLONEDDS_URI=file:///home/unitree/unitree_ros2/cyclonedds_ws/src/cyclonedds.xml"

ExecStartPre=/bin/bash -c 'source /opt/ros/foxy/setup.bash && source /home/unitree/unitree_ros2/cyclonedds_ws/install/setup.bash'
ExecStart=/usr/bin/python3 /home/unitree/unitree_ros2/analysis/go2_http_server.py --port 8001 --host 0.0.0.0
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "需要 sudo 权限安装服务..."
sudo cp /tmp/go2-http.service $SERVICE_FILE
sudo systemctl daemon-reload
sudo systemctl enable go2-http
sudo systemctl start go2-http

echo "✅ 服务已安装并启动"
echo "查看状态: sudo systemctl status go2-http"
echo "查看日志: sudo journalctl -u go2-http -f"
