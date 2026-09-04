# IVO: IMU-Vision Overlay

Yuhyeon Lee · 2025

[![Electron](https://img.shields.io/badge/electron-27.0.0-47848F)](https://www.electronjs.org/)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-lightgrey)](#requirements)
[![License](https://img.shields.io/github/license/blueion0612/IVO)](LICENSE)
[![Release](https://img.shields.io/github/v/release/blueion0612/IVO)](https://github.com/blueion0612/IVO/releases)
[![checks](https://github.com/blueion0612/IVO/actions/workflows/checks.yml/badge.svg)](https://github.com/blueion0612/IVO/actions/workflows/checks.yml)

[**Architecture**](docs/architecture.md) · [**IMU input**](docs/imu-input.md) · [**Pipeline notes**](docs/IVO_System_Pipeline_EN.md) · [**Streaming app**](https://github.com/blueion0612/IMU_Stream_APP_MJU)

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/figures/hero_system-dark.png">
  <img alt="A smartwatch sends inertial data through a phone to the IVO desktop app, a webcam supplies hand landmarks, and haptic acknowledgement returns to the wrist" src="docs/figures/hero_system.png">
</picture>

**IVO** drives a presentation without a clicker. A gesture on a smartwatch changes
the slide, and the watch buzzes back to confirm it was read. A webcam adds hand
tracking for pointing and drawing on top of whatever is on screen. Speech becomes
transcript and summary locally, and handwriting on the overlay becomes text, working
arithmetic and plotted graphs.

## Features

- **IMU Gesture Recognition**: Control presentations using smartwatch gestures (15 unique gestures)
- **Hand Tracking Mode**: Draw and point on screen using webcam-based hand detection
- **Real-time OCR**: Handwriting-to-text conversion with calculation and graph generation
- **Speech-to-Text (STT)**: Local Whisper-based transcription with CUDA acceleration
- **Q&A Summarization**: Ollama LLM (gemma2:9b) for high-quality Q&A summarization
- **Sticky Note Mode**: Voice-to-text sticky notes with dictionary lookup (Korean/English)
- **Vocabulary Dictionary**: Korean (국립국어원 API) and English (Free Dictionary API) word definitions
- **Presentation Timer**: Built-in timer for time management
- **Haptic Feedback**: Vibration feedback on smartwatch for gesture confirmation
- **Device Selection**: Camera and microphone selection by device name for consistent setup
- **Cross-Platform**: Supports Windows and macOS

Each of these is broken down in [the feature notes](docs/features.md).

---

## Quick start

Install first, see [Requirements](#requirements).

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

## Usage

IVO recognizes 15 distinct gestures:

| Gesture | Action | Description |
|---|---|---|
| **Left Swipe** | Previous Slide | Navigate to previous slide |
| **Right Swipe** | Next Slide | Navigate to next slide |
| **Up Swipe** | Pointer Mode | Activate laser pointer overlay |
| **Down Swipe** | STT Recording | Toggle speech-to-text recording |
| **Circle CW** | Recording Mode | Start STT recording session |
| **Circle CCW** | Sticky Note Mode | Toggle sticky note mode with voice input |
| **Double Left** | Jump -3 Slides | Skip back 3 slides |
| **Double Right** | Jump +3 Slides | Skip forward 3 slides |
| **X Motion** | Reset All | Disable all features and reset state |
| **Double Tap** | Hand Drawing | Toggle hand tracking drawing mode |
| **90° Left** | OCR Start | Begin OCR session for handwriting |
| **90° Right** | Toggle Draw/Pointer | Switch between drawing and pointer modes |
| **Figure 8** | Timer Toggle | Start/stop presentation timer |
| **Square** | Calibrate | 4-corner hand tracking calibration |
| **Triangle** | Blackout | Toggle screen blackout mode |

---

### Keyboard shortcuts

### Debug Shortcuts (F1-F12)

| Key | Gesture | Action |
|-----|---------|--------|
| F1 | Left | Previous Slide |
| F2 | Right | Next Slide |
| F3 | Up | Pointer Mode ON |
| F4 | Down | STT Recording Toggle |
| F5 | Circle CW | Recording Mode |
| F6 | Circle CCW | Sticky Note Mode |
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

### Configuration

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

<details>
<summary><b>Troubleshooting</b></summary>

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

</details>

## Repository layout

```
ivo/
├── src/
│   ├── main/                    # Electron main process
│   │   ├── main.js              # Application entry point
│   │   ├── gesture-controller.js # IMU gesture Python manager
│   │   ├── hand-tracking.js     # Hand tracking Python manager
│   │   ├── stt-manager.js       # STT subprocess manager
│   │   ├── summarizer-manager.js # QA summarizer subprocess manager
│   │   ├── vocab-manager.js     # Vocabulary dictionary subprocess manager
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
│           ├── summary-stack.js     # Summary display
│           └── sticky-note-manager.js # Sticky note mode with dictionary
│
├── py/                          # Python modules
│   ├── gesture/                 # IMU gesture recognition
│   │   └── gesture_controller.py
│   ├── vision/                  # Computer vision
│   │   └── hand_tracker.py      # MediaPipe hand tracking
│   ├── stt/                     # Speech-to-Text
│   │   ├── stt_server.py        # Whisper STT server
│   │   ├── qa_summarizer.py     # Ollama LLM summarization module
│   │   └── qa_summarizer_server.py
│   ├── vocab/                   # Vocabulary dictionary
│   │   └── vocab_server.py      # Korean/English dictionary server
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
requests>=2.28.0
pygrabber>=0.2
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

<details>
<summary><b>Installing and building from source</b></summary>

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

# Install Ollama for Q&A Summarization
# Download from https://ollama.com/download
# Then pull the model:
ollama pull gemma2:9b
```

### Step 3: Download Model Weights

Download the pre-trained gesture recognition models from the [Google Drive](https://drive.google.com/drive/folders/1eac_bqIQ1vY2Z1D-OqNQRVsJi-RC-cR-?usp=drive_link) and place them in the `models/` directory:
- `stage1_best.pt` - Entry detection model
- `stage2_best.pt` - Gesture classification model

> **Note**: These models were trained using the [IMU Gesture Classifier](https://github.com/blueion0612/IMU_Gesture_Classifier) framework. The Google Drive also contains the original IMU gesture dataset if you want to train custom models.

### Step 4: Configure API Keys (Optional)

For Korean dictionary lookup in Sticky Note mode, create a `.env` file in the project root:

```bash
# .env
KOREAN_DICT_API_KEY=your_api_key_here
```

Get your free API key from [국립국어원 Open API](https://opendict.korean.go.kr/service/openApiInfo).

> **Note**: English dictionary lookup works without any API key using the free [Free Dictionary API](https://dictionaryapi.dev/).

---

### Building

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

</details>

## Limitations

- **The models are trained on one wearer.** Gesture recognition has not been
  evaluated on anyone else's movements, and the two-stage detector's thresholds were
  tuned by hand.
- **UDP with no acknowledgement.** A dropped packet shortens the window the
  classifier sees, and nothing detects that.
- **The desktop app must be reachable from the phone**, which means the same local
  network and no client isolation on the access point.
- **Speech to text and summarisation run locally**, so both want a GPU. On CPU they
  work but are not interactive.
- **Hand tracking needs the calibration step** whenever the camera or the screen
  moves.
- Windows and macOS only. Nothing here has been run on Linux.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**IVO - IMU-Vision Overlay**
MJU Capstone Project 2025

Made by **LYH**

### Related Repositories

| Repository | Description |
|------------|-------------|
| [IMU Streaming App](https://github.com/blueion0612/IMU_Stream_APP_MJU) | WearOS/Android app for streaming IMU sensor data |
| [IMU Gesture Classifier](https://github.com/blueion0612/IMU_Gesture_Classifier) | Training framework for gesture recognition models |

### Resources

- [Pre-trained Models & Dataset (Google Drive)](https://drive.google.com/drive/folders/1eac_bqIQ1vY2Z1D-OqNQRVsJi-RC-cR-?usp=drive_link)

---

<div align="center">

**[Report Bug](https://github.com/blueion0612/IVO/issues) · [Request Feature](https://github.com/blueion0612/IVO/issues)**

</div>

