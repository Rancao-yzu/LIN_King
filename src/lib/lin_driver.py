# -*- coding: utf-8 -*-
"""LIN 驱动封装 — 基于 lin_lib 的上层驱动, 封装设备开关与收发

参考 ZLG USBCANFD LIN DEMO 的报文处理方式:
- 主站发送控制帧 (头部+响应): 先 VCI_SetLINPublish 配置响应数据,
  再 VCI_TransmitLIN 发送帧头, 设备自动附带预配置数据发出.
- 主站轮询从站 (仅头部): 直接 VCI_TransmitLIN 发送帧头, 从站响应.
- PID 校验位由硬件自动计算, rawVal 只需填 6bit ID (参考 demo: rawVal = i).
- ZCAN_LIN_MSG 中 RxData 字段 "仅接收数据时有效", 发送时填 data 无效.
"""

import time
import threading
from .lin_lib import (
    LinApi,
    USBCANFD,
    LIN_MODE_MASTER,
    CHKSUM_CLASSIC,
    CHKSUM_DEFAULT,
    LIN_DATA_FRAME,
    ZCAN_LIN_MSG,
    ZCAN_LIN_PUBLISH_CFG,
    make_init_config,
)

RX_BUFF_SIZE = 100


class LinDriver:
    """LIN 总线驱动: 负责设备开关、帧收发、后台接收线程"""

    def __init__(self, dev_type=USBCANFD, dev_idx=0, chn=0, baud=19200):
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

        cfg = make_init_config(LIN_MODE_MASTER, self._baud, CHKSUM_CLASSIC)
        if not self._api.InitLIN(self._dev_type, self._dev_idx, self._chn, cfg):
            self._api.CloseDevice(self._dev_type, self._dev_idx)
            return False, "初始化 LIN 通道失败"

        if not self._api.StartLIN(self._dev_type, self._dev_idx, self._chn):
            self._api.CloseDevice(self._dev_type, self._dev_idx)
            return False, "启动 LIN 通道失败"

        # 等待硬件稳定 (与 ZLG testLin.c 的 msleep(1000) 一致)
        time.sleep(1)

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

    def set_publish(self, frame_id, data, data_len=8):
        """配置主站响应数据 (对应 ZXDOC 中的 "头部和响应").
        调用后, 当主站发送该 ID 的帧头时, 设备自动附带此数据发出.
        frame_id: 6bit ID, data: 字节列表.
        构造数组方式参考 ZLG LIN_DEMO.py: (Type * n)() 后逐元素赋值."""
        cfgs = (ZCAN_LIN_PUBLISH_CFG * 1)()
        cfgs[0].ID = frame_id & 0x3F
        cfgs[0].dataLen = data_len
        cfgs[0].chkSumMode = CHKSUM_DEFAULT
        for j in range(min(len(data), 8)):
            cfgs[0].data[j] = data[j]
        return self._api.SetLINPublish(
            self._dev_type, self._dev_idx, self._chn, cfgs, 1)

    def send_frame(self, frame_id, data=None):
        """发送 LIN 帧 (头部+响应). frame_id: 6bit ID, data: 字节列表
        主站发送控制/命令帧. 先配置响应数据, 再发送帧头触发发送.
        (ZCAN_LIN_MSG.RxData 仅接收有效, 发送数据必须通过 SetLINPublish)"""
        if data is None:
            data = [0] * 8
        self.set_publish(frame_id, data)
        return self.send_header(frame_id)

    def send_header(self, frame_id):
        """发送 LIN 帧头 (仅头部). frame_id: 6bit ID
        主站仅发送帧头 (Break+Sync+PID), 硬件自动计算 PID 校验位.
        - 若该 ID 已 SetLINPublish, 则发送头部+响应 (控制帧).
        - 若未 SetLINPublish, 则仅发头部, 等待从站响应 (轮询)."""
        msg = ZCAN_LIN_MSG()
        msg.dataType = LIN_DATA_FRAME
        msg.chnl = self._chn
        msg.data.zcanLINData.PID.rawVal = frame_id & 0x3F  # 硬件自动加校验位

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
                        'id': d.PID.rawVal & 0x3F,
                        'data': [d.RxData.data[j] for j in range(8)],
                    }
                    if self._rx_callback:
                        self._rx_callback(info)
            except Exception:
                pass
            time.sleep(0.01)
