# tb4-uav: UAV 侧 Docker 镜像
# 基于 ARM64 Ubuntu 22.04 + ROS2 Humble + mavros + uav_controller
# 目标平台: Jetson Xavier NX (aarch64)
#
# 构建: docker build -f Dockerfile.tb4-uav -t tb4-uav .
# 运行: docker run -it --rm --net=host --device=/dev/ttyTHS1 tb4-uav

FROM arm64v8/ros:humble-ros-base

# 避免交互式提示
ENV DEBIAN_FRONTEND=noninteractive

# 安装 mavros + 依赖
RUN apt-get update && apt-get install -y \
    ros-humble-mavros \
    ros-humble-mavros-extras \
    ros-humble-mavros-msgs \
    ros-humble-geographic-msgs \
    python3-colcon-common-extensions \
    && rm -rf /var/lib/apt/lists/*

# 安装 GeographicLib (mavros 需要)
RUN /opt/ros/humble/lib/mavros/install_geographiclib_datasets.sh

# 创建工作空间
RUN mkdir -p /root/ros2_ws/src

# 拷贝源码（在 NX 上 build 时 mount 或 COPY）
# 这里用 COPY，实际构建时 docker build -f Dockerfile.tb4-uav -t tb4-uav ~/ros2_ws/
COPY src/ /root/ros2_ws/src/

# 构建
RUN /bin/bash -c "source /opt/ros/humble/setup.bash && \
    cd /root/ros2_ws && \
    colcon build --symlink-install"

# 自动 source 环境
RUN echo 'source /opt/ros/humble/setup.bash' >> /root/.bashrc && \
    echo 'source /root/ros2_ws/install/setup.bash' >> /root/.bashrc && \
    echo 'echo "tb4-uav 容器就绪 | fcu_url 默认 ttyTHS0，可覆盖"' >> /root/.bashrc

# 默认启动 mavros + 控制器
CMD ["/bin/bash", "-c", "source /root/ros2_ws/install/setup.bash && \
    ros2 launch uav_controller uav_controller.launch.py \
    fcu_url:=serial:///dev/ttyTHS0:921600"]
