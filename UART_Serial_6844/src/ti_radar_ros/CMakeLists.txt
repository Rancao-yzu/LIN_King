cmake_minimum_required(VERSION 3.0.2)
project(ti_radar_ros)

find_package(catkin REQUIRED COMPONENTS
  rospy
  std_msgs
  sensor_msgs
  arbe_msgs
)

catkin_package(
  CATKIN_DEPENDS rospy std_msgs sensor_msgs arbe_msgs
)

# 安装Python脚本
catkin_install_python(PROGRAMS
  scripts/ti_radar_publisher.py
  scripts/radar_visualizer.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

# 安装launch文件
install(DIRECTORY launch/
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}/launch
)

# 安装配置文件
install(DIRECTORY config/
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}/config
)