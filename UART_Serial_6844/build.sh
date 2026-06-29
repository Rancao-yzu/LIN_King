#!/bin/bash
# 编译ROS工作空间

cd /home/zjh/桌面/UART_Serial_6844
catkin_make
source devel/setup.bash

echo "编译完成！"