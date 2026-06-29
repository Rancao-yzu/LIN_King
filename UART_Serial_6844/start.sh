#!/bin/bash
# 启动TI雷达ROS节点

# 设置串口权限
sudo chmod 666 /dev/ttyACM0
sudo chmod 666 /dev/ttyACM1

cd /home/zjh/桌面/UART_Serial_6844
source devel/setup.bash
roslaunch ti_radar_ros ti_radar.launch