#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lin_lib.py — USBCANFD LIN 通道 Python 绑定
============================================

基于 libusbcanfd.so 动态库, 通过 ctypes 封装 C 接口。
使用时直接 import lin_lib, 调用其中的函数和结构体。

对应 C 头文件: src_example/zcan.h

提供的结构体:
  ZCANLINData          — LIN 数据帧
  ZCANLINErrData       — LIN 错误帧
  ZCAN_LIN_MSG         — LIN 消息 (含联合体)
  ZCAN_LIN_INIT_CONFIG — LIN 初始化配置
  ZCAN_LIN_PUBLISH_CFG — LIN 发布/响应配置

提供的函数 (通过 linapi 访问):
  linapi.OpenDevice(dev_type, dev_idx)
  linapi.CloseDevice(dev_type, dev_idx)
  linapi.InitLIN(dev_type, dev_idx, chn, config)
  linapi.StartLIN(dev_type, dev_idx, chn)
  linapi.ResetLIN(dev_type, dev_idx, chn)
  linapi.TransmitLIN(dev_type, dev_idx, chn, msg_array, count)
  linapi.ReceiveLIN(dev_type, dev_idx, chn, msg_array, count, wait_ms)
  linapi.SetLINPublish(dev_type, dev_idx, chn, cfg_array, count)

常量:
  USBCANFD = 33         # 设备类型号
  LIN_MODE_SLAVE  = 0   # 从机模式
  LIN_MODE_MASTER = 1   # 主机模式
  CHKSUM_DEFAULT  = 0   # 默认校验
  CHKSUM_CLASSIC  = 1   # 经典校验
  CHKSUM_ENHANCE  = 2   # 增强校验
  CHKSUM_AUTO     = 3   # 自动
  LIN_DATA_FRAME  = 0   # LIN 数据帧
  LIN_ERROR_FRAME = 1   # LIN 错误帧

示例:
    import lin_lib

    linapi = lin_lib.LinApi()
    linapi.OpenDevice(lin_lib.USBCANFD, 0)
    ...
    linapi.CloseDevice(lin_lib.USBCANFD, 0)
"""

import ctypes
from ctypes import *

# ============================================================
# 常量
# ============================================================

USBCANFD = 33    # 设备类型号: 33 = USBCANFD 系列 (100U/200U/400U)

# --- LIN 模式 ---
LIN_MODE_SLAVE  = 0   # 从机
LIN_MODE_MASTER = 1   # 主机

# --- 校验方式 ---
CHKSUM_DEFAULT = 0    # 默认, 跟随启动配置
CHKSUM_CLASSIC = 1    # 经典校验 (LIN 1.x)
CHKSUM_ENHANCE = 2    # 增强校验 (LIN 2.x)
CHKSUM_AUTO    = 3    # 自动 (仅 ZCAN_SetLINSubscribe)

# --- 帧类型 ---
LIN_DATA_FRAME  = 0   # LIN 数据帧 (dataType)
LIN_ERROR_FRAME = 1   # LIN 错误帧

# --- SN 号命令码 (VCI_SetReference / VCI_GetReference) ---
CMD_SET_SN = 0x42     # 写入 SN 号
CMD_GET_SN = 0x43     # 读取 SN 号

# ============================================================
# 数据结构 — 必须与 zcan.h #pragma pack(push, 1) 区域完全一致
# ============================================================

# --- ZCANLINData: LIN 数据帧 (tagZCANLINData) ---

class _PID_UNION_VAL(ctypes.Structure):
    """PID 位域: ID(6bit) + Parity(2bit)
    C: struct { U8 ID:6; U8 Parity:2; } unionVal;
    """
    _pack_ = 1
    _fields_ = [
        ("ID",     ctypes.c_uint8, 6),   # 帧 ID (0~63)
        ("Parity", ctypes.c_uint8, 2),   # ID 奇偶校验位
    ]

class _PID_UNION(ctypes.Union):
    """PID 联合体: 位域视图 或 原始字节
    C: union { struct { U8 ID:6; U8 Parity:2; } unionVal; U8 rawVal; } PID;
    """
    _pack_ = 1
    _fields_ = [
        ("unionVal", _PID_UNION_VAL),    # 按位域访问
        ("rawVal",   ctypes.c_uint8),    # 按原始字节访问
    ]

class _RX_DATA(ctypes.Structure):
    """接收数据段
    C: struct { U64 timeStamp; U8 dataLen; U8 dir; U8 chkSum;
                U8 reserved[13]; U8 data[8]; } RxData;
    """
    _pack_ = 1
    _fields_ = [
        ("timeStamp", ctypes.c_uint64),        # 时间戳, 单位微秒 (us)
        ("dataLen",   ctypes.c_uint8),         # 数据长度 (1~8)
        ("dir",       ctypes.c_uint8),         # 方向: 0=接收, 1=发送
        ("chkSum",    ctypes.c_uint8),         # 数据校验和
        ("reserved",  ctypes.c_uint8 * 13),    # 保留
        ("data",      ctypes.c_uint8 * 8),     # 数据字节
    ]

class ZCANLINData(ctypes.Structure):
    """LIN 数据帧结构体 (tagZCANLINData)
    总大小 = 1(PID) + 32(RxData) + 7(reserved) = 40 bytes
    """
    _pack_ = 1
    _fields_ = [
        ("PID",      _PID_UNION),              # 受保护 ID
        ("RxData",   _RX_DATA),                # 接收数据
        ("reserved", ctypes.c_uint8 * 7),      # 保留
    ]

# --- ZCANLINErrData: LIN 错误帧 (tagZCANLINErrData) ---

class _ERR_PID_UNION_VAL(ctypes.Structure):
    """错误帧 PID 位域 (与正常帧相同)"""
    _pack_ = 1
    _fields_ = [
        ("ID",     ctypes.c_uint8, 6),
        ("Parity", ctypes.c_uint8, 2),
    ]

class _ERR_PID_UNION(ctypes.Union):
    _pack_ = 1
    _fields_ = [
        ("unionVal", _ERR_PID_UNION_VAL),
        ("rawVal",   ctypes.c_uint8),
    ]

class _ERR_DATA_UNION(ctypes.Union):
    """错误详情联合体
    C: union { struct { U16 errStage:4; U16 errReason:4; U16 reserved:8; };
               U16 unionErrData; } errData;
    """
    _pack_ = 1
    _fields_ = [
        ("errStage",     ctypes.c_uint16, 4),  # 错误阶段
        ("errReason",    ctypes.c_uint16, 4),  # 错误原因
        ("reserved",     ctypes.c_uint16, 8),  # 保留
        ("unionErrData", ctypes.c_uint16),     # 联合值
    ]

class ZCANLINErrData(ctypes.Structure):
    """LIN 错误帧结构体 (tagZCANLINErrData)
    总大小 = 8 + 1 + 1 + 8 + 2 + 1 + 1 + 10 = 32 bytes
    """
    _pack_ = 1
    _fields_ = [
        ("timeStamp", ctypes.c_uint64),        # 时间戳 (us)
        ("PID",       _ERR_PID_UNION),         # 受保护 ID
        ("dataLen",   ctypes.c_uint8),         # 数据长度
        ("data",      ctypes.c_uint8 * 8),     # 数据
        ("errData",   _ERR_DATA_UNION),        # 错误详情
        ("dir",       ctypes.c_uint8),         # 方向
        ("chkSum",    ctypes.c_uint8),         # 校验和
        ("reserved",  ctypes.c_uint8 * 10),    # 保留
    ]

# --- ZCAN_LIN_MSG: LIN 消息 (_VCI_LIN_MSG) ---

class _LIN_DATA_UNION(ctypes.Union):
    """消息数据联合体: 根据 dataType 选成员
    C: union { ZCANLINData zcanLINData; ZCANLINErrData zcanLINErrData; U8 raw[46]; }
    """
    _pack_ = 1
    _fields_ = [
        ("zcanLINData",    ZCANLINData),        # dataType=0 时用
        ("zcanLINErrData", ZCANLINErrData),     # dataType=1 时用
        ("raw",            ctypes.c_uint8 * 46),  # 原始 46 字节
    ]

class ZCAN_LIN_MSG(ctypes.Structure):
    """LIN 消息结构体
    C: typedef struct { U8 chnl; U8 dataType; union { ... } data; } ZCAN_LIN_MSG;
    """
    _pack_ = 1
    _fields_ = [
        ("chnl",     ctypes.c_uint8),           # 通道号
        ("dataType", ctypes.c_uint8),           # 帧类型
        ("data",     _LIN_DATA_UNION),          # 数据 (联合体)
    ]

# --- 设备信息 ---

class ZCAN_DEV_INF(ctypes.Structure):
    """设备信息结构体 (对应 zcan.h)
    C: typedef struct { U16 hwv; U16 fwv; U16 drv; U16 api; U16 irq;
                        U8 chn; U8 sn[20]; U8 id[40]; U16 pad[4]; } ZCAN_DEV_INF;
    """
    _pack_ = 1
    _fields_ = [
        ("hwv", ctypes.c_uint16),         # 硬件版本
        ("fwv", ctypes.c_uint16),         # 固件版本
        ("drv", ctypes.c_uint16),         # 驱动版本
        ("api", ctypes.c_uint16),         # API 版本
        ("irq", ctypes.c_uint16),         # 中断号
        ("chn", ctypes.c_uint8),          # CAN 通道数
        ("sn",  ctypes.c_uint8 * 20),     # 序列号 (SN)
        ("id",  ctypes.c_uint8 * 40),     # 设备 ID
        ("pad", ctypes.c_uint16 * 4),     # 保留
    ]

# --- 配置结构体 ---

class ZCAN_LIN_INIT_CONFIG(ctypes.Structure):
    """LIN 通道初始化配置
    C: typedef struct { U8 linMode; U8 chkSumMode; U16 reserved; U32 linBaud; }
    """
    _pack_ = 1
    _fields_ = [
        ("linMode",    ctypes.c_uint8),         # 0=从机, 1=主机
        ("chkSumMode", ctypes.c_uint8),         # 1=经典, 2=增强, 3=自动
        ("reserved",   ctypes.c_uint16),        # 保留
        ("linBaud",    ctypes.c_uint32),        # 波特率 1000~20000
    ]

class ZCAN_LIN_PUBLISH_CFG(ctypes.Structure):
    """LIN 发布/响应配置
    用于主机"头部+响应" 或 从机"订阅响应"。
    C: typedef struct { U8 ID; U8 dataLen; U8 data[8]; U8 chkSumMode; U8 reserved[5]; }
    """
    _pack_ = 1
    _fields_ = [
        ("ID",         ctypes.c_uint8),         # 受保护 ID (0~63)
        ("dataLen",    ctypes.c_uint8),         # 数据长度 (1~8)
        ("data",       ctypes.c_uint8 * 8),     # 响应数据
        ("chkSumMode", ctypes.c_uint8),         # 校验方式
        ("reserved",   ctypes.c_uint8 * 5),     # 保留
    ]

# ============================================================
# LinApi — 封装所有 C API 调用
# ============================================================

class LinApi:
    """
    USBCANFD LIN 通道 C API 封装。

    内部加载 libusbcanfd.so, 设置函数签名, 提供 Python 风格的方法。

    用法:
        api = LinApi()
        api.OpenDevice(USBCANFD, 0)
        ...
        api.CloseDevice(USBCANFD, 0)
    """

    def __init__(self):
        # 从系统库路径加载动态库
        self._lib = ctypes.CDLL("libusbcanfd.so")
        self._setup_signatures()

    def _setup_signatures(self):
        """设置所有 C 函数的 argtypes / restype"""
        lib = self._lib

        # --- 设备开关 ---
        # int VCI_OpenDevice(int DevType, int DevIdx, int Reserved);
        lib.VCI_OpenDevice.argtypes = [c_int, c_int, c_int]
        lib.VCI_OpenDevice.restype  = c_int

        # int VCI_CloseDevice(int DevType, int DevIdx);
        lib.VCI_CloseDevice.argtypes = [c_int, c_int]
        lib.VCI_CloseDevice.restype  = c_int

        # --- 设备信息 ---
        # int VCI_ReadBoardInfo(int DevType, int DevIdx, ZCAN_DEV_INF *pInfo);
        lib.VCI_ReadBoardInfo.argtypes = [c_int, c_int, POINTER(ZCAN_DEV_INF)]
        lib.VCI_ReadBoardInfo.restype  = c_int

        # int VCI_SetReference(int DevType, int DevIdx, int Chn, int Cmd, void *pData);
        lib.VCI_SetReference.argtypes = [c_int, c_int, c_int, c_int, c_void_p]
        lib.VCI_SetReference.restype  = c_int

        # int VCI_GetReference(int DevType, int DevIdx, int Chn, int Cmd, void *pData);
        lib.VCI_GetReference.argtypes = [c_int, c_int, c_int, c_int, c_void_p]
        lib.VCI_GetReference.restype  = c_int

        # --- LIN 通道管理 ---
        # int VCI_InitLIN(int DevType, int DevIdx, int Chn, ZCAN_LIN_INIT_CONFIG *pCfg);
        lib.VCI_InitLIN.argtypes = [c_int, c_int, c_int, POINTER(ZCAN_LIN_INIT_CONFIG)]
        lib.VCI_InitLIN.restype  = c_int

        # int VCI_StartLIN(int DevType, int DevIdx, int Chn);
        lib.VCI_StartLIN.argtypes = [c_int, c_int, c_int]
        lib.VCI_StartLIN.restype  = c_int

        # int VCI_ResetLIN(int DevType, int DevIdx, int Chn);
        lib.VCI_ResetLIN.argtypes = [c_int, c_int, c_int]
        lib.VCI_ResetLIN.restype  = c_int

        # --- LIN 收发 ---
        # int VCI_TransmitLIN(int DevType, int DevIdx, int Chn, ZCAN_LIN_MSG *pMsg, int Len);
        lib.VCI_TransmitLIN.argtypes = [
            c_int, c_int, c_int, POINTER(ZCAN_LIN_MSG), c_int
        ]
        lib.VCI_TransmitLIN.restype = c_int

        # int VCI_ReceiveLIN(int DevType, int DevIdx, int Chn, ZCAN_LIN_MSG *pMsg, int Len, int WaitTime);
        lib.VCI_ReceiveLIN.argtypes = [
            c_int, c_int, c_int, POINTER(ZCAN_LIN_MSG), c_int, c_int
        ]
        lib.VCI_ReceiveLIN.restype = c_int

        # --- LIN 发布/订阅 ---
        # int VCI_SetLINPublish(int DevType, int DevIdx, int Chn, ZCAN_LIN_PUBLISH_CFG *pCfg, int Count);
        lib.VCI_SetLINPublish.argtypes = [
            c_int, c_int, c_int, POINTER(ZCAN_LIN_PUBLISH_CFG), c_int
        ]
        lib.VCI_SetLINPublish.restype = c_int

    # ================================================================
    # 公开方法
    # ================================================================

    def OpenDevice(self, dev_type, dev_idx, reserved=0):
        """打开设备。返回 True/False。"""
        return bool(self._lib.VCI_OpenDevice(dev_type, dev_idx, reserved))

    def CloseDevice(self, dev_type, dev_idx):
        """关闭设备。返回 True/False。"""
        return bool(self._lib.VCI_CloseDevice(dev_type, dev_idx))

    def ReadBoardInfo(self, dev_type, dev_idx):
        """
        读取设备板载信息。
        返回: (ZCAN_DEV_INF 结构体, True/False 成功标志)
        """
        info = ZCAN_DEV_INF()
        ok = bool(self._lib.VCI_ReadBoardInfo(dev_type, dev_idx, byref(info)))
        return info, ok

    def SetReference(self, dev_type, dev_idx, chn, cmd, data_buf):
        """
        向设备写入参数/命令 (如 SN 号、终端电阻等)。
        data_buf: ctypes 缓冲区 (create_string_buffer 等)
        返回 True/False。
        """
        return bool(self._lib.VCI_SetReference(dev_type, dev_idx, chn, cmd, data_buf))

    def GetReference(self, dev_type, dev_idx, chn, cmd, data_buf):
        """
        从设备读取参数/命令。
        data_buf: ctypes 缓冲区 (数据回填到此缓冲区)
        返回 True/False。
        """
        return bool(self._lib.VCI_GetReference(dev_type, dev_idx, chn, cmd, data_buf))

    def InitLIN(self, dev_type, dev_idx, chn, config):
        """
        初始化 LIN 通道。
        config 为 ZCAN_LIN_INIT_CONFIG 实例 (传引用)。
        返回 True/False。
        """
        return bool(self._lib.VCI_InitLIN(dev_type, dev_idx, chn, byref(config)))

    def StartLIN(self, dev_type, dev_idx, chn):
        """启动 LIN 通道。返回 True/False。"""
        return bool(self._lib.VCI_StartLIN(dev_type, dev_idx, chn))

    def ResetLIN(self, dev_type, dev_idx, chn):
        """复位 LIN 通道。返回 True/False。"""
        return bool(self._lib.VCI_ResetLIN(dev_type, dev_idx, chn))

    def TransmitLIN(self, dev_type, dev_idx, chn, msg_array, count):
        """
        发送 LIN 帧头 (仅主站可用)。
        msg_array: ZCAN_LIN_MSG 数组 (ctypes 数组)
        count:     数组长度
        返回: 实际发送帧数 (int)
        """
        return self._lib.VCI_TransmitLIN(dev_type, dev_idx, chn, msg_array, count)

    def ReceiveLIN(self, dev_type, dev_idx, chn, msg_array, count, wait_ms):
        """
        接收 LIN 数据。
        msg_array: ZCAN_LIN_MSG 数组 (预分配缓冲区)
        count:     缓冲区最大帧数
        wait_ms:   等待超时 (ms)
        返回: 实际收到帧数 (int)
        """
        return self._lib.VCI_ReceiveLIN(dev_type, dev_idx, chn, msg_array, count, wait_ms)

    def SetLINPublish(self, dev_type, dev_idx, chn, cfg_array, count):
        """
        设置 LIN 发布/响应。
        cfg_array: ZCAN_LIN_PUBLISH_CFG 数组 (ctypes 数组或指针)
        count:     配置条数
        返回 True/False。
        """
        return bool(self._lib.VCI_SetLINPublish(dev_type, dev_idx, chn, cfg_array, count))


# ============================================================
# 辅助函数
# ============================================================

def cstr(raw_bytes, max_len):
    """
    将 C 的 char[N] 定长数组转为 Python 字符串。
    截断到第一个 '\0' 并解码为 UTF-8。
    """
    return bytes(raw_bytes[:max_len]).split(b'\x00', 1)[0].decode('utf-8', errors='replace')


# ============================================================
# 便捷函数 — 创建默认配置
# ============================================================

def make_init_config(lin_mode, baud=9600, chksum=CHKSUM_CLASSIC):
    """
    快速创建 LIN 初始化配置。

    参数:
        lin_mode: LIN_MODE_MASTER (1) 或 LIN_MODE_SLAVE (0)
        baud:     波特率, 默认 9600
        chksum:   校验方式, 默认经典校验
    """
    cfg = ZCAN_LIN_INIT_CONFIG()
    cfg.linMode    = lin_mode
    cfg.linBaud    = baud
    cfg.chkSumMode = chksum
    return cfg


def make_publish_cfg(pid, data_bytes, data_len=8, chksum=CHKSUM_DEFAULT):
    """
    快速创建 LIN 发布/响应配置。

    参数:
        pid:       受保护 ID (0~63)
        data_bytes: 8 字节数据 (bytes 或 list)
        data_len:  数据长度 (1~8)
        chksum:    校验方式, 默认跟随启动配置
    """
    cfg = ZCAN_LIN_PUBLISH_CFG()
    cfg.ID         = pid
    cfg.dataLen    = data_len
    cfg.chkSumMode = chksum
    for j in range(min(len(data_bytes), 8)):
        cfg.data[j] = data_bytes[j]
    return cfg


def make_tx_msg(pid, chn=0):
    """
    快速创建发送用的 LIN 消息 (仅设置帧头和通道)。

    参数:
        pid: 受保护 ID (原始值, 写入 PID.rawVal)
        chn: 通道号, 默认 0 (主站)
    """
    msg = ZCAN_LIN_MSG()
    msg.dataType = 0
    msg.chnl = chn
    msg.data.zcanLINData.PID.rawVal = pid
    return msg
