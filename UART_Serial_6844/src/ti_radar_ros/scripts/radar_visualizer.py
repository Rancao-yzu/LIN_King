#!/usr/bin/env python3
"""
TI雷达可视化节点
订阅雷达数据话题，转换为PointCloud2并在rviz中显示
"""

import rospy
import math
from sensor_msgs.msg import PointCloud2, PointField
from std_msgs.msg import Header
from arbe_msgs.msg import sofaOutput


class RadarVisualizer:
    """雷达可视化节点"""
    
    def __init__(self):
        # 获取参数
        self.input_topic = rospy.get_param('~input_topic', '/wf/radar/sofa_0')
        self.output_topic = rospy.get_param('~output_topic', '/radar/pointcloud')
        self.frame_id = rospy.get_param('~frame_id', 'radar')
        
        # 订阅者
        self.sub = rospy.Subscriber(self.input_topic, sofaOutput, self.callback)
        
        # 发布者
        self.pub = rospy.Publisher(self.output_topic, PointCloud2, queue_size=10)
        
        rospy.loginfo(f"雷达可视化节点已启动")
        rospy.loginfo(f"订阅: {self.input_topic}")
        rospy.loginfo(f"发布: {self.output_topic}")

    def callback(self, msg):
        """接收sofaOutput消息并转换为PointCloud2"""
        # 创建PointCloud2消息
        cloud_msg = PointCloud2()
        cloud_msg.header = msg.header
        cloud_msg.header.frame_id = self.frame_id
        
        # 定义点云字段
        # x, y, z, intensity (SNR), doppler
        cloud_msg.fields = [
            PointField(name='x', offset=0, datatype=PointField.FLOAT32, count=1),
            PointField(name='y', offset=4, datatype=PointField.FLOAT32, count=1),
            PointField(name='z', offset=8, datatype=PointField.FLOAT32, count=1),
            PointField(name='intensity', offset=12, datatype=PointField.FLOAT32, count=1),
            PointField(name='doppler', offset=16, datatype=PointField.FLOAT32, count=1),
        ]
        
        cloud_msg.height = 1
        cloud_msg.width = len(msg.floatData)
        cloud_msg.point_step = 20  # 5个float32 = 20字节
        cloud_msg.row_step = cloud_msg.point_step * cloud_msg.width
        cloud_msg.is_dense = True
        
        # 转换点云数据
        data = []
        for point in msg.floatData:
            # 将极坐标转换为笛卡尔坐标
            # elevation: 俯仰角, azimuth: 方位角, range: 距离
            r = point.range
            elev = point.elevation
            azim = point.azimuth
            
            # 计算x, y, z
            # x: 前向, y: 左向, z: 上向
            x = r * math.cos(elev) * math.cos(azim)
            y = r * math.cos(elev) * math.sin(azim)
            z = r * math.sin(elev)
            
            # 打包数据: x, y, z, intensity, doppler
            import struct
            data.extend(struct.pack('fffff', x, y, z, point.snr, point.doppler))
        
        cloud_msg.data = bytes(data)
        
        # 发布点云
        self.pub.publish(cloud_msg)


def main():
    rospy.init_node('radar_visualizer', anonymous=True)
    
    visualizer = RadarVisualizer()
    
    rospy.spin()


if __name__ == '__main__':
    main()