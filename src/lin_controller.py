# -*- coding: utf-8 -*-
"""LIN 控制业务逻辑层 — 管理协议指令、状态轮询、响应解析, 与 UI 解耦"""

import time
from datetime import datetime
import threading
from protocol import (
    PID_MOTOR_STATUS, 
    SEND_REPEAT, SEND_INTERVAL_MS,
)
from lib.lin_driver import LinDriver


class LinController:
    """LIN 总线控制器 — 所有业务逻辑集中在此"""

    def __init__(self):
        self._driver = LinDriver(chn=1, baud=19200)
        self._driver.set_rx_callback(self._on_rx)

        self._connected = False

        # 回调接口 (由 UI 注册)
        self._cb_log = None          # cb_log(direction, frame_id, data_list)
        self._cb_result = None       # cb_result(success: bool, message: str)
        self._cb_motor_status = None # cb_motor_status(info_dict)
        self._cb_motor_polling = None  # cb(motor_polling: bool)

        # 电机轮询
        self._motor_poll_thread = None
        self._motor_poll_stop = False
        self._motor_polling = False


    # 回调注册
    def set_on_log(self, cb):
        """注册报文日志回调: cb(direction, frame_id, data_list)"""
        self._cb_log = cb

    def set_on_result(self, cb):
        """注册执行结果回调: cb(success, message)"""
        self._cb_result = cb

    def set_on_motor_status(self, cb):
        """注册电机状态回调: cb(info_dict)
        info_dict: {'learn_done': bool, 'position': int, 'max_stroke': int, 'fault': int}
        """
        self._cb_motor_status = cb

    def set_on_motor_polling(self, cb):
        """注册电机轮询状态回调: cb(is_polling: bool)"""
        self._cb_motor_polling = cb


    # 设备连接
    @property
    def is_connected(self):
        return self._connected

    @property
    def is_motor_polling(self):
        return self._motor_polling


    def connect(self):
        """连接设备 (不自动启动轮询)"""
        if self._connected:
            self._emit_result(False, "设备已连接, 请勿操作")
            return False, "设备已连接"
        success, msg = self._driver.open()
        if success:
            self._connected = True
        self._emit_result(success, msg)
        return success, msg

    def disconnect(self):
        """断开设备"""
        if not self._connected:
            self._emit_result(False, "设备未连接, 请勿操作")
            return
        self.stop_motor_polling()
        self._driver.close()
        self._connected = False
        self._emit_result(True, "设备已断开")


    # 控制指令 (按防丢机制: 连续 5 次, 间隔 100ms)
    def send_custom(self, frame_id, data, repeat=True):
        """自定义发送帧. repeat=True 时按防丢机制连续发送 5 次.
        在子线程执行, 避免阻塞 tkinter 主循环导致崩溃.
        TX 日志由接收线程的回环统一记录, 不主动调用."""
        t = threading.Thread(
            target=self._send_custom_worker,
            args=(frame_id, list(data), repeat),
            daemon=True,
        )
        t.start()

    def _send_custom_worker(self, frame_id, data, repeat):
        """send_custom 的实际执行体 (子线程).
        防丢重发: 只配置一次响应数据 (SetLINPublish), 然后连续发送5次帧头.
        重复调用 SetLINPublish 会导致硬件配置混乱, 破坏报文发送."""
        tag = f"ID=0x{frame_id:02X}"
        try:
            if repeat:
                self._driver.set_publish(frame_id, data)
                for i in range(SEND_REPEAT):
                    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    print(f"[{current_time}] 开始发送第 {i+1}/{SEND_REPEAT} 次")
                    self._driver.send_header(frame_id)
                    if i < SEND_REPEAT - 1:
                        time.sleep(SEND_INTERVAL_MS / 1000.0)
            else:
                self._driver.send_frame(frame_id, data)
        except Exception as e:
            self._emit_result(False, f"发送失败: {e}")
            return
        self._emit_result(True, f"{tag} 发送完成")


    # 电机状态轮询
    def start_motor_polling(self):
        """启动电机状态轮询 (100ms 间隔)"""
        if self._motor_polling:
            return
        if not self._connected:
            self._emit_result(False, "请先连接设备")
            return
        self._motor_polling = True
        self._motor_poll_stop = False
        self._motor_poll_thread = threading.Thread(target=self._motor_poll_loop, daemon=True)
        self._motor_poll_thread.start()
        if self._cb_motor_polling:
            self._cb_motor_polling(True)
        self._emit_result(True, "电机轮询已启动")

    def stop_motor_polling(self):
        """停止电机状态轮询"""
        if not self._motor_polling:
            return
        self._motor_polling = False
        self._motor_poll_stop = True
        if self._cb_motor_polling:
            self._cb_motor_polling(False)
        self._emit_result(True, "电机轮询已停止")

    def _motor_poll_loop(self):
        """电机状态轮询循环 — 仅发送帧头, 等待电机从站响应数据.
        TX 日志由接收线程的回环统一记录."""
        while not self._motor_poll_stop:
            try:
                self._driver.send_header(PID_MOTOR_STATUS)
            except Exception:
                pass
            time.sleep(0.1)

    # 接收处理
    def _on_rx(self, msg):
        fid = msg['id']
        data = msg['data']
        direction = msg['direction']

        if self._cb_log:
            self._cb_log(direction, fid, list(data))

        if direction == 'RX':
            if fid == PID_MOTOR_STATUS:
                self._parse_motor_response(data)

    def _parse_motor_response(self, data):
        info = {
            'learn_done': data[0] == 0x01,
            'position': data[1] | (data[2] << 8),
            'max_stroke': data[3] | (data[4] << 8),  # 最大行程改为双字节（低字节在前）
            'fault': data[5],  # 故障帧移至 DATA[5]
        }
        if self._cb_motor_status:
            self._cb_motor_status(info)


    # 内部辅助
    def _emit_result(self, success, message):
        if self._cb_result:
            self._cb_result(success, message)
