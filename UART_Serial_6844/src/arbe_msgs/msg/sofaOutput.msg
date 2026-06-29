# SOFA雷达输出消息
std_msgs/Header header

uint32 frameID         # 帧ID
uint32 SGUNum          # SGU数量
uint8[] padding        # 填充数据

wffloatData[] floatData  # 点云数据数组