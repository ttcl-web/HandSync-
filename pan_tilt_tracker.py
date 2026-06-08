"""
Hand-tracking Pan/Tilt PTZ controller  (v2 — safe servo rate)

- Tracks hand position via webcam + MediaPipe
- Hand X → Pan angle (base rotation, left↔right)
- Hand Y → Tilt angle (pitch, up↔down)
- Sends "P<angle>\\n" "T<angle>\\n" over serial to STM32F103C8T6
- P-control + dead zone + heavy low-pass filtering
- Rate-limited output to protect servos from stutter / stall / burnout

Protocol (matches STM32 firmware):
  P<angle>\\n   → set pan  (0~180°)
  T<angle>\\n   → set tilt (0~180°)
  Commands are sent *only when angles actually change* beyond a deadband,
  and *at most once per MIN_SEND_INTERVAL seconds*.

Press 'q' to quit.
"""

import sys
import cv2
import mediapipe as mp
import numpy as np
import os
import urllib.request
import time
from collections import deque

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ====================  Config  ====================
SERIAL_PORT  = "COM9"
BAUDRATE     = 115200                        # STM32 USART1 波特率

CAMERA_INDEX = 1                             # 1=外接USB  0=内置

# --- 舵机角度范围 ---
PAN_MIN,  PAN_MAX  = 0, 180
TILT_MIN, TILT_MAX = 0, 120                 # 俯仰限幅

PAN_CENTER  = 90
TILT_CENTER = 90

# --- 控制参数 ---
KP_X = 0.7                                   # PAN  P增益（稍降防过冲）
KP_Y = 0.6                                   # TILT P增益
DEAD_ZONE_PX = 30                            # 死区 (px)

# --- 伺服保护 ---
MIN_SEND_INTERVAL = 0.12                     # 最短发送间隔 120ms （≈8 Hz）
SMOOTH_WINDOW     = 8                        # 移动平均窗口（加大更平滑）
MAX_DEG_PER_SEC   = 50.0                     # 舵机最大角速度 °/s
ANGLE_DEADBAND    = 1.5                      # 角度变化 <1.5° 不发指令
LOST_TIMEOUT      = 2.0                      # 丢手后多少秒回到中点（0=不回中）

# --- 串口心跳 ---
HEARTBEAT_INTERVAL = 1.0                     # 每N秒发一次心跳（避免舵机失能后漂移）

# ====================  Download model  ====================
MODEL_PATH = "hand_landmarker.task"
MODEL_URL  = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/" \
             "hand_landmarker/float16/latest/hand_landmarker.task"
if not os.path.exists(MODEL_PATH):
    print(f"Downloading model to {MODEL_PATH} ...")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    print("Download complete")

# ====================  Init serial  ====================
from serial import Serial, SerialException

serial_ok = False
ser = None
try:
    ser = Serial(SERIAL_PORT, BAUDRATE, timeout=0.05)
    serial_ok = True
    print(f"Serial {SERIAL_PORT} @ {BAUDRATE} bps — OK")
except ImportError:
    print("pyserial not installed.  Running WITHOUT serial control.")
    print("  →  pip install pyserial")
except SerialException as e:
    print(f"Serial open failed: {e}")
    print("Running WITHOUT serial control.")

# ====================  Init MediaPipe  ====================
from mediapipe.tasks import python as mp_py
from mediapipe.tasks.python import vision as mp_vis

_opts = mp_vis.HandLandmarkerOptions(
    base_options=mp_py.BaseOptions(model_asset_path=MODEL_PATH),
    running_mode=mp_vis.RunningMode.VIDEO,
    num_hands=1,
    min_hand_detection_confidence=0.5,
    min_tracking_confidence=0.5,
)
hand_landmarker = mp_vis.HandLandmarker.create_from_options(_opts)

from mediapipe.tasks.python.vision import drawing_utils
from mediapipe.tasks.python.vision import HandLandmarksConnections

# ====================  Open camera  ====================
cap = cv2.VideoCapture(CAMERA_INDEX)
if not cap.isOpened():
    print(f"Camera index {CAMERA_INDEX} not found, trying index 0 …")
    CAMERA_INDEX = 0
    cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("Error: Cannot open any camera.")
    if serial_ok:
        ser.close()
    exit()

# 读一帧确认分辨率
ret, temp = cap.read()
if ret:
    cam_h, cam_w = temp.shape[:2]
else:
    cam_h, cam_w = 480, 640
# 重新打开（部分后端打开后再读首帧会慢）
cap.release()
cap = cv2.VideoCapture(CAMERA_INDEX)
if not cap.isOpened():
    cap = cv2.VideoCapture(0)

print(f"Camera: {cam_w}x{cam_h}  |  MediaPipe {mp.__version__}")
print(f"Pan  {PAN_MIN}–{PAN_MAX}   Tilt  {TILT_MIN}–{TILT_MAX}")
print("Press 'q' to quit\n")

# ====================  State  ====================
frame_ts_ms    = 0
frame_count    = 0
last_send_time = 0.0
last_heartbeat = time.time()

current_pan     = float(PAN_CENTER)
current_tilt    = float(TILT_CENTER)
last_sent_pan   = int(PAN_CENTER)
last_sent_tilt  = int(TILT_CENTER)

smooth_pan  = deque([float(PAN_CENTER)]  * SMOOTH_WINDOW, maxlen=SMOOTH_WINDOW)
smooth_tilt = deque([float(TILT_CENTER)] * SMOOTH_WINDOW, maxlen=SMOOTH_WINDOW)

hand_lost_at = None                          # 丢手时间戳（None=当前检测到手）

# ====================  Helper: send  ====================
def send_servo_cmd(pan: int, tilt: int) -> bool:
    """Send P<pan>\\n T<tilt>\\n.  Returns True on success."""
    global last_sent_pan, last_sent_tilt, last_send_time
    if not serial_ok:
        return False
    try:
        ser.write(f"P{pan}\nT{tilt}\n".encode())
        last_sent_pan  = pan
        last_sent_tilt = tilt
        last_send_time = time.time()
        return True
    except Exception as e:
        print(f"Serial write error: {e}")
        return False

def send_single(angle: int, axis: str) -> bool:
    """Send a single-axis command (used for fine adjustments)."""
    if not serial_ok:
        return False
    try:
        ser.write(f"{axis}{angle}\n".encode())
        return True
    except Exception:
        return False

# ====================  Helper: servo speed limiter  ====================
def rate_limit(desired: float, current: float, dt: float) -> float:
    """Limit angular change to MAX_DEG_PER_SEC."""
    if dt <= 0:
        return desired
    max_delta = MAX_DEG_PER_SEC * dt
    return np.clip(desired, current - max_delta, current + max_delta)

# ====================  Helper: dead-zone + P-control  ====================
def compute_angles(hand_cx, hand_cy, w, h):
    """
    Returns (new_pan, new_tilt, err_x, err_y).
    P-control inside dead-zone.
    """
    global current_pan, current_tilt

    cx, cy = w // 2, h // 2
    err_x = hand_cx - cx          # (+) 手在右边
    err_y = hand_cy - cy          # (+) 手在下边

    new_pan  = current_pan
    new_tilt = current_tilt

    # PAN
    if abs(err_x) > DEAD_ZONE_PX:
        delta = KP_X * (err_x / (w / 2)) * 90.0
        new_pan = np.clip(current_pan + delta, PAN_MIN, PAN_MAX)

    # TILT  (手往上 → tilt 增大)
    if abs(err_y) > DEAD_ZONE_PX:
        delta = -KP_Y * (err_y / (h / 2)) * 90.0
        new_tilt = np.clip(current_tilt + delta, TILT_MIN, TILT_MAX)

    return new_pan, new_tilt, err_x, err_y

# ====================  Initial → center  ====================
send_servo_cmd(PAN_CENTER, TILT_CENTER)
print("Sent center position (P90 T90)\n")

# ====================  Main loop  ====================
while True:
    t0 = time.time()

    ret, frame = cap.read()
    if not ret:
        print("Cannot read video frame")
        break

    # Mirror
    frame = cv2.flip(frame, 1)
    h, w = frame.shape[:2]
    cx, cy = w // 2, h // 2

    # RGB → MediaPipe Image
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

    result = hand_landmarker.detect_for_video(mp_img, frame_ts_ms)
    frame_ts_ms  += 33
    frame_count   += 1

    hand_found = False
    hand_cx = hand_cy = 0
    err_x = err_y = 0

    if result.hand_landmarks:
        for hl in result.hand_landmarks:
            hand_found = True
            lm_list = list(hl)

            # 手掌中心 = 21点平均
            cx_norm = sum(lm.x for lm in lm_list) / 21
            cy_norm = sum(lm.y for lm in lm_list) / 21
            hand_cx = int(cx_norm * w)
            hand_cy = int(cy_norm * h)

            # 绘制骨架
            drawing_utils.draw_landmarks(
                frame, hl,
                connections=HandLandmarksConnections.HAND_CONNECTIONS,
                connection_drawing_spec=drawing_utils.DrawingSpec(
                    color=(255, 255, 255), thickness=1),
                landmark_drawing_spec=drawing_utils.DrawingSpec(
                    color=(0, 255, 0), thickness=1, circle_radius=3),
            )

            # 手掌中心标记
            cv2.circle(frame, (hand_cx, hand_cy), 12, (0, 255, 255), -1)
            cv2.circle(frame, (hand_cx, hand_cy), 14, (0, 0, 0), 2)
            break

    # ---- 丢手检测 ----
    if hand_found:
        hand_lost_at = None                                 # 复位计时器
    else:
        if hand_lost_at is None:
            hand_lost_at = time.time()                      # 刚开始丢

    # ---- 计算目标角度 ----
    if hand_found:
        new_pan, new_tilt, err_x, err_y = compute_angles(hand_cx, hand_cy, w, h)
    else:
        # 手丢失：可选缓慢回中
        if LOST_TIMEOUT > 0 and hand_lost_at is not None:
            elapsed = time.time() - hand_lost_at
            if elapsed > LOST_TIMEOUT:
                # 超过超时 → 逐步回中
                new_pan  = current_pan  + (PAN_CENTER  - current_pan)  * 0.03
                new_tilt = current_tilt + (TILT_CENTER - current_tilt) * 0.03
            else:
                new_pan  = current_pan
                new_tilt = current_tilt
        else:
            new_pan  = current_pan
            new_tilt = current_tilt
        err_x = err_y = 0

    # ---- 速率限幅 (防突然跳变) ----
    dt = max(time.time() - t0, 0.001)                      # 至少 1ms
    current_pan  = rate_limit(new_pan,  current_pan,  dt)
    current_tilt = rate_limit(new_tilt, current_tilt, dt)

    # ---- 移动平均 ----
    smooth_pan.append(current_pan)
    smooth_tilt.append(current_tilt)
    pan_f  = sum(smooth_pan)  / SMOOTH_WINDOW
    tilt_f = sum(smooth_tilt) / SMOOTH_WINDOW

    # ---- 串口发送 (限间隔 + 限变化量) ----
    now = time.time()
    p_int = int(round(pan_f))
    t_int = int(round(tilt_f))

    can_send = (serial_ok
                and (now - last_send_time) >= MIN_SEND_INTERVAL
                and (abs(p_int - last_sent_pan)  >= ANGLE_DEADBAND
                     or abs(t_int - last_sent_tilt) >= ANGLE_DEADBAND))

    if can_send:
        send_servo_cmd(p_int, t_int)

    # ---- 心跳 (长时间不动时重发一次防止舵机漂移) ----
    if serial_ok and (now - last_send_time) > HEARTBEAT_INTERVAL:
        send_servo_cmd(p_int, t_int)
        last_heartbeat = now

    # ====================  HUD  ====================
    # 顶栏
    cv2.rectangle(frame, (0, 0), (w, 62), (15, 15, 15), -1)

    status_c = (0, 255, 0) if hand_found else (0, 0, 255)
    cv2.putText(frame, f"PAN:{p_int:3d}  TILT:{t_int:3d}",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_c, 2)
    cv2.putText(frame,
                f"SER: {'ON' if serial_ok else 'OFF'}  |  "
                f"Hand: {'Found' if hand_found else 'LOST'}"
                f"{' ('+str(int(time.time()-hand_lost_at))+'s)' if hand_lost_at and not hand_found else ''}"
                f"  |  Sending @ {1/MIN_SEND_INTERVAL:.0f} Hz",
                (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)

    if hand_found:
        cv2.putText(frame, f"Err: ({err_x:+4d}, {err_y:+4d})",
                    (hand_cx + 20, hand_cy - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)

    # 十字准星 + 死区圈
    cv2.line(frame, (cx - 15, cy), (cx + 15, cy), (0, 0, 255), 1)
    cv2.line(frame, (cx, cy - 15), (cx, cy + 15), (0, 0, 255), 1)
    cv2.circle(frame, (cx, cy), DEAD_ZONE_PX, (0, 0, 255), 1)

    # 方向标签
    cv2.putText(frame, "PAN <<",  (10, h - 55),  cv2.FONT_HERSHEY_SIMPLEX, 0.4, (120,120,120), 1)
    cv2.putText(frame, "PAN >>",  (w - 80, h - 55), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (120,120,120), 1)
    cv2.putText(frame, "TILT ^^", (w // 2 - 30, h - 55), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (120,120,120), 1)

    # 手→中心连线
    if hand_found:
        cv2.line(frame, (hand_cx, hand_cy), (cx, cy), (255, 255, 0), 1, cv2.LINE_AA)

    # 显示
    cv2.imshow("Pan/Tilt Hand Tracker", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# ====================  Cleanup  ====================
print("\nReturning servos to center …")
send_servo_cmd(PAN_CENTER, TILT_CENTER)
time.sleep(0.15)
cap.release()
cv2.destroyAllWindows()
hand_landmarker.close()
if serial_ok:
    ser.close()
print("Program exited")
