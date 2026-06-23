
# USBCANFD Linux 驱动快速使用指南

## 一、解压驱动包

```bash
tar -zxvf usbcanfd_libusb_x64_1.0.13_260316.tar.gz
cd usbcanfd_libusb_x64_1.0.13_260316
```

## 二、检查并安装 libusb

```bash
# 检查是否已安装
dpkg -l | grep libusb

# 如果未安装，执行以下命令
sudo apt-get install libusb-1.0-0 libusb-1.0-0-dev
```

## 三、编译示例程序

```bash
make
```

## 四、拷贝动态库到系统目录

```bash
sudo cp libusbcanfd.so libzuds.so /lib
```

## 五、创建软链接

```bash
sudo ln -s /lib/libusbcanfd.so /lib/libusbcanfd.so.1.0.13
sudo ln -s /lib/libzuds.so /lib/libzuds.so.20231025
```

## 六、配置 USB 设备权限

```bash
# 创建 udev 规则（永久生效）
sudo bash -c 'echo "SUBSYSTEMS==\"usb\", ATTRS{idVendor}==\"3068\", ATTRS{idProduct}==\"0009\", GROUP=\"users\", MODE=\"0666\"" > /etc/udev/rules.d/50-usbcanfd.rules'

# 重新加载规则
sudo udevadm control --reload
sudo udevadm trigger
```

重新插拔设备后生效。

## 七、运行 LIN 通信示例

```bash
sudo ./testLin
```


---

## 常用命令速查

| 操作 | 命令 |
|------|------|
| 查看设备 | `lsusb \| grep 3068` |
| 临时授权 | `sudo chmod 666 /dev/bus/usb/*/*` |
| 查看库版本 | `./verison.sh ./libusbcanfd.so` |
| 清理编译文件 | `make clean` |
