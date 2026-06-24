# -*- coding: utf-8 -*-
"""TI mmWave 6844 串口协议解析"""

import struct
import math
import os
import random
from datetime import datetime
import serial
# ============================================================
# 配置: 串口设备路径, 为空则运行 demo
SERIAL_PORT = "/dev/ttyUSB0"        # 例如 "/dev/ttyUSB0"
SERIAL_BAUD = 6250000

# ============================================================
# 协议常量
MAGIC_WORD = (0x0102, 0x0304, 0x0506, 0x0708)
MAGIC_BYTES = struct.pack('<4H', *MAGIC_WORD)  # 8字节同步字，用于帧定位

# 各结构体字节数
HEADER_SIZE      = 40   # MmwDemo_output_message_headerID_t  
TLV_SIZE         = 8    # MmwDemo_output_message_tl_t
POINT_UNIT_SIZE  = 20   # MmwDemo_output_message_point_uint_t
POINT_SIZE       = 8    # MmwDemo_output_message_UARTpoint_t
SEGMENT_LEN      = 32   # 32字节对齐

# struct 解包格式 (little-endian)
HEADER_FMT       = '<4H5I2H2I'   # magicWord[4] + 5*u32 + numDetectedObj[2] + 2*u32
TLV_FMT          = '<2I'         # type + length
POINT_UNIT_FMT   = '<5f'         # 5个float单位
POINT_FMT        = '<2bh2H'      # elev(b) + azim(b) + dopp(h) + range(H) + snr(H)

# 物理量换算系数 (来自 6844通信.md )
UNIT_AZIMUTH     = (math.pi / 2.0) / 127.0   # 方位角 rad/quant
UNIT_ELEVATION   = (math.pi / 2.0) / 127.0   # 俯仰角 rad/quant
UNIT_RANGE       = 0.00025                    # 距离 m/quant
UNIT_DOPPLER     = 0.00028                    # 速度 m/s per quant
UNIT_SNR         = 1.0 / 256.0               # SNR linear/quant (dB in Q8)


class Parser:
    """6844 流式解析器，支持同步字搜索、不完整帧缓冲"""

    def __init__(self):
        self.buf = bytearray()
        self.frame_cnt = 0
        self.err_cnt = 0

    def feed(self, data: bytes):
        """喂入原始字节流，返回解析到的完整帧列表"""
        self.buf.extend(data)
        frames = []
        while len(self.buf) >= HEADER_SIZE:
            # 搜索同步字 0x0102 0x0304 0x0506 0x0708
            idx = self.buf.find(MAGIC_BYTES)
            if idx < 0:
                self.buf = self.buf[-7:] if len(self.buf) > 7 else self.buf
                break
            if idx > 0:
                self.buf = self.buf[idx:]  # 丢弃同步字前的无效数据
            if len(self.buf) < HEADER_SIZE:
                break

            hdr = struct.unpack(HEADER_FMT, bytes(self.buf[:HEADER_SIZE]))
            if tuple(hdr[0:4]) != MAGIC_WORD:
                self.buf = self.buf[2:]; self.err_cnt += 1; continue

            total_len = hdr[5]  # totalPacketLen，已32字节对齐
            if total_len < HEADER_SIZE + TLV_SIZE + POINT_UNIT_SIZE:
                self.buf = self.buf[2:]; self.err_cnt += 1; continue
            if len(self.buf) < total_len:
                break  # 不完整帧，等更多数据

            raw = bytes(self.buf[:total_len])
            self.buf = self.buf[total_len:]

            num_points = hdr[9]  # numDetectedObj[0]
            payload = raw[HEADER_SIZE:total_len]
            off = 0

            # TLV: type + length
            tlv_type, tlv_len = struct.unpack_from(TLV_FMT, payload, off); off += TLV_SIZE
            # PointUnit: 5个float
            eu, au, du, ru, su = struct.unpack_from(POINT_UNIT_FMT, payload, off); off += POINT_UNIT_SIZE

            # 点云数组，每个点8字节，换算为物理单位
            points = []
            n = min(num_points, (len(payload) - off) // POINT_SIZE)
            for _ in range(n):
                el, az, dp, rg, sn = struct.unpack_from(POINT_FMT, payload, off); off += POINT_SIZE
                points.append((
                    el * UNIT_ELEVATION, az * UNIT_AZIMUTH,
                    dp * UNIT_DOPPLER, rg * UNIT_RANGE, sn * UNIT_SNR,
                    el, az, dp, rg, sn))  # 末尾5项为原始量化值

            self.frame_cnt += 1
            frames.append({
                'hdr': hdr, 'tlv': (tlv_type, tlv_len),
                'unit': (eu, au, du, ru, su), 'pts': points})
        return frames



def write_frame(f, frame, idx):
    """将单帧解析结果写入日志文件"""
    h = frame['hdr']
    # header 各字段: 
    f.write(f"\n\n--- Frame #{idx} (frameNumber={h[7]}) points={h[9]} ---\n")
    f.write(f"  magic={[f'0x{w:04X}' for w in h[0:4]]} ver=0x{h[4]:08X} totalLen={h[5]} plat=0x{h[6]:05X}\n")
    f.write(f"  time={h[8]} numTLVs={h[11]} subFrame={h[12]}\n")
    u = frame['unit']
    f.write(f"  unit: elev={u[0]:.10f} azim={u[1]:.10f} dopp={u[2]:.10f} range={u[3]:.10f} snr={u[4]:.10f}\n")
    # 点云: (elev_rad, azim_rad, dopp_m/s, range_m, snr_linear, elev_raw, azim_raw, dopp_raw, range_raw, snr_raw)
    for i, p in enumerate(frame['pts']):
        f.write(f"  pt[{i:3d}] elev={p[0]: .6f} azim={p[1]: .6f} dopp={p[2]: .4f} range={p[3]: .4f} snr={p[4]: .4f}\n")


def gen_test_data(n_frames=5, max_pts=10):
    """生成符合6844协议的模拟二进制数据，用于无硬件时测试"""
    random.seed(42)
    data = bytearray()
    for fi in range(n_frames):
        np = random.randint(1, max_pts)
        # 计算包长，按32字节向上取整
        pl = TLV_SIZE + POINT_UNIT_SIZE + POINT_SIZE * np
        raw_len = HEADER_SIZE + pl
        pkt_len = SEGMENT_LEN * ((raw_len + SEGMENT_LEN - 1) // SEGMENT_LEN)
        data.extend(struct.pack(HEADER_FMT,
            *MAGIC_WORD, 0x01020304, pkt_len, 0xA6432, fi, fi * 1000000, np, 0, 1, 0))
        data.extend(struct.pack(TLV_FMT, 6, pl))
        data.extend(struct.pack(POINT_UNIT_FMT, UNIT_ELEVATION, UNIT_AZIMUTH, UNIT_DOPPLER, UNIT_RANGE, UNIT_SNR))
        for _ in range(np):
            data.extend(struct.pack(POINT_FMT,
                random.randint(-127, 127), random.randint(-127, 127),
                random.randint(-32768, 32767), random.randint(0, 65535), random.randint(0, 65535)))
        data.extend(b'\x00' * (pkt_len - raw_len))
    return bytes(data)


def main():
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
    os.makedirs(out_dir, exist_ok=True)
    log_path = os.path.join(out_dir, f'serial_{ts}.log')

    if SERIAL_PORT:
        ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=1.0)
        p = Parser()
        log = open(log_path, 'w')
        log.write(f"# 6844 parse log\n")
        total_pts = 0
        print(f"serial {SERIAL_PORT} @ {SERIAL_BAUD}, Ctrl+C stop")
        try:
            while True:
                chunk = ser.read(4096)
                if chunk:
                    for f in p.feed(chunk):
                        write_frame(log, f, p.frame_cnt)
                        total_pts += f['hdr'][9]
                        log.flush()
        except KeyboardInterrupt:
            pass
        finally:
            ser.close()
        log.write(f"\n# done: {p.frame_cnt} frames {total_pts} pts {p.err_cnt} err\n")
        log.close()
        print(f"done: {p.frame_cnt} frames {total_pts} pts => {log_path}")
    else:
        print("SERIAL_PORT empty, run demo")
        data = gen_test_data(5, 10)
        print(f"test data: {len(data)} bytes")
        p = Parser()
        log = open(log_path, 'w')
        log.write(f"# 6844 parse log\n")
        total_pts = 0
        for i in range(0, len(data), 128):
            for f in p.feed(data[i:i+128]):
                write_frame(log, f, p.frame_cnt)
                total_pts += f['hdr'][9]
        log.write(f"\n# done: {p.frame_cnt} frames {total_pts} pts {p.err_cnt} err\n")
        log.close()
        print(f"done: {p.frame_cnt} frames {total_pts} pts => {log_path}")


if __name__ == '__main__':
    main()
