#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
list_lin_device.py — USBCANFD 设备信息 & SN 号读写
===================================================

基于 lin_lib 封装, 不再直接操作 ctypes。

对应 C demo (src_example/test.c) 中的:
  - get_device_info() → 读取设备硬件/固件/序列号等信息
  - test_sn()         → 自定义设备 SN 号并回读验证
"""

import ctypes

from lib.lin_lib import (
    LinApi,
    USBCANFD,
    CMD_SET_SN,
    CMD_GET_SN,
    cstr,
)


def get_device_info(api, dev_type=USBCANFD, dev_idx=0):
    """
    读取并打印设备信息。

    参数:
        api:      LinApi 实例 (设备需已打开)
        dev_type: 设备类型号, 默认 33 (USBCANFD)
        dev_idx:  设备索引号, 默认 0

    返回:
        ZCAN_DEV_INF 结构体, 失败返回 None
    """
    info, ok = api.ReadBoardInfo(dev_type, dev_idx)
    if not ok:
        print("ReadBoardInfo failed — 请确认已打开设备且设备已连接")
        return None

    sn = cstr(info.sn, 20)
    dev_id = cstr(info.id, 40)

    print(
        f"HWV=0x{info.hwv:04X}, "
        f"FWV=0x{info.fwv:04X}, "
        f"DRV=0x{info.drv:04X}, "
        f"API=0x{info.api:04X}, "
        f"IRQ=0x{info.irq:04X}, "
        f"CHN=0x{info.chn:02X}, "
        f"SN={sn}, "
        f"ID={dev_id}"
    )
    return info


def set_sn(api, dev_type, dev_idx, chn, sn):
    """
    设置设备 SN 号。

    参数:
        api:      LinApi 实例
        dev_type: 设备类型号
        dev_idx:  设备索引号
        chn:      通道号 (通常传 0)
        sn:       要设置的 SN 字符串, 如 "A001"

    返回: True/False
    """
    buf = ctypes.create_string_buffer(sn.encode('utf-8'), 128)
    if not api.SetReference(dev_type, dev_idx, chn, CMD_SET_SN, buf):
        print("CMD_SET_SN failed — 请确认设备已打开且支持 SN 写入")
        return False
    print(f"set_sn: {sn}")
    return True


def get_sn(api, dev_type, dev_idx, chn):
    """
    获取设备 SN 号。

    参数:
        api:      LinApi 实例
        dev_type: 设备类型号
        dev_idx:  设备索引号
        chn:      通道号 (通常传 0)

    返回: SN 字符串, 失败返回 None
    """
    buf = ctypes.create_string_buffer(128)
    if not api.GetReference(dev_type, dev_idx, chn, CMD_GET_SN, buf):
        print("CMD_GET_SN failed — 请确认设备已打开")
        return None
    sn = buf.value.decode('utf-8', errors='replace')
    print(f"get_sn: {sn}")
    return sn


def test_sn(api, dev_type=USBCANFD, dev_idx=0, chn=0):
    """
    演示 SN 号设置与读取 (先写后读验证)。

    参数:
        api: LinApi 实例 (设备需已打开)
    """
    set_sn(api, dev_type, dev_idx, chn, "A001")
    get_sn(api, dev_type, dev_idx, chn)


# 自测入口

if __name__ == "__main__":
    DT = USBCANFD
    DI = 0
    api = LinApi()

    # 所有 API 调用前必须先打开设备
    if not api.OpenDevice(DT, DI):
        print("Open device fail — 请检查设备连接和 USB 权限")
        exit(1)
    print("Open device success")

    print()
    print("=" * 50)
    print("  设备信息 (get_device_info)")
    get_device_info(api, DT, DI)

    print()
    print("=" * 50)
    print("  SN 号读写 (test_sn)")
    test_sn(api, DT, DI, 0)

    api.CloseDevice(DT, DI)
    print()
    print("CloseDevice success")
