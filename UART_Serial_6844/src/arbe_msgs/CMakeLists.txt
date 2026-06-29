cmake_minimum_required(VERSION 3.0.2)
project(arbe_msgs)

find_package(catkin REQUIRED COMPONENTS
  message_generation
  std_msgs
)

# 添加消息文件
add_message_files(
  FILES
  wffloatData.msg
  sofaOutput.msg
)

# 生成消息
generate_messages(
  DEPENDENCIES
  std_msgs
)

catkin_package(
  CATKIN_DEPENDS message_runtime std_msgs
)