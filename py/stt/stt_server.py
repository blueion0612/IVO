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
from typing import Optional, List

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

# ===== Configuration =====
SAMPLE_RATE = 16000

MODEL_NAME = "large-v3"      # Multilingual SOTA model
DEVICE = "cuda"              # Use CUDA with 4090
COMPUTE_TYPE = "float16"     # FP16 (speed + memory saving)


def send_message(msg_type: str, **kwargs):
    """Send JSON message to stdout"""
    msg = {"type": msg_type, **kwargs}
    print(json.dumps(msg, ensure_ascii=False), flush=True)


class STTServer:
    """JSON protocol based STT server for Electron communication"""

    def __init__(
        self,
        model_name: str = MODEL_NAME,
        device: str = DEVICE,
        compute_type: str = COMPUTE_TYPE,
    ) -> None:
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

        try:
            self.stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
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

        duration_sec = len(audio) / SAMPLE_RATE

        # Skip if too short
        if duration_sec < 0.5:
            send_message("warning", message="Audio too short")
            return None

        # Normalize volume if too quiet
        max_abs = float(np.max(np.abs(audio)))
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
                vad_filter=True,
                vad_parameters={
                    "min_silence_duration_ms": 500,
                    "speech_pad_ms": 200,
                },
            )

            text = "".join(seg.text for seg in segments).strip()
            lang_code = getattr(info, "language", "")
            lang_prob = float(getattr(info, "language_probability", 0.0))

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
        server = STTServer()
        server.run()
    except Exception as e:
        send_message("error", message=f"Server initialization failed: {str(e)}")
        sys.exit(1)
