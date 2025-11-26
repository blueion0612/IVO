#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Real-time two-stage IMU gesture recognition with WebSocket integration
원본 realtime_two_stage_inference.py와 완전 동일한 로직 구현
- 50Hz 리샘플링
- Stage1 후 2.5초간 Stage2 candidate windows 수집
- 가장 높은 confidence의 결과 선택
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

# Windows 인코딩 설정
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

# -------------------------------------------------------------------
# Config (IMU Streaming App v0.4.1 - 30 floats)
# -------------------------------------------------------------------
WATCH_PHONE_IMU_LOOKUP = {
    # Watch 데이터 (인덱스 0-14)
    "sw_dt": 0,           # 샘플 간 시간 간격 (초)
    "sw_h": 1,            # 타임스탬프 - 시
    "sw_m": 2,            # 타임스탬프 - 분
    "sw_s": 3,            # 타임스탬프 - 초
    "sw_ns": 4,           # 타임스탬프 - 나노초
    # linear acceleration (m/s²)
    "sw_lacc_x": 5, "sw_lacc_y": 6, "sw_lacc_z": 7,
    # gyroscope (rad/s)
    "sw_gyro_x": 8, "sw_gyro_y": 9, "sw_gyro_z": 10,
    # rotation vector (quaternion)
    "sw_rotvec_w": 11, "sw_rotvec_x": 12, "sw_rotvec_y": 13, "sw_rotvec_z": 14,

    # Phone 데이터 (인덱스 15-29)
    "ph_dt": 15,          # 샘플 간 시간 간격 (초)
    "ph_h": 16,           # 타임스탬프 - 시
    "ph_m": 17,           # 타임스탬프 - 분
    "ph_s": 18,           # 타임스탬프 - 초
    "ph_ns": 19,          # 타임스탬프 - 나노초
    # linear acceleration (m/s²)
    "ph_lacc_x": 20, "ph_lacc_y": 21, "ph_lacc_z": 22,
    # gyroscope (rad/s)
    "ph_gyro_x": 23, "ph_gyro_y": 24, "ph_gyro_z": 25,
    # rotation vector (quaternion)
    "ph_rotvec_w": 26, "ph_rotvec_x": 27, "ph_rotvec_y": 28, "ph_rotvec_z": 29,
}

MSG_SIZE = 30 * 4  # 120 bytes (30 floats × 4 bytes)
DEFAULT_PORT = 65000
HAPTIC_PORT = 65010  # 햅틱 피드백 전송 포트

# -------------------------------------------------------------------
# Haptic Feedback Presets
# -------------------------------------------------------------------
HAPTIC_PRESETS = {
    # Stage1 감지: 짧고 약한 진동 1회 (준비 신호)
    "stage1_detected": {"intensity": 100, "count": 1, "duration": 80},

    # Stage2 인식 성공: 강한 진동 2회 (성공 피드백)
    "gesture_success": {"intensity": 255, "count": 2, "duration": 100},

    # Stage2 인식 실패: 약한 진동 3회 빠르게 (실패 피드백)
    "gesture_fail": {"intensity": 150, "count": 3, "duration": 50},

    # Drawing 모드 진입: 중간 강도 1회
    "mode_drawing": {"intensity": 180, "count": 1, "duration": 120},

    # Pointer 모드 진입: 약한 진동 1회
    "mode_pointer": {"intensity": 120, "count": 1, "duration": 80},

    # 색상/팔레트 선택: 아주 짧은 틱
    "selection_tick": {"intensity": 80, "count": 1, "duration": 50},

    # 슬라이드 이동: 중간 강도 1회
    "slide_change": {"intensity": 150, "count": 1, "duration": 80},

    # 캘리브레이션 포인트 기록: 짧은 피드백
    "calibration_point": {"intensity": 200, "count": 1, "duration": 60},

    # 캘리브레이션 완료: 성공 패턴
    "calibration_done": {"intensity": 255, "count": 2, "duration": 150},

    # 녹음 시작/중지: 알림 진동
    "recording_toggle": {"intensity": 200, "count": 1, "duration": 100},

    # OCR 시작: 짧은 알림
    "ocr_start": {"intensity": 150, "count": 1, "duration": 80},

    # OCR 완료: 성공 피드백
    "ocr_complete": {"intensity": 220, "count": 2, "duration": 80},
}

DETECTION_CHANNELS = [
    "sw_lacc_x", "sw_lacc_y", "sw_lacc_z",
    "sw_gyro_x", "sw_gyro_y", "sw_gyro_z",
]

# 제스처 매핑 (기본값, config에서 덮어쓰기 가능)
DEFAULT_GESTURE_TO_COMMAND = {
    0: "3",  # left -> Previous slide
    1: "4",  # right -> Next slide  
    2: "0",  # up -> Overlay ON
    3: "1",  # down -> Overlay OFF
    4: "5",  # circle_cw -> Caption start
    5: "8",  # circle_ccw -> Caption stop
    6: "JUMP_BACK",  # double_left -> Jump -3
    7: "JUMP_FORWARD",  # double_right -> Jump +3
    8: "2",  # x -> Reset all
    9: "6",  # double_tap -> Hand drawing
    10: "COLOR_PREV",  # 90_left -> Previous color
    11: "COLOR_NEXT",  # 90_right -> Next color
    12: "TIMER_TOGGLE",  # figure_eight -> Timer toggle
    13: "CALIBRATE",  # square -> Calibration
    14: "BLACKOUT"  # triangle -> Blackout
}

# Config 파일 로드 함수
def load_config(config_path="config.json"):
    """config.json 파일 로드"""
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[CONFIG] Failed to load {config_path}: {e}")
    return {}

# 전역 설정
CONFIG = {}
GESTURE_TO_COMMAND = DEFAULT_GESTURE_TO_COMMAND.copy()

# -------------------------------------------------------------------
# Haptic Feedback Sender
# -------------------------------------------------------------------
class HapticSender:
    """UDP를 통해 햅틱 피드백을 Phone으로 전송"""
    def __init__(self):
        self._socket = None
        self.phone_ip = None  # IMU 패킷에서 자동 감지

    def _get_socket(self):
        """소켓 획득 (필요시 새로 생성)"""
        if self._socket is None:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        return self._socket

    def set_phone_ip(self, ip: str):
        """Phone IP 설정 (IMU 패킷 수신 시 자동 호출)"""
        if self.phone_ip != ip:
            self.phone_ip = ip
            print(f"[HAPTIC] Phone IP set to: {ip}")

    def send(self, preset_name: str = None, intensity: int = None, count: int = None, duration: int = None):
        """
        햅틱 피드백 전송
        preset_name: HAPTIC_PRESETS의 키 (예: "stage1_detected")
        또는 개별 파라미터로 직접 지정
        """
        if not self.phone_ip:
            print("[HAPTIC] Phone IP not set, skipping haptic")
            return False

        # 프리셋 사용
        if preset_name and preset_name in HAPTIC_PRESETS:
            preset = HAPTIC_PRESETS[preset_name]
            intensity = preset["intensity"]
            count = preset["count"]
            duration = preset["duration"]
        elif intensity is None or count is None or duration is None:
            print(f"[HAPTIC] Invalid parameters: preset={preset_name}, i={intensity}, c={count}, d={duration}")
            return False

        # 범위 검증
        intensity = max(1, min(255, intensity))
        count = max(1, min(10, count))
        duration = max(50, min(500, duration))

        try:
            # Little Endian으로 패킹 (Python 기본값)
            data = struct.pack('<iii', intensity, count, duration)
            sock = self._get_socket()
            sock.sendto(data, (self.phone_ip, HAPTIC_PORT))
            print(f"[HAPTIC] Sent to {self.phone_ip}:{HAPTIC_PORT} - intensity={intensity}, count={count}, duration={duration}ms")
            return True
        except OSError as e:
            # 소켓 오류 시 재생성 시도
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
        if self._socket:
            try:
                self._socket.close()
            except:
                pass
            self._socket = None


# -------------------------------------------------------------------
# Haptic Receiver (별도 WebSocket 연결로 햅틱 요청 수신)
# 동기 방식으로 구현 - imu_test.py와 유사하게
# -------------------------------------------------------------------
class HapticReceiver:
    """별도 스레드에서 동기 WebSocket으로 햅틱 요청 수신"""
    def __init__(self, ws_url: str, haptic_sender: HapticSender):
        self.ws_url = ws_url
        self.haptic_sender = haptic_sender
        self._thread = None
        self._stop = False

    def start(self):
        """수신 스레드 시작"""
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print(f"[HAPTIC-RX] Receiver thread started for {self.ws_url}", flush=True)

    def _run(self):
        """별도 스레드에서 동기 WebSocket 연결"""
        import websocket  # websocket-client 라이브러리 사용

        while not self._stop:
            ws = None
            try:
                print(f"[HAPTIC-RX] Connecting to {self.ws_url}...", flush=True)
                ws = websocket.create_connection(self.ws_url, timeout=5)
                print(f"[HAPTIC-RX] Connected!", flush=True)

                ws.settimeout(0.5)  # recv 타임아웃 설정

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
        """수신 메시지 처리"""
        try:
            msg = json.loads(raw_msg)
            if msg.get("type") == "haptic_request":
                preset = msg.get("preset")
                print(f"[HAPTIC-RX] ★ Haptic request: {preset}", flush=True)
                if preset and self.haptic_sender:
                    result = self.haptic_sender.send(preset)
                    print(f"[HAPTIC-RX] Send result: {result}", flush=True)
        except json.JSONDecodeError as e:
            print(f"[HAPTIC-RX] JSON decode error: {e}", flush=True)
        except Exception as e:
            print(f"[HAPTIC-RX] Handle error: {e}", flush=True)

    def stop(self):
        """수신 스레드 종료"""
        self._stop = True
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)


# -------------------------------------------------------------------
# WebSocket Command Sender
# -------------------------------------------------------------------
class CommandSender:
    def __init__(self, ws_url="ws://127.0.0.1:17890"):
        self.ws_url = ws_url
        self.ws = None
        self.connected = False

    async def connect(self):
        """WebSocket 연결"""
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
        """메시지 전송"""
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
        """Stage1 감지 알림"""
        await self.send_message({
            "type": "stage1_detected",
            "duration": duration
        })

    async def send_gesture_recognized(self, gesture_name: str, confidence: float):
        """제스처 인식 결과"""
        await self.send_message({
            "type": "gesture_recognized",
            "gesture": gesture_name,
            "confidence": confidence
        })

    async def send_command(self, cmd: str):
        """명령 전송"""
        await self.send_message({"code": cmd})

    async def send_hold_extended(self, remaining_sec: float):
        """Hold 상태 - Stage2 타이머 연장 알림"""
        await self.send_message({
            "type": "hold_extended",
            "remaining": remaining_sec
        })

    async def send_stage2_cancelled(self):
        """Stage2 취소 알림 (hold 후 움직임 없이 타임아웃)"""
        await self.send_message({
            "type": "stage2_cancelled"
        })

    async def close(self):
        if self.ws:
            await self.ws.close()
            self.connected = False

# -------------------------------------------------------------------
# IMU Listener (UDP) - 원본과 동일
# -------------------------------------------------------------------
class IMUListener:
    def __init__(self, ip: str, port: int):
        self.ip = ip
        self.port = port
        self.socket = None
        self.listening = False

    def start(self) -> bool:
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
        self.listening = False
        if self.socket:
            self.socket.close()
            self.socket = None
        print("[IMU] Listener stopped")

    def recv_one(self, timeout: float = 0.1) -> Optional[Tuple[float, np.ndarray, str]]:
        """
        IMU 패킷 수신
        Returns: (timestamp, values, sender_ip) 또는 None
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
            sender_ip = addr[0]  # Phone IP 추출
            return ts, np.array(values, dtype=np.float32), sender_ip
        except socket.timeout:
            return None
        except Exception as e:
            print(f"[IMU] Error receiving: {e}")
            return None

# -------------------------------------------------------------------
# Ring buffer - 원본과 동일
# -------------------------------------------------------------------
class IMURingBuffer:
    def __init__(self, maxlen: int):
        self.timestamps = deque(maxlen=maxlen)
        self.frames = deque(maxlen=maxlen)

    def add(self, timestamp: float, values: np.ndarray):
        self.timestamps.append(float(timestamp))
        self.frames.append(values.astype(np.float32))

    def __len__(self):
        return len(self.frames)

    def get_recent(self, n: int) -> Tuple[np.ndarray, np.ndarray]:
        n = min(n, len(self.frames))
        if n == 0:
            return np.zeros((0,), dtype=np.float64), np.zeros((0, 30), dtype=np.float32)
        times = np.array(list(self.timestamps)[-n:], dtype=np.float64)
        frames = np.stack(list(self.frames)[-n:], axis=0)
        return times, frames

    def get_by_time_range(self, t_start: float, t_end: float) -> Tuple[np.ndarray, np.ndarray]:
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
        self.timestamps.clear()
        self.frames.clear()

# -------------------------------------------------------------------
# Model definitions - Stage1
# -------------------------------------------------------------------
class Stage1MLPModel(nn.Module):
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
    if model_type == "mlp":
        return Stage1MLPModel(input_shape)
    elif model_type == "lstm":
        return Stage1LSTMModel(input_shape)
    elif model_type == "gru":
        return Stage1GRUModel(input_shape)
    else:
        print(f"[WARNING] Unknown Stage1 model_type '{model_type}', using MLP")
        return Stage1MLPModel(input_shape)

# -------------------------------------------------------------------
# Model definitions - Stage2
# -------------------------------------------------------------------
class Stage2MLPModel(nn.Module):
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

# TCN components for Stage2
class TCNBlock(nn.Module):
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
    if model_type == "mlp":
        return Stage2MLPModel(input_shape, num_classes)
    elif model_type == "gru":
        return Stage2GRUModel(input_shape, num_classes)
    elif model_type == "tcn":
        return Stage2TCNModel(input_shape, num_classes)
    else:
        print(f"[WARNING] Unknown Stage2 model_type '{model_type}', using GRU")
        return Stage2GRUModel(input_shape, num_classes)

# -------------------------------------------------------------------
# Stage1 Detector (원본과 동일한 리샘플링 로직)
# -------------------------------------------------------------------
class Stage1Detector:
    def __init__(self, ckpt_path: str, buffer: IMURingBuffer, device: torch.device):
        self.buffer = buffer
        self.device = device
        self.last_infer_time = None

        ckpt: Dict[str, Any] = torch.load(ckpt_path, map_location=device)
        self.model_type: str = ckpt["model_type"]
        self.input_shape = tuple(ckpt["input_shape"])  # (T1, 6)
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
        
        # state_dict key handling
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
        x = X.astype(np.float64)
        x = np.nan_to_num(x, nan=0.0, posinf=self.clip_value, neginf=-self.clip_value)
        x = np.clip(x, -self.clip_value, self.clip_value)
        std_safe = np.where(self.std < self.eps, 1.0, self.std)
        x = (x - self.mean) / std_safe
        x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
        return x.astype(np.float32)

    def maybe_detect(self, current_time: float) -> Tuple[bool, Optional[float]]:
        win_len = self.input_shape[0]  # T1
        if len(self.buffer) < win_len:
            return False, None

        # step_sec 기준으로 호출 빈도 제한
        if (self.last_infer_time is not None) and (current_time - self.last_infer_time < self.step_sec):
            return False, None

        # 1) 시간 구간 설정 (학습과 동일하게 window_sec 기준)
        t_end = current_time
        t_start = t_end - self.window_sec

        # 2) 해당 시간 구간의 데이터를 버퍼에서 가져오기
        times, frames = self.buffer.get_by_time_range(t_start, t_end)
        if times.shape[0] < 2:
            return False, None

        # 3) 선택한 6채널만 추출
        imu_raw = frames[:, self.det_indices]  # (N_raw, 6)

        # 4) 50Hz로 리샘플 (길이 = win_len)
        dt = 1.0 / self.target_fs
        t_grid = t_start + np.arange(win_len, dtype=np.float64) * dt

        X_resampled = np.zeros((win_len, len(self.det_indices)), dtype=np.float32)
        for ch in range(len(self.det_indices)):
            X_resampled[:, ch] = np.interp(t_grid, times, imu_raw[:, ch])

        # 5) 학습 때와 동일한 z-score 정규화
        X_norm = self._preprocess(X_resampled)
        x_t = torch.from_numpy(X_norm[None, ...]).to(self.device)

        # 6) 추론
        with torch.no_grad():
            logits = self.model(x_t)
            if logits.ndim > 1:
                logits = logits.squeeze(1)
            prob = torch.sigmoid(logits)[0].item()

        self.last_infer_time = current_time
        is_gesture = prob >= self.threshold
        return bool(is_gesture), float(prob)

# -------------------------------------------------------------------
# Stage2 Classifier (원본과 동일한 리샘플링 및 후보 선택 로직)
# -------------------------------------------------------------------
class Stage2Classifier:
    def __init__(self, ckpt_path: str, buffer: IMURingBuffer, device: torch.device):
        self.buffer = buffer
        self.device = device

        ckpt: Dict[str, Any] = torch.load(ckpt_path, map_location=device)
        self.model_type: str = ckpt["model_type"]
        self.input_shape = tuple(ckpt["input_shape"])  # (T2, 6)
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

        self.model = build_stage2_model(self.model_type, self.input_shape, self.num_classes).to(device)
        
        # state_dict key handling
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

        times, frames = self.buffer.get_by_time_range(t_start, t_end)
        if frames.shape[0] == 0 or times.shape[0] < 2:
            return None, None, None

        imu_raw = frames[:, self.det_indices]  # (N_raw, 6)

        # 1) 50Hz 리샘플링
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

        # 2) 리샘플된 길이가 seq_len보다 짧으면 -> center crop/pad 한 번만 수행
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

        # 3) 충분히 길면: 리샘플된 시퀀스에서 슬라이딩 윈도우
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

# -------------------------------------------------------------------
# Main async loop (원본과 동일한 로직 + WebSocket 통합)
# -------------------------------------------------------------------
async def main_async():
    parser = argparse.ArgumentParser(
        description="Real-time two-stage IMU gesture recognition with WebSocket"
    )
    parser.add_argument("--config", type=str, default="config.json",
                        help="Config file path (optional)")
    parser.add_argument("--ip", type=str, default=None,
                        help="Local IP to bind UDP socket")
    parser.add_argument("--port", type=int, default=None,
                        help="UDP port")
    parser.add_argument("--stage1_ckpt", type=str, default=None,
                        help="Path to Stage1 checkpoint")
    parser.add_argument("--stage2_ckpt", type=str, default=None,
                        help="Path to Stage2 checkpoint")
    parser.add_argument("--cooldown", type=float, default=None,
                        help="Seconds to ignore new Stage1 detections after one entry")
    parser.add_argument("--stage2_collect_sec", type=float, default=None,
                        help="Seconds after Stage1 to collect Stage2 candidate windows")
    parser.add_argument("--stage2_step_sec", type=float, default=None,
                        help="Stage2 candidate window step in seconds")
    parser.add_argument("--device", type=str, default=None,
                        help="cpu / cuda / auto")
    parser.add_argument("--ws_url", type=str, default=None,
                        help="WebSocket URL for sending commands")

    args = parser.parse_args()
    
    # Load config if exists
    global CONFIG, GESTURE_TO_COMMAND
    CONFIG = {}
    if os.path.exists(args.config):
        try:
            with open(args.config, 'r', encoding='utf-8') as f:
                CONFIG = json.load(f)
            print(f"[CONFIG] Loaded from {args.config}")
            
            # Update GESTURE_TO_COMMAND from config
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
    stage1_ckpt = args.stage1_ckpt or imu_config.get("stage1_checkpoint", "./models/stage1_best.pt")
    stage2_ckpt = args.stage2_ckpt or imu_config.get("stage2_checkpoint", "./models/stage2_best.pt")
    cooldown = args.cooldown or imu_config.get("cooldown_sec", 2.0)
    stage2_collect_sec = args.stage2_collect_sec or imu_config.get("stage2_collection_sec", 2.5)
    stage2_step_sec = args.stage2_step_sec or imu_config.get("stage2_step_sec", 0.5)
    device_str = args.device or imu_config.get("device", "auto")
    ws_url = args.ws_url or ws_config.get("url", "ws://127.0.0.1:17890")

    # Device
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

    # Stage1/Stage2 ckpt를 잠깐 열어서 window/seq_len, target_fs 확인
    tmp1 = torch.load(stage1_ckpt, map_location="cpu")
    T1 = int(tmp1["input_shape"][0])
    target_fs = float(tmp1.get("target_fs", 50.0))

    tmp2 = torch.load(stage2_ckpt, map_location="cpu")
    seq_len2 = int(tmp2.get("seq_len", tmp2["input_shape"][0]))

    max_T = max(T1, seq_len2)
    history_sec = max_T / target_fs * 4.0
    buffer_size = int(history_sec * target_fs)
    print(f"[BUFFER] history_sec≈{history_sec:.1f}s, buffer_size={buffer_size}")

    imu_buffer = IMURingBuffer(maxlen=buffer_size)

    stage1 = Stage1Detector(stage1_ckpt, imu_buffer, device)
    stage2 = Stage2Classifier(stage2_ckpt, imu_buffer, device)

    # Haptic Feedback
    haptic_sender = HapticSender()

    # WebSocket (명령 전송용)
    cmd_sender = CommandSender(ws_url)
    await cmd_sender.connect()

    # Haptic Receiver (별도 스레드에서 햅틱 요청 수신)
    haptic_receiver = HapticReceiver(ws_url, haptic_sender)
    haptic_receiver.start()

    listener = IMUListener(ip, port)
    if not listener.start():
        return

    print("\n[RUN] Real-time two-stage inference with WebSocket started.")
    print("      Stage1: entry gesture detection")
    print(f"      Stage2: {stage2_collect_sec:.1f}s after entry, sliding windows step={stage2_step_sec:.2f}s")
    print("      Haptic feedback: enabled (receiver thread running)")
    print("      Press Ctrl+C to stop.\n")

    last_stage1_time = -1e9
    stage2_pending = False
    stage2_start_time = None

    # Hold detection settings
    # 가속도 + 자이로 모두 거의 안 움직일 때만 hold로 판단
    HOLD_ACCEL_THRESHOLD = 0.3    # m/s^2 - 가속도 변화량 임계값
    HOLD_GYRO_THRESHOLD = 0.15    # rad/s - 자이로 변화량 임계값 (약 8.6 deg/s)
    HOLD_EXTEND_SEC = 2.0         # hold 감지 시 연장할 시간
    hold_check_interval = 0.5     # hold 체크 간격 (초)
    last_hold_check_time = 0
    last_hold_notify_time = 0     # 마지막 hold 알림 시간
    consecutive_hold_count = 0    # 연속 hold 감지 횟수 (2회 이상일 때만 실제 hold로 판단)
    is_holding = False            # 현재 hold 상태인지

    def calculate_motion_magnitude(buffer, window_sec=0.3):
        """
        최근 window_sec 동안의 움직임 크기 계산
        가속도(3축) + 자이로(3축) 총 6축의 표준편차 사용
        """
        if len(buffer) < 5:
            return float('inf'), float('inf')  # 데이터 부족시 움직임 있는 것으로 처리

        # 버퍼에서 최근 데이터 가져오기
        times, frames = buffer.get_recent(50)  # 최근 1초 분량 (50Hz 기준)
        if len(times) < 3:
            return float('inf'), float('inf')

        now = times[-1]
        t_start = now - window_sec

        # 시간 범위 내 데이터만 선택
        mask = times >= t_start
        if mask.sum() < 3:
            return float('inf'), float('inf')

        # Watch 가속도 인덱스: sw_lacc_x=5, sw_lacc_y=6, sw_lacc_z=7
        # Watch 자이로 인덱스: sw_gyro_x=8, sw_gyro_y=9, sw_gyro_z=10
        accel_data = frames[mask][:, 5:8]
        gyro_data = frames[mask][:, 8:11]

        # 가속도의 표준편차 (m/s^2)
        accel_std = np.std(accel_data, axis=0)
        accel_mag = np.linalg.norm(accel_std)

        # 자이로의 표준편차 (rad/s)
        gyro_std = np.std(gyro_data, axis=0)
        gyro_mag = np.linalg.norm(gyro_std)

        return accel_mag, gyro_mag

    try:
        while True:
            pkt = listener.recv_one(timeout=0.01)

            if pkt is None:
                # Stage2 timeout 체크
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
                            print(
                                f"[STAGE2] Final gesture (best of candidates): "
                                f"id={pred_id}, name={pred_name}, conf={best_prob:.3f}"
                            )

                            # Send gesture recognition event
                            await cmd_sender.send_gesture_recognized(pred_name, best_prob)

                            # Send command if mapped
                            if pred_id in GESTURE_TO_COMMAND:
                                cmd = GESTURE_TO_COMMAND[pred_id]
                                print(f"         → Command: {cmd}")
                                await cmd_sender.send_command(cmd)

                            # 햅틱 피드백: 제스처 인식 성공
                            haptic_sender.send("gesture_success")
                        else:
                            print("[STAGE2] Not enough data or no valid candidate in window.")
                            # 햅틱 피드백: 제스처 인식 실패
                            haptic_sender.send("gesture_fail")

                        # 🔁 Stage2 끝났으니 버퍼/상태 초기화 + 쿨다운
                        stage2_pending = False
                        imu_buffer.clear()
                        stage1.last_infer_time = None
                        last_stage1_time = time.time()

                await asyncio.sleep(0.001)
                continue

            ts, values, sender_ip = pkt
            imu_buffer.add(ts, values)

            # Phone IP 자동 설정 (햅틱 피드백용)
            haptic_sender.set_phone_ip(sender_ip)

            # ✅ Stage2 대기 중: Hold 감지 및 타이머 연장 체크
            if stage2_pending:
                current_deadline = stage2_start_time + stage2_collect_sec

                # Hold 체크 (일정 간격으로)
                if ts - last_hold_check_time >= hold_check_interval:
                    last_hold_check_time = ts
                    accel_mag, gyro_mag = calculate_motion_magnitude(imu_buffer)

                    # 가속도와 자이로 모두 임계값 이하일 때만 hold로 판단
                    is_still = (accel_mag < HOLD_ACCEL_THRESHOLD) and (gyro_mag < HOLD_GYRO_THRESHOLD)

                    if is_still:
                        consecutive_hold_count += 1

                        # 연속 2회 이상 정지 감지될 때만 실제 hold로 판단
                        if consecutive_hold_count >= 2:
                            # 무한 대기: 타이머 계속 연장
                            stage2_collect_sec = ts - stage2_start_time + HOLD_EXTEND_SEC

                            # hold 상태 시작 시 한번만 알림
                            if not is_holding:
                                is_holding = True
                                print(f"[HOLD] Arm held still (accel={accel_mag:.3f}, gyro={gyro_mag:.3f}), waiting...")
                                await cmd_sender.send_hold_extended(-1)  # -1 = 무한 대기
                    else:
                        # 움직임 감지 - 연속 hold 카운트 리셋
                        consecutive_hold_count = 0
                        is_holding = False

            # ✅ Stage2 대기 중이고, 시간이 지나면 바로 Stage2 수행
            if stage2_pending and ts >= stage2_start_time + stage2_collect_sec:
                pred_id, pred_name, best_prob = stage2.classify_in_time_range(
                    t_start=stage2_start_time,
                    t_end=stage2_start_time + stage2_collect_sec,
                    step_sec=stage2_step_sec,
                    target_fs=target_fs,
                )

                if pred_id is not None:
                    print(
                        f"[STAGE2] Final gesture (best of candidates): "
                        f"id={pred_id}, name={pred_name}, conf={best_prob:.3f}"
                    )

                    # Send gesture recognition event
                    await cmd_sender.send_gesture_recognized(pred_name, best_prob)

                    # Send command if mapped
                    if pred_id in GESTURE_TO_COMMAND:
                        cmd = GESTURE_TO_COMMAND[pred_id]
                        print(f"         → Command: {cmd}")
                        await cmd_sender.send_command(cmd)

                    # 햅틱 피드백: 제스처 인식 성공
                    haptic_sender.send("gesture_success")
                else:
                    print("[STAGE2] Not enough data or no valid candidate in window.")
                    # 햅틱 피드백: 제스처 인식 실패
                    haptic_sender.send("gesture_fail")

                # 🔁 여기서도 동일하게 버퍼/상태 리셋 + 쿨다운 시작
                stage2_pending = False
                imu_buffer.clear()
                stage1.last_infer_time = None
                last_stage1_time = time.time()
                # Hold 변수 리셋
                consecutive_hold_count = 0
                is_holding = False
                stage2_collect_sec = args.stage2_collect_sec or imu_config.get("stage2_collection_sec", 2.5)
                continue

            # 아직 Stage2 대기 상태가 아닐 때만 Stage1으로 엔트리 감지
            if not stage2_pending:
                is_gesture, prob = stage1.maybe_detect(ts)
                if not is_gesture:
                    continue

                # cooldown 적용 (너무 자주 엔트리 감지되는 것 방지)
                if ts - last_stage1_time < cooldown:
                    continue

                # 🔥 여기서 버퍼/상태 리셋: 앞으로 들어오는 데이터는 Stage2용
                imu_buffer.clear()
                stage1.last_infer_time = None

                last_stage1_time = ts
                stage2_pending = True
                stage2_start_time = ts

                # Hold 변수 리셋
                consecutive_hold_count = 0
                is_holding = False
                last_hold_check_time = ts
                last_hold_notify_time = 0
                stage2_collect_sec = args.stage2_collect_sec or imu_config.get("stage2_collection_sec", 2.5)

                print(
                    f"[STAGE1] Entry gesture detected! prob={prob:.3f}\n"
                    f"          -> Perform Stage2 gesture within {stage2_collect_sec:.1f}s (hold to extend)..."
                )

                # Send Stage1 detection notification
                await cmd_sender.send_stage1_detected(stage2_collect_sec)

                # 햅틱 피드백: Stage1 감지 (준비 신호)
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
    """Entry point"""
    try:
        asyncio.run(main_async())
    except Exception as e:
        print(f"[ERROR] Failed to run: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
