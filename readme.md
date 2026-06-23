# LIN_King — USBCANFD LIN 通道 Python 通信库

基于 ZLG USBCANFD 系列设备 (100U) 的 LIN 总线通信 Python 封装。

## 目录结构

```
LIN_King/
├── src/
│   ├── lib/
│   │   └── lin_lib.py          ← 底层绑定: 结构体 + C API 封装
│   ├── LIN_go.py               ← LIN 主从通讯示例
│   └── list_lin_device.py      ← 查询设备信息 & SN 号读写
├── src_example/                 ← ZLG  C demo 
│   ├── zcan.h                  ← C 头文件
│   ├── testLin.c               ← LIN 主从通讯 C demo
│   └── test.c                  ← CAN/CANFD + 设备信息 C demo
```

---
使用前必读！
> linux下的驱动文件见  __lib/usbcanfd_libusb_x64_1.0.13_260316.zip  
> [build.md](lib/build.md) - 驱动安装指南;  
> [Lin.md](lib/Lin.md) - 通信原理  



## 库的使用方法（见src）

### LinApi 全部方法

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `OpenDevice(type, idx)` | 打开设备 | `True/False` |
| `CloseDevice(type, idx)` | 关闭设备 | `True/False` |
| `ReadBoardInfo(type, idx)` | 读取设备信息 | `(ZCAN_DEV_INF, bool)` |
| `SetReference(type, idx, ch, cmd, buf)` | 写入参数/命令 | `True/False` |
| `GetReference(type, idx, ch, cmd, buf)` | 读取参数/命令 | `True/False` |
| `InitLIN(type, idx, ch, cfg)` | 初始化 LIN 通道 | `True/False` |
| `StartLIN(type, idx, ch)` | 启动 LIN 通道 | `True/False` |
| `ResetLIN(type, idx, ch)` | 复位 LIN 通道 | `True/False` |
| `TransmitLIN(type, idx, ch, msgs, n)` | 发送帧头 (仅主站) | 实际发送数 |
| `ReceiveLIN(type, idx, ch, buf, n, ms)` | 接收数据 | 实际收到数 |
| `SetLINPublish(type, idx, ch, cfgs, n)` | 设置发布/响应 | `True/False` |

### 主要结构体

| 结构体 | 对应 C 类型 | 用途 |
|--------|------------|------|
| `ZCANLINData` | `tagZCANLINData` | LIN 数据帧 |
| `ZCANLINErrData` | `tagZCANLINErrData` | LIN 错误帧 |
| `ZCAN_LIN_MSG` | `_VCI_LIN_MSG` | LIN 消息 (含联合体) |
| `ZCAN_LIN_INIT_CONFIG` | `_VCI_LIN_INIT_CONFIG` | 通道初始化 |
| `ZCAN_LIN_PUBLISH_CFG` | `_VCI_LIN_PUBLISH_CFG` | 发布/响应配置 |
| `ZCAN_DEV_INF` | `ZCAN_DEV_INF` | 设备信息 |

### 常量

```python
USBCANFD = 33       # 设备类型号
LIN_MODE_SLAVE  = 0 # 从机
LIN_MODE_MASTER = 1 # 主机
CHKSUM_CLASSIC  = 1 # 经典校验
CHKSUM_ENHANCE  = 2 # 增强校验
LIN_DATA_FRAME  = 0 # 数据帧
LIN_ERROR_FRAME = 1 # 错误帧
CMD_SET_SN = 0x42   # 写 SN
CMD_GET_SN = 0x43   # 读 SN
```


## 与 C demo 的对应关系

| C (src_example/testLin.c) | Python |
|---------------------------|--------|
| `VCI_OpenDevice` | `api.OpenDevice()` |
| `VCI_InitLIN` + `VCI_StartLIN` | `api.InitLIN()` + `api.StartLIN()` |
| `pthread_create(rx_thread)` | `LinReceiver` 类 + `threading.Thread` |
| `VCI_SetLINPublish` | `api.SetLINPublish()` |
| `VCI_TransmitLIN` | `api.TransmitLIN()` |
| `VCI_ReceiveLIN` | `api.ReceiveLIN()` |
| `VCI_ResetLIN` + `VCI_CloseDevice` | `api.ResetLIN()` + `api.CloseDevice()` |
