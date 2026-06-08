"""
Hand gesture number recognition (0-5)
- MediaPipe hand landmark detection (0.10.x tasks API)
- Counts extended fingers to recognize numbers 0~5
- Press 'q' to quit
"""

import sys
import cv2
import mediapipe as mp
import os
import urllib.request

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ==================== Download model file (if not exists) ====================
MODEL_PATH = "hand_landmarker.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"

if not os.path.exists(MODEL_PATH):
    print(f"Downloading model to {MODEL_PATH} ...")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    print("Download complete")

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
    num_hands=2,
    min_hand_detection_confidence=0.5,
    min_tracking_confidence=0.5,
)
hand_landmarker = HandLandmarker.create_from_options(options)

# ==================== Drawing utils ====================
from mediapipe.tasks.python.vision import drawing_utils
from mediapipe.tasks.python.vision import HandLandmarksConnections

conn_spec = drawing_utils.DrawingSpec(color=(255, 0, 0), thickness=2)
point_spec = drawing_utils.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=3)

# ==================== Finger landmark indices ====================
# MediaPipe hand topology:
#   Thumb:  0(wrist) - 1 - 2 - 3 - 4(tip)
#   Index:  0(wrist) - 5 - 6 - 7 - 8(tip)
#   Middle: 0(wrist) - 9 -10 -11 -12(tip)
#   Ring:   0(wrist) -13 -14 -15 -16(tip)
#   Pinky:  0(wrist) -17 -18 -19 -20(tip)

FINGER_TIPS = [4, 8, 12, 16, 20]         # thumb, index, middle, ring, pinky
FINGER_PIPS = [2, 6, 10, 14, 18]          # PIP joints for comparison
FINGER_MCPS = [1, 5, 9,  13, 17]          # MCP joints (base of finger)

def count_extended_fingers(landmarks, handedness_label):
    """
    Count extended fingers based on landmark positions.
    - For thumb:  compare tip.x vs MCP.x (horizontal, depends on hand side)
    - For other 4 fingers: compare tip.y vs PIP.y (vertical)
    Returns: int (0-5)
    """
    if len(landmarks) != 21:
        return 0

    count = 0

    # --- Thumb (index 4) ---
    # Thumb goes sideways. For LEFT hand: thumb extended = tip.x < MCP.x
    # For RIGHT hand: thumb extended = tip.x > MCP.x
    thumb_tip = landmarks[4]
    thumb_mcp = landmarks[1]
    if handedness_label == "Left":
        if thumb_tip.x < thumb_mcp.x:
            count += 1
    else:  # Right
        if thumb_tip.x > thumb_mcp.x:
            count += 1

    # --- Index, Middle, Ring, Pinky (tips 8, 12, 16, 20) ---
    # Extended if tip.y < PIP.y (tip is above the middle joint)
    for tip_idx, pip_idx in zip(FINGER_TIPS[1:], FINGER_PIPS[1:]):
        if landmarks[tip_idx].y < landmarks[pip_idx].y:
            count += 1

    return count

# ==================== Colors for each number ====================
NUM_COLORS = [
    (0, 0, 255),      # 0 - red
    (0, 255, 0),      # 1 - green
    (255, 0, 0),      # 2 - blue
    (0, 255, 255),    # 3 - yellow
    (255, 0, 255),    # 4 - magenta
    (255, 255, 0),    # 5 - cyan
]

# ==================== Open camera ====================
cap = cv2.VideoCapture(1)
if not cap.isOpened():
    print("External camera (index 1) not found, trying built-in (index 0)...")
    cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("Error: Cannot open any camera.")
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

    # Convert to RGB and wrap as MediaPipe Image
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

    # Detect hands
    result = hand_landmarker.detect_for_video(mp_image, frame_timestamp_ms)
    frame_timestamp_ms += 33  # ~30fps

    total_count = 0
    if result.hand_landmarks and result.handedness:
        for i, hand_landmarks in enumerate(result.hand_landmarks):
            # Get handedness (Left / Right)
            h_label = "Right"
            if i < len(result.handedness) and len(result.handedness[i]) > 0:
                h_label = result.handedness[i][0].category_name

            # Draw hand skeleton
            drawing_utils.draw_landmarks(
                frame,
                hand_landmarks,
                connections=HandLandmarksConnections.HAND_CONNECTIONS,
                connection_drawing_spec=conn_spec,
                landmark_drawing_spec=point_spec,
            )

            # Count extended fingers
            num = count_extended_fingers(hand_landmarks, h_label)
            total_count += num

            # Get wrist position for text placement
            wrist = hand_landmarks[0]
            wx, wy = int(wrist.x * w), int(wrist.y * h)

            # Display number above wrist
            color = NUM_COLORS[min(num, 5)]
            cv2.putText(frame, f"{num}", (wx - 20, wy - 30),
                        cv2.FONT_HERSHEY_DUPLEX, 2.0, color, 4)
            cv2.putText(frame, f"({h_label} hand)", (wx - 30, wy + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

    # Display total at top-left
    cv2.putText(frame, f"Number: {total_count}", (10, 40),
                cv2.FONT_HERSHEY_DUPLEX, 1.0, NUM_COLORS[min(total_count, 5)], 3)

    # Display hint
    cv2.putText(frame, "Press 'q' to quit", (10, h - 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

    # Show frame
    cv2.imshow("Hand Gesture Number Recognition", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# ==================== Release resources ====================
cap.release()
cv2.destroyAllWindows()
hand_landmarker.close()
print("Program exited")
