#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Hand Tracking Module for IVO (IMU-Vision Overlay)

Uses MediaPipe HandLandmarker for real-time hand tracking and gesture detection.
Communicates with Electron via JSON over stdout.

Features:
- 21-point hand landmark detection
- Drawing gesture detection (thumb touching middle finger PIP)
- Pinky extension detection for calibration
- 4-point calibration region mapping
- Hysteresis-based gesture state management
"""

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
    """Thread function to read stdin commands."""
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
                    pass
        except Exception:
            break


def ensure_model():
    """Download MediaPipe hand landmarker model if not present."""
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
    """Send JSON message to Electron via stdout."""
    print(json.dumps(msg))
    sys.stdout.flush()


def angle_at(p_a, p_b, p_c):
    """Calculate angle at point p_b formed by points p_a, p_b, p_c."""
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
    Detect pinky finger extension for calibration.

    Uses multiple criteria:
    - Joint angles at PIP and DIP
    - Tip/PIP height relationship
    - Distance from palm center
    """
    pinky_mcp, pinky_pip, pinky_dip, pinky_tip = [lm_px[i] for i in IDX["pinky"]]

    # Check joint angles
    ang1 = angle_at(pinky_mcp, pinky_pip, pinky_dip)
    ang2 = angle_at(pinky_pip, pinky_dip, pinky_tip)

    # Check if tip is above PIP (y decreases upward)
    height_check = pinky_tip[1] < pinky_pip[1]

    # Check distance from palm center
    palm_center = lm_px[0]
    dist_tip = math.hypot(pinky_tip[0] - palm_center[0], pinky_tip[1] - palm_center[1])
    dist_pip = math.hypot(pinky_pip[0] - palm_center[0], pinky_pip[1] - palm_center[1])
    dist_check = dist_tip > dist_pip * 1.2

    angle_extended = ang1 >= 150 and ang2 >= 150
    return angle_extended and (height_check or dist_check)


def smooth_point(prev, new, alpha=0.25):
    """Apply exponential smoothing to cursor position."""
    if prev is None:
        return new
    return {
        "x": alpha * new["x"] + (1 - alpha) * prev["x"],
        "y": alpha * new["y"] + (1 - alpha) * prev["y"]
    }


def compute_calibration_region(points, target_aspect=None):
    """
    Compute calibration region as the minimum bounding rectangle of 4 points.

    Simply uses the min/max of the 4 calibration points to create a bounding box.
    No aspect ratio adjustment - direct linear mapping from camera space to screen.
    """
    if len(points) != 4:
        return None

    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    width = max_x - min_x
    height = max_y - min_y

    # Minimum size check
    if width < 0.01 or height < 0.01:
        return None

    return {
        "min_x": min_x,
        "min_y": min_y,
        "width": width,
        "height": height
    }


def apply_calibration(cursor_pos, region):
    """Map cursor position to calibration region."""
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


def finger_open_norm(lm, tip_idx, pip_idx, margin=0.02):
    """
    Check if finger is extended using normalized landmarks.

    Args:
        lm: Normalized landmarks (0-1 range)
        tip_idx: Fingertip landmark index
        pip_idx: PIP joint landmark index
        margin: Tolerance margin (fraction of screen height)

    Returns:
        True if finger tip is above PIP joint
    """
    tip_y = lm[tip_idx].y
    pip_y = lm[pip_idx].y
    return tip_y < (pip_y - margin)


def is_only_index_extended_norm(lm, margin=0.02):
    """
    Check if only index finger is extended (thumb ignored).

    Args:
        lm: Normalized landmarks
        margin: Tolerance margin

    Returns:
        True if only index finger is extended
    """
    index_open = finger_open_norm(lm, 8, 6, margin)
    middle_open = finger_open_norm(lm, 12, 10, margin)
    ring_open = finger_open_norm(lm, 16, 14, margin)
    pinky_open = finger_open_norm(lm, 20, 18, margin)

    return index_open and not (middle_open or ring_open or pinky_open)


def is_thumb_touch_middle_pip_norm(lm, distance_threshold=0.04):
    """
    Check if thumb tip is touching middle finger PIP joint.

    Args:
        lm: Normalized landmarks
        distance_threshold: Maximum distance to consider as touching

    Returns:
        True if thumb is touching middle PIP
    """
    thumb_tip = lm[4]     # THUMB_TIP
    middle_pip = lm[10]   # MIDDLE_PIP

    dx = thumb_tip.x - middle_pip.x
    dy = thumb_tip.y - middle_pip.y
    dist = math.hypot(dx, dy)

    return dist < distance_threshold


def is_draw_gesture_norm(lm, distance_threshold=0.04):
    """
    Detect drawing gesture: thumb touching middle finger PIP.

    Args:
        lm: Normalized landmarks
        distance_threshold: Touch detection threshold

    Returns:
        True if drawing gesture is detected
    """
    return is_thumb_touch_middle_pip_norm(lm, distance_threshold=distance_threshold)


class DoubleTapDetector:
    """
    Detect double-tap gesture (thumb touching middle PIP twice quickly).

    Used for calibration point marking.
    """
    def __init__(self, tap_timeout=0.4, min_gap=0.1):
        """
        Args:
            tap_timeout: Maximum time between taps (seconds)
            min_gap: Minimum time between tap release and next tap (seconds)
        """
        self.tap_timeout = tap_timeout
        self.min_gap = min_gap
        self.last_tap_time = 0
        self.tap_count = 0
        self.was_touching = False
        self.last_release_time = 0

    def update(self, is_touching):
        """
        Update detector state and check for double-tap.

        Args:
            is_touching: Whether thumb is currently touching middle PIP

        Returns:
            True if double-tap detected
        """
        current_time = time.time()
        double_tap_detected = False

        # Detect rising edge (not touching -> touching)
        if is_touching and not self.was_touching:
            # Check if this is a valid tap (not too soon after last release)
            if current_time - self.last_release_time >= self.min_gap:
                # Check if within timeout of last tap
                if current_time - self.last_tap_time <= self.tap_timeout:
                    self.tap_count += 1
                else:
                    self.tap_count = 1

                self.last_tap_time = current_time

                # Double tap detected
                if self.tap_count >= 2:
                    double_tap_detected = True
                    self.tap_count = 0

        # Detect falling edge (touching -> not touching)
        if not is_touching and self.was_touching:
            self.last_release_time = current_time

        self.was_touching = is_touching
        return double_tap_detected

    def reset(self):
        """Reset detector state."""
        self.tap_count = 0
        self.last_tap_time = 0
        self.last_release_time = 0
        self.was_touching = False


def parse_args():
    """Parse command line arguments."""
    import argparse
    parser = argparse.ArgumentParser(description="Hand Tracking for IVO")
    parser.add_argument('--camera', type=int, default=0,
                        help='Camera device index (default: 0)')
    parser.add_argument('--camera-name', type=str, default='',
                        help='Camera device name for matching (overrides --camera)')
    return parser.parse_args()


def enumerate_cameras(max_cameras=10):
    """
    Enumerate available cameras and their names (Windows only).

    On Windows, uses DirectShow to get camera names.
    Returns list of (index, name) tuples.
    """
    cameras = []

    if os.name == 'nt':
        # Try to get camera names using Windows API
        try:
            from pygrabber.dshow_graph import FilterGraph
            graph = FilterGraph()
            devices = graph.get_input_devices()
            for idx, name in enumerate(devices):
                cameras.append((idx, name))
            return cameras
        except ImportError:
            pass

        # Fallback: try cv2 with DirectShow and just check which indices work
        for idx in range(max_cameras):
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
            if cap.isOpened():
                # Try to get backend name
                backend = cap.getBackendName()
                cameras.append((idx, f"Camera {idx} ({backend})"))
                cap.release()
    else:
        # Linux/Mac: just check which indices work
        for idx in range(max_cameras):
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                cameras.append((idx, f"Camera {idx}"))
                cap.release()

    return cameras


def find_camera_by_name(camera_name, max_cameras=10):
    """
    Find camera index by matching name.

    Uses substring matching (case-insensitive).
    Returns camera index or 0 if not found.
    """
    if not camera_name:
        return 0

    camera_name_lower = camera_name.lower()

    # Try pygrabber first (Windows DirectShow device enumeration)
    if os.name == 'nt':
        try:
            from pygrabber.dshow_graph import FilterGraph
            graph = FilterGraph()
            devices = graph.get_input_devices()

            # Exact match first
            for idx, name in enumerate(devices):
                if name.lower() == camera_name_lower:
                    send_message({"type": "status", "message": f"Camera matched (exact): {name} at index {idx}"})
                    return idx

            # Substring match
            for idx, name in enumerate(devices):
                if camera_name_lower in name.lower() or name.lower() in camera_name_lower:
                    send_message({"type": "status", "message": f"Camera matched (partial): {name} at index {idx}"})
                    return idx

            send_message({"type": "status", "message": f"Camera not found by name: {camera_name}. Available: {devices}"})

        except ImportError:
            send_message({"type": "status", "message": "pygrabber not available, falling back to index 0"})

    # Fallback to first available camera
    return 0


def main():
    """Main entry point for hand tracking."""
    args = parse_args()

    # Determine camera index
    camera_name = getattr(args, 'camera_name', '')
    if camera_name:
        camera_index = find_camera_by_name(camera_name)
        send_message({"type": "status", "message": f"Using camera name '{camera_name}' -> index {camera_index}"})
    else:
        camera_index = args.camera

    ensure_model()

    # Start stdin reader thread
    reader_thread = threading.Thread(target=stdin_reader, args=(cmd_queue,), daemon=True)
    reader_thread.start()

    # Redirect stderr to devnull on Windows
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

    # Open webcam with selected camera index
    if os.name == "nt":
        cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    else:
        cap = cv2.VideoCapture(camera_index)

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
            "index": camera_index,
            "width": actual_width,
            "height": actual_height
        }
    })

    # Tracking states
    last_cursor = None
    was_drawing = False
    cursor_buffer = []
    BUFFER_SIZE = 3

    # Drawing hysteresis (consecutive frames for on/off decision)
    stable_can_draw = False
    draw_on_count = 0
    draw_off_count = 0
    DRAW_ON_FRAMES = 4   # Minimum consecutive frames to start drawing
    DRAW_OFF_FRAMES = 4  # Minimum consecutive frames to stop drawing

    # Calibration states
    calibrating = False
    calibration_points = []
    calibration_region = None
    last_calibration_time = 0
    CALIBRATION_COOLDOWN = 0.3

    # Double-tap detector for calibration
    calibration_tap_detector = DoubleTapDetector(tap_timeout=0.4, min_gap=0.1)

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
                        # Force drawing off and reset state during calibration
                        stable_can_draw = False
                        draw_on_count = 0
                        draw_off_count = 0
                        if was_drawing:
                            send_message({"type": "draw_disable"})
                            was_drawing = False

                        # Reset double-tap detector for fresh calibration
                        calibration_tap_detector.reset()

                        send_message({"type": "calibration_started"})
                        send_message({"type": "status", "message": "Calibration started - double-tap to mark 4 corners"})

                    elif command == "reset_calibration":
                        calibration_region = None
                        calibration_points = []
                        calibrating = False
                        send_message({"type": "calibration_reset"})
                        send_message({"type": "status", "message": "Calibration reset"})

                    elif command == "set_calibration":
                        # Restore calibration region from saved state (sent by Electron)
                        region = cmd.get("region")
                        if region and isinstance(region, dict):
                            calibration_region = region
                            calibration_points = []  # Clear any partial points
                            calibrating = False
                            send_message({"type": "calibration_restored", "region": region})
                            send_message({"type": "status", "message": "Calibration restored"})

                except queue.Empty:
                    break
                except Exception as e:
                    send_message({"type": "error", "message": f"Command error: {str(e)}"})

            ret, frame = cap.read()
            if not ret:
                continue

            # Flip frame horizontally (mirror mode)
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
                # Process first detected hand
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
                    # Calibration mode: double-tap (thumb touch middle PIP twice) = add point
                    current_time = time.time()

                    # Force drawing off during calibration
                    stable_can_draw = False
                    draw_on_count = 0
                    draw_off_count = 0
                    can_draw = False
                    if was_drawing:
                        send_message({"type": "draw_disable"})
                        was_drawing = False

                    # Detect thumb-middle touch for double-tap
                    is_touching = is_thumb_touch_middle_pip_norm(landmarks, distance_threshold=0.04)
                    double_tap = calibration_tap_detector.update(is_touching)

                    if double_tap and cursor_pos is not None:
                        # Double-tap detected with cooldown
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
                                    calibration_points
                                )
                                calibrating = False
                                calibration_tap_detector.reset()

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

                else:
                    # Normal mode: detect draw gesture
                    raw_can_draw = is_draw_gesture_norm(landmarks, distance_threshold=0.04)

                    # Apply hysteresis
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

                # Reset double-tap detector when hand is lost
                calibration_tap_detector.reset()

                send_message({
                    "type": "cursor",
                    "position": None,
                    "drawing": False,
                    "calibrating": calibrating,
                    "calibrated": calibration_region is not None
                })

                last_cursor = None

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
