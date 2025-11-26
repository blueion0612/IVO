# hand_tracker_fixed.py
# 수정된 버전: 검지만 펴고 있을 때만 그리기 (히스테리시스 + normalized y 기반 판정)

import os
import sys
import json
import time
import math
import threading
import queue
import urllib.request
import cv2
import numpy as np

# Suppress MediaPipe warnings
os.environ["GLOG_minloglevel"] = "3"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
import logging
logging.getLogger().setLevel(logging.ERROR)

import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/"
             "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task")
MODEL_DIR = "models"
MODEL_PATH = os.path.join(MODEL_DIR, "hand_landmarker.task")

# Command queue for cross-platform stdin handling
cmd_queue = queue.Queue()


def stdin_reader(q):
    """Thread function to read stdin commands"""
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()
            if line:
                try:
                    cmd = json.loads(line)
                    q.put(cmd)
                except json.JSONDecodeError:
                    # Ignore invalid JSON
                    pass
        except Exception:
            break


def ensure_model():
    os.makedirs(MODEL_DIR, exist_ok=True)
    if not os.path.isfile(MODEL_PATH):
        print(json.dumps({"type": "status", "message": "Downloading MediaPipe model..."}))
        sys.stdout.flush()
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)


# Finger landmark indices (MediaPipe Hand)
IDX = dict(
    thumb=(1, 2, 3, 4),
    index=(5, 6, 7, 8),
    middle=(9, 10, 11, 12),
    ring=(13, 14, 15, 16),
    pinky=(17, 18, 19, 20)
)


def send_message(msg):
    """Send JSON message to Electron via stdout"""
    print(json.dumps(msg))
    sys.stdout.flush()


def angle_at(p_a, p_b, p_c):
    """Calculate angle at point p_b (for 일부 보조 로직)"""
    ba = (p_a[0] - p_b[0], p_a[1] - p_b[1])
    bc = (p_c[0] - p_b[0], p_c[1] - p_b[1])
    dot = ba[0] * bc[0] + ba[1] * bc[1]
    na = math.hypot(*ba)
    nb = math.hypot(*bc)
    if na * nb == 0:
        return 0.0
    cosv = max(-1.0, min(1.0, dot / (na * nb)))
    return math.degrees(math.acos(cosv))


def is_pinky_extended_reliable(lm_px):
    """
    새끼손가락 펴짐 판정 (캘리브레이션용)
    - 두 관절 각도
    - tip/pip 높이 관계
    - 팜과의 거리
    를 같이 보고 결정
    """
    pinky_mcp, pinky_pip, pinky_dip, pinky_tip = [lm_px[i] for i in IDX["pinky"]]

    # 각도 체크
    ang1 = angle_at(pinky_mcp, pinky_pip, pinky_dip)
    ang2 = angle_at(pinky_pip, pinky_dip, pinky_tip)

    # tip 이 pip 보다 위에 있으면 (y가 더 작으면) 펴진 편
    height_check = pinky_tip[1] < pinky_pip[1]

    # 손바닥과의 거리 비교
    palm_center = lm_px[0]
    dist_tip = math.hypot(pinky_tip[0] - palm_center[0], pinky_tip[1] - palm_center[1])
    dist_pip = math.hypot(pinky_pip[0] - palm_center[0], pinky_pip[1] - palm_center[1])
    dist_check = dist_tip > dist_pip * 1.2

    angle_extended = ang1 >= 150 and ang2 >= 150
    return angle_extended and (height_check or dist_check)


def smooth_point(prev, new, alpha=0.25):
    """Smooth point movement"""
    if prev is None:
        return new
    return {
        "x": alpha * new["x"] + (1 - alpha) * prev["x"],
        "y": alpha * new["y"] + (1 - alpha) * prev["y"]
    }


def compute_calibration_region(points, target_aspect=1.333):
    """Compute calibration region from 4 points with aspect ratio preservation"""
    if len(points) != 4:
        return None

    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    raw_width = max_x - min_x
    raw_height = max_y - min_y

    if raw_width < 0.01 or raw_height < 0.01:
        return None

    cx = (min_x + max_x) / 2.0
    cy = (min_y + max_y) / 2.0

    current_aspect = raw_width / raw_height if raw_height > 0 else target_aspect

    width = raw_width
    height = raw_height

    if current_aspect > target_aspect:
        height = width / target_aspect
    else:
        width = height * target_aspect

    half_w = width / 2.0
    half_h = height / 2.0

    min_x = max(0.0, cx - half_w)
    max_x = min(1.0, cx + half_w)
    min_y = max(0.0, cy - half_h)
    max_y = min(1.0, cy + half_h)

    return {
        "min_x": min_x,
        "min_y": min_y,
        "width": max_x - min_x,
        "height": max_y - min_y
    }


def apply_calibration(cursor_pos, region):
    """Apply calibration mapping to cursor position"""
    if cursor_pos is None or region is None:
        return cursor_pos

    if region["width"] > 0 and region["height"] > 0:
        x = (cursor_pos["x"] - region["min_x"]) / region["width"]
        y = (cursor_pos["y"] - region["min_y"] / region["height"])  # BUG? fix: parentheses
        # Actually need: (cursor_pos["y"] - region["min_y"]) / region["height"]
        # We'll correct below.

    # Corrected apply_calibration (we override above implementation):
    if cursor_pos is None or region is None:
        return cursor_pos

    if region["width"] > 0 and region["height"] > 0:
        x = (cursor_pos["x"] - region["min_x"]) / region["width"]
        y = (cursor_pos["y"] - region["min_y"]) / region["height"]

        x = max(0.0, min(1.0, x))
        y = max(0.0, min(1.0, y))

        return {"x": x, "y": y}
    else:
        return cursor_pos


# --------- Normalized landmark 기반 손가락 펴짐 판정 ---------


def finger_open_norm(lm, tip_idx, pip_idx, margin=0.02):
    """
    normalized landmark 기반 손가락 펴짐 판정
    - lm: result.hand_landmarks[0] (0~1 범위)
    - y는 아래로 증가 → tip.y < pip.y 이면 '위에 있음' = 펴진 상태
    - margin: 오차 허용 (화면 높이의 비율)
    """
    tip_y = lm[tip_idx].y
    pip_y = lm[pip_idx].y
    return tip_y < (pip_y - margin)


def is_only_index_extended_norm(lm, margin=0.02):
    """
    index finger만 펴져 있는지 판정 (엄지는 무시)
    lm: normalized landmarks (result.hand_landmarks[0])
    """
    index_open = finger_open_norm(lm, 8, 6, margin)
    middle_open = finger_open_norm(lm, 12, 10, margin)
    ring_open = finger_open_norm(lm, 16, 14, margin)
    pinky_open = finger_open_norm(lm, 20, 18, margin)

    # 엄지는 자유, 나머지 3개 손가락은 모두 접혀 있어야 함
    return index_open and not (middle_open or ring_open or pinky_open)

def is_thumb_touch_middle_pip_norm(lm, distance_threshold=0.04):
    """
    엄지 끝(4)이 중지 세 번째 마디(PIP, 10)에 '닿았다고' 볼 수 있을 정도로
    가까운지 판단 (normalized 좌표 기준)
    - lm: result.hand_landmarks[0] (0~1 범위)
    - distance_threshold: 허용 거리 (0~1 중 비율, 필요하면 조정)
    """
    thumb_tip = lm[4]   # THUMB_TIP
    middle_pip = lm[10] # MIDDLE_PIP (중지 세 번째 마디)

    dx = thumb_tip.x - middle_pip.x
    dy = thumb_tip.y - middle_pip.y
    dist = math.hypot(dx, dy)

    return dist < distance_threshold


def is_draw_gesture_norm(lm, distance_threshold=0.04):
    """
    '그리기' 제스처:
      - 엄지 끝이 중지 PIP(세 번째 마디)에 닿아 있을 때
    """
    return is_thumb_touch_middle_pip_norm(lm, distance_threshold=distance_threshold)


def main():
    ensure_model()

    # Start stdin reader thread
    reader_thread = threading.Thread(target=stdin_reader, args=(cmd_queue,), daemon=True)
    reader_thread.start()

    # Redirect stderr to devnull
    if os.name == 'nt':
        stderr_backup = sys.stderr
        sys.stderr = open(os.devnull, 'w')

    # Initialize MediaPipe
    BaseOptions = mp_python.BaseOptions
    HandLandmarker = vision.HandLandmarker
    HandLandmarkerOptions = vision.HandLandmarkerOptions
    RunningMode = vision.RunningMode

    options = HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=RunningMode.VIDEO,
        num_hands=1,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    landmarker = HandLandmarker.create_from_options(options)

    # Open webcam
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(0)


    
    if not cap.isOpened():
        send_message({"type": "error", "message": "Cannot open webcam"})
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)

    actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    send_message({
        "type": "ready",
        "camera": {
            "width": actual_width,
            "height": actual_height
        }
    })

    # States
    last_cursor = None
    was_drawing = False
    cursor_buffer = []
    BUFFER_SIZE = 3

    # Drawing hysteresis (연속 프레임 기준으로 on/off 결정)
    stable_can_draw = False
    draw_on_count = 0
    draw_off_count = 0
    DRAW_ON_FRAMES = 4   # 최소 4프레임 연속 true면 그리기 시작
    DRAW_OFF_FRAMES = 4  # 최소 4프레임 연속 false면 그리기 종료

    # Calibration states
    calibrating = False
    calibration_points = []
    calibration_region = None
    prev_pinky_ext = False
    last_calibration_time = 0
    CALIBRATION_COOLDOWN = 0.5

    ts_ms = 0
    frame_count = 0
    fps_timer = time.time()

    try:
        while True:
            # Process queued commands from stdin
            while not cmd_queue.empty():
                try:
                    cmd = cmd_queue.get_nowait()
                    command = cmd.get("command")

                    if command == "start_calibration":
                        calibrating = True
                        calibration_points = []
                        calibration_region = None
                        # 캘리브레이션 들어갈 때는 그리기 강제 off + 상태 초기화
                        stable_can_draw = False
                        draw_on_count = 0
                        draw_off_count = 0
                        if was_drawing:
                            send_message({"type": "draw_disable"})
                            was_drawing = False

                        send_message({"type": "calibration_started"})
                        send_message({"type": "status", "message": "Calibration started - mark 4 corners"})

                    elif command == "reset_calibration":
                        calibration_region = None
                        calibration_points = []
                        calibrating = False
                        send_message({"type": "calibration_reset"})
                        send_message({"type": "status", "message": "Calibration reset"})

                except queue.Empty:
                    break
                except Exception as e:
                    send_message({"type": "error", "message": f"Command error: {str(e)}"})

            ret, frame = cap.read()
            if not ret:
                continue

            # Flip frame horizontally
            frame = cv2.flip(frame, 1)

            # FPS calculation
            frame_count += 1
            current_time = time.time()
            if current_time - fps_timer >= 1.0:
                fps = frame_count / (current_time - fps_timer)
                send_message({"type": "fps", "value": round(fps, 1)})
                frame_count = 0
                fps_timer = current_time

            # Convert BGR to RGB for MediaPipe
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

            # Detect hands
            result = landmarker.detect_for_video(mp_image, ts_ms)
            ts_ms += 33  # ~30fps

            if result.hand_landmarks and len(result.hand_landmarks) > 0:
                # Process first hand
                landmarks = result.hand_landmarks[0]

                # Convert to pixel coordinates
                h, w = frame.shape[:2]
                lm_px = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]

                # Get index finger tip position (normalized)
                tip_idx = 8
                cursor_pos = {
                    "x": landmarks[tip_idx].x,
                    "y": landmarks[tip_idx].y
                }

                # Buffer for smoothing
                cursor_buffer.append(cursor_pos)
                if len(cursor_buffer) > BUFFER_SIZE:
                    cursor_buffer.pop(0)

                if len(cursor_buffer) > 0:
                    avg_x = sum(p["x"] for p in cursor_buffer) / len(cursor_buffer)
                    avg_y = sum(p["y"] for p in cursor_buffer) / len(cursor_buffer)
                    cursor_pos = {"x": avg_x, "y": avg_y}

                cursor_pos = smooth_point(last_cursor, cursor_pos, alpha=0.3)
                last_cursor = cursor_pos

                if calibrating:
                    # Calibration mode: pinky up->down = add point
                    pinky_ext = is_pinky_extended_reliable(lm_px)
                    current_time = time.time()

                    # 캘리브레이션 중에는 항상 그리기 off + 히스테리시스 상태 초기화
                    stable_can_draw = False
                    draw_on_count = 0
                    draw_off_count = 0
                    can_draw = False
                    if was_drawing:
                        send_message({"type": "draw_disable"})
                        was_drawing = False

                    if prev_pinky_ext and not pinky_ext and cursor_pos is not None:
                        # falling edge + 쿨다운
                        if current_time - last_calibration_time > CALIBRATION_COOLDOWN:
                            calibration_points.append(cursor_pos.copy())
                            last_calibration_time = current_time

                            send_message({
                                "type": "calibration_point",
                                "index": len(calibration_points),
                                "position": cursor_pos,
                                "total": 4
                            })

                            if len(calibration_points) == 4:
                                calibration_region = compute_calibration_region(
                                    calibration_points,
                                    target_aspect=actual_width / actual_height
                                )
                                calibrating = False

                                if calibration_region:
                                    send_message({
                                        "type": "calibration_done",
                                        "region": calibration_region
                                    })
                                    send_message({
                                        "type": "status",
                                        "message": "Calibration complete!"
                                    })
                                else:
                                    send_message({
                                        "type": "calibration_failed",
                                        "message": "Calibration area too small"
                                    })
                                    calibration_points = []

                    prev_pinky_ext = pinky_ext

                else:
                    # Normal mode: Only draw when ONLY index is extended (normalized landmarks)
                    raw_can_draw = is_draw_gesture_norm(landmarks, distance_threshold=0.04)

                    # ---- 히스테리시스 적용 ----
                    if raw_can_draw:
                        draw_on_count += 1
                        draw_off_count = 0
                    else:
                        draw_off_count += 1
                        draw_on_count = 0

                    if not stable_can_draw and draw_on_count >= DRAW_ON_FRAMES:
                        stable_can_draw = True
                    elif stable_can_draw and draw_off_count >= DRAW_OFF_FRAMES:
                        stable_can_draw = False

                    can_draw = stable_can_draw

                    # Send drawing state changes
                    if can_draw != was_drawing:
                        if can_draw:
                            send_message({"type": "draw_enable"})
                        else:
                            send_message({"type": "draw_disable"})
                        was_drawing = can_draw

                # Apply calibration if available
                if calibration_region is not None:
                    mapped_cursor = apply_calibration(cursor_pos, calibration_region)
                else:
                    mapped_cursor = cursor_pos

                # Send cursor position
                send_message({
                    "type": "cursor",
                    "position": mapped_cursor,
                    "drawing": can_draw if not calibrating else False,
                    "calibrating": calibrating,
                    "calibrated": calibration_region is not None
                })

            else:
                # No hand detected
                cursor_buffer.clear()

                if was_drawing:
                    send_message({"type": "draw_disable"})
                    was_drawing = False

                stable_can_draw = False
                draw_on_count = 0
                draw_off_count = 0

                send_message({
                    "type": "cursor",
                    "position": None,
                    "drawing": False,
                    "calibrating": calibrating,
                    "calibrated": calibration_region is not None
                })

                last_cursor = None
                prev_pinky_ext = False

    except KeyboardInterrupt:
        pass
    except Exception as e:
        send_message({"type": "error", "message": str(e)})
    finally:
        cap.release()
        if os.name == 'nt' and 'stderr_backup' in locals():
            sys.stderr = stderr_backup
        send_message({"type": "shutdown"})


if __name__ == "__main__":
    main()
