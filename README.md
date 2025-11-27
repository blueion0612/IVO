# IVO - IMU-Vision Overlay

<div align="center">

![IVO Logo](image/1.jpg)

**Gesture-Controlled Presentation Overlay System**

[![Electron](https://img.shields.io/badge/Electron-27.0.0-47848F?logo=electron&logoColor=white)](https://www.electronjs.org/)
[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS-lightgrey)](https://github.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

*MJU Capstone Project 2025*

</div>

---

## Overview

**IVO (IMU-Vision Overlay)** is a presentation overlay system that enables hands-free slide control through IMU (Inertial Measurement Unit) gesture recognition and computer vision-based hand tracking. It provides a seamless, interactive presentation experience without traditional input devices.

### Key Features

- **IMU Gesture Recognition**: Control presentations using smartwatch gestures (15 unique gestures)
- **Hand Tracking Mode**: Draw and point on screen using webcam-based hand detection
- **Real-time OCR**: Handwriting-to-text conversion with calculation and graph generation
- **Speech-to-Text (STT)**: Local Whisper-based transcription with CUDA acceleration
- **Q&A Summarization**: KoBART-based Korean text summarization for Q&A sessions
- **Presentation Timer**: Built-in timer for time management
- **Haptic Feedback**: Vibration feedback on smartwatch for gesture confirmation
- **Cross-Platform**: Supports Windows and macOS

---

## Table of Contents

- [System Architecture](#system-architecture)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Gesture Commands](#gesture-commands)
- [Features](#features)
- [IMU Data Communication](#imu-data-communication)
- [Configuration](#configuration)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Building from Source](#building-from-source)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Credits](#credits)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              IVO System Overview                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────┐     Bluetooth     ┌──────────────┐       UDP        ┌──────────────┐
│  Smartwatch  │  ─────────────>   │  Smartphone  │  ─────────────>  │  IVO Desktop │
│   (WearOS)   │    IMU Data       │   (Android)  │   Port 65000     │   (Electron) │
│              │                   │              │                   │              │
│  - Sensors   │                   │  - Relay     │                   │  - Overlay   │
│  - Haptics   │ <─────────────    │  - Forward   │ <─────────────    │  - Gesture   │
│              │    Vibration      │              │   Port 65010      │  - Hand Track│
└──────────────┘                   └──────────────┘                   └──────────────┘
                                                                              │
                                                                              │
                                   ┌──────────────┐                           │
                                   │   Webcam     │ <─────────────────────────┘
                                   │              │    Hand Tracking
                                   │  - MediaPipe │    (Optional)
                                   └──────────────┘
```

### Two-Stage Gesture Recognition

IVO uses a two-stage neural network approach for robust gesture recognition:

1. **Stage 1 - Entry Detection**: Detects when a gesture motion begins
2. **Stage 2 - Gesture Classification**: Classifies the specific gesture type

This architecture minimizes false positives while maintaining responsiveness.

---

## Installation

### Prerequisites

- **Node.js** 18.x or higher
- **Python** 3.9 or higher
- **npm** 9.x or higher
- **IMU Streaming App** (for gesture control): [Download from GitHub](https://github.com/blueion0612/IMU_Stream_APP_MJU)

### Step 1: Clone Repository

```bash
git clone https://github.com/blueion0612/IVO.git
cd IVO
```

### Step 2: Install Dependencies

```bash
# Install Node.js dependencies
npm install

# Install Python dependencies (Core)
pip install torch mediapipe opencv-python numpy sympy matplotlib pillow requests websockets

# Install Python dependencies (STT - requires CUDA)
pip install faster-whisper sounddevice

# Install Python dependencies (Summarization)
pip install transformers
```

### Step 3: Download Model Weights

Place the trained model files in the `models/` directory:
- `stage1_best.pt` - Entry detection model
- `stage2_best.pt` - Gesture classification model

---

## Quick Start

### Development Mode

```bash
# Launch with launcher UI
npm start

# Launch directly (skip launcher)
npm run start:direct
```

### Production Build

```bash
# Build for Windows
npm run build

# Build for macOS
npm run build:mac
```

---

## Gesture Commands

IVO recognizes 15 distinct gestures:

| Gesture | Icon | Action | Description |
|---------|------|--------|-------------|
| **Left Swipe** | ⬅️ | Previous Slide | Navigate to previous slide |
| **Right Swipe** | ➡️ | Next Slide | Navigate to next slide |
| **Up Swipe** | ⬆️ | Pointer Mode | Activate laser pointer overlay |
| **Down Swipe** | ⬇️ | STT Recording | Toggle speech-to-text recording |
| **Circle CW** | 🔃 | Start STT Session | Initialize STT and start recording |
| **Circle CCW** | 🔄 | Summarize & Exit | Generate Q&A summary and exit STT |
| **Double Left** | ⏪ | Jump -3 Slides | Skip back 3 slides |
| **Double Right** | ⏩ | Jump +3 Slides | Skip forward 3 slides |
| **X Motion** | ❌ | Reset All | Disable all features and reset state |
| **Double Tap** | 👆👆 | Hand Drawing | Toggle hand tracking drawing mode |
| **90° Left** | ↩️ | OCR Start | Begin OCR session for handwriting |
| **90° Right** | ↪️ | Toggle Draw/Pointer | Switch between drawing and pointer modes |
| **Figure 8** | ♾️ | Timer Toggle | Start/stop presentation timer |
| **Square** | ⬜ | Calibrate | 4-corner hand tracking calibration |
| **Triangle** | 🔺 | Blackout | Toggle screen blackout mode |

---

## Features

### 1. Gesture-Based Slide Control

Control PowerPoint, Keynote, or any presentation software using wrist gestures detected by your smartwatch's IMU sensors.

- **15 Unique Gestures**: Comprehensive gesture set for full presentation control
- **Two-Stage Recognition**: Stage 1 detects gesture start, Stage 2 classifies gesture type
- **Haptic Feedback**: Real-time vibration feedback on smartwatch for gesture confirmation
- **Low Latency**: ~2.5 seconds for gesture recognition with high accuracy

### 2. Hand Tracking Overlay

- **Pointer Mode**: Use your index finger as a laser pointer with visual cursor
- **Drawing Mode**: Draw annotations on screen using pinch gesture (thumb + index finger)
- **Double-Tap Calibration**: Use double-tap gesture to trigger 4-corner screen calibration
- **Calibration Persistence**: Calibration data persists across hand tracking restarts
- **Color Palette**: 6 colors (Red, Yellow, Green, Blue, Purple, Black) with hover-dwell selection
- **Line Width**: 4 thickness options (2px, 4px, 8px, 12px)
- **Control Panel**: On-screen tool panel accessible via hand pointer hover-dwell

### 3. OCR & Calculation

- **Text OCR**: Convert handwritten text to digital text using Google Vision API
- **Math OCR**: Recognize LaTeX mathematical expressions using SimpleTex API
- **Calculator**: Evaluate mathematical expressions with SymPy
- **Graph Plotter**: Generate function graphs with Matplotlib
- **OCR Session**: Draw → OCR → Result display workflow with undo support

### 4. Speech-to-Text (STT) & Q&A Summarization

**Local STT Engine:**
- **Whisper large-v3**: Local speech recognition via faster-whisper
- **CUDA Acceleration**: GPU-accelerated transcription for low latency
- **Multi-language**: Automatic Korean/English language detection
- **VAD Filtering**: Voice Activity Detection to filter silence

**Conversation Stack UI:**
- **Speaker Tags**: Presenter, Q1, Q2, Q3 speaker identification
- **Hand Pointer Selection**: Hover-dwell on speaker buttons to change speaker
- **Real-time Display**: Transcriptions appear immediately with speaker attribution
- **Scrollable History**: Full conversation history with auto-scroll

**Q&A Summarization:**
- **KoBART Model**: Korean BART model for abstractive summarization
- **Q/A Pair Extraction**: Automatically groups questions with presenter answers
- **Bullet-point Format**: Clean, readable summary output
- **Fallback Mode**: Rule-based summarization when model unavailable

**STT Workflow:**
1. **Circle CW** → Initialize STT session (loads Whisper model)
2. **Down Swipe** → Start/stop recording (toggle)
3. Use hand pointer to select speaker for each transcription
4. **Circle CCW** → Generate summary and exit STT mode

### 5. Presentation Timer

- **Visual Display**: Large, readable timer overlay
- **Figure 8 Toggle**: Start/stop timer with figure-8 gesture
- **Elapsed Time**: Shows presentation duration in MM:SS format

### 6. Blackout Mode

- **Triangle Gesture**: Toggle full-screen black overlay
- **Presentation Pause**: Temporarily hide screen content during Q&A or breaks

---

## IMU Data Communication

### Overview

| Parameter | Value |
|-----------|-------|
| Protocol | UDP |
| IMU Port | 65000 |
| Haptic Port | 65010 |
| IMU Endian | Big Endian |
| Haptic Endian | Little Endian |
| Message Size | 120 bytes (30 floats) |

### IMU Data Structure (30 floats)

#### Watch Data (Index 0-14)

| Index | Field | Description | Unit |
|-------|-------|-------------|------|
| 0 | sw_dT | Sample time delta | seconds |
| 1-4 | w_ts_* | Timestamp (h, m, s, nano) | - |
| 5-7 | w_lacc_* | Linear Acceleration (X, Y, Z) | m/s² |
| 8-10 | w_gyro_* | Gyroscope (X, Y, Z) | rad/s |
| 11-14 | w_rotvec_* | Rotation Vector (W, X, Y, Z) | quaternion |

#### Phone Data (Index 15-29)

| Index | Field | Description | Unit |
|-------|-------|-------------|------|
| 15 | p_dT | Sample time delta | seconds |
| 16-19 | p_ts_* | Timestamp (h, m, s, nano) | - |
| 20-22 | p_lacc_* | Linear Acceleration (X, Y, Z) | m/s² |
| 23-25 | p_gyro_* | Gyroscope (X, Y, Z) | rad/s |
| 26-29 | p_rotvec_* | Rotation Vector (W, X, Y, Z) | quaternion |

### Python Parsing Example

```python
import struct

MSG_SIZE = 120  # 30 floats × 4 bytes
data, addr = udp_socket.recvfrom(MSG_SIZE)

# Parse as Big Endian
values = struct.unpack('>30f', data[:MSG_SIZE])

# Extract Watch data
watch_lacc = (values[5], values[6], values[7])      # X, Y, Z
watch_gyro = (values[8], values[9], values[10])     # X, Y, Z
watch_rotvec = (values[11], values[12], values[13], values[14])  # W, X, Y, Z

# Extract Phone data
phone_lacc = (values[20], values[21], values[22])   # X, Y, Z
phone_gyro = (values[23], values[24], values[25])   # X, Y, Z
```

### Haptic Feedback

Send vibration commands to the smartwatch:

```python
import struct

# Haptic parameters
intensity = 200   # 1-255
count = 2         # 1-10
duration = 150    # 50-500 ms

# Pack as Little Endian
data = struct.pack('<iii', intensity, count, duration)
sock.sendto(data, (phone_ip, 65010))
```

### Data Flow Diagram

```
┌─────────────┐    Bluetooth    ┌─────────────┐      UDP        ┌─────────────┐
│   Watch     │  ───────────>   │   Phone     │  ───────────>   │   Server    │
│  (WearOS)   │    IMU 15f      │  (Android)  │   IMU 30f       │  (Python)   │
│             │                 │             │   Port 65000    │             │
│             │                 │             │   Big Endian    │             │
└─────────────┘                 └─────────────┘                 └─────────────┘
      ▲                               ▲                               │
      │        Bluetooth              │           UDP                 │
      │        Big Endian             │        Little Endian          │
      └───────────────────────────────┴───────────────────────────────┘
                              Haptic Command (12 bytes)
                              Port 65010
```

---

## Configuration

Configuration is stored in `config/config.json`:

### Key Settings

```json
{
  "imu": {
    "udp_ip": "192.168.0.48",
    "udp_port": 65000,
    "stage1_threshold": 0.5,
    "stage2_collection_sec": 2.5,
    "cooldown_sec": 2.0
  },
  "websocket": {
    "port": 17890
  },
  "overlay": {
    "default_color": "rgba(255, 0, 0, 0.8)",
    "line_width": 4,
    "hover_duration_ms": 700
  }
}
```

### Gesture Mapping

Customize gesture-to-command mappings in the `gesture_to_command` section.

---

## Keyboard Shortcuts

### Debug Shortcuts (F1-F12)

| Key | Gesture | Action |
|-----|---------|--------|
| F1 | Left | Previous Slide |
| F2 | Right | Next Slide |
| F3 | Up | Pointer Mode ON |
| F4 | Down | STT Recording Toggle |
| F5 | Circle CW | Start STT Session |
| F6 | Circle CCW | Summarize & Exit STT |
| F7 | Double Left | Jump -3 Slides |
| F8 | Double Right | Jump +3 Slides |
| F9 | X | Reset All |
| F10 | Double Tap | Hand Drawing Mode |
| F11 | Figure 8 | Timer Toggle |
| F12 | Triangle | Blackout Toggle |

### Special Keys

| Key | Action |
|-----|--------|
| H | Start Hand Tracking |
| C | Calibrate Hand Tracking (clears saved calibration) |
| P | Toggle Pointer/Drawing Mode |
| M | Test Summary Generation |
| Escape | Quit Application |
| Ctrl+Q | Quit Application |
| Ctrl+Shift+1 | Gesture Detect UI Test |
| Ctrl+Shift+R | Restart Gesture Controller |

---

## Building from Source

### Windows

```bash
npm run build        # Creates NSIS installer
npm run dist         # Creates installer without publishing
npm run build:portable  # Creates portable version
```

### macOS

```bash
npm run build:mac    # Creates DMG
npm run dist:mac     # Creates DMG without publishing
```

### Build Output

Built applications are placed in the `dist/` directory:
- Windows: `IVO Setup 3.0.0.exe`
- macOS: `IVO-3.0.0.dmg`

---

## Project Structure

```
ivo/
├── src/
│   ├── main/                    # Electron main process
│   │   ├── main.js              # Application entry point
│   │   ├── gesture-controller.js # IMU gesture Python manager
│   │   ├── hand-tracking.js     # Hand tracking Python manager
│   │   ├── stt-manager.js       # STT subprocess manager
│   │   ├── summarizer-manager.js # QA summarizer subprocess manager
│   │   ├── websocket-server.js  # WebSocket for gesture data
│   │   ├── ocr-handlers.js      # OCR/calc/graph IPC handlers
│   │   ├── ppt-controller.js    # PPT/Keynote slide control
│   │   └── timer.js             # Presentation timer
│   │
│   ├── preload/
│   │   └── preload.js           # Electron context bridge
│   │
│   └── renderer/                # Frontend UI
│       ├── index.html           # Overlay HTML
│       ├── launcher.html        # Launcher UI
│       ├── overlay.js           # Main overlay logic
│       ├── styles/              # CSS styles
│       └── modules/             # UI modules
│           ├── gesture-ui.js        # Gesture feedback UI
│           ├── hand-cursor.js       # Hand cursor rendering
│           ├── calibration.js       # Calibration UI
│           ├── control-panel.js     # Control panel
│           ├── canvas-drawing.js    # Drawing canvas
│           ├── ocr-manager.js       # OCR results manager
│           ├── conversation-stack.js # STT conversation display
│           └── summary-stack.js     # Summary display
│
├── py/                          # Python modules
│   ├── gesture/                 # IMU gesture recognition
│   │   └── gesture_controller.py
│   ├── vision/                  # Computer vision
│   │   └── hand_tracker.py      # MediaPipe hand tracking
│   ├── stt/                     # Speech-to-Text
│   │   ├── stt_server.py        # Whisper STT server
│   │   ├── qa_summarizer.py     # KoBART summarization module
│   │   └── qa_summarizer_server.py
│   ├── ocr/                     # OCR & Math
│   │   ├── InkOCR.py            # Core OCR engine
│   │   ├── ink_ocr_cli.py       # OCR CLI wrapper
│   │   ├── calc_cli.py          # Calculator CLI
│   │   ├── math_cli.py          # Math operation CLI
│   │   └── graph_cli.py         # Graph plotting CLI
│   └── test/                    # Test scripts
│       ├── imu_test.py          # IMU data test
│       └── realtime_stt.py      # STT console test
│
├── models/                      # Neural network weights
│   ├── stage1_best.pt           # Gesture entry detection
│   └── stage2_best.pt           # Gesture classification
├── config/
│   └── config.json              # Application configuration
├── image/                       # App assets
└── package.json                 # npm configuration
```

---

## Requirements

### Python Dependencies

```
torch>=2.0.0
mediapipe>=0.10.0
opencv-python>=4.8.0
numpy>=1.24.0
sympy>=1.12
matplotlib>=3.7.0
```

### Node.js Dependencies

```json
{
  "dependencies": {
    "ws": "^8.14.2"
  },
  "devDependencies": {
    "electron": "^27.0.0",
    "electron-builder": "^24.13.3"
  }
}
```

### Hardware Requirements

- **Computer**: Windows 10/11 or macOS 10.14+
- **Webcam**: For hand tracking (optional)
- **Smartwatch**: WearOS device with IMU sensors
- **Smartphone**: Android device with [IMU Streaming App](https://github.com/blueion0612/IMU_Stream_APP_MJU)

---

## Troubleshooting

### Python Not Found

Ensure Python is installed and in PATH:

```bash
# Windows
where python

# macOS/Linux
which python3
```

### WebSocket Connection Failed

Check that the IMU Streaming App is running and connected to the same network.

### Hand Tracking Not Working

1. Ensure webcam is connected and accessible
2. Check lighting conditions
3. Run calibration (C key or Square gesture)

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Credits

**IVO - IMU-Vision Overlay**
MJU Capstone Project 2025

Made by **LYH**

---

<div align="center">

**[Report Bug](https://github.com/blueion0612/IVO/issues) · [Request Feature](https://github.com/blueion0612/IVO/issues)**

</div>
