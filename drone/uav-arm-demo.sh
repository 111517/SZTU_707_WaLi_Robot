#!/bin/bash
# UAV ARM 演示脚本 — 分步可控
# 用法: sudo uav-arm-demo

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ROS_CMD='docker exec uav-run bash -c "source /opt/ros/humble/setup.bash'

echo "========================================"
echo "  无人机 OFFBOARD ARM 演示"
echo "  拆浆状态 — 电机怠速旋转"
echo "========================================"
echo ""

# Step 1: 确认 setpoint 流
echo -e "${GREEN}[1/4]${NC} 确认 setpoint 流..."
docker exec uav-run bash -c "source /opt/ros/humble/setup.bash && timeout 3 ros2 topic hz /mavros/setpoint_position/local 2>&1" | tail -1
echo ""

# Step 2: 切 OFFBOARD
echo -e "${GREEN}[2/4]${NC} 切换 OFFBOARD 模式..."
docker exec uav-run bash -c "source /opt/ros/humble/setup.bash && ros2 service call /mavros/set_mode mavros_msgs/srv/SetMode '{custom_mode: OFFBOARD}'" 2>&1
sleep 2
docker exec uav-run bash -c "source /opt/ros/humble/setup.bash && ros2 topic echo /mavros/state --once 2>&1 | grep mode"
echo ""

# Step 3: 人工确认
echo -e "${YELLOW}========================================"
echo -e "${YELLOW}  即将 ARM — 电机将怠速旋转！"
echo -e "${YELLOW}  确保：拆浆 + 电机周围无障碍物"
echo -e "${YELLOW}========================================${NC}"
read -p "按回车继续，Ctrl+C 取消..."

# Step 4: ARM
echo ""
echo -e "${GREEN}[3/4]${NC} ARM 解锁..."
docker exec uav-run bash -c "source /opt/ros/humble/setup.bash && ros2 service call /mavros/cmd/arming mavros_msgs/srv/CommandBool '{value: true}'" 2>&1
sleep 1
ARM_STATE=$(docker exec uav-run bash -c "source /opt/ros/humble/setup.bash && ros2 topic echo /mavros/state --once 2>&1 | grep armed")

if echo "$ARM_STATE" | grep -q "true"; then
    echo ""
    echo -e "${GREEN}✅ ARM 成功！电机怠速中...${NC}"
    echo ""
    echo -e "${YELLOW}按回车 DISARM 停止电机${NC}"
    read
else
    echo ""
    echo -e "${RED}❌ ARM 失败，请检查飞控状态${NC}"
    echo "$ARM_STATE"
    exit 1
fi

# Step 5: DISARM
echo ""
echo -e "${GREEN}[4/4]${NC} DISARM + 切回 MANUAL..."
sleep 0.5
docker exec uav-run bash -c "source /opt/ros/humble/setup.bash && ros2 service call /mavros/set_mode mavros_msgs/srv/SetMode '{custom_mode: MANUAL}'" 2>&1
sleep 1
docker exec uav-run bash -c "source /opt/ros/humble/setup.bash && ros2 service call /mavros/cmd/arming mavros_msgs/srv/CommandBool '{value: false}'" 2>&1
sleep 1

docker exec uav-run bash -c "source /opt/ros/humble/setup.bash && ros2 topic echo /mavros/state --once 2>&1 | grep -E 'armed|mode'"

echo ""
echo -e "${GREEN}DISARM 完成${NC}"
