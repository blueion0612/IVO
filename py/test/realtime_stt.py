"""
Realtime STT Test Script

Interactive console-based speech-to-text testing using faster-whisper.
Press Enter to start/stop recording, 'q' to quit.

Requirements:
    pip install faster-whisper sounddevice numpy

Usage:
    python realtime_stt.py
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"  # Avoid OMP Error #15 (Windows + CUDA)

import sys
from typing import Optional, Tuple, List

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

# ===== Configuration =====
SAMPLE_RATE = 16000

MODEL_NAME = "large-v3"      # Multilingual SOTA model
DEVICE = "cuda"              # Use CUDA (for RTX 4090)
COMPUTE_TYPE = "float16"     # FP16 (speed + memory optimization)


class ButtonRecorder:
    """Button-triggered STT recorder. Start/stop to transcribe entire segment."""

    def __init__(
        self,
        model_name: str = MODEL_NAME,
        device: str = DEVICE,
        compute_type: str = COMPUTE_TYPE,
    ) -> None:
        print(f"[INFO] Loading Whisper model ({model_name}, device={device}, compute_type={compute_type})...")
        self.model = WhisperModel(model_name, device=device, compute_type=compute_type)

        self.stream: Optional[sd.InputStream] = None
        self.chunks: List[np.ndarray] = []

    # ===== Audio Callback =====
    def _callback(self, indata, frames, time_info, status):
        if status:
            print(f"[SD-STATUS] {status}", file=sys.stderr)
        # Copy (frames, channels) array to list
        self.chunks.append(indata.copy())

    # ===== Public Methods =====
    def start(self) -> None:
        """Start recording (call on button press)."""
        if self.stream is not None:
            # Already recording
            print("[REC] Already recording.", file=sys.stderr)
            return

        self.chunks = []

        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            callback=self._callback,
        )
        self.stream.start()
        print("[REC] Recording started")

    def stop_and_transcribe(self) -> Tuple[str, str, float]:
        """
        Stop recording and transcribe the entire recorded segment with Whisper.
        Returns: (text, lang_code, lang_prob)
        """
        if self.stream is None:
            raise RuntimeError("Recording not started. Call start() first.")

        # Stop recording
        self.stream.stop()
        self.stream.close()
        self.stream = None
        print("[REC] Recording stopped")

        if not self.chunks:
            print("[REC] No audio recorded.", file=sys.stderr)
            return "", "", 0.0

        # Concatenate (N, 1) arrays to (N,) mono float32
        audio = np.concatenate(self.chunks, axis=0).astype("float32")
        if audio.ndim == 2:
            audio = audio[:, 0]

        duration_sec = len(audio) / SAMPLE_RATE
        print(f"[ASR] Transcribing {duration_sec:.2f}s audio...", file=sys.stderr)

        # Normalize if volume too low
        max_abs = float(np.max(np.abs(audio)))
        if max_abs > 0:
            audio = audio / max_abs

        # ===== Whisper transcription (entire segment at once) =====
        # Auto language detection (KO/EN both supported)
        # VAD filter to remove silence/noise and reduce hallucination
        segments, info = self.model.transcribe(
            audio,
            task="transcribe",          # No translation, keep original
            beam_size=5,                # Good accuracy, fast on 4090
            best_of=5,
            temperature=0.0,            # Deterministic decoding (reduce hallucination)
            condition_on_previous_text=False,  # Process each segment independently
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

        return text, lang_code, lang_prob


# ===== Console Test Loop =====
if __name__ == "__main__":
    """
    Usage:
    1. Run: python realtime_stt.py
    2. Enter -> Start recording
    3. Enter again -> Stop recording + show transcription
    4. 'q' + Enter -> Exit
    """
    recorder = ButtonRecorder()

    print("\n[INFO] Enter = Start recording, Enter again = Stop & transcribe, 'q' = Quit")

    while True:
        cmd = input("\n[READY] Enter=Record, q=Quit : ").strip().lower()
        if cmd == "q":
            break

        # Start recording
        recorder.start()
        input("[RECORDING] Press Enter to stop...")

        # Stop recording + transcribe
        text, lang, prob = recorder.stop_and_transcribe()
        if text:
            print(f"\n▶ {text}")
            print(f"[LANG] {lang} ({prob:.2f})")
        else:
            print("\n[ASR] 인식된 텍스트가 없습니다.")
