# -*- coding: utf-8 -*-
"""LIN 控制业务逻辑层 — 管理协议指令、状态轮询、响应解析, 与 UI 解耦"""

import time
import threading
from protocol import (
    PID_MOTOR_STATUS, PID_RADAR_STATUS,
    SEND_REPEAT, SEND_INTERVAL_MS,
)
from lib.lin_driver import LinDriver


class LinController:
    """LIN 总线控制器 — 所有业务逻辑集中在此"""

    def __init__(self):
        self._driver = LinDriver()
        self._driver.set_rx_callback(self._on_rx)

        self._connected = False

        # 回调接口 (由 UI 注册)
        self._cb_log = None          # cb_log(direction, frame_id, data_list)
        self._cb_result = None       # cb_result(success: bool, message: str)
        self._cb_motor_status = None # cb_motor_status(info_dict)
        self._cb_radar_status = None # cb_radar_status(info_dict)
        self._cb_motor_polling = None  # cb(motor_polling: bool)
        self._cb_radar_polling = None  # cb(radar_polling: bool)

        # 电机轮询
        self._motor_poll_thread = None
        self._motor_poll_stop = False
        self._motor_polling = False

        # 雷达轮询
        self._radar_poll_thread = None
        self._radar_poll_stop = False
        self._radar_polling = False


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

    def set_on_radar_status(self, cb):
        """注册雷达状态回调: cb(info_dict)
        info_dict: {'obstacle': int, 'fault': int}
        """
        self._cb_radar_status = cb

    def set_on_motor_polling(self, cb):
        """注册电机轮询状态回调: cb(is_polling: bool)"""
        self._cb_motor_polling = cb

    def set_on_radar_polling(self, cb):
        """注册雷达轮询状态回调: cb(is_polling: bool)"""
        self._cb_radar_polling = cb


    # 设备连接
    @property
    def is_connected(self):
        return self._connected

    @property
    def is_motor_polling(self):
        return self._motor_polling

    @property
    def is_radar_polling(self):
        return self._radar_polling

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
        self.stop_radar_polling()
        self._driver.close()
        self._connected = False
        self._emit_result(True, "设备已断开")


    # 控制指令 (按防丢机制: 连续 5 次, 间隔 100ms)
    def send_custom(self, frame_id, data, repeat=True):
        """自定义发送帧. repeat=True 时按防丢机制连续发送 5 次"""
        tag = f"ID=0x{frame_id:02X}"
        if repeat:
            for i in range(SEND_REPEAT):
                try:
                    self._driver.send_frame(frame_id, data)
                except Exception as e:
                    self._emit_result(False, f"发送失败: {e}")
                    return
                if self._cb_log:
                    self._cb_log('TX', frame_id, list(data))
                if i < SEND_REPEAT - 1:
                    time.sleep(SEND_INTERVAL_MS / 1000.0)
        else:
            try:
                self._driver.send_frame(frame_id, data)
            except Exception as e:
                self._emit_result(False, f"发送失败: {e}")
                return
            if self._cb_log:
                self._cb_log('TX', frame_id, list(data))
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
        """电机状态轮询循环"""
        while not self._motor_poll_stop:
            try:
                self._driver.send_frame(PID_MOTOR_STATUS, [0] * 8)
                if self._cb_log:
                    self._cb_log('TX', PID_MOTOR_STATUS, [0] * 8)
            except Exception:
                pass
            time.sleep(0.1)

    # 雷达状态轮询
    def start_radar_polling(self):
        """启动雷达状态轮询 (100ms 间隔)"""
        if self._radar_polling:
            return
        if not self._connected:
            self._emit_result(False, "请先连接设备")
            return
        self._radar_polling = True
        self._radar_poll_stop = False
        self._radar_poll_thread = threading.Thread(target=self._radar_poll_loop, daemon=True)
        self._radar_poll_thread.start()
        if self._cb_radar_polling:
            self._cb_radar_polling(True)
        self._emit_result(True, "雷达轮询已启动")

    def stop_radar_polling(self):
        """停止雷达状态轮询"""
        if not self._radar_polling:
            return
        self._radar_polling = False
        self._radar_poll_stop = True
        if self._cb_radar_polling:
            self._cb_radar_polling(False)
        self._emit_result(True, "雷达轮询已停止")

    def _radar_poll_loop(self):
        """雷达状态轮询循环"""
        while not self._radar_poll_stop:
            try:
                self._driver.send_frame(PID_RADAR_STATUS, [0] * 8)
                if self._cb_log:
                    self._cb_log('TX', PID_RADAR_STATUS, [0] * 8)
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
            elif fid == PID_RADAR_STATUS:
                self._parse_radar_response(data)

    def _parse_motor_response(self, data):
        info = {
            'learn_done': data[0] == 0x01,
            'position': data[1] | (data[2] << 8),
            'max_stroke': data[3] | (data[4] << 8),  # 最大行程改为双字节（低字节在前）
            'fault': data[5],  # 故障帧移至 DATA[5]
        }
        if self._cb_motor_status:
            self._cb_motor_status(info)

    def _parse_radar_response(self, data):
        info = {
            'obstacle': data[0],
            'fault': data[1],
        }
        if self._cb_radar_status:
            self._cb_radar_status(info)

    # 内部辅助
    def _emit_result(self, success, message):
        if self._cb_result:
            self._cb_result(success, message)
