"""
STT Server - JSON protocol based Speech-to-Text service for Electron IPC
Uses faster-whisper for local transcription with CUDA acceleration

Protocol:
    Input (stdin):  {"command": "start|stop|quit"}
    Output (stdout): {"type": "ready|recording_started|recording_stopped|transcription|error", ...}
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"  # Avoid OMP Error #15 (Windows + CUDA)

import sys
import json
import argparse
from typing import Optional, List

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

# ===== Configuration =====
TARGET_SAMPLE_RATE = 16000   # Whisper expects 16kHz

MODEL_NAME = "large-v3"      # Multilingual SOTA model
DEVICE = "cuda"              # Use CUDA with 4090
COMPUTE_TYPE = "float16"     # FP16 (speed + memory saving)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="STT Server for IVO")
    parser.add_argument('--mic-name', type=str, default=None,
                        help='Microphone device name to match (default: system default)')
    return parser.parse_args()


def send_message(msg_type: str, **kwargs):
    """Send JSON message to stdout"""
    msg = {"type": msg_type, **kwargs}
    print(json.dumps(msg, ensure_ascii=False), flush=True)


def get_input_devices() -> List[dict]:
    """
    Get list of input-only audio devices with their indices.
    Filters to use WASAPI devices on Windows for best compatibility with browser.
    """
    devices = sd.query_devices()
    hostapis = sd.query_hostapis()

    input_devices = []
    seen_names = set()  # To avoid duplicates across host APIs

    # Find WASAPI host API index (preferred on Windows)
    wasapi_idx = None
    for i, api in enumerate(hostapis):
        if 'WASAPI' in api['name']:
            wasapi_idx = i
            break

    for idx, dev in enumerate(devices):
        # Filter for input devices (max_input_channels > 0)
        if dev['max_input_channels'] > 0:
            name = dev['name']
            hostapi = dev['hostapi']

            # On Windows, prefer WASAPI devices (same as browser uses)
            # Skip duplicate device names from other host APIs
            if wasapi_idx is not None:
                if hostapi != wasapi_idx:
                    continue  # Skip non-WASAPI devices

            # Avoid duplicate device names
            if name in seen_names:
                continue
            seen_names.add(name)

            input_devices.append({
                'index': idx,  # Original sounddevice index
                'name': name,
                'channels': dev['max_input_channels'],
                'hostapi': hostapi,
                'hostapi_name': hostapis[hostapi]['name']
            })

    return input_devices


def find_mic_by_name(input_devices: List[dict], target_name: str) -> Optional[int]:
    """Find microphone by name matching. Returns sounddevice index or None."""
    if not target_name:
        return None

    # Normalize target name for comparison
    target_lower = target_name.lower()

    # Try exact match first
    for dev in input_devices:
        if dev['name'].lower() == target_lower:
            return dev['index']

    # Try partial match (device name contains target or vice versa)
    for dev in input_devices:
        dev_lower = dev['name'].lower()
        if target_lower in dev_lower or dev_lower in target_lower:
            return dev['index']

    # Try matching significant keywords
    target_words = set(target_lower.split())
    for dev in input_devices:
        dev_words = set(dev['name'].lower().split())
        # If more than half of target words match
        common = target_words & dev_words
        if len(common) >= len(target_words) / 2:
            return dev['index']

    return None


class STTServer:
    """JSON protocol based STT server for Electron communication"""

    def __init__(
        self,
        model_name: str = MODEL_NAME,
        device: str = DEVICE,
        compute_type: str = COMPUTE_TYPE,
        mic_name: Optional[str] = None,
    ) -> None:
        # Get list of input-only devices (WASAPI preferred)
        input_devices = get_input_devices()

        # Log available input devices
        send_message("info", message=f"Found {len(input_devices)} input device(s)")
        for i, dev in enumerate(input_devices):
            send_message("info", message=f"  [{i}] {dev['name']} ({dev['hostapi_name']}, sd_idx={dev['index']})")

        # Find microphone by name
        if mic_name:
            send_message("info", message=f"Looking for mic: {mic_name}")
            matched_idx = find_mic_by_name(input_devices, mic_name)
            if matched_idx is not None:
                # Find the device info for logging
                matched_dev = next((d for d in input_devices if d['index'] == matched_idx), None)
                if matched_dev:
                    send_message("info", message=f"Matched: {matched_dev['name']} (sd_idx={matched_idx})")
                self.mic_index = matched_idx
            else:
                send_message("warning", message=f"No match found for '{mic_name}', using default")
                self.mic_index = None
        else:
            send_message("info", message="Using default microphone")
            self.mic_index = None

        send_message("info", message=f"Loading Whisper model ({model_name}, device={device})...")

        try:
            self.model = WhisperModel(model_name, device=device, compute_type=compute_type)
            send_message("ready")
        except Exception as e:
            send_message("error", message=f"Failed to load model: {str(e)}")
            raise

        self.stream: Optional[sd.InputStream] = None
        self.chunks: List[np.ndarray] = []
        self.is_recording = False
        self.device_sample_rate = None  # Will be set when recording starts

    def _audio_callback(self, indata, frames, time_info, status):
        """Audio stream callback - saves audio chunks"""
        if status:
            send_message("warning", message=f"Audio status: {status}")
        # Copy (frames, channels) array to list
        self.chunks.append(indata.copy())

    def start_recording(self) -> bool:
        """Start microphone recording"""
        if self.is_recording:
            send_message("warning", message="Already recording")
            return False

        self.chunks = []

        # Get device's default sample rate
        try:
            if self.mic_index is not None:
                dev_info = sd.query_devices(self.mic_index)
                self.device_sample_rate = int(dev_info['default_samplerate'])
            else:
                self.device_sample_rate = int(sd.query_devices(kind='input')['default_samplerate'])
            send_message("info", message=f"Device sample rate: {self.device_sample_rate}Hz")
        except Exception as e:
            send_message("warning", message=f"Could not get device sample rate: {e}, using 48000")
            self.device_sample_rate = 48000

        try:
            self.stream = sd.InputStream(
                samplerate=self.device_sample_rate,  # Use device's native sample rate
                channels=1,
                dtype="float32",
                device=self.mic_index,
                callback=self._audio_callback,
            )
            self.stream.start()
            self.is_recording = True
            send_message("recording_started")
            return True
        except Exception as e:
            send_message("error", message=f"Failed to start recording: {str(e)}")
            return False

    def stop_and_transcribe(self) -> Optional[dict]:
        """Stop recording and transcribe the audio"""
        if not self.is_recording:
            send_message("warning", message="Not recording")
            return None

        # Stop recording
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self.is_recording = False
        send_message("recording_stopped")

        if not self.chunks:
            send_message("warning", message="No audio recorded")
            return None

        # Concatenate chunks to single mono float32 array
        audio = np.concatenate(self.chunks, axis=0).astype("float32")
        if audio.ndim == 2:
            audio = audio[:, 0]

        # Resample to 16kHz if needed (Whisper requirement)
        source_rate = self.device_sample_rate or 48000
        if source_rate != TARGET_SAMPLE_RATE:
            # Simple linear interpolation resampling
            duration = len(audio) / source_rate
            target_length = int(duration * TARGET_SAMPLE_RATE)
            indices = np.linspace(0, len(audio) - 1, target_length)
            audio = np.interp(indices, np.arange(len(audio)), audio).astype("float32")
            send_message("info", message=f"Resampled {source_rate}Hz -> {TARGET_SAMPLE_RATE}Hz")

        duration_sec = len(audio) / TARGET_SAMPLE_RATE
        num_chunks = len(self.chunks)

        # Audio level analysis
        max_abs = float(np.max(np.abs(audio)))
        rms = float(np.sqrt(np.mean(audio ** 2)))
        db_rms = 20 * np.log10(rms + 1e-10)

        send_message("info", message=f"Audio: {duration_sec:.1f}s, {num_chunks} chunks, max={max_abs:.4f}, RMS={db_rms:.1f}dB")

        # Skip if too short
        if duration_sec < 0.5:
            send_message("warning", message="Audio too short")
            return None

        # Check if audio is too quiet (likely wrong mic or no input)
        if max_abs < 0.001:
            send_message("warning", message=f"Audio level too low (max={max_abs:.6f}). Check microphone selection.")
            return None

        # Normalize volume
        if max_abs > 0:
            audio = audio / max_abs

        # ===== Whisper transcription =====
        try:
            segments, info = self.model.transcribe(
                audio,
                task="transcribe",          # No translation, keep original
                beam_size=5,                # Accuracy vs speed tradeoff
                best_of=5,
                temperature=0.0,            # Deterministic decoding (reduce hallucination)
                condition_on_previous_text=False,
                without_timestamps=True,
                vad_filter=False,           # Disable VAD - let Whisper handle all audio
            )

            text = "".join(seg.text for seg in segments).strip()
            lang_code = getattr(info, "language", "")
            lang_prob = float(getattr(info, "language_probability", 0.0))

            # If no text detected
            if not text:
                send_message("warning", message="No speech detected in audio")
                return None

            result = {
                "text": text,
                "lang": lang_code,
                "prob": lang_prob,
                "duration": duration_sec
            }

            send_message("transcription", **result)
            return result

        except Exception as e:
            send_message("error", message=f"Transcription failed: {str(e)}")
            return None

    def run(self):
        """Main loop - reads JSON commands from stdin"""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                cmd = json.loads(line)
                command = cmd.get("command", "")

                if command == "start":
                    self.start_recording()
                elif command == "stop":
                    self.stop_and_transcribe()
                elif command == "quit":
                    if self.is_recording:
                        self.stream.stop()
                        self.stream.close()
                    send_message("shutdown")
                    break
                else:
                    send_message("error", message=f"Unknown command: {command}")

            except json.JSONDecodeError:
                send_message("error", message=f"Invalid JSON: {line}")
            except Exception as e:
                send_message("error", message=f"Command error: {str(e)}")


if __name__ == "__main__":
    try:
        args = parse_args()
        server = STTServer(mic_name=args.mic_name)
        server.run()
    except Exception as e:
        send_message("error", message=f"Server initialization failed: {str(e)}")
        sys.exit(1)
