# HandSync — 手势视觉控制工作室 🖐️🤖

> 基于 MediaPipe + OpenCV + STM32 的手势识别与伺服云台控制系统

[![Python](https://img.shields.io/badge/Python-3.8+-blue)](https://www.python.org/)
[![MediaPipe](https://img.shields.io/badge/MediaPipe-0.10+-orange)](https://developers.google.com/mediapipe)
[![STM32](https://img.shields.io/badge/STM32-F103C8T6-green)](https://www.st.com/)
[![License](https://img.shields.io/badge/License-MIT-lightgrey)](LICENSE)

---

## 📖 项目简介

**HandSync** 是一套将计算机视觉手势识别与硬件伺服控制相结合的系统。通过摄像头实时捕捉手部动作，借助 Google MediaPipe 进行高精度手部关键点检测，最终通过串口控制 STM32 + 双舵机云台，实现"手指挥、舵机动"的实时跟随效果。

同时附带两个创意应用：**霓虹空气绘画** 和 **手势数字识别**。

### 🎬 核心场景

```
  [摄像头] ──帧──▶ [MediaPipe 手部检测] ──坐标──▶ [P Control + 平滑滤波]
                                                         │
                                                    [串口 P<角度>/T<角度>]
                                                         │
                                              [STM32F103C8T6] ──PWM──▶ [SG90 舵机 × 2]
                                                                      PAN（水平旋转）
                                                                      TILT（俯仰）
```

---

## 🚀 功能一览

| 程序 | 功能 | 操作方式 |
|------|------|----------|
| `pan_tilt_tracker.py` | **手势云台追踪** — 手在哪，舵机转到哪 | 移动手控制云台，按 `Q` 退出 |
| `magic_paint.py` | **霓虹魔法绘画** — 隔空作画，霓虹光效 | 食指=画线，五指=喷涂，握拳=清屏，`C`清屏 `S`保存 |
| `hand_detection_test.py` | **手势数字识别** — 识别 0~5 | 伸出不同数量手指，屏幕显示数字 |
| `model.py` | 手势识别精简版（可用于二次开发） | 同上 |

---

## 🛠️ 硬件需求

### 必须（仅云台追踪功能需要）
- **STM32F103C8T6** 最小系统板（蓝色药丸 / Blue Pill）
- **SG90 微型舵机** × 2（水平 PAN + 俯仰 TILT）
- **USB 转串口模块** 或直接使用 STM32 的 USB-TTL
- 5V 电源（舵机和 STM32 可共用）

### 可选
- USB 外接摄像头（推荐，笔记本内置摄像头也可用）
- 云台支架 / 3D 打印外壳

### 接线

| STM32 引脚 | 连接 |
|-----------|------|
| PA0 (TIM2_CH1) | PAN 舵机信号线（水平旋转） |
| PA1 (TIM2_CH2) | TILT 舵机信号线（俯仰） |
| PA9 (USART1_TX) | USB-TTL 模块 RX |
| PA10 (USART1_RX) | USB-TTL 模块 TX |
| GND | 共地 |
| 5V / 3.3V | 舵机电源（建议独立供电） |

---

## 💻 软件环境

### PC 端（Python）

```bash
# 1. 克隆项目
git clone git@github.com:ttcl-web/7bb28-main.git
cd 7bb28-main

# 2. 安装依赖
pip install opencv-python mediapipe pyserial numpy

# 3. 运行（首次会自动下载 MediaPipe 手部模型 ~7MB）
python pan_tilt_tracker.py
```

> 模型文件 `hand_landmarker.task` 已内置在项目中，无需手动下载。

### STM32 端（Keil MDK-ARM V5）

1. 打开 `Serial_port_controlled_servo/Project/` 下的 Keil 工程
2. 确认芯片型号为 STM32F103C8T6
3. 编译 → 下载到开发板
4. 串口参数：**115200, 8N1**

---

## 📡 通信协议

| 命令 | 示例 | 说明 |
|------|------|------|
| `P<角度>\n` | `P90\n` | 设置 PAN 水平角度 (0°–180°) |
| `T<角度>\n` | `T45\n` | 设置 TILT 俯仰角度 (0°–120°) |
| `R\n` | `R\n` | 复位到中点 (P90, T90) |

- 波特率：115200
- 脉冲范围：500–2500 μs → 0°–180° (SG90)
- Python 端自动限速 ~8 Hz，防止舵机抖舵/烧毁

---

## 🎛️ 参数调优

在 `pan_tilt_tracker.py` 顶部可调整：

```python
SERIAL_PORT  = "COM9"          # 改成你的串口号
CAMERA_INDEX = 1               # 0=内置摄像头  1=外接USB

KP_X = 0.7                     # PAN 比例增益（越大越快，也越容易过冲）
KP_Y = 0.6                     # TILT 比例增益
DEAD_ZONE_PX = 30              # 死区像素（手在中心附近不触发移动）
SMOOTH_WINDOW = 8              # 平滑窗口（越大越平滑，响应越慢）
MIN_SEND_INTERVAL = 0.12       # 最短发送间隔（秒），保护舵机
MAX_DEG_PER_SEC = 50.0         # 舵机最大角速度（°/s）
LOST_TIMEOUT = 2.0             # 手丢失后多少秒自动回中（0=不回中）
```

---

## 📂 项目结构

```
7bb28-main/
├── pan_tilt_tracker.py          # 🔥 主程序：手势云台追踪
├── magic_paint.py               # 🎨 霓虹魔法绘画
├── hand_detection_test.py       # ✋ 手势数字识别 (0-5)
├── model.py                     # 手势识别精简版
├── hand_landmarker.task         # MediaPipe 手部模型文件
├── pan_tilt.zip                 # Python 源代码打包
├── Serial_port_controlled_servo/ # STM32 固件 (Keil5)
│   ├── User/main.c              #   主程序 + 串口命令解析
│   ├── Hardware/Steer/steer.c   #   双舵机 PWM 驱动
│   ├── Basic/usart/usart.c      #   串口驱动
│   └── ...
├── STM32F103C8T6串口控制舵机.zip # STM32 固件打包
├── LICENSE                      # MIT 许可证
└── README.md
```

---

## 🎮 操作说明

### 手势云台追踪 (`pan_tilt_tracker.py`)

```
┌────────────────────────────────────┐
│  将手放入摄像头画面                  │
│  手向左移 → 云台向左转               │
│  手向右移 → 云台向右转               │
│  手向上移 → 云台仰起                 │
│  手向下移 → 云台俯下                 │
│                                    │
│  手移出画面 2 秒后 → 自动回中        │
│  按 Q 退出（自动回中后关闭）          │
└────────────────────────────────────┘
```

### 魔法绘画 (`magic_paint.py`)

| 手势 | 效果 |
|------|------|
| ☝️ 食指 | 精细霓虹画笔 |
| ✌️ 食指+中指 | 粗画笔 |
| 🖐️ 五指张开 | 彩虹喷涂（随机颜色） |
| ✊ 握拳 | 粒子爆炸 + 清屏 |
| 上下移动 | 改变画笔颜色（彩虹渐变） |
| `C` 键 | 清屏 |
| `S` 键 | 保存画布截图 |

### 手势数字识别 (`hand_detection_test.py`)

伸出 0~5 根手指，画面左上角显示识别结果。支持双手（两数相加）。

---

## ❓ 常见问题

<details>
<summary><b>Q: 提示找不到串口？</b></summary>

修改 `pan_tilt_tracker.py` 中的 `SERIAL_PORT` 为你的实际串口号（如 `COM3`, `COM5`）。Windows 可在设备管理器 → 端口 中查看。
</details>

<details>
<summary><b>Q: 没有 STM32 硬件，能体验吗？</b></summary>

可以！如果串口打开失败，程序会自动进入"无串口模式"——摄像头和手部追踪正常显示，只是不发送舵机指令。魔法绘画和手势识别也不依赖 STM32。
</details>

<details>
<summary><b>Q: 摄像头打不开？</b></summary>

将 `CAMERA_INDEX` 改为 `0`（使用内置摄像头），或检查是否有其他程序占用摄像头。
</details>

<details>
<summary><b>Q: 舵机抖动/过热？</b></summary>

增大 `SMOOTH_WINDOW`（如 12）、增大 `ANGLE_DEADBAND`（如 2.5）、减小 `KP_X/KP_Y`（如 0.5）。
</details>

<details>
<summary><b>Q: MediaPipe 模型下载失败？</b></summary>

项目已内置 `hand_landmarker.task` 文件，无需下载。如果丢失，可手动从 [MediaPipe 官方](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker) 获取。
</details>

---

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源，STM32 固件部分基于 STM32 标准固件库。

---

## 🙏 致谢

- [Google MediaPipe](https://developers.google.com/mediapipe) — 手部关键点检测
- [OpenCV](https://opencv.org/) — 计算机视觉处理
- [STM32 标准固件库](https://www.st.com/) — 微控制器开发

---

> 💡 **HandSync** 不仅仅是一个云台控制器——它是一个将 AI 视觉能力延伸到物理世界的开源工具包。欢迎 Star ⭐ 和 PR！
