"""
Hand tracking + serial left/right detection
- MediaPipe hand landmark detection (0.10.x tasks API)
- Hand on left  → sends "1" over serial
- Hand on right → sends "2" over serial
Press 'q' to quit
"""

import sys
import cv2
import mediapipe as mp
import numpy as np
import os
import urllib.request

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ==================== Config ====================
# Serial port (change to your actual COM port)
SERIAL_PORT = 'COM9'
BAUDRATE = 115200

# Dead zone: +/- N pixels around center, no send in this zone
DEAD_ZONE = 30

# Cooldown: skip sending if same command was sent within N frames
COOLDOWN = 10

WIN_NAME = "Hand Tracking - Press 'q' to quit"

# ==================== Download model file (if not exists) ====================
MODEL_PATH = "hand_landmarker.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"

if not os.path.exists(MODEL_PATH):
    print(f"Downloading model to {MODEL_PATH} ...")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    print("Download complete")

# ==================== Init serial port ====================
serial_available = False
try:
    import serial
    ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=0.1)
    serial_available = True
    print(f"Serial port {SERIAL_PORT} opened OK")
except ImportError:
    print("pyserial not installed. Running without serial control.")
    print("Install: pip install pyserial")
except Exception as e:
    print(f"Serial open failed: {e}")
    print("Running without serial control.")

# ==================== Init MediaPipe HandLandmarker ====================
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

BaseOptions = mp_python.BaseOptions
HandLandmarker = mp_vision.HandLandmarker
HandLandmarkerOptions = mp_vision.HandLandmarkerOptions
VisionRunningMode = mp_vision.RunningMode

options = HandLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=MODEL_PATH),
    running_mode=VisionRunningMode.VIDEO,
    num_hands=1,
    min_hand_detection_confidence=0.5,
    min_tracking_confidence=0.5,
)
hand_landmarker = HandLandmarker.create_from_options(options)

# ==================== Drawing utils ====================
from mediapipe.tasks.python.vision import drawing_utils
from mediapipe.tasks.python.vision import HandLandmarksConnections

conn_spec = drawing_utils.DrawingSpec(color=(255, 0, 0), thickness=2)
point_spec = drawing_utils.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=3)

# ==================== State ====================
last_command = None       # "1" or "2" or None
cooldown_counter = 0

def send_command(cmd):
    """Send command string over serial"""
    global last_command, cooldown_counter
    if not serial_available:
        return
    if cmd != last_command and cooldown_counter <= 0:
        try:
            ser.write(cmd.encode())
            print(f"Sent: {cmd.strip()}")
            last_command = cmd
            cooldown_counter = COOLDOWN
        except Exception as e:
            print(f"Serial write error: {e}")

# ==================== Open camera ====================
# [Built-in camera] cap = cv2.VideoCapture(0)
# [External USB camera] use index 1
cap = cv2.VideoCapture(1)
if not cap.isOpened():
    # Fallback to built-in if external not found
    print("External camera (index 1) not found, trying built-in (index 0)...")
    cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("Error: Cannot open any camera.")
    if serial_available:
        ser.close()
    exit()

print(f"Camera ready (MediaPipe {mp.__version__}), press 'q' to quit")

# ==================== Frame timestamp counter ====================
frame_timestamp_ms = 0

while True:
    ret, frame = cap.read()
    if not ret:
        print("Cannot read video frame")
        break

    # Mirror-like horizontal flip
    frame = cv2.flip(frame, 1)
    h, w, _ = frame.shape
    center_x = w // 2

    # Convert to RGB and wrap as MediaPipe Image
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

    # Detect hands
    result = hand_landmarker.detect_for_video(mp_image, frame_timestamp_ms)
    frame_timestamp_ms += 33  # ~30fps

    # Cooldown tick
    if cooldown_counter > 0:
        cooldown_counter -= 1

    target_found = False
    side = None  # "L" or "R"

    if result.hand_landmarks:
        for hand_landmarks in result.hand_landmarks:
            # Draw hand skeleton
            drawing_utils.draw_landmarks(
                frame,
                hand_landmarks,
                connections=HandLandmarksConnections.HAND_CONNECTIONS,
                connection_drawing_spec=conn_spec,
                landmark_drawing_spec=point_spec,
            )

            # Calculate hand center (average of all 21 landmarks)
            cx = sum([lm.x for lm in hand_landmarks]) / 21
            target_x = int(cx * w)
            target_y = int(sum([lm.y for lm in hand_landmarks]) / 21 * h)

            # Mark hand center
            cv2.circle(frame, (target_x, target_y), 10, (0, 255, 0), -1)

            # Determine side
            if target_x < center_x - DEAD_ZONE:
                side = "L"
            elif target_x > center_x + DEAD_ZONE:
                side = "R"
            else:
                side = None  # dead zone

            target_found = True

            # Display info
            side_text = f"Side: {side}" if side else "Side: (dead zone)"
            cv2.putText(frame, side_text, (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            # Only process first hand
            break

    # Draw center line
    cv2.line(frame, (center_x, 0), (center_x, h), (0, 0, 255), 1)
    # Draw dead zone boundaries
    cv2.line(frame, (center_x - DEAD_ZONE, 0), (center_x - DEAD_ZONE, h), (0, 0, 255), 1)
    cv2.line(frame, (center_x + DEAD_ZONE, 0), (center_x + DEAD_ZONE, h), (0, 0, 255), 1)

    # Label zones
    cv2.putText(frame, "L (send 1)", (10, h - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    cv2.putText(frame, "R (send 2)", (w - 100, h - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

    # Send serial command based on side
    if not target_found:
        # No hand detected → reset
        last_command = None
    elif side == "L":
        send_command("1\n")
    elif side == "R":
        send_command("2\n")
    else:
        # In dead zone → reset so next move triggers a send
        last_command = None

    # Show frame
    cv2.imshow(WIN_NAME, frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# ==================== Release resources ====================
cap.release()
cv2.destroyAllWindows()
hand_landmarker.close()
if serial_available:
    ser.close()
print("Program exited")
