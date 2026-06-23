# -*- coding: utf-8 -*-
"""LIN 驱动封装 — 基于 lin_lib 的上层驱动, 封装设备开关与收发"""

import time
import threading
from .lin_lib import (
    LinApi,
    USBCANFD,
    LIN_MODE_MASTER,
    CHKSUM_ENHANCE,
    LIN_DATA_FRAME,
    ZCAN_LIN_MSG,
    make_init_config,
)

RX_BUFF_SIZE = 100


class LinDriver:
    """LIN 总线驱动: 负责设备开关、帧收发、后台接收线程"""

    def __init__(self, dev_type=USBCANFD, dev_idx=0, chn=0, baud=9600):
        self._api = LinApi()
        self._dev_type = dev_type
        self._dev_idx = dev_idx
        self._chn = chn
        self._baud = baud
        self._opened = False
        self._started = False

        self._rx_thread = None
        self._rx_stop = False
        self._rx_callback = None

    # ================================================================
    # 设备操作
    # ================================================================

    def open(self):
        """打开设备、初始化并启动 LIN 主站通道, 同时开启后台接收"""
        if not self._api.OpenDevice(self._dev_type, self._dev_idx):
            return False, "打开设备失败, 请检查连接和 USB 权限"

        cfg = make_init_config(LIN_MODE_MASTER, self._baud, CHKSUM_ENHANCE)
        if not self._api.InitLIN(self._dev_type, self._dev_idx, self._chn, cfg):
            self._api.CloseDevice(self._dev_type, self._dev_idx)
            return False, "初始化 LIN 通道失败"

        if not self._api.StartLIN(self._dev_type, self._dev_idx, self._chn):
            self._api.CloseDevice(self._dev_type, self._dev_idx)
            return False, "启动 LIN 通道失败"

        self._opened = True
        self._started = True

        self._rx_stop = False
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._rx_thread.start()

        return True, "设备打开成功"

    def close(self):
        """关闭设备, 停止接收线程"""
        self._rx_stop = True
        if self._rx_thread:
            self._rx_thread.join(timeout=2)

        if self._started:
            self._api.ResetLIN(self._dev_type, self._dev_idx, self._chn)
        if self._opened:
            self._api.CloseDevice(self._dev_type, self._dev_idx)

        self._opened = False
        self._started = False

    # ================================================================
    # 收发
    # ================================================================

    def set_rx_callback(self, callback):
        """设置接收回调: callback(msg_dict)
        msg_dict = {'timestamp': int, 'channel': int, 'direction': 'TX'|'RX',
                    'id': int, 'data': [int x8]}
        """
        self._rx_callback = callback

    def send_frame(self, frame_id, data=None):
        """发送 LIN 帧 (仅主站). frame_id: 6bit ID, data: 8 字节列表"""
        if data is None:
            data = [0] * 8

        msg = ZCAN_LIN_MSG()
        msg.dataType = LIN_DATA_FRAME
        msg.chnl = self._chn
        msg.data.zcanLINData.PID.unionVal.ID = frame_id & 0x3F

        for i, b in enumerate(data[:8]):
            msg.data.zcanLINData.RxData.data[i] = b
        msg.data.zcanLINData.RxData.dataLen = 8
        msg.data.zcanLINData.RxData.dir = 1

        msgs = (ZCAN_LIN_MSG * 1)(msg)
        return self._api.TransmitLIN(self._dev_type, self._dev_idx, self._chn, msgs, 1)

    # ================================================================
    # 后台接收
    # ================================================================

    def _rx_loop(self):
        buff = (ZCAN_LIN_MSG * RX_BUFF_SIZE)()

        while not self._rx_stop:
            try:
                count = self._api.ReceiveLIN(
                    self._dev_type, self._dev_idx, self._chn,
                    buff, RX_BUFF_SIZE, 50
                )
                for i in range(count):
                    msg = buff[i]
                    if msg.dataType != LIN_DATA_FRAME:
                        continue
                    d = msg.data.zcanLINData
                    info = {
                        'timestamp': d.RxData.timeStamp,
                        'channel': msg.chnl,
                        'direction': 'TX' if d.RxData.dir else 'RX',
                        'id': d.PID.unionVal.ID,
                        'data': [d.RxData.data[j] for j in range(8)],
                    }
                    if self._rx_callback:
                        self._rx_callback(info)
            except Exception:
                pass
            time.sleep(0.01)
