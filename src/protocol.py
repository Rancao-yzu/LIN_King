# -*- coding: utf-8 -*-
"""LIN 通讯协议常量 (沙发项目 LIN_sofa_V1.2)"""

# ============================================================
# 帧 ID 定义
# ============================================================
PID_MOTOR_CTRL   = 0x01  # 电机控制帧 (上位机 → 电机)
PID_MOTOR_STATUS = 0x02  # 电机状态帧 (上位机 ↔ 电机)

# ============================================================
# DATA[0] 位域定义 (控制帧)
# bit0-1: 电机自学习状态
# bit2-3: 电机运动状态  
# bit4-5: 障碍物标志
# ============================================================

# bit0-1 — 电机自学习状态
LEARN_DEFAULT = 0x00  # 默认值
LEARN_DO      = 0x01  # 电机进行自学习
LEARN_NO      = 0x02  # 电机不进行自学习

# bit2-3 — 电机运动状态
MOTION_DEFAULT  = 0x00  # 默认值
MOTION_EXTEND   = 0x01  # 电机转动伸出
MOTION_RETRACT  = 0x02  # 电机转动收回
MOTION_STOP     = 0x03  # 电机停止转动

# bit4-5 — 障碍物标志
OBSTACLE_DEFAULT = 0x00  # 默认值 (算法未就绪 / 雷达故障)
OBSTACLE_NONE    = 0x01  # 无障碍物
OBSTACLE_EXISTS  = 0x02  # 有障碍物

# ============================================================
# 响应帧常量
# ============================================================
LEARN_NOT_DONE = 0x00  # 自学习未完成
LEARN_DONE     = 0x01  # 自学习已完成

RADAR_FAULT_NONE    = 0x00  # 雷达无故障
RADAR_FAULT_BLOCKED = 0x01  # 雷达遮挡故障

# ============================================================
# 发送参数
# ============================================================
SEND_REPEAT      = 5    # 防丢重发次数
SEND_INTERVAL_MS = 100  # 发送间隔 (ms)

# ============================================================
# 工具函数
# ============================================================

def format_hex(data, length=8):
    """将字节列表格式化为十六进制字符串, 如 '01 00 00 ...'
    空列表 (仅头部帧) 返回 '(仅头部)'"""
    if not data:
        return '(仅头部)'
    return ' '.join(f'{b:02X}' for b in data[:length])


# ============================================================
# 帧描述 (供日志 [] 使用)
# ============================================================

# 电机动作文本
_MOTION_TEXT = {0x00: None, 0x01: "伸出", 0x02: "回收", 0x03: "停止"}
# 自学习文本
_LEARN_TEXT  = {0x00: None, 0x01: "自学习", 0x02: "不自学习"}
# 障碍物文本
_OBS_TEXT    = {0x00: None, 0x01: "无障碍物", 0x02: "有障碍物"}


def describe_frame(frame_id, data):
    """解析帧数据, 返回 [] 内的描述文本"""
    if frame_id == PID_MOTOR_CTRL and data:
        d0 = data[0]
        motion = (d0 >> 2) & 0x03
        learn  = d0 & 0x03
        obs    = (d0 >> 4) & 0x03
        parts = [v for v in (_MOTION_TEXT.get(motion),
                             _LEARN_TEXT.get(learn),
                             _OBS_TEXT.get(obs)) if v]
        return "，".join(parts) if parts else "空闲"

    if frame_id == PID_MOTOR_STATUS and len(data) >= 6:
        learn_flag = "✓自学习" if data[0] == 0x01 else "✗未学习"
        pos = data[1] | (data[2] << 8)
        stroke = data[3] | (data[4] << 8)
        fault = data[5]
        fault_str = f"故障0x{fault:02X}" if fault else "无故障"
        return f"{learn_flag} 位置{pos} 行程{stroke} {fault_str}"

    return FRAME_NAME.get(frame_id, f"0x{frame_id:02X}")


# ============================================================
# 描述映射 (供 UI 使用)
# ============================================================

FRAME_NAME = {
    PID_MOTOR_CTRL:   "电机控制",
    PID_MOTOR_STATUS: "电机状态",
}

LEARN_STATUS_TEXT = {LEARN_NOT_DONE: "未完成", LEARN_DONE: "已完成"}