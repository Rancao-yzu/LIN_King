#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LIN_go.py — USBCANFD LIN 主机-从机对接通讯
============================================

测试拓扑:
  LIN0 (主站) ←──→ LIN1 (从站)
  波特率: 9600bps, 经典校验

工作流程:
  1. OpenDevice   → 打开设备
  2. InitLIN  *2  → 初始化 LIN0(主) + LIN1(从)
  3. StartLIN *2  → 启动通道
  4. 接收线程     → 每个通道独立轮询
  5. SetLINPublish → 主站发布 ID 0-2, 从站订阅 ID 3-4
  6. TransmitLIN   → 主站发送 ID 0-4 帧头
  7. Enter 退出    → ResetLIN + CloseDevice
"""

import time

import threading

from lib.lin_lib import (
    LinApi,
    USBCANFD,
    LIN_MODE_MASTER,
    LIN_MODE_SLAVE,
    CHKSUM_DEFAULT,
    CHKSUM_CLASSIC,
    LIN_DATA_FRAME,
    ZCAN_LIN_MSG,
    ZCAN_LIN_PUBLISH_CFG,
    make_init_config,
    make_publish_cfg,
    make_tx_msg,
)



MAX_CHANNELS = 2     # LIN 通道数
RX_WAIT_TIME = 100   # 接收超时 (ms)
RX_BUFF_SIZE = 1000  # 接收缓冲帧数


class LinReceiver:
    """LIN 通道独立接收线程"""

    def __init__(self, api, dev_type, dev_idx, chn):
        self.api      = api
        self.dev_type = dev_type
        self.dev_idx  = dev_idx
        self.chn      = chn
        self.stop     = False
        self.total    = 0
        self.thread   = None

    def receive_loop(self):
        buff = (ZCAN_LIN_MSG * RX_BUFF_SIZE)()

        while not self.stop:
            count = self.api.ReceiveLIN(
                self.dev_type, self.dev_idx, self.chn,
                buff, RX_BUFF_SIZE, RX_WAIT_TIME
            )

            for i in range(count):
                msg = buff[i]
                if msg.dataType != LIN_DATA_FRAME:
                    continue

                d = msg.data.zcanLINData
                ts  = d.RxData.timeStamp
                ch  = msg.chnl
                dr  = "TX" if d.RxData.dir else "RX"
                pid = d.PID.unionVal.ID
                dlen = d.RxData.dataLen
                vals = [d.RxData.data[j] for j in range(8)]

                print(f"[{ts}] LIN{ch} {dr} "
                      f"ID: 0x{pid:02X}  len:{dlen}  Data: ", end="")
                for j in range(dlen):
                    print(f"{vals[j]:X} ", end="")
                print()
                self.total += 1

            time.sleep(0.01)

    def start(self):
        self.thread = threading.Thread(target=self.receive_loop)
        self.thread.daemon = True
        self.thread.start()

    def join(self):
        if self.thread:
            self.thread.join()


def main():
    DT = USBCANFD
    DI = 0
    api = LinApi()

    print("=== USBCANFD LIN 通信测试 ===")

    # 1. 打开设备
    if not api.OpenDevice(DT, DI):
        print("Open device fail")
        return
    print("Open device success")

    # 2. 配置 LIN 通道: LIN0=主机, LIN1=从机
    cfgs = [
        make_init_config(LIN_MODE_MASTER, 9600, CHKSUM_CLASSIC),
        make_init_config(LIN_MODE_SLAVE,  9600, CHKSUM_CLASSIC),
    ]

    # 3. 初始化 & 启动, 同时启动接收线程
    receivers = []
    for i in range(MAX_CHANNELS):
        if not api.InitLIN(DT, DI, i, cfgs[i]):
            # 初始化失败, 关闭设备
            print(f"init LIN {i} fail")
            api.CloseDevice(DT, DI)
            return
        
        print(f"init LIN {i} success")

        if not api.StartLIN(DT, DI, i):
            # 启动失败, 关闭设备
            print(f"start LIN {i} fail")
            api.CloseDevice(DT, DI)
            return
        else:
            # 启动成功, 启动接收线程
            print(f"start LIN {i} success")

        r = LinReceiver(api, DT, DI, i)
        r.start()
        receivers.append(r)

    time.sleep(1)

    # 4. 设置 LIN 发布/响应
    #    LIN0 (主站) 发布 ID 0-2
    #    LIN1 (从站) 订阅 ID 3-4
    publish_cfgs = [make_publish_cfg(i, [i]*8) for i in range(5)]

    if not api.SetLINPublish(DT, DI, 0,
                             (ZCAN_LIN_PUBLISH_CFG * 3)(*publish_cfgs[0:3]), 3):
        print("set LIN0 publish failed")

    if not api.SetLINPublish(DT, DI, 1,
                             (ZCAN_LIN_PUBLISH_CFG * 2)(*publish_cfgs[3:5]), 2):
        print("set LIN1 publish failed")

    # 5. 主站发送 ID 0-4 帧头
    tx_msgs = [make_tx_msg(i, 0) for i in range(5)]
    tx_arr  = (ZCAN_LIN_MSG * 5)(*tx_msgs)
    scount  = api.TransmitLIN(DT, DI, 0, tx_arr, 5)
    print(f"Send LIN count : {scount}")

    print("\nWaiting for data, press Enter to exit...\n")
    input()

    # 6. 清理
    print("\nCleaning up...")
    for i in range(MAX_CHANNELS):
        receivers[i].stop = True
        receivers[i].join()
        if not api.ResetLIN(DT, DI, i):
            print(f"ResetLIN({i}) fail")
        else:
            print(f"ResetLIN({i}) success")

    api.CloseDevice(DT, DI)
    print("CloseDevice success")

    for i, r in enumerate(receivers):
        print(f"LIN{i} total received: {r.total}")


if __name__ == "__main__":
    main()

