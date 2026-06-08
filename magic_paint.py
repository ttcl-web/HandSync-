"""
Neon Magic Paint — Air drawing with hand gestures
- Index finger = paint (neon glow trail)
- Open palm (5 fingers) = rainbow spray mode
- Fist (0 fingers) = clear canvas with particle burst
- Move hand up/down to change brush color (rainbow gradient)
- 'c' = clear canvas | 's' = save screenshot | 'q' = quit

Adapted for mediapipe 0.10.x (tasks API)
"""

import sys
import cv2
import mediapipe as mp
import numpy as np
import os
import urllib.request
import math
import random
from collections import deque

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ==================== Config ====================
CANVAS_FADE_SPEED = 0.95          # how fast old strokes fade (1.0 = never fade)
TRAIL_LENGTH = 8                  # number of trailing glow points
PARTICLE_COUNT = 80               # particles on clear
SPRAY_RADIUS = 35                 # spray mode scatter radius

WIN_NAME = "Neon Magic Paint — 'c' clear | 's' save | 'q' quit"

# ==================== Download model ====================
MODEL_PATH = "hand_landmarker.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"
if not os.path.exists(MODEL_PATH):
    print(f"Downloading model to {MODEL_PATH} ...")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    print("Download complete")

# ==================== Init MediaPipe ====================
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

options = mp_vision.HandLandmarkerOptions(
    base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
    running_mode=mp_vision.RunningMode.VIDEO,
    num_hands=1,
    min_hand_detection_confidence=0.5,
    min_tracking_confidence=0.5,
)
hand_landmarker = mp_vision.HandLandmarker.create_from_options(options)

# ==================== Drawing utils ====================
from mediapipe.tasks.python.vision import drawing_utils
from mediapipe.tasks.python.vision import HandLandmarksConnections

# ==================== Finger indices ====================
FINGER_TIPS = [4, 8, 12, 16, 20]
FINGER_PIPS = [2, 6, 10, 14, 18]

def count_extended_fingers(landmarks, h_label):
    """Count extended fingers (same logic as model.py)"""
    if len(landmarks) != 21:
        return 0
    count = 0
    thumb_tip = landmarks[4]
    thumb_mcp = landmarks[1]
    if h_label == "Left":
        if thumb_tip.x < thumb_mcp.x:
            count += 1
    else:
        if thumb_tip.x > thumb_mcp.x:
            count += 1
    for tip_idx, pip_idx in zip(FINGER_TIPS[1:], FINGER_PIPS[1:]):
        if landmarks[tip_idx].y < landmarks[pip_idx].y:
            count += 1
    return count


def hsv_to_bgr(h, s=1.0, v=1.0):
    """Convert HSV (0-360, 0-1, 0-1) to BGR (0-255)"""
    h = h % 360
    c = v * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = v - c
    if h < 60:   r, g, b = c, x, 0
    elif h < 120: r, g, b = x, c, 0
    elif h < 180: r, g, b = 0, c, x
    elif h < 240: r, g, b = 0, x, c
    elif h < 300: r, g, b = x, 0, c
    else:         r, g, b = c, 0, x
    return (int((b + m) * 255), int((g + m) * 255), int((r + m) * 255))


def create_glow_ring(frame, center, radius, color, alpha=0.6):
    """Draw a glowing ring overlay"""
    overlay = frame.copy()
    for r in range(radius, radius - 6, -2):
        a = alpha * (r / radius) * 0.5
        cv2.circle(overlay, center, r, color, -1)
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)


def draw_glow_line(frame, p1, p2, color, thickness=2):
    """Draw a line with neon glow effect"""
    # Outer glow
    cv2.line(frame, p1, p2, color, thickness + 4, cv2.LINE_AA)
    cv2.line(frame, p1, p2, (255, 255, 255), thickness, cv2.LINE_AA)
    cv2.line(frame, p1, p2, color, thickness, cv2.LINE_AA)


# ==================== Open camera ====================
cap = cv2.VideoCapture(1)
if not cap.isOpened():
    cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("Error: Cannot open any camera.")
    exit()

# Get frame dimensions first
ret, temp_frame = cap.read()
if not ret:
    print("Error: Cannot read from camera.")
    cap.release()
    exit()
temp_frame = cv2.flip(temp_frame, 1)
h, w = temp_frame.shape[:2]
cap.release()

# Re-open (some backends need this)
cap = cv2.VideoCapture(1)
if not cap.isOpened():
    cap = cv2.VideoCapture(0)

# ==================== Canvas ====================
canvas = np.zeros((h, w, 3), dtype=np.float32)  # float for smooth fading

# ==================== State ====================
prev_point = None        # previous finger position for smooth lines
trail = deque(maxlen=TRAIL_LENGTH)
particles = []           # active particle effects: [(x, y, vx, vy, life, color)]
current_mode = ""        # display string
hue_offset = 0           # rainbow cycling

print(f"Camera ready (MediaPipe {mp.__version__})")
print("Controls:  Index finger = paint | Fist = clear | Open palm = spray | 'c' clear | 's' save | 'q' quit")

frame_timestamp_ms = 0

while True:
    ret, frame = cap.read()
    if not ret:
        print("Cannot read video frame")
        break

    frame = cv2.flip(frame, 1)

    # ---- Fade canvas ----
    canvas = canvas * CANVAS_FADE_SPEED
    canvas_uint8 = np.clip(canvas, 0, 255).astype(np.uint8)

    # ---- Detect hands ----
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
    result = hand_landmarker.detect_for_video(mp_image, frame_timestamp_ms)
    frame_timestamp_ms += 33

    hand_detected = False
    finger_count = 0
    hand_label = "Right"
    tip_pos = None

    if result.hand_landmarks and result.handedness:
        for i, hand_landmarks in enumerate(result.hand_landmarks):
            hand_detected = True

            if i < len(result.handedness) and len(result.handedness[i]) > 0:
                hand_label = result.handedness[i][0].category_name

            finger_count = count_extended_fingers(hand_landmarks, hand_label)

            # Index fingertip (landmark 8)
            index_tip = hand_landmarks[8]
            tip_x = int(index_tip.x * w)
            tip_y = int(index_tip.y * h)
            tip_pos = (tip_x, tip_y)

            # Color: hue from vertical position (rainbow gradient top→bottom)
            hue = int(tip_y / h * 360 + hue_offset)
            paint_color = hsv_to_bgr(hue)

            # ---- Update trail ----
            trail.append(tip_pos)

            # ---- Draw hand skeleton ----
            conn_color = (255, 255, 255) if finger_count != 1 else paint_color
            conn_spec = drawing_utils.DrawingSpec(color=conn_color, thickness=1)
            point_spec = drawing_utils.DrawingSpec(color=paint_color, thickness=1, circle_radius=2)
            drawing_utils.draw_landmarks(
                frame, hand_landmarks,
                connections=HandLandmarksConnections.HAND_CONNECTIONS,
                connection_drawing_spec=conn_spec,
                landmark_drawing_spec=point_spec,
            )

            # ---- Index finger glow ring ----
            if finger_count == 1 or finger_count == 2:
                create_glow_ring(frame, tip_pos, 12, paint_color, 0.7)
                current_mode = "PAINT"
            elif finger_count == 5:
                create_glow_ring(frame, tip_pos, 28, paint_color, 0.5)
                current_mode = "SPRAY"
            elif finger_count == 0:
                current_mode = "CLEAR!"
            else:
                current_mode = "HOVER"

            break  # only first hand

    # ---- Paint / Spray / Clear ----
    if hand_detected and tip_pos is not None:
        if finger_count == 1:  # Index only = precise paint
            if prev_point is not None:
                # Draw on canvas between previous and current tip position
                dist = math.hypot(tip_pos[0] - prev_point[0], tip_pos[1] - prev_point[1])
                steps = max(int(dist / 3), 1)
                for s in range(steps + 1):
                    t = s / steps
                    ix = int(prev_point[0] + (tip_pos[0] - prev_point[0]) * t)
                    iy = int(prev_point[1] + (tip_pos[1] - prev_point[1]) * t)
                    cv2.circle(canvas, (ix, iy), 3, hsv_to_bgr(hue_offset + (iy / h * 360)),
                               -1, cv2.LINE_AA)

            # Also draw on canvas
            cv2.circle(canvas, tip_pos, 2, paint_color, -1, cv2.LINE_AA)
            prev_point = tip_pos

        elif finger_count == 2:  # Index + middle = thick paint
            if prev_point is not None:
                cv2.line(canvas, prev_point, tip_pos, paint_color, 5, cv2.LINE_AA)
            cv2.circle(canvas, tip_pos, 4, paint_color, -1, cv2.LINE_AA)
            prev_point = tip_pos
            current_mode = "THICK PAINT"

        elif finger_count == 5:  # Open palm = spray mode
            for _ in range(6):
                sx = tip_pos[0] + random.randint(-SPRAY_RADIUS, SPRAY_RADIUS)
                sy = tip_pos[1] + random.randint(-SPRAY_RADIUS, SPRAY_RADIUS)
                spray_color = hsv_to_bgr(random.randint(0, 360))
                cv2.circle(canvas, (sx, sy), 1, spray_color, -1, cv2.LINE_AA)
            prev_point = tip_pos

        elif finger_count == 0:  # Fist = clear canvas burst
            # Spawn particles
            for _ in range(PARTICLE_COUNT):
                angle = random.uniform(0, 2 * math.pi)
                speed = random.uniform(2, 12)
                vx = math.cos(angle) * speed
                vy = math.sin(angle) * speed
                life = random.uniform(0.5, 1.5)
                pcolor = hsv_to_bgr(random.randint(0, 360))
                particles.append((tip_pos[0], tip_pos[1], vx, vy, life, pcolor))
            # Clear canvas with fade (not instant — cool effect)
            canvas = np.zeros((h, w, 3), dtype=np.float32)
            prev_point = None

        else:  # 3 or 4 fingers = hover, no paint
            prev_point = None
    else:
        prev_point = None  # reset when hand lost

    # ---- Update & draw particles ----
    alive_particles = []
    for px, py, vx, vy, life, pcolor in particles:
        life -= 0.033  # ~30fps
        if life > 0:
            px += vx
            py += vy
            vy += 0.15  # gravity
            alpha = life / 1.5
            # Draw on canvas (where it might overlap)
            cv2.circle(canvas, (int(px), int(py)), 2 + int(life * 3),
                       pcolor, -1, cv2.LINE_AA)
            alive_particles.append((px, py, vx, vy, life, pcolor))
    particles = alive_particles

    # ---- Merge canvas onto frame ----
    # Convert canvas to uint8
    canvas_uint8 = np.clip(canvas, 0, 255).astype(np.uint8)
    # Mask: where canvas has color
    canvas_gray = cv2.cvtColor(canvas_uint8, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(canvas_gray, 5, 255, cv2.THRESH_BINARY)
    mask_inv = cv2.bitwise_not(mask)

    frame_bg = cv2.bitwise_and(frame, frame, mask=mask_inv)
    canvas_fg = cv2.bitwise_and(canvas_uint8, canvas_uint8, mask=mask)
    frame = cv2.add(frame_bg, canvas_fg)

    # ---- HUD ----
    # Top bar
    cv2.rectangle(frame, (0, 0), (w, 48), (20, 20, 20), -1)
    cv2.rectangle(frame, (0, 48), (w, 50), (60, 60, 60), -1)

    mode_colors = {
        "PAINT": (0, 255, 0),
        "THICK PAINT": (255, 200, 0),
        "SPRAY": (255, 0, 255),
        "HOVER": (128, 128, 128),
        "CLEAR!": (0, 0, 255),
    }
    mcolor = mode_colors.get(current_mode, (200, 200, 200))
    cv2.putText(frame, f"MODE: {current_mode}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, mcolor, 2)
    cv2.putText(frame, "| C=clear | S=save | Q=quit", (w - 300, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

    # ---- Trail dots on frame ----
    for j, tp in enumerate(trail):
        alpha_t = j / TRAIL_LENGTH
        r = int(4 * alpha_t) + 1
        c = hsv_to_bgr(hue_offset + (tp[1] / h * 360))
        cv2.circle(frame, tp, r, c, -1, cv2.LINE_AA)

    # ---- Show ----
    cv2.imshow(WIN_NAME, frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif key == ord('c'):
        canvas = np.zeros((h, w, 3), dtype=np.float32)
        particles.clear()
        print("Canvas cleared")
    elif key == ord('s'):
        # Save the current canvas
        save_frame = np.clip(canvas, 0, 255).astype(np.uint8)
        # Add canvas to background
        filename = f"painting_{len(os.listdir('.'))}.png"
        cv2.imwrite(filename, save_frame)
        print(f"Saved: {filename}")

    # Cycle hue
    hue_offset = (hue_offset + 0.5) % 360

# ==================== Release ====================
cap.release()
cv2.destroyAllWindows()
hand_landmarker.close()
print("Program exited")
