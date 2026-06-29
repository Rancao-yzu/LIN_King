#!/usr/bin/env python3
"""
TI雷达ROS发布节点
从串口读取雷达数据，解析后发布到ROS话题
"""

import rospy
import serial
import struct
import math
from arbe_msgs.msg import sofaOutput, wffloatData


# 帧同步字
MAGIC_WORD = (0x0102, 0x0304, 0x0506, 0x0708)
MAGIC_BYTES = struct.pack('<4H', *MAGIC_WORD)

# 数据结构大小
HEADER_SIZE = 40
TLV_SIZE = 8
POINT_UNIT_SIZE = 20
POINT_SIZE = 8

# 解包格式
HEADER_FMT = '<4H5I2H2I'
TLV_FMT = '<2I'
POINT_UNIT_FMT = '<5f'
POINT_FMT = '<2bh2H'

# 物理量换算系数
UNIT_AZIMUTH = (math.pi / 2.0) / 127.0
UNIT_ELEVATION = (math.pi / 2.0) / 127.0
UNIT_RANGE = 0.00025
UNIT_DOPPLER = 0.00028
UNIT_SNR = 1.0 / 256.0


class Parser:
    """6844流式解析器"""
    
    def __init__(self):
        self.buf = bytearray()
        self.frame_cnt = 0
        self.err_cnt = 0

    def feed(self, data):
        """喂入原始字节流，返回解析到的完整帧列表"""
        self.buf.extend(data)
        frames = []
        
        while len(self.buf) >= HEADER_SIZE:
            idx = self.buf.find(MAGIC_BYTES)
            if idx < 0:
                self.buf = self.buf[-7:] if len(self.buf) > 7 else self.buf
                break
            
            if idx > 0:
                self.buf = self.buf[idx:]
            
            if len(self.buf) < HEADER_SIZE:
                break

            hdr = struct.unpack(HEADER_FMT, bytes(self.buf[:HEADER_SIZE]))
            
            if tuple(hdr[0:4]) != MAGIC_WORD:
                self.buf = self.buf[2:]
                self.err_cnt += 1
                continue

            total_len = hdr[5]
            
            if total_len < HEADER_SIZE + TLV_SIZE + POINT_UNIT_SIZE:
                self.buf = self.buf[2:]
                self.err_cnt += 1
                continue
            
            if len(self.buf) < total_len:
                break

            raw = bytes(self.buf[:total_len])
            self.buf = self.buf[total_len:]

            num_points = hdr[9]
            payload = raw[HEADER_SIZE:total_len]
            off = 0

            tlv_type, tlv_len = struct.unpack_from(TLV_FMT, payload, off)
            off += TLV_SIZE
            
            eu, au, du, ru, su = struct.unpack_from(POINT_UNIT_FMT, payload, off)
            off += POINT_UNIT_SIZE

            points = []
            n = min(num_points, (len(payload) - off) // POINT_SIZE)
            for _ in range(n):
                el, az, dp, rg, sn = struct.unpack_from(POINT_FMT, payload, off)
                off += POINT_SIZE
                
                points.append((
                    el * UNIT_ELEVATION, az * UNIT_AZIMUTH,
                    dp * UNIT_DOPPLER, rg * UNIT_RANGE, sn * UNIT_SNR))

            self.frame_cnt += 1
            frames.append({
                'hdr': hdr,
                'pts': points,
                'frame_id': hdr[7],
                'timestamp': hdr[8]})
        
        return frames


class TIRadarPublisher:
    """TI雷达ROS发布节点"""
    
    def __init__(self):
        # 获取ROS参数
        self.control_port_name = rospy.get_param('~control_port', '/dev/ttyACM0')
        self.data_port_name = rospy.get_param('~data_port', '/dev/ttyACM1')
        self.control_baudrate = rospy.get_param('~control_baudrate', 115200)
        self.data_baudrate = rospy.get_param('~data_baudrate', 1250000)
        self.config_file = rospy.get_param('~config_file', 'cpd_bottomShafa_20260610_oneZone.cfg')
        self.frame_id = rospy.get_param('~frame_id', 'radar')
        
        # 初始化串口
        self.control_port = None
        self.data_port = None
        self.parser = Parser()
        
        # ROS发布者
        self.pub = rospy.Publisher('/wf/radar/sofa_0', sofaOutput, queue_size=10)
        
        # 连接串口
        if not self.connect():
            rospy.signal_shutdown("串口连接失败")
            return
        
        # 发送配置
        if not self.send_config():
            rospy.signal_shutdown("雷达配置失败")
            return
        
        rospy.loginfo("TI雷达节点已启动，开始发布数据到 /wf/radar/sofa_0")

    def connect(self):
        """连接串口"""
        try:
            rospy.loginfo(f"连接控制端口: {self.control_port_name}")
            self.control_port = serial.Serial(
                self.control_port_name,
                self.control_baudrate,
                timeout=10
            )
            self.control_port.write_timeout = 5
            
            rospy.loginfo(f"连接数据端口: {self.data_port_name}")
            self.data_port = serial.Serial(
                self.data_port_name,
                self.data_baudrate,
                timeout=10
            )
            self.data_port.write_timeout = 5
            
            self.control_port.reset_input_buffer()
            self.control_port.reset_output_buffer()
            self.data_port.reset_input_buffer()
            self.data_port.reset_output_buffer()
            
            return True
        except Exception as e:
            rospy.logerr(f"串口连接失败: {e}")
            return False

    def write_line_slow(self, command):
        """逐字符发送命令"""
        char_delay = 0.002 if self.control_port.baudrate > 115200 else 0.0005
        
        for i, char in enumerate(command):
            if i < len(command) - 1:
                self.control_port.write(char.encode('ascii'))
                rospy.sleep(char_delay)
            else:
                self.control_port.write((char + '\r\n').encode('ascii'))

    def send_command(self, command):
        """发送CLI命令并等待响应"""
        command = command.strip()
        
        if not command or command.startswith('%'):
            return True
        
        rospy.loginfo(f"发送: {command}")
        self.write_line_slow(command)
        
        for attempt in range(3):
            try:
                response = self.control_port.readline().decode('ascii').strip()
                if response:
                    rospy.loginfo(f"响应: {response}")
                    
                    if 'Done' in response:
                        return True
                    elif 'Error' in response:
                        rospy.logerr("命令执行失败")
                        return False
                    elif 'not recognized' in response:
                        rospy.logerr("命令未识别")
                        return False
                    elif 'Debug:' in response:
                        continue
            except Exception as e:
                rospy.logwarn(f"读取响应异常: {e}")
                continue
        
        return True

    def change_baudrate(self, new_baudrate):
        """更改数据端口波特率"""
        rospy.loginfo(f"更改数据端口波特率: {self.data_baudrate} -> {new_baudrate}")
        
        self.data_port.close()
        rospy.sleep(0.5)
        
        self.data_baudrate = new_baudrate
        self.data_port = serial.Serial(
            self.data_port_name,
            self.data_baudrate,
            timeout=10
        )
        self.data_port.write_timeout = 5

    def send_config(self):
        """发送配置文件"""
        import os
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', self.config_file)
        
        if not os.path.exists(config_path):
            # 尝试从工作目录查找
            config_path = self.config_file
        
        if not os.path.exists(config_path):
            rospy.logerr(f"配置文件不存在: {config_path}")
            return False
        
        rospy.loginfo(f"发送配置文件: {config_path}")
        
        with open(config_path, 'r') as f:
            lines = f.readlines()
        
        sensor_start_cmd = None
        
        for line in lines:
            command = line.strip()
            
            if not command or command.startswith('%'):
                continue
            
            if command.startswith('sensorStart'):
                sensor_start_cmd = command
                continue
            
            if not self.send_command(command):
                return False
            
            if command.startswith('baudRate'):
                parts = command.split()
                if len(parts) >= 2:
                    self.change_baudrate(int(parts[1]))
            
            rospy.sleep(0.05)
        
        if sensor_start_cmd:
            # 先sensorStop清理残留状态，再启动
            self.write_line_slow('sensorStop 0')
            rospy.sleep(1.0)
            rospy.loginfo(f"启动传感器: {sensor_start_cmd}")
            self.write_line_slow(sensor_start_cmd)
        
        return True

    def run(self):
        """主循环：读取并发布数据"""
        rate = rospy.Rate(100)  # 100Hz
        
        while not rospy.is_shutdown():
            try:
                if self.data_port.in_waiting > 0:
                    data = self.data_port.read(self.data_port.in_waiting)
                    
                    if data:
                        frames = self.parser.feed(data)
                        
                        for frame in frames:
                            self.publish_frame(frame)
                
                rate.sleep()
                
            except Exception as e:
                rospy.logerr(f"数据读取错误: {e}")
                break

    def publish_frame(self, frame):
        """发布单帧数据到ROS话题"""
        msg = sofaOutput()
        msg.header.stamp = rospy.Time.now()
        msg.header.frame_id = self.frame_id
        
        msg.frameID = frame['frame_id']
        msg.SGUNum = len(frame['pts'])
        msg.padding = []
        
        # 填充点云数据
        for pt in frame['pts']:
            point = wffloatData()
            point.elevation = pt[0]
            point.azimuth = pt[1]
            point.doppler = pt[2]
            point.range = pt[3]
            point.snr = pt[4]
            msg.floatData.append(point)
        
        self.pub.publish(msg)
        
        if self.parser.frame_cnt % 10 == 0 or self.parser.frame_cnt <= 10:
            rospy.loginfo(f"发布帧 #{self.parser.frame_cnt}, 点数: {len(frame['pts'])}")

    def shutdown(self):
        """关闭前停止传感器，把波特率切回 115200，再关闭串口"""
        if self.control_port and self.control_port.is_open:
            try:
                self.write_line_slow('sensorStop 0')
                rospy.sleep(0.2)
                # 波特率切回默认，下次启动才能正常通信
                self.write_line_slow('baudRate 115200')
                print("波特率已切回 115200")
                rospy.sleep(0.2)
            except:
                pass
            self.control_port.close()
            rospy.loginfo("控制端口已关闭")
        
        if self.data_port and self.data_port.is_open:
            self.data_port.close()
            rospy.loginfo("数据端口已关闭")


def main():
    rospy.init_node('ti_radar_publisher', anonymous=True)
    
    node = TIRadarPublisher()
    
    rospy.on_shutdown(node.shutdown)
    
    if rospy.is_shutdown():
        return
    
    node.run()


if __name__ == '__main__':
    main()