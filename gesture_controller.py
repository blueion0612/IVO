#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Real-time Two-Stage IMU Gesture Recognition with WebSocket Integration

This module implements a two-stage gesture recognition pipeline:
- Stage 1: Detects gesture entry using sliding window classification
- Stage 2: Classifies the specific gesture within a collection window

Features:
- 50Hz resampling for consistent input
- 2.5s Stage2 candidate window collection
- Selects highest confidence result from candidates
- Haptic feedback via UDP
- WebSocket command transmission
"""

import argparse
import socket
import struct
import time
import json
import asyncio
import threading
import os
import sys
from collections import deque
from typing import Tuple, Optional, Dict, Any

# Windows encoding configuration
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

try:
    import websockets
except ImportError:
    print("[ERROR] websockets not installed. Please run: pip install websockets")
    sys.exit(1)


# =============================================================================
# IMU Data Configuration (IMU Streaming App v0.4.1 - 30 floats)
# =============================================================================

WATCH_PHONE_IMU_LOOKUP = {
    # Watch data (indices 0-14)
    "sw_dt": 0,           # Time interval between samples (seconds)
    "sw_h": 1,            # Timestamp - hour
    "sw_m": 2,            # Timestamp - minute
    "sw_s": 3,            # Timestamp - second
    "sw_ns": 4,           # Timestamp - nanosecond
    # Linear acceleration (m/s²)
    "sw_lacc_x": 5, "sw_lacc_y": 6, "sw_lacc_z": 7,
    # Gyroscope (rad/s)
    "sw_gyro_x": 8, "sw_gyro_y": 9, "sw_gyro_z": 10,
    # Rotation vector (quaternion)
    "sw_rotvec_w": 11, "sw_rotvec_x": 12, "sw_rotvec_y": 13, "sw_rotvec_z": 14,

    # Phone data (indices 15-29)
    "ph_dt": 15,          # Time interval between samples (seconds)
    "ph_h": 16,           # Timestamp - hour
    "ph_m": 17,           # Timestamp - minute
    "ph_s": 18,           # Timestamp - second
    "ph_ns": 19,          # Timestamp - nanosecond
    # Linear acceleration (m/s²)
    "ph_lacc_x": 20, "ph_lacc_y": 21, "ph_lacc_z": 22,
    # Gyroscope (rad/s)
    "ph_gyro_x": 23, "ph_gyro_y": 24, "ph_gyro_z": 25,
    # Rotation vector (quaternion)
    "ph_rotvec_w": 26, "ph_rotvec_x": 27, "ph_rotvec_y": 28, "ph_rotvec_z": 29,
}

MSG_SIZE = 30 * 4  # 120 bytes (30 floats × 4 bytes)
DEFAULT_PORT = 65000
HAPTIC_PORT = 65010


# =============================================================================
# Haptic Feedback Presets
# =============================================================================

HAPTIC_PRESETS = {
    # Stage1 detection: short weak vibration (ready signal)
    "stage1_detected": {"intensity": 100, "count": 1, "duration": 80},
    # Stage2 recognition success: strong double vibration
    "gesture_success": {"intensity": 255, "count": 2, "duration": 100},
    # Stage2 recognition failure: quick triple weak vibration
    "gesture_fail": {"intensity": 150, "count": 3, "duration": 50},
    # Drawing mode entry: medium single vibration
    "mode_drawing": {"intensity": 180, "count": 1, "duration": 120},
    # Pointer mode entry: light single vibration
    "mode_pointer": {"intensity": 120, "count": 1, "duration": 80},
    # Color/palette selection: very short tick
    "selection_tick": {"intensity": 80, "count": 1, "duration": 50},
    # Slide change: medium single vibration
    "slide_change": {"intensity": 150, "count": 1, "duration": 80},
    # Calibration point recorded: short feedback
    "calibration_point": {"intensity": 200, "count": 1, "duration": 60},
    # Calibration complete: success pattern
    "calibration_done": {"intensity": 255, "count": 2, "duration": 150},
    # Recording toggle: notification vibration
    "recording_toggle": {"intensity": 200, "count": 1, "duration": 100},
    # OCR start: short notification
    "ocr_start": {"intensity": 150, "count": 1, "duration": 80},
    # OCR complete: success feedback
    "ocr_complete": {"intensity": 220, "count": 2, "duration": 80},
}

DETECTION_CHANNELS = [
    "sw_lacc_x", "sw_lacc_y", "sw_lacc_z",
    "sw_gyro_x", "sw_gyro_y", "sw_gyro_z",
]

# Default gesture to command mapping (can be overridden by config)
DEFAULT_GESTURE_TO_COMMAND = {
    0: "3",              # left -> Previous slide
    1: "4",              # right -> Next slide
    2: "0",              # up -> Overlay ON
    3: "1",              # down -> Overlay OFF
    4: "5",              # circle_cw -> Caption start
    5: "8",              # circle_ccw -> Caption stop
    6: "JUMP_BACK",      # double_left -> Jump -3
    7: "JUMP_FORWARD",   # double_right -> Jump +3
    8: "2",              # x -> Reset all
    9: "6",              # double_tap -> Hand drawing
    10: "COLOR_PREV",    # 90_left -> Previous color
    11: "COLOR_NEXT",    # 90_right -> Next color
    12: "TIMER_TOGGLE",  # figure_eight -> Timer toggle
    13: "CALIBRATE",     # square -> Calibration
    14: "BLACKOUT"       # triangle -> Blackout
}


def load_config(config_path="config.json"):
    """Load configuration from JSON file."""
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[CONFIG] Failed to load {config_path}: {e}")
    return {}


# Global configuration
CONFIG = {}
GESTURE_TO_COMMAND = DEFAULT_GESTURE_TO_COMMAND.copy()


# =============================================================================
# Haptic Feedback Sender
# =============================================================================

class HapticSender:
    """Sends haptic feedback commands to phone via UDP."""

    def __init__(self):
        self._socket = None
        self.phone_ip = None  # Auto-detected from IMU packets

    def _get_socket(self):
        """Get or create UDP socket."""
        if self._socket is None:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        return self._socket

    def set_phone_ip(self, ip: str):
        """Set phone IP address (auto-called on IMU packet receive)."""
        if self.phone_ip != ip:
            self.phone_ip = ip
            print(f"[HAPTIC] Phone IP set to: {ip}")

    def send(self, preset_name: str = None, intensity: int = None,
             count: int = None, duration: int = None):
        """
        Send haptic feedback.

        Args:
            preset_name: Key from HAPTIC_PRESETS (e.g., "stage1_detected")
            intensity: Vibration intensity (1-255)
            count: Number of vibrations (1-10)
            duration: Duration per vibration in ms (50-500)
        """
        if not self.phone_ip:
            print("[HAPTIC] Phone IP not set, skipping haptic")
            return False

        # Use preset if specified
        if preset_name and preset_name in HAPTIC_PRESETS:
            preset = HAPTIC_PRESETS[preset_name]
            intensity = preset["intensity"]
            count = preset["count"]
            duration = preset["duration"]
        elif intensity is None or count is None or duration is None:
            print(f"[HAPTIC] Invalid parameters: preset={preset_name}, "
                  f"i={intensity}, c={count}, d={duration}")
            return False

        # Validate ranges
        intensity = max(1, min(255, intensity))
        count = max(1, min(10, count))
        duration = max(50, min(500, duration))

        try:
            # Pack as Little Endian (Python default)
            data = struct.pack('<iii', intensity, count, duration)
            sock = self._get_socket()
            sock.sendto(data, (self.phone_ip, HAPTIC_PORT))
            print(f"[HAPTIC] Sent to {self.phone_ip}:{HAPTIC_PORT} - "
                  f"intensity={intensity}, count={count}, duration={duration}ms")
            return True
        except OSError as e:
            print(f"[HAPTIC] Socket error: {e}, recreating socket...")
            self._socket = None
            try:
                sock = self._get_socket()
                sock.sendto(data, (self.phone_ip, HAPTIC_PORT))
                print(f"[HAPTIC] Retry sent to {self.phone_ip}:{HAPTIC_PORT}")
                return True
            except Exception as e2:
                print(f"[HAPTIC] Retry failed: {e2}")
                return False
        except Exception as e:
            print(f"[HAPTIC] Send error: {e}")
            return False

    def close(self):
        """Close the UDP socket."""
        if self._socket:
            try:
                self._socket.close()
            except:
                pass
            self._socket = None


# =============================================================================
# Haptic Receiver (Sync WebSocket in separate thread)
# =============================================================================

class HapticReceiver:
    """Receives haptic requests via sync WebSocket in separate thread."""

    def __init__(self, ws_url: str, haptic_sender: HapticSender):
        self.ws_url = ws_url
        self.haptic_sender = haptic_sender
        self._thread = None
        self._stop = False

    def start(self):
        """Start receiver thread."""
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print(f"[HAPTIC-RX] Receiver thread started for {self.ws_url}", flush=True)

    def _run(self):
        """Run sync WebSocket connection in separate thread."""
        import websocket

        while not self._stop:
            ws = None
            try:
                print(f"[HAPTIC-RX] Connecting to {self.ws_url}...", flush=True)
                ws = websocket.create_connection(self.ws_url, timeout=5)
                print(f"[HAPTIC-RX] Connected!", flush=True)
                ws.settimeout(0.5)

                while not self._stop:
                    try:
                        message = ws.recv()
                        self._handle_message(message)
                    except websocket.WebSocketTimeoutException:
                        continue
                    except websocket.WebSocketConnectionClosedException:
                        print("[HAPTIC-RX] Connection closed, reconnecting...", flush=True)
                        break

            except Exception as e:
                if not self._stop:
                    print(f"[HAPTIC-RX] Connection error: {e}, retrying in 2s...", flush=True)
                    time.sleep(2.0)
            finally:
                if ws:
                    try:
                        ws.close()
                    except:
                        pass

    def _handle_message(self, raw_msg: str):
        """Process received message."""
        try:
            msg = json.loads(raw_msg)
            if msg.get("type") == "haptic_request":
                preset = msg.get("preset")
                print(f"[HAPTIC-RX] Haptic request: {preset}", flush=True)
                if preset and self.haptic_sender:
                    result = self.haptic_sender.send(preset)
                    print(f"[HAPTIC-RX] Send result: {result}", flush=True)
        except json.JSONDecodeError as e:
            print(f"[HAPTIC-RX] JSON decode error: {e}", flush=True)
        except Exception as e:
            print(f"[HAPTIC-RX] Handle error: {e}", flush=True)

    def stop(self):
        """Stop receiver thread."""
        self._stop = True
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)


# =============================================================================
# WebSocket Command Sender
# =============================================================================

class CommandSender:
    """Sends commands to Electron via WebSocket."""

    def __init__(self, ws_url="ws://127.0.0.1:17890"):
        self.ws_url = ws_url
        self.ws = None
        self.connected = False

    async def connect(self):
        """Connect to WebSocket server."""
        try:
            self.ws = await websockets.connect(self.ws_url)
            self.connected = True
            print(f"[WS] Connected to {self.ws_url}")
            return True
        except Exception as e:
            print(f"[WS] Failed to connect: {e}")
            self.connected = False
            return False

    async def send_message(self, message: dict):
        """Send JSON message."""
        if not self.connected or not self.ws:
            if not await self.connect():
                return

        try:
            msg_str = json.dumps(message)
            await self.ws.send(msg_str)
        except Exception as e:
            print(f"[WS] Send error: {e}")
            self.connected = False
            await self.connect()

    async def send_stage1_detected(self, duration: float):
        """Send Stage1 detection notification."""
        await self.send_message({
            "type": "stage1_detected",
            "duration": duration
        })

    async def send_gesture_recognized(self, gesture_name: str, confidence: float):
        """Send gesture recognition result."""
        await self.send_message({
            "type": "gesture_recognized",
            "gesture": gesture_name,
            "confidence": confidence
        })

    async def send_command(self, cmd: str):
        """Send command code."""
        await self.send_message({"code": cmd})

    async def send_hold_extended(self, remaining_sec: float):
        """Send hold state notification (Stage2 timer extended)."""
        await self.send_message({
            "type": "hold_extended",
            "remaining": remaining_sec
        })

    async def send_stage2_cancelled(self):
        """Send Stage2 cancellation notification."""
        await self.send_message({
            "type": "stage2_cancelled"
        })

    async def close(self):
        """Close WebSocket connection."""
        if self.ws:
            await self.ws.close()
            self.connected = False


# =============================================================================
# IMU Listener (UDP)
# =============================================================================

class IMUListener:
    """Receives IMU data via UDP."""

    def __init__(self, ip: str, port: int):
        self.ip = ip
        self.port = port
        self.socket = None
        self.listening = False

    def start(self) -> bool:
        """Start listening for IMU packets."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.bind((self.ip, self.port))
            self.socket.settimeout(0.1)
            self.listening = True
            print(f"[IMU] Listening on {self.ip}:{self.port}")
            return True
        except Exception as e:
            print(f"[IMU] Failed to bind {self.ip}:{self.port} - {e}")
            return False

    def stop(self):
        """Stop listening."""
        self.listening = False
        if self.socket:
            self.socket.close()
            self.socket = None
        print("[IMU] Listener stopped")

    def recv_one(self, timeout: float = 0.1) -> Optional[Tuple[float, np.ndarray, str]]:
        """
        Receive one IMU packet.

        Returns:
            Tuple of (timestamp, values, sender_ip) or None
        """
        if not self.listening or self.socket is None:
            return None
        self.socket.settimeout(timeout)
        try:
            data, addr = self.socket.recvfrom(MSG_SIZE)
            if len(data) != MSG_SIZE:
                return None
            values = struct.unpack('>30f', data)  # Big Endian, 30 floats
            ts = time.time()
            sender_ip = addr[0]
            return ts, np.array(values, dtype=np.float32), sender_ip
        except socket.timeout:
            return None
        except Exception as e:
            print(f"[IMU] Error receiving: {e}")
            return None


# =============================================================================
# Ring Buffer for IMU Data
# =============================================================================

class IMURingBuffer:
    """Circular buffer for storing IMU data with timestamps."""

    def __init__(self, maxlen: int):
        self.timestamps = deque(maxlen=maxlen)
        self.frames = deque(maxlen=maxlen)

    def add(self, timestamp: float, values: np.ndarray):
        """Add a new IMU frame."""
        self.timestamps.append(float(timestamp))
        self.frames.append(values.astype(np.float32))

    def __len__(self):
        return len(self.frames)

    def get_recent(self, n: int) -> Tuple[np.ndarray, np.ndarray]:
        """Get the most recent n frames."""
        n = min(n, len(self.frames))
        if n == 0:
            return np.zeros((0,), dtype=np.float64), np.zeros((0, 30), dtype=np.float32)
        times = np.array(list(self.timestamps)[-n:], dtype=np.float64)
        frames = np.stack(list(self.frames)[-n:], axis=0)
        return times, frames

    def get_by_time_range(self, t_start: float, t_end: float) -> Tuple[np.ndarray, np.ndarray]:
        """Get frames within a time range."""
        times_list = []
        frames_list = []
        for ts, fr in zip(self.timestamps, self.frames):
            if ts < t_start or ts > t_end:
                continue
            times_list.append(ts)
            frames_list.append(fr)
        if not times_list:
            return np.zeros((0,), dtype=np.float64), np.zeros((0, 30), dtype=np.float32)
        return (
            np.array(times_list, dtype=np.float64),
            np.stack(frames_list, axis=0).astype(np.float32),
        )

    def clear(self):
        """Clear all data."""
        self.timestamps.clear()
        self.frames.clear()


# =============================================================================
# Stage 1 Model Definitions
# =============================================================================

class Stage1MLPModel(nn.Module):
    """MLP model for Stage 1 gesture entry detection."""

    def __init__(self, input_shape):
        super().__init__()
        T, D = input_shape
        self.fc = nn.Sequential(
            nn.Flatten(),
            nn.Linear(T * D, 256),
            nn.ReLU(),
            nn.Dropout(0.4),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
        )

    def forward(self, x):
        return self.fc(x).squeeze(1)


class Stage1LSTMModel(nn.Module):
    """LSTM model for Stage 1 gesture entry detection."""

    def __init__(self, input_shape):
        super().__init__()
        T, D = input_shape
        self.lstm = nn.LSTM(
            input_size=D,
            hidden_size=64,
            num_layers=1,
            batch_first=True,
        )
        self.fc = nn.Sequential(
            nn.Dropout(0.4),
            nn.Linear(64, 64),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(64, 1),
        )

    def forward(self, x):
        _, (h_n, _) = self.lstm(x)
        h = h_n[-1]
        return self.fc(h).squeeze(1)


class Stage1GRUModel(nn.Module):
    """GRU model for Stage 1 gesture entry detection."""

    def __init__(self, input_shape):
        super().__init__()
        T, D = input_shape
        self.gru = nn.GRU(
            input_size=D,
            hidden_size=64,
            num_layers=1,
            batch_first=True,
        )
        self.fc = nn.Sequential(
            nn.Dropout(0.4),
            nn.Linear(64, 64),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(64, 1),
        )

    def forward(self, x):
        _, h_n = self.gru(x)
        h = h_n[-1]
        return self.fc(h).squeeze(1)


def build_stage1_model(model_type: str, input_shape: tuple) -> nn.Module:
    """Build Stage 1 model based on type."""
    if model_type == "mlp":
        return Stage1MLPModel(input_shape)
    elif model_type == "lstm":
        return Stage1LSTMModel(input_shape)
    elif model_type == "gru":
        return Stage1GRUModel(input_shape)
    else:
        print(f"[WARNING] Unknown Stage1 model_type '{model_type}', using MLP")
        return Stage1MLPModel(input_shape)


# =============================================================================
# Stage 2 Model Definitions
# =============================================================================

class Stage2MLPModel(nn.Module):
    """MLP model for Stage 2 gesture classification."""

    def __init__(self, input_shape, num_classes):
        super().__init__()
        T, D = input_shape
        self.net = nn.Sequential(
            nn.Flatten(),
            nn.Linear(T * D, 256),
            nn.ReLU(),
            nn.Dropout(0.4),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, num_classes),
        )

    def forward(self, x):
        return self.net(x)


class Stage2GRUModel(nn.Module):
    """GRU model for Stage 2 gesture classification."""

    def __init__(self, input_shape, num_classes):
        super().__init__()
        T, D = input_shape
        self.gru = nn.GRU(
            input_size=D,
            hidden_size=128,
            num_layers=2,
            batch_first=True,
            dropout=0.2,
        )
        self.fc = nn.Sequential(
            nn.Dropout(0.4),
            nn.Linear(128, 128),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(128, num_classes),
        )

    def forward(self, x):
        _, h_n = self.gru(x)
        h = h_n[-1]
        return self.fc(h)


class TCNBlock(nn.Module):
    """Temporal Convolutional Network block."""

    def __init__(self, in_channels, out_channels, kernel_size=3, dilation=1, dropout=0.2):
        super().__init__()
        padding = dilation * (kernel_size - 1)
        self.conv = nn.Conv1d(
            in_channels=in_channels,
            out_channels=out_channels,
            kernel_size=kernel_size,
            dilation=dilation,
            padding=padding,
        )
        self.bn = nn.BatchNorm1d(out_channels)
        self.dropout = nn.Dropout(dropout)
        self.relu = nn.ReLU()

        self.downsample = None
        if in_channels != out_channels:
            self.downsample = nn.Conv1d(in_channels, out_channels, kernel_size=1)

    def forward(self, x):
        out = self.conv(x)
        out = out[..., : x.size(-1)]
        out = self.bn(out)
        out = self.dropout(out)

        res = x
        if self.downsample is not None:
            res = self.downsample(x)

        out = self.relu(out + res)
        return out


class Stage2TCNModel(nn.Module):
    """TCN model for Stage 2 gesture classification."""

    def __init__(self, input_shape, num_classes):
        super().__init__()
        T, D = input_shape
        C_in = D
        self.tcn = nn.Sequential(
            TCNBlock(C_in, 64, kernel_size=3, dilation=1, dropout=0.2),
            TCNBlock(64, 64, kernel_size=3, dilation=2, dropout=0.2),
            TCNBlock(64, 64, kernel_size=3, dilation=4, dropout=0.2),
        )
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.fc = nn.Sequential(
            nn.Linear(64, 64),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(64, num_classes),
        )

    def forward(self, x):
        x = x.permute(0, 2, 1)
        out = self.tcn(x)
        out = self.pool(out).squeeze(-1)
        return self.fc(out)


def build_stage2_model(model_type: str, input_shape: tuple, num_classes: int) -> nn.Module:
    """Build Stage 2 model based on type."""
    if model_type == "mlp":
        return Stage2MLPModel(input_shape, num_classes)
    elif model_type == "gru":
        return Stage2GRUModel(input_shape, num_classes)
    elif model_type == "tcn":
        return Stage2TCNModel(input_shape, num_classes)
    else:
        print(f"[WARNING] Unknown Stage2 model_type '{model_type}', using GRU")
        return Stage2GRUModel(input_shape, num_classes)


# =============================================================================
# Stage 1 Detector
# =============================================================================

class Stage1Detector:
    """Detects gesture entry using Stage 1 model with resampling."""

    def __init__(self, ckpt_path: str, buffer: IMURingBuffer, device: torch.device):
        self.buffer = buffer
        self.device = device
        self.last_infer_time = None

        ckpt: Dict[str, Any] = torch.load(ckpt_path, map_location=device)
        self.model_type: str = ckpt["model_type"]
        self.input_shape = tuple(ckpt["input_shape"])
        self.window_sec: float = float(ckpt["window_sec"])
        self.step_sec: float = float(ckpt["step_sec"])
        self.threshold: float = float(ckpt["threshold"])
        self.target_fs: float = float(ckpt.get("target_fs", 50.0))

        self.detection_channels = ckpt.get("detection_channels", DETECTION_CHANNELS)
        self.det_indices = [WATCH_PHONE_IMU_LOOKUP[name] for name in self.detection_channels]

        self.mean = np.array(ckpt["norm_mean"], dtype=np.float32)
        self.std = np.array(ckpt["norm_std"], dtype=np.float32)
        self.eps = float(ckpt.get("norm_eps", 1e-6))
        self.clip_value = float(ckpt.get("norm_clip_value", 1e4))

        self.model = build_stage1_model(self.model_type, self.input_shape).to(device)

        if "state_dict" in ckpt:
            self.model.load_state_dict(ckpt["state_dict"])
        elif "model_state_dict" in ckpt:
            self.model.load_state_dict(ckpt["model_state_dict"])
        else:
            self.model.load_state_dict(ckpt)

        self.model.eval()

        print(f"[Stage1] Loaded from {ckpt_path}")
        print(f"  model_type = {self.model_type}")
        print(f"  window_sec = {self.window_sec}, step_sec = {self.step_sec}")
        print(f"  threshold  = {self.threshold}, target_fs = {self.target_fs}")

    def _preprocess(self, X: np.ndarray) -> np.ndarray:
        """Apply z-score normalization."""
        x = X.astype(np.float64)
        x = np.nan_to_num(x, nan=0.0, posinf=self.clip_value, neginf=-self.clip_value)
        x = np.clip(x, -self.clip_value, self.clip_value)
        std_safe = np.where(self.std < self.eps, 1.0, self.std)
        x = (x - self.mean) / std_safe
        x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
        return x.astype(np.float32)

    def maybe_detect(self, current_time: float) -> Tuple[bool, Optional[float]]:
        """Check for gesture entry detection."""
        win_len = self.input_shape[0]
        if len(self.buffer) < win_len:
            return False, None

        # Limit call frequency based on step_sec
        if (self.last_infer_time is not None) and \
           (current_time - self.last_infer_time < self.step_sec):
            return False, None

        # Set time range
        t_end = current_time
        t_start = t_end - self.window_sec

        # Get data from buffer
        times, frames = self.buffer.get_by_time_range(t_start, t_end)
        if times.shape[0] < 2:
            return False, None

        # Extract detection channels
        imu_raw = frames[:, self.det_indices]

        # Resample to target frequency
        dt = 1.0 / self.target_fs
        t_grid = t_start + np.arange(win_len, dtype=np.float64) * dt

        X_resampled = np.zeros((win_len, len(self.det_indices)), dtype=np.float32)
        for ch in range(len(self.det_indices)):
            X_resampled[:, ch] = np.interp(t_grid, times, imu_raw[:, ch])

        # Normalize and infer
        X_norm = self._preprocess(X_resampled)
        x_t = torch.from_numpy(X_norm[None, ...]).to(self.device)

        with torch.no_grad():
            logits = self.model(x_t)
            if logits.ndim > 1:
                logits = logits.squeeze(1)
            prob = torch.sigmoid(logits)[0].item()

        self.last_infer_time = current_time
        is_gesture = prob >= self.threshold
        return bool(is_gesture), float(prob)


# =============================================================================
# Stage 2 Classifier
# =============================================================================

class Stage2Classifier:
    """Classifies gestures using Stage 2 model with candidate selection."""

    def __init__(self, ckpt_path: str, buffer: IMURingBuffer, device: torch.device):
        self.buffer = buffer
        self.device = device

        ckpt: Dict[str, Any] = torch.load(ckpt_path, map_location=device)
        self.model_type: str = ckpt["model_type"]
        self.input_shape = tuple(ckpt["input_shape"])
        self.seq_len: int = int(ckpt.get("seq_len", self.input_shape[0]))
        self.num_classes: int = int(ckpt["num_classes"])
        self.class_id_to_name: Dict[int, str] = ckpt.get("class_id_to_name", {})

        self.detection_channels = ckpt.get("detection_channels", DETECTION_CHANNELS)
        self.det_indices = [WATCH_PHONE_IMU_LOOKUP[name] for name in self.detection_channels]

        self.mean = np.array(ckpt["norm_mean"], dtype=np.float32)
        self.std = np.array(ckpt["norm_std"], dtype=np.float32)
        self.eps = float(ckpt.get("norm_eps", 1e-6))
        self.clip_value = float(ckpt.get("norm_clip_value", 1e4))

        self.target_fs: float = float(ckpt.get("target_fs", 50.0))

        self.model = build_stage2_model(
            self.model_type, self.input_shape, self.num_classes
        ).to(device)

        if "state_dict" in ckpt:
            self.model.load_state_dict(ckpt["state_dict"])
        elif "model_state_dict" in ckpt:
            self.model.load_state_dict(ckpt["model_state_dict"])
        else:
            self.model.load_state_dict(ckpt)

        self.model.eval()

        print(f"[Stage2] Loaded from {ckpt_path}")
        print(f"  model_type = {self.model_type}")
        print(f"  seq_len    = {self.seq_len}, num_classes = {self.num_classes}")

    @staticmethod
    def _center_crop_or_pad(seq: np.ndarray, target_len: int) -> np.ndarray:
        """Center crop or pad sequence to target length."""
        L, D = seq.shape
        if L == target_len:
            return seq.astype(np.float32)
        if L > target_len:
            start = (L - target_len) // 2
            end = start + target_len
            return seq[start:end].astype(np.float32)
        out = np.zeros((target_len, D), dtype=np.float32)
        start = (target_len - L) // 2
        out[start:start+L] = seq.astype(np.float32)
        return out

    def _preprocess(self, X: np.ndarray) -> np.ndarray:
        """Apply z-score normalization."""
        x = X.astype(np.float64)
        x = np.nan_to_num(x, nan=0.0, posinf=self.clip_value, neginf=-self.clip_value)
        x = np.clip(x, -self.clip_value, self.clip_value)
        std_safe = np.where(self.std < self.eps, 1.0, self.std)
        x = (x - self.mean) / std_safe
        x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
        return x.astype(np.float32)

    def classify_in_time_range(
        self,
        t_start: float,
        t_end: float,
        step_sec: float = 0.5,
        target_fs: float = 50.0,
    ) -> Tuple[Optional[int], Optional[str], Optional[float]]:
        """
        Classify gesture within time range using sliding window.

        Returns:
            Tuple of (class_id, class_name, confidence) or (None, None, None)
        """
        times, frames = self.buffer.get_by_time_range(t_start, t_end)
        if frames.shape[0] == 0 or times.shape[0] < 2:
            return None, None, None

        imu_raw = frames[:, self.det_indices]

        # Resample to target frequency
        dt = 1.0 / target_fs
        duration = max(t_end - t_start, 0.0)
        resampled_len = int(round(duration * target_fs))
        if resampled_len < 2:
            return None, None, None

        t_grid = t_start + np.arange(resampled_len, dtype=np.float64) * dt
        imu_res = np.zeros((resampled_len, imu_raw.shape[1]), dtype=np.float32)
        for ch in range(imu_raw.shape[1]):
            imu_res[:, ch] = np.interp(t_grid, times, imu_raw[:, ch])

        N = imu_res.shape[0]
        win_len = self.seq_len

        # If too short, use center crop/pad
        if N < win_len:
            seq = self._center_crop_or_pad(imu_res, win_len)
            Xn = self._preprocess(seq)
            x_t = torch.from_numpy(Xn[None, ...]).to(self.device)
            with torch.no_grad():
                logits = self.model(x_t)
                probs = F.softmax(logits, dim=1).cpu().numpy()[0]
            best_id = int(np.argmax(probs))
            best_prob = float(probs[best_id])
            name = self.class_id_to_name.get(best_id, f"class_{best_id}")
            return best_id, name, best_prob

        # Sliding window over resampled sequence
        step_frames = max(1, int(round(step_sec * target_fs)))

        best_prob = -1.0
        best_id = None

        for start_idx in range(0, N - win_len + 1, step_frames):
            seg = imu_res[start_idx:start_idx + win_len]
            Xn = self._preprocess(seg)
            x_t = torch.from_numpy(Xn[None, ...]).to(self.device)
            with torch.no_grad():
                logits = self.model(x_t)
                probs = F.softmax(logits, dim=1).cpu().numpy()[0]
            p_max = float(probs.max())
            pred_id = int(np.argmax(probs))

            if p_max > best_prob:
                best_prob = p_max
                best_id = pred_id

        if best_id is None:
            return None, None, None

        name = self.class_id_to_name.get(best_id, f"class_{best_id}")
        return best_id, name, best_prob


# =============================================================================
# Main Async Loop
# =============================================================================

async def main_async():
    """Main async entry point."""
    parser = argparse.ArgumentParser(
        description="Real-time two-stage IMU gesture recognition with WebSocket"
    )
    parser.add_argument("--config", type=str, default="config.json",
                        help="Config file path")
    parser.add_argument("--ip", type=str, default=None,
                        help="Local IP to bind UDP socket")
    parser.add_argument("--port", type=int, default=None,
                        help="UDP port")
    parser.add_argument("--stage1_ckpt", type=str, default=None,
                        help="Path to Stage1 checkpoint")
    parser.add_argument("--stage2_ckpt", type=str, default=None,
                        help="Path to Stage2 checkpoint")
    parser.add_argument("--cooldown", type=float, default=None,
                        help="Cooldown seconds after Stage1 detection")
    parser.add_argument("--stage2_collect_sec", type=float, default=None,
                        help="Stage2 collection window duration")
    parser.add_argument("--stage2_step_sec", type=float, default=None,
                        help="Stage2 sliding window step")
    parser.add_argument("--device", type=str, default=None,
                        help="Device: cpu / cuda / auto")
    parser.add_argument("--ws_url", type=str, default=None,
                        help="WebSocket URL for commands")

    args = parser.parse_args()

    # Load config
    global CONFIG, GESTURE_TO_COMMAND
    CONFIG = {}
    if os.path.exists(args.config):
        try:
            with open(args.config, 'r', encoding='utf-8') as f:
                CONFIG = json.load(f)
            print(f"[CONFIG] Loaded from {args.config}")

            if "gesture_mapping" in CONFIG:
                for k, v in CONFIG["gesture_mapping"].items():
                    GESTURE_TO_COMMAND[int(k)] = v
                print(f"[CONFIG] Loaded {len(CONFIG['gesture_mapping'])} gesture mappings")
        except Exception as e:
            print(f"[CONFIG] Failed to load {args.config}: {e}")
            CONFIG = {}

    # Apply config with command line override
    imu_config = CONFIG.get("imu", {})
    ws_config = CONFIG.get("websocket", {})

    ip = args.ip or imu_config.get("udp_ip", "0.0.0.0")
    port = args.port or imu_config.get("udp_port", DEFAULT_PORT)
    stage1_ckpt = args.stage1_ckpt or imu_config.get(
        "stage1_checkpoint", "./models/stage1_best.pt"
    )
    stage2_ckpt = args.stage2_ckpt or imu_config.get(
        "stage2_checkpoint", "./models/stage2_best.pt"
    )
    cooldown = args.cooldown or imu_config.get("cooldown_sec", 2.0)
    stage2_collect_sec = args.stage2_collect_sec or imu_config.get(
        "stage2_collection_sec", 2.5
    )
    stage2_step_sec = args.stage2_step_sec or imu_config.get("stage2_step_sec", 0.5)
    device_str = args.device or imu_config.get("device", "auto")
    ws_url = args.ws_url or ws_config.get("url", "ws://127.0.0.1:17890")

    # Select device
    if device_str == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(device_str)
    print(f"[DEVICE] Using device: {device}")

    # Check checkpoint files
    if not os.path.exists(stage1_ckpt):
        print(f"[ERROR] Stage1 checkpoint not found: {stage1_ckpt}")
        return
    if not os.path.exists(stage2_ckpt):
        print(f"[ERROR] Stage2 checkpoint not found: {stage2_ckpt}")
        return

    # Get window/seq_len info from checkpoints
    tmp1 = torch.load(stage1_ckpt, map_location="cpu")
    T1 = int(tmp1["input_shape"][0])
    target_fs = float(tmp1.get("target_fs", 50.0))

    tmp2 = torch.load(stage2_ckpt, map_location="cpu")
    seq_len2 = int(tmp2.get("seq_len", tmp2["input_shape"][0]))

    max_T = max(T1, seq_len2)
    history_sec = max_T / target_fs * 4.0
    buffer_size = int(history_sec * target_fs)
    print(f"[BUFFER] history_sec={history_sec:.1f}s, buffer_size={buffer_size}")

    imu_buffer = IMURingBuffer(maxlen=buffer_size)

    stage1 = Stage1Detector(stage1_ckpt, imu_buffer, device)
    stage2 = Stage2Classifier(stage2_ckpt, imu_buffer, device)

    haptic_sender = HapticSender()
    cmd_sender = CommandSender(ws_url)
    await cmd_sender.connect()

    haptic_receiver = HapticReceiver(ws_url, haptic_sender)
    haptic_receiver.start()

    listener = IMUListener(ip, port)
    if not listener.start():
        return

    print("\n[RUN] Real-time two-stage inference with WebSocket started.")
    print("      Stage1: entry gesture detection")
    print(f"      Stage2: {stage2_collect_sec:.1f}s collection, step={stage2_step_sec:.2f}s")
    print("      Haptic feedback: enabled")
    print("      Press Ctrl+C to stop.\n")

    last_stage1_time = -1e9
    stage2_pending = False
    stage2_start_time = None

    # Hold detection settings
    HOLD_ACCEL_THRESHOLD = 0.3    # m/s² - acceleration threshold
    HOLD_GYRO_THRESHOLD = 0.15   # rad/s - gyroscope threshold
    HOLD_EXTEND_SEC = 2.0        # Hold extension time
    hold_check_interval = 0.5
    last_hold_check_time = 0
    last_hold_notify_time = 0
    consecutive_hold_count = 0
    is_holding = False

    def calculate_motion_magnitude(buffer, window_sec=0.3):
        """Calculate motion magnitude over recent window."""
        if len(buffer) < 5:
            return float('inf'), float('inf')

        times, frames = buffer.get_recent(50)
        if len(times) < 3:
            return float('inf'), float('inf')

        now = times[-1]
        t_start = now - window_sec

        mask = times >= t_start
        if mask.sum() < 3:
            return float('inf'), float('inf')

        # Watch accel: indices 5-7, gyro: indices 8-10
        accel_data = frames[mask][:, 5:8]
        gyro_data = frames[mask][:, 8:11]

        accel_std = np.std(accel_data, axis=0)
        accel_mag = np.linalg.norm(accel_std)

        gyro_std = np.std(gyro_data, axis=0)
        gyro_mag = np.linalg.norm(gyro_std)

        return accel_mag, gyro_mag

    try:
        while True:
            pkt = listener.recv_one(timeout=0.01)

            if pkt is None:
                # Check Stage2 timeout
                if stage2_pending:
                    now = time.time()
                    if now >= stage2_start_time + stage2_collect_sec:
                        pred_id, pred_name, best_prob = stage2.classify_in_time_range(
                            t_start=stage2_start_time,
                            t_end=stage2_start_time + stage2_collect_sec,
                            step_sec=stage2_step_sec,
                            target_fs=target_fs,
                        )

                        if pred_id is not None:
                            print(f"[STAGE2] Final gesture: id={pred_id}, "
                                  f"name={pred_name}, conf={best_prob:.3f}")
                            await cmd_sender.send_gesture_recognized(pred_name, best_prob)

                            if pred_id in GESTURE_TO_COMMAND:
                                cmd = GESTURE_TO_COMMAND[pred_id]
                                print(f"         -> Command: {cmd}")
                                await cmd_sender.send_command(cmd)

                            haptic_sender.send("gesture_success")
                        else:
                            print("[STAGE2] No valid candidate in window.")
                            haptic_sender.send("gesture_fail")

                        # Reset state
                        stage2_pending = False
                        imu_buffer.clear()
                        stage1.last_infer_time = None
                        last_stage1_time = time.time()

                await asyncio.sleep(0.001)
                continue

            ts, values, sender_ip = pkt
            imu_buffer.add(ts, values)
            haptic_sender.set_phone_ip(sender_ip)

            # Stage2 pending: check for hold state
            if stage2_pending:
                current_deadline = stage2_start_time + stage2_collect_sec

                if ts - last_hold_check_time >= hold_check_interval:
                    last_hold_check_time = ts
                    accel_mag, gyro_mag = calculate_motion_magnitude(imu_buffer)

                    is_still = (accel_mag < HOLD_ACCEL_THRESHOLD) and \
                               (gyro_mag < HOLD_GYRO_THRESHOLD)

                    if is_still:
                        consecutive_hold_count += 1

                        if consecutive_hold_count >= 2:
                            stage2_collect_sec = ts - stage2_start_time + HOLD_EXTEND_SEC

                            if not is_holding:
                                is_holding = True
                                print(f"[HOLD] Arm held still (accel={accel_mag:.3f}, "
                                      f"gyro={gyro_mag:.3f}), waiting...")
                                await cmd_sender.send_hold_extended(-1)
                    else:
                        consecutive_hold_count = 0
                        is_holding = False

            # Stage2 collection complete
            if stage2_pending and ts >= stage2_start_time + stage2_collect_sec:
                pred_id, pred_name, best_prob = stage2.classify_in_time_range(
                    t_start=stage2_start_time,
                    t_end=stage2_start_time + stage2_collect_sec,
                    step_sec=stage2_step_sec,
                    target_fs=target_fs,
                )

                if pred_id is not None:
                    print(f"[STAGE2] Final gesture: id={pred_id}, "
                          f"name={pred_name}, conf={best_prob:.3f}")
                    await cmd_sender.send_gesture_recognized(pred_name, best_prob)

                    if pred_id in GESTURE_TO_COMMAND:
                        cmd = GESTURE_TO_COMMAND[pred_id]
                        print(f"         -> Command: {cmd}")
                        await cmd_sender.send_command(cmd)

                    haptic_sender.send("gesture_success")
                else:
                    print("[STAGE2] No valid candidate in window.")
                    haptic_sender.send("gesture_fail")

                # Reset state
                stage2_pending = False
                imu_buffer.clear()
                stage1.last_infer_time = None
                last_stage1_time = time.time()
                consecutive_hold_count = 0
                is_holding = False
                stage2_collect_sec = args.stage2_collect_sec or \
                    imu_config.get("stage2_collection_sec", 2.5)
                continue

            # Stage1 detection (only when not in Stage2)
            if not stage2_pending:
                is_gesture, prob = stage1.maybe_detect(ts)
                if not is_gesture:
                    continue

                if ts - last_stage1_time < cooldown:
                    continue

                # Reset buffer for Stage2
                imu_buffer.clear()
                stage1.last_infer_time = None

                last_stage1_time = ts
                stage2_pending = True
                stage2_start_time = ts

                consecutive_hold_count = 0
                is_holding = False
                last_hold_check_time = ts
                last_hold_notify_time = 0
                stage2_collect_sec = args.stage2_collect_sec or \
                    imu_config.get("stage2_collection_sec", 2.5)

                print(f"[STAGE1] Entry gesture detected! prob={prob:.3f}\n"
                      f"         -> Perform gesture within {stage2_collect_sec:.1f}s...")

                await cmd_sender.send_stage1_detected(stage2_collect_sec)
                haptic_sender.send("stage1_detected")

    except KeyboardInterrupt:
        print("\n[RUN] Interrupted by user.")
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        listener.stop()
        haptic_receiver.stop()
        await cmd_sender.close()
        haptic_sender.close()
        print("[RUN] Finished.")


def main():
    """Entry point."""
    try:
        asyncio.run(main_async())
    except Exception as e:
        print(f"[ERROR] Failed to run: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
