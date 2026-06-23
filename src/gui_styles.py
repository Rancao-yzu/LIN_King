# -*- coding: utf-8 -*-
"""GUI —— 主题色、样式定义、自定义按钮组"""

import tkinter as tk
from tkinter import ttk

# ---- 主题色定义 ----
ORANGE_PRIMARY = "#008AFC"   # 主色调：按钮背景、选中态强调
ORANGE_LIGHT = "#C9F1FD"    # 浅色调：表格标题背景、占位区域背景
ORANGE_ACCENT = '#FF6B00'   # 强调色：标签、说明
BG_CARD = "#F7FDFD"         # 主背景色：窗口底色
TEXT_DARK = '#3E2723'       # 主文字色：标题、正文

SECTION_GAP = 5            # 区域间距

LOG_COLORS = {              # 日志级别对应文字颜色
    "INFO": "#3E2723",      # 普通信息 —— 深灰
    "SEND": "#E67E22",      # 发送消息 —— 橙色
    "RECV": "#27AE60",      # 接收消息 —— 绿色
    "ERROR": "#E74C3C",     # 错误消息 —— 红色
    "OK": "#2E7D32",        # 成功消息 —— 深绿
}


def setup_styles():
    """配置 ttk 全局样式：卡片、标签、输入框、表格、滚动条"""
    style = ttk.Style()
    style.theme_use('clam')

    style.configure('Card.TFrame', background=BG_CARD)
    style.configure('Card.TLabelframe', background=BG_CARD)
    style.configure('Card.TLabelframe.Label', background=BG_CARD,
                    foreground=TEXT_DARK, font=('Microsoft YaHei', 10, 'bold'))

    style.configure('TLabel', background=BG_CARD, foreground=TEXT_DARK,
                    font=('Microsoft YaHei', 9))
    style.configure('Hint.TLabel', foreground=ORANGE_ACCENT, font=('Microsoft YaHei', 9))

    style.configure('TEntry', fieldbackground=BG_CARD, foreground=TEXT_DARK,
                    borderwidth=1, relief='solid')
    style.map('TEntry', bordercolor=[('focus', ORANGE_PRIMARY)],
              lightcolor=[('focus', ORANGE_PRIMARY)])

    style.configure('TCombobox', fieldbackground=BG_CARD, foreground=TEXT_DARK,
                    arrowcolor=ORANGE_PRIMARY)
    style.map('TCombobox', fieldbackground=[('readonly', BG_CARD)],
              bordercolor=[('focus', ORANGE_PRIMARY)])

    style.configure('Treeview', background=BG_CARD, foreground=TEXT_DARK,
                    fieldbackground=BG_CARD, rowheight=28,
                    font=('Consolas', 9))
    style.configure('Treeview.Heading', background=ORANGE_LIGHT,
                    foreground=ORANGE_PRIMARY, font=('Microsoft YaHei', 9, 'bold'),
                    relief='flat', borderwidth=0)
    style.map('Treeview.Heading', background=[('active', ORANGE_LIGHT)])

    # OTA 进度条样式
    style.configure('OTA.Horizontal.TProgressbar',
                    troughcolor=ORANGE_LIGHT,
                    background=ORANGE_PRIMARY,
                    thickness=18,
                    borderwidth=0,
                    lightcolor=ORANGE_PRIMARY,
                    darkcolor=ORANGE_PRIMARY)

class FlatButton(tk.Canvas):
    """扁平按钮：Canvas 自绘矩形 + 文字，支持 hover 变色、禁用态"""

    def __init__(self, parent, text, command=None, width=110, height=34,
                 bg=ORANGE_PRIMARY, hover=ORANGE_ACCENT, fg='white',
                 font=('Microsoft YaHei', 10), **kwargs):
        super().__init__(parent, width=width, height=height,
                         highlightthickness=0, bd=0,
                         bg=parent['bg'] if 'bg' in parent.keys() else BG_CARD,
                         **kwargs)
        self._bg = bg
        self._hover = hover
        self._fg = fg
        self._font = font
        self._text = text
        self._command = command
        self._enabled = True

        self._rect_id = None
        self._text_id = None

        self._draw()
        self.bind('<Enter>', self._on_enter)
        self.bind('<Leave>', self._on_leave)
        self.bind('<Button-1>', self._on_click)

    def _draw(self, color=None):
        self.delete('all')
        c = color if color else (self._bg if self._enabled else '#CCCCCC')
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        self._rect_id = self.create_rectangle(2, 2, w - 2, h - 2, fill=c, outline=c)
        self._text_id = self.create_text(w // 2, h // 2, text=self._text,
                                         fill=self._fg if self._enabled else '#999999',
                                         font=self._font)

    def _on_enter(self, event):
        if self._enabled:
            self._draw(self._hover)

    def _on_leave(self, event):
        self._draw()

    def _on_click(self, event):
        if self._enabled and self._command:
            self._command()

    def configure(self, **kwargs):
        if 'state' in kwargs:
            state = kwargs.pop('state')
            self.set_enabled(state != tk.DISABLED)
        if 'text' in kwargs:
            self._text = kwargs.pop('text')
            self._draw()
        if 'command' in kwargs:
            self._command = kwargs.pop('command')
        super().configure(**kwargs)

    def set_enabled(self, enabled):
        self._enabled = enabled
        self._draw()

    def cget(self, key):
        if key == 'state':
            return tk.NORMAL if self._enabled else tk.DISABLED
        return super().cget(key)

