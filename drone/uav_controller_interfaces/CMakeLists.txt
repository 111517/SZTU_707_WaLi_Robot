cmake_minimum_required(VERSION 3.8)
project(uav_controller_interfaces)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/UavCommand.msg"
)

ament_package()
