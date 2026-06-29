#!/usr/bin/env python3
"""
TI雷达集成脚本 - 配置、接收、解析一体化
功能：
1. 通过控制端口发送配置命令
2. 通过数据端口接收二进制数据流
3. 实时解析点云数据并保存到日志文件


!!!此脚本独立于ROS节点运行，适用于调试和数据采集
"""

import serial
import time
import sys
import struct
import math
import os
from pathlib import Path
from datetime import datetime


# 串口设备路径
CONTROL_PORT = '/dev/ttyACM0'      # 控制端口，用于发送CLI命令
DATA_PORT = '/dev/ttyACM1'         # 数据端口，用于接收雷达数据流
CONTROL_BAUDRATE = 115200          # 控制端口波特率（固定）
DATA_BAUDRATE = 1250000            # 数据端口初始波特率，配置后可能变更
CONFIG_FILE = 'cpd_bottomShafa_20260610_oneZone.cfg'  # 雷达配置文件

# 帧同步字，用于识别数据帧起始位置
MAGIC_WORD = (0x0102, 0x0304, 0x0506, 0x0708)
MAGIC_BYTES = struct.pack('<4H', *MAGIC_WORD)  # 打包为8字节二进制

# 各数据结构大小（字节）
HEADER_SIZE = 40      # 帧头大小
TLV_SIZE = 8          # TLV（Type-Length-Value）头大小
POINT_UNIT_SIZE = 20  # 点云单位信息大小
POINT_SIZE = 8        # 单个点云数据大小
SEGMENT_LEN = 32      # 数据帧32字节对齐

# struct 解包格式字符串（little-endian）
HEADER_FMT = '<4H5I2H2I'    # 帧头格式：4个同步字 + 5个u32 + 2个u16 + 2个u32
TLV_FMT = '<2I'             # TLV格式：类型(u32) + 长度(u32)
POINT_UNIT_FMT = '<5f'      # 点云单位：5个float（俯仰、方位、速度、距离、SNR）
POINT_FMT = '<2bh2H'        # 点云数据：俯仰(b) + 方位(b) + 速度(h) + 距离(H) + SNR(H)

# 物理量换算系数（将量化值转换为实际物理单位）
UNIT_AZIMUTH = (math.pi / 2.0) / 127.0      # 方位角：rad/quant
UNIT_ELEVATION = (math.pi / 2.0) / 127.0    # 俯仰角：rad/quant
UNIT_RANGE = 0.00025                        # 距离：m/quant
UNIT_DOPPLER = 0.00028                      # 速度：m/s per quant
UNIT_SNR = 1.0 / 256.0                      # SNR：linear/quant (dB in Q8)


class Parser:
    """6844 流式解析器 - 支持同步字搜索和不完整帧缓冲"""

    def __init__(self):
        self.buf = bytearray()      # 接收缓冲区，用于处理不完整帧
        self.frame_cnt = 0          # 成功解析的帧计数
        self.err_cnt = 0            # 错误帧计数

    def feed(self, data: bytes):
        """
        喂入原始字节流，返回解析到的完整帧列表
        流式解析：处理不完整帧、搜索同步字、验证帧完整性
        """
        self.buf.extend(data)       # 将新数据追加到缓冲区
        frames = []                 # 存储解析出的完整帧
        
        # 循环处理缓冲区中的数据，直到无法继续解析
        while len(self.buf) >= HEADER_SIZE:
            # 搜索同步字（帧起始标记）
            idx = self.buf.find(MAGIC_BYTES)
            if idx < 0:
                # 未找到同步字，保留最后7字节（可能包含部分同步字）
                self.buf = self.buf[-7:] if len(self.buf) > 7 else self.buf
                break
            
            # 丢弃同步字前的无效数据
            if idx > 0:
                self.buf = self.buf[idx:]
            
            # 检查是否有足够的数据读取帧头
            if len(self.buf) < HEADER_SIZE:
                break

            # 解析帧头
            hdr = struct.unpack(HEADER_FMT, bytes(self.buf[:HEADER_SIZE]))
            
            # 验证同步字是否正确
            if tuple(hdr[0:4]) != MAGIC_WORD:
                self.buf = self.buf[2:]  # 跳过2字节继续搜索
                self.err_cnt += 1
                continue

            # 获取帧总长度（已32字节对齐）
            total_len = hdr[5]
            
            # 验证帧长度是否合理
            if total_len < HEADER_SIZE + TLV_SIZE + POINT_UNIT_SIZE:
                self.buf = self.buf[2:]
                self.err_cnt += 1
                continue
            
            # 检查缓冲区是否有完整的帧数据
            if len(self.buf) < total_len:
                break  # 不完整帧，等待更多数据

            # 提取完整帧数据
            raw = bytes(self.buf[:total_len])
            self.buf = self.buf[total_len:]  # 从缓冲区移除已处理的数据

            # 解析帧内容
            num_points = hdr[9]  # 点云数量
            payload = raw[HEADER_SIZE:total_len]  # 帧载荷数据
            off = 0  # 偏移量

            # 解析TLV头（Type-Length-Value）
            tlv_type, tlv_len = struct.unpack_from(TLV_FMT, payload, off)
            off += TLV_SIZE
            
            # 解析点云单位信息（换算系数）
            eu, au, du, ru, su = struct.unpack_from(POINT_UNIT_FMT, payload, off)
            off += POINT_UNIT_SIZE

            # 解析点云数组
            points = []
            n = min(num_points, (len(payload) - off) // POINT_SIZE)
            for _ in range(n):
                # 解析单个点云数据
                el, az, dp, rg, sn = struct.unpack_from(POINT_FMT, payload, off)
                off += POINT_SIZE
                
                # 转换为物理单位并保存原始量化值
                points.append((
                    el * UNIT_ELEVATION, az * UNIT_AZIMUTH,
                    dp * UNIT_DOPPLER, rg * UNIT_RANGE, sn * UNIT_SNR,
                    el, az, dp, rg, sn))  # 后5项为原始量化值

            self.frame_cnt += 1
            frames.append({
                'hdr': hdr, 'tlv': (tlv_type, tlv_len),
                'unit': (eu, au, du, ru, su), 'pts': points,
                'raw': raw})  # 保存原始完整报文
        
        return frames


class TIRadarIntegrated:
    """TI雷达集成类 - 配置、接收、解析一体化"""

    def __init__(self):
        self.control_port = None            # 控制端口串口对象
        self.data_port = None               # 数据端口串口对象
        self.data_baudrate = DATA_BAUDRATE  # 当前数据端口波特率
        self.parser = Parser()              # 数据解析器实例

    def connect(self):
        """
        连接串口
        - 打开控制端口,用于发送CLI命令
        - 打开数据端口,用于接收雷达数据
        - 清空缓冲区
        """
        try:
            # 打开控制端口
            print(f"连接控制端口: {CONTROL_PORT}")
            self.control_port = serial.Serial(
                CONTROL_PORT,
                CONTROL_BAUDRATE,
                timeout=10
            )
            self.control_port.write_timeout = 5
            print(f"---控制端口已连接 @ {CONTROL_BAUDRATE} baud")

            # 打开数据端口
            print(f"连接数据端口: {DATA_PORT}")
            self.data_port = serial.Serial(
                DATA_PORT,
                self.data_baudrate,
                timeout=10
            )
            self.data_port.write_timeout = 5
            print(f"---数据端口已连接 @ {self.data_baudrate} baud")

            # 清空缓冲区，避免残留数据干扰
            self.control_port.reset_input_buffer()
            self.control_port.reset_output_buffer()
            self.data_port.reset_input_buffer()
            self.data_port.reset_output_buffer()

            return True

        except Exception as e:
            print(f"===连接失败: {e}")
            return False

    def write_line_slow(self, command):
        """
        逐字符发送命令
        确保雷达能正确接收命令
        """
        char_delay = 0.002 if self.control_port.baudrate > 115200 else 0.0005

        # 逐字符发送，最后一个字符附加CR/LF终止符
        for i, char in enumerate(command):
            if i < len(command) - 1:
                self.control_port.write(char.encode('ascii'))
                time.sleep(char_delay)
            else:
                # 最后一个字符附加\r\n（与MATLAB writeline一致）
                self.control_port.write((char + '\r\n').encode('ascii'))

    def send_command(self, command):
        """
        发送CLI命令并等待响应
        - 跳过空行和注释行
        - 最多重试3次读取响应
        - 检查响应内容
        """
        command = command.strip()

        # 跳过空行和注释（%开头）
        if not command or command.startswith('%'):
            return True

        print(f"发送: {command}")
        self.write_line_slow(command)

        # 等待设备响应（最多尝试3次）
        for attempt in range(3):
            try:
                response = self.control_port.readline().decode('ascii').strip()
                if response:
                    print(f"响应: {response}")

                    # 检查响应内容
                    if 'Done' in response:
                        return True
                    elif 'Error' in response:
                        print(f"--Error in response--命令执行失败")
                        return False
                    elif 'not recognized' in response:
                        print(f"--命令未识别")
                        return False
                    elif 'Debug:' in response:
                        # Debug信息，继续等待Done
                        continue

            except Exception as e:
                print(f"读取响应异常 (尝试 {attempt+1}/3): {e}")
                continue

        # 如果没有明确的Done/Error，认为成功
        return True

    def change_baudrate(self, new_baudrate):
        """
        更改数据端口波特率
        - 关闭数据端口
        - 以新波特率重新打开
        """
        print(f"更改数据端口波特率: {self.data_baudrate} -> {new_baudrate}")

        # 关闭数据端口
        self.data_port.close()
        time.sleep(0.5)  # 等待端口完全关闭

        # 以新波特率重新打开数据端口
        self.data_baudrate = new_baudrate
        self.data_port = serial.Serial(
            DATA_PORT,
            self.data_baudrate,
            timeout=10
        )
        self.data_port.write_timeout = 5

        print(f"---数据端口波特率已更新: {self.data_baudrate} baud")

    def send_config(self):
        """
        发送配置文件
        - 逐行发送配置命令
        - 处理波特率变更命令
        - 最后发送sensorStart启动雷达
        """
        config_path = Path(CONFIG_FILE)
        if not config_path.exists():
            print(f"---配置文件不存在: {CONFIG_FILE}")
            return False

        print(f"\n发送配置文件: {CONFIG_FILE}")
        print("=" * 60)

        with open(config_path, 'r') as f:
            lines = f.readlines()

        sensor_start_cmd = None  # 保存 sensorStart 启动雷达命令，最后发送

        for line in lines:
            command = line.strip()

            # 跳过空行和注释
            if not command or command.startswith('%'):
                continue

            # 保存sensorStart命令
            if command.startswith('sensorStart'):
                sensor_start_cmd = command
                print(f"保存: {sensor_start_cmd}")
                continue

            # 发送命令
            if not self.send_command(command):
                return False

            # 处理波特率变更命令
            if command.startswith('baudRate'):
                parts = command.split()
                if len(parts) >= 2:
                    self.change_baudrate(int(parts[1]))

            time.sleep(0.05)  # 命令间隔

        print("=" * 60)
        print("配置文件发送完成")

        # 发送sensorStart启动雷达
        if sensor_start_cmd:
            print(f"\n启动传感器: {sensor_start_cmd}")
            self.write_line_slow(sensor_start_cmd)
            print(" ----雷达传感器已启动")

        return True

    def receive_and_parse(self, output_dir='radar_data'):
        """
        接收并解析雷达数据
        - 持续从数据端口读取二进制数据
        - 实时解析点云数据
        - 将解析结果写入日志文件
        - 显示统计信息（帧数、点数、数据量、速率）
        """
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = output_path / f'radar_parse_{timestamp}.log'

        print(f"\n开始接收并解析数据...")
        print(f"日志文件: {log_file}")
        print("按 Ctrl+C 停止\n")

        total_bytes = 0      # 总接收字节数
        total_points = 0     # 总点云数量
        start_time = time.time()

        try:
            with open(log_file, 'w') as f:
                f.write(f"# TI雷达数据解析日志\n")
                f.write(f"# 开始时间: {timestamp}\n\n")

                while True:
                    # 检查数据端口是否有数据
                    if self.data_port.in_waiting > 0:
                        # 读取所有可用数据
                        data = self.data_port.read(self.data_port.in_waiting)

                        if data:
                            total_bytes += len(data)

                            # 解析数据
                            frames = self.parser.feed(data)

                            # 写入解析结果
                            for frame in frames:
                                self.write_frame(f, frame)
                                total_points += frame['hdr'][9]

                            # 每10帧显示一次统计信息
                            if self.parser.frame_cnt % 10 == 0:
                                elapsed = time.time() - start_time
                                rate = total_bytes / elapsed if elapsed > 0 else 0
                                print(f"帧: {self.parser.frame_cnt}, "
                                      f"total_points: {total_points}, "
                                      f"total_MB: {total_bytes/1024/1024:.2f} MB, "
                                      f"速率: {rate/1024:.2f} KB/s")

                    # 短暂休眠避免CPU占用过高
                    time.sleep(0.001)

        except KeyboardInterrupt:
            # 用户中断，显示统计信息
            print(f"\n\n接收已停止")
            elapsed = time.time() - start_time
            print(f"总计帧数: {self.parser.frame_cnt}")
            print(f"总计点数: {total_points}")
            print(f"数据量: {total_bytes} 字节 ({total_bytes/1024/1024:.2f} MB)")
            print(f"接收时长: {elapsed:.2f} 秒")
            print(f"平均速率: {total_bytes/elapsed/1024:.2f} KB/s")
            print(f"错误帧数: {self.parser.err_cnt}")
            print(f"日志已保存到: {log_file}")

    def write_frame(self, f, frame):
        """
        将单帧解析结果写入日志文件
        - 写入帧头信息（帧号、点数、时间戳）
        - 写入点云单位信息
        - 写入每个点云的物理量（俯仰角、方位角、速度、距离、SNR）
        """
        h = frame['hdr']
        raw = frame['raw']

        # 写入帧头信息
        f.write(f"\n--- Frame #{self.parser.frame_cnt} (frameNumber={h[7]}) points={h[9]} ---\n")
        f.write(f"  magic={[f'0x{w:04X}' for w in h[0:4]]} totalLen={h[5]}\n")
        f.write(f"  time={h[8]}\n")

        # 写入点云单位信息
        u = frame['unit']
        f.write(f"  unit: elev={u[0]:.10f} azim={u[1]:.10f} dopp={u[2]:.10f} range={u[3]:.10f} snr={u[4]:.10f}\n")

        # 写入每个点云数据
        for i, p in enumerate(frame['pts']):
            f.write(f"  pt[{i:3d}] elev={p[0]: .6f} azim={p[1]: .6f} "
                   f"dopp={p[2]: .4f} range={p[3]: .4f} snr={p[4]: .4f}\n")

        f.flush()  # 立即写入文件

    def disconnect(self):
        """断开串口连接"""
        if self.control_port and self.control_port.is_open:
            self.control_port.close()
            print("控制端口已断开")

        if self.data_port and self.data_port.is_open:
            self.data_port.close()
            print("数据端口已断开")


def main():
    """
    主函数 - 执行流程：
    1. 连接串口（控制端口和数据端口）
    2. 发送配置文件并启动雷达
    3. 接收并解析雷达数据
    4. 处理用户中断和异常
    5. 断开连接
    """
    print("=" * 60)
    print("TI雷达集成工具 - 配置+接收+解析")
    print("=" * 60)

    radar = TIRadarIntegrated()

    # 连接串口
    if not radar.connect():
        print("连接失败，退出")
        sys.exit(1)

    try:
        # 发送配置文件
        if radar.send_config():
            print("\n---雷达配置成功")
            # 开始接收并解析数据
            radar.receive_and_parse()
        else:
            print("\n---配置失败")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n---用户中断，退出...")
    except Exception as e:
        print(f"\n---发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 确保断开连接
        radar.disconnect()


if __name__ == '__main__':
    main()