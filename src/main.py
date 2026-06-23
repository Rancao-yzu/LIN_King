# -*- coding: utf-8 -*-
"""LIN 沙发项目 — 上位机控制界面 (tkinter/ttk + 自定义扁平按钮)"""

import tkinter as tk
from tkinter import ttk
from datetime import datetime

from gui_styles import (
    setup_styles, BG_CARD, TEXT_DARK,
    ORANGE_PRIMARY, ORANGE_ACCENT,LOG_COLORS, SECTION_GAP,FlatButton,
)
from protocol import (
    FRAME_NAME, format_hex,
    LEARN_STATUS_TEXT, OBSTACLE_TEXT, RADAR_FAULT_TEXT,
)
from lin_controller import LinController

def _btn(parent, text, command, width=120, bg=ORANGE_PRIMARY, hover=ORANGE_ACCENT, fg='white'):
    """快捷创建扁平按钮"""
    return FlatButton(parent, text=text, command=command,
                       width=width, height=34, bg=bg, hover=hover, fg=fg)

# 控制面板 (左侧)
class ControlPanel(ttk.LabelFrame):
    """控制按钮区域 — 使用扁平按钮, 分组布局"""

    def __init__(self, parent, controller: LinController):
        super().__init__(parent, text="控制面板", style='Card.TLabelframe')
        self._ctrl = controller

        row = 0

        # ---- 设备连接 ----
        ttk.Label(self, text="▸ 设备", font=('Microsoft YaHei', 9, 'bold'),
                  foreground=ORANGE_PRIMARY, background=BG_CARD).grid(
            row=row, column=0, columnspan=2, sticky='w', padx=4, pady=(6, 2))
        row += 1

        self._btn_connect = _btn(self, "连接设备", self._on_connect,
                                 bg=LOG_COLORS["RECV"], hover=LOG_COLORS["OK"])
        self._btn_connect.grid(row=row, column=0, padx=4, pady=3)

        self._btn_disconnect = _btn(self, "断开设备", self._ctrl.disconnect,
                                    bg=LOG_COLORS["ERROR"], hover=ORANGE_ACCENT)
        self._btn_disconnect.grid(row=row, column=1, padx=4, pady=3)
        row += 1

        # ---- 分隔 ----
        ttk.Separator(self, orient='horizontal').grid(
            row=row, column=0, columnspan=2, sticky='ew', pady=8, padx=4)
        row += 1

        # ---- 自定义发送 ----
        ttk.Label(self, text="▸ 自定义发送", font=('Microsoft YaHei', 9, 'bold'),
                  foreground=ORANGE_PRIMARY, background=BG_CARD).grid(
            row=row, column=0, columnspan=2, sticky='w', padx=4, pady=(2, 2))
        row += 1

        # 帧类型选择
        ttk.Label(self, text="帧类型:", background=BG_CARD).grid(
            row=row, column=0, sticky='w', padx=4, pady=2)
        self._frame_type_var = tk.StringVar()
        self._frame_combo = ttk.Combobox(self, textvariable=self._frame_type_var,
                                          state='readonly', width=24)
        self._frame_combo['values'] = ["电机控制帧 (0x01)", "雷达控制帧 (0x03)"]
        self._frame_combo.current(0)
        self._frame_combo.grid(row=row, column=1, sticky='w', padx=4, pady=2)
        self._frame_combo.bind('<<ComboboxSelected>>', self._update_preview)
        row += 1

        # DATA[0] 自学习状态
        self._cbo_d0 = self._add_combo(row, "DATA[0] 电机自学习:",
            ["默认值 (0x00)", "电机进行自学习 (0x01)", "电机不进行自学习 (0x02)"])
        row += 1

        # DATA[1] 电机动作
        self._cbo_d1 = self._add_combo(row, "DATA[1] 电机动作:",
            ["默认值 (0x00)", "电机转动伸出 (0x01)", "电机转动收回 (0x02)", "电机停止转动 (0x03)"])
        row += 1

        # DATA[2] 障碍物
        self._cbo_d2 = self._add_combo(row, "DATA[2] 障碍物:",
            ["默认值 (0x00)", "无障碍物 (0x01)", "有障碍物 (0x02)"])
        row += 1

        # 预览
        self._preview_label = ttk.Label(self, text="", foreground=TEXT_DARK,
                                         font=('Consolas', 9), background=BG_CARD)
        self._preview_label.grid(row=row, column=0, columnspan=2,
                                  sticky='w', padx=4, pady=(6, 2))
        self._update_preview()
        row += 1

        # 防丢重发 + 发送按钮
        self._repeat_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self, text="防丢重发 (5*100ms)", variable=self._repeat_var).grid(
            row=row, column=0, sticky='w', padx=4, pady=4)
        _btn(self, "发送", self._on_send, width=100,
             bg=ORANGE_PRIMARY, hover=ORANGE_ACCENT).grid(
            row=row, column=1, padx=4, pady=4)
        row += 1

        # ---- 分隔 ----
        ttk.Separator(self, orient='horizontal').grid(
            row=row, column=0, columnspan=2, sticky='ew', pady=8, padx=4)
        row += 1

        # ---- 电机轮询 ----
        ttk.Label(self, text="▸ 电机轮询", font=('Microsoft YaHei', 9, 'bold'),
                  foreground=ORANGE_PRIMARY, background=BG_CARD).grid(
            row=row, column=0, columnspan=2, sticky='w', padx=4, pady=(2, 2))
        row += 1

        self._btn_motor_poll_start = _btn(self, "开始", self._ctrl.start_motor_polling,
                                          bg=LOG_COLORS["RECV"], hover=LOG_COLORS["OK"])
        self._btn_motor_poll_start.grid(row=row, column=0, padx=4, pady=3)

        self._btn_motor_poll_stop = _btn(self, "停止", self._ctrl.stop_motor_polling,
                                         bg=LOG_COLORS["ERROR"], hover=ORANGE_ACCENT)
        self._btn_motor_poll_stop.grid(row=row, column=1, padx=4, pady=3)
        row += 1

        # ---- 雷达轮询 ----
        ttk.Label(self, text="▸ 雷达轮询", font=('Microsoft YaHei', 9, 'bold'),
                  foreground=ORANGE_PRIMARY, background=BG_CARD).grid(
            row=row, column=0, columnspan=2, sticky='w', padx=4, pady=(6, 2))
        row += 1

        self._btn_radar_poll_start = _btn(self, "开始", self._ctrl.start_radar_polling,
                                          bg=LOG_COLORS["RECV"], hover=LOG_COLORS["OK"])
        self._btn_radar_poll_start.grid(row=row, column=0, padx=4, pady=3)

        self._btn_radar_poll_stop = _btn(self, "停止", self._ctrl.stop_radar_polling,
                                         bg=LOG_COLORS["ERROR"], hover=ORANGE_ACCENT)
        self._btn_radar_poll_stop.grid(row=row, column=1, padx=4, pady=3)
        row += 1

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

    def _add_combo(self, row, label, values):
        ttk.Label(self, text=label, background=BG_CARD).grid(
            row=row, column=0, sticky='w', padx=4, pady=2)
        var = tk.StringVar()
        cbo = ttk.Combobox(self, textvariable=var, state='readonly', width=24, values=values)
        cbo.current(0)
        cbo.grid(row=row, column=1, sticky='w', padx=4, pady=2)
        cbo.bind('<<ComboboxSelected>>', self._update_preview)
        return cbo

    def _get_combo_val(self, cbo):
        """从 Combobox 文本中提取 hex 值, 如 '电机转动伸出 (0x01)' → 0x01"""
        text = cbo.get()
        if '(' in text and ')' in text:
            return int(text.split('(')[-1].rstrip(')'), 16)
        return 0

    def _update_preview(self, event=None):
        fid = self._get_combo_val(self._frame_combo)
        d0 = self._get_combo_val(self._cbo_d0)
        d1 = self._get_combo_val(self._cbo_d1)
        d2 = self._get_combo_val(self._cbo_d2)
        data_str = f"{d0:02X} {d1:02X} {d2:02X} 00 00 00 00 00"
        self._preview_label.config(
            text=f"预览: ID=0x{fid:02X}  Data: {data_str}")

    def _on_connect(self):
        self._ctrl.connect()

    def _on_send(self):
        fid = self._get_combo_val(self._frame_combo)
        data = [
            self._get_combo_val(self._cbo_d0),
            self._get_combo_val(self._cbo_d1),
            self._get_combo_val(self._cbo_d2),
            0, 0, 0, 0, 0,
        ]
        self._ctrl.send_custom(fid, data, repeat=self._repeat_var.get())


# 状态面板 (右侧)
class StatusPanel(ttk.LabelFrame):
    """执行状态 & 从节点状态显示"""

    def __init__(self, parent):
        super().__init__(parent, text="状态", style='Card.TLabelframe')

        row = 0

        # 连接状态
        self._conn_label = self._add_field(row, "设备连接", "● 未连接", ORANGE_ACCENT)
        row += 1

        # 执行结果
        self._result_label = self._add_field(row, "执行结果", "—")
        row += 1

        # 电机轮询状态
        self._motor_poll_label = self._add_field(row, "电机轮询", "○ 未启动", ORANGE_ACCENT)
        row += 1

        # 雷达轮询状态
        self._radar_poll_label = self._add_field(row, "雷达轮询", "○ 未启动", ORANGE_ACCENT)
        row += 1

        ttk.Separator(self, orient='horizontal').grid(
            row=row, column=0, columnspan=2, sticky='ew', pady=8, padx=4)
        row += 1

        # 电机状态
        ttk.Label(self, text="电机状态", font=('Microsoft YaHei', 9, 'bold'),
                  foreground=ORANGE_PRIMARY, background=BG_CARD).grid(
            row=row, column=0, columnspan=2, sticky='w', padx=4, pady=(2, 2))
        row += 1

        self._motor_labels = {}
        for text, key in [("自学习:", "learn"), ("位置:", "position"),
                           ("最大行程:", "stroke"), ("故障:", "fault")]:
            self._motor_labels[key] = self._add_field(row, text, "—")
            row += 1

        ttk.Separator(self, orient='horizontal').grid(
            row=row, column=0, columnspan=2, sticky='ew', pady=8, padx=4)
        row += 1

        # 雷达状态
        ttk.Label(self, text="雷达状态", font=('Microsoft YaHei', 9, 'bold'),
                  foreground=ORANGE_PRIMARY, background=BG_CARD).grid(
            row=row, column=0, columnspan=2, sticky='w', padx=4, pady=(2, 2))
        row += 1

        self._radar_labels = {}
        for text, key in [("障碍物:", "obstacle"), ("故障:", "fault")]:
            self._radar_labels[key] = self._add_field(row, text, "—")
            row += 1

    def _add_field(self, row, label_text, value_text, value_color=TEXT_DARK):
        """添加一行 标签: 值"""
        ttk.Label(self, text=label_text).grid(
            row=row, column=0, sticky='w', padx=4, pady=1)
        lb = ttk.Label(self, text=value_text, foreground=value_color)
        lb.grid(row=row, column=1, sticky='w', padx=4, pady=1)
        return lb

    # ---------- 更新方法 ----------

    def set_connected(self, connected: bool):
        if connected:
            self._conn_label.config(text="● 已连接", foreground="#27AE60")
        else:
            self._conn_label.config(text="● 未连接", foreground=ORANGE_ACCENT)
            self.set_motor_polling(False)
            self.set_radar_polling(False)

    def set_result(self, success: bool, message: str):
        color = "#27AE60" if success else "#E74C3C"
        tag = "✓" if success else "✗"
        self._result_label.config(text=f"{tag} {message}", foreground=color)

    def set_motor_polling(self, active: bool):
        if active:
            self._motor_poll_label.config(text="● 轮询中", foreground="#27AE60")
        else:
            self._motor_poll_label.config(text="○ 未启动", foreground=ORANGE_ACCENT)

    def set_radar_polling(self, active: bool):
        if active:
            self._radar_poll_label.config(text="● 轮询中", foreground="#27AE60")
        else:
            self._radar_poll_label.config(text="○ 未启动", foreground=ORANGE_ACCENT)

    def set_motor_status(self, info: dict):
        self._motor_labels['learn'].config(
            text=LEARN_STATUS_TEXT.get(1 if info['learn_done'] else 0, "—"))
        self._motor_labels['position'].config(text=str(info['position']))
        self._motor_labels['stroke'].config(text=str(info['max_stroke']))
        self._motor_labels['fault'].config(text=f"0x{info['fault']:02X}")

    def set_radar_status(self, info: dict):
        self._radar_labels['obstacle'].config(
            text=OBSTACLE_TEXT.get(info['obstacle'], f"0x{info['obstacle']:02X}"))
        self._radar_labels['fault'].config(
            text=RADAR_FAULT_TEXT.get(info['fault'], f"0x{info['fault']:02X}"))


# 报文监视 (底部)
class MessageLog(ttk.LabelFrame):
    """RX/TX 报文日志"""

    MAX_LINES = 500

    def __init__(self, parent):
        super().__init__(parent, text="报文监控  RX / TX", style='Card.TLabelframe')

        # 工具栏 (扁平按钮)
        toolbar = ttk.Frame(self, style='Card.TFrame')
        toolbar.pack(fill='x', padx=2, pady=(0, 4))

        _btn(toolbar, "清空", self.clear, width=60,
             bg=TEXT_DARK, hover=ORANGE_PRIMARY).pack(side='left', padx=(0, 4))

        self._pause_btn = _btn(toolbar, "暂停", self._toggle_pause, width=60,
                               bg=TEXT_DARK, hover=ORANGE_PRIMARY)
        self._pause_btn.pack(side='left')
        self._paused = False

        # 文本框 + 滚动条
        frame = ttk.Frame(self)
        frame.pack(fill='both', expand=True, padx=2, pady=(0, 2))

        self._text = tk.Text(
            frame, wrap='none', state='disabled',
            bg='#FFFFFF', fg='#2D2D2D',
            font=('Consolas', 9),
            insertbackground='black',
            relief='solid', borderwidth=1,
            padx=6, pady=4,
        )
        self._text.pack(side='left', fill='both', expand=True)

        scroll_y = ttk.Scrollbar(frame, orient='vertical', command=self._text.yview)
        scroll_y.pack(side='right', fill='y')
        self._text.configure(yscrollcommand=scroll_y.set)

        # 颜色标签
        self._text.tag_configure("TX", foreground=LOG_COLORS["SEND"])
        self._text.tag_configure("RX", foreground=LOG_COLORS["RECV"])
        self._text.tag_configure("ERR", foreground=LOG_COLORS["ERROR"])
        self._text.tag_configure("INFO", foreground=LOG_COLORS["INFO"])
        self._text.tag_configure("OK", foreground=LOG_COLORS["OK"])
        self._text.tag_configure("TIME", foreground="#AAAAAA")

        self._line_count = 0

    def clear(self):
        self._text.configure(state='normal')
        self._text.delete('1.0', 'end')
        self._text.configure(state='disabled')
        self._line_count = 0

    def _toggle_pause(self):
        self._paused = not self._paused
        self._pause_btn.configure(text="继续" if self._paused else "暂停")

    def is_paused(self):
        return self._paused

    def append(self, tag, message):
        """线程安全地追加日志行"""
        if self._paused:
            return

        def _do():
            try:
                self._text.configure(state='normal')
                now = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                self._text.insert('end', f"[{now}] ", "TIME")
                self._text.insert('end', f"{message}\n", tag)
                self._text.configure(state='disabled')
                self._text.see('end')

                self._line_count += 1
                if self._line_count > self.MAX_LINES:
                    self._text.configure(state='normal')
                    self._text.delete('1.0', '2.0')
                    self._text.configure(state='disabled')
                    self._line_count -= 1
            except Exception:
                pass

        self._text.after(0, _do)

    def append_tx(self, frame_id, data):
        name = FRAME_NAME.get(frame_id, f"0x{frame_id:02X}")
        self.append("TX", f"TX  ID:0x{frame_id:02X} [{name}]  {format_hex(data)}")

    def append_rx(self, frame_id, data):
        name = FRAME_NAME.get(frame_id, f"0x{frame_id:02X}")
        self.append("RX", f"RX  ID:0x{frame_id:02X} [{name}]  {format_hex(data)}")

    def append_info(self, text):
        self.append("INFO", text)

    def append_ok(self, text):
        self.append("OK", text)

    def append_error(self, text):
        self.append("ERR", text)


# 主窗口
class LinApp:
    """LIN 上位机主应用"""

    def __init__(self):
        self._root = tk.Tk()
        self._root.title("LIN King — 沙发项目上位机")
        self._root.geometry("860x720")
        self._root.configure(bg=BG_CARD)
        self._root.minsize(740, 580)

        setup_styles()

        # 业务控制器
        self._ctrl = LinController()
        self._wire_callbacks()

        # 构建 UI
        self._build_ui()

        # 关闭窗口时断开设备
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _wire_callbacks(self):
        """将控制器回调连接到 UI 更新"""
        self._ctrl.set_on_log(self._on_log)
        self._ctrl.set_on_result(self._on_result)
        self._ctrl.set_on_motor_status(self._on_motor_status)
        self._ctrl.set_on_radar_status(self._on_radar_status)
        self._ctrl.set_on_motor_polling(self._on_motor_polling)
        self._ctrl.set_on_radar_polling(self._on_radar_polling)

    def _build_ui(self):
        # === 顶部区域: 控制面板(左) + 状态面板(右) ===
        top = ttk.Frame(self._root, style='Card.TFrame')
        top.pack(fill='x', padx=SECTION_GAP, pady=(SECTION_GAP, 0))

        self._control_panel = ControlPanel(top, self._ctrl)
        self._control_panel.pack(side='left', fill='y',
                                 padx=(0, SECTION_GAP // 2))

        self._status_panel = StatusPanel(top)
        self._status_panel.pack(side='left', fill='both', expand=True,
                                padx=(SECTION_GAP // 2, 0))

        # === 底部区域: 报文日志 ===
        self._msg_log = MessageLog(self._root)
        self._msg_log.pack(fill='both', expand=True,
                           padx=SECTION_GAP, pady=SECTION_GAP)

    # ================================================================
    # 回调处理 — 线程安全地更新 UI

    def _on_log(self, direction, frame_id, data):
        if direction == 'TX':
            self._msg_log.append_tx(frame_id, data)
        else:
            self._msg_log.append_rx(frame_id, data)

    def _on_result(self, success, message):
        self._status_panel.set_result(success, message)
        self._status_panel.set_connected(self._ctrl.is_connected)
        if success:
            self._msg_log.append_ok(message)
        else:
            self._msg_log.append_error(message)

    def _on_motor_status(self, info):
        self._status_panel.set_motor_status(info)

    def _on_radar_status(self, info):
        self._status_panel.set_radar_status(info)

    def _on_motor_polling(self, active):
        self._status_panel.set_motor_polling(active)

    def _on_radar_polling(self, active):
        self._status_panel.set_radar_polling(active)

    def _on_close(self):
        try:
            self._ctrl.disconnect()
        except Exception:
            pass
        self._root.destroy()

    def run(self):
        self._root.mainloop()



if __name__ == "__main__":
    app = LinApp()
    app.run()
