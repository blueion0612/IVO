# Feature notes

What each part of IVO does, in detail. The summary is in the
[README](../README.md#features).

## 1. Gesture-Based Slide Control

Control PowerPoint, Keynote, or any presentation software using wrist gestures detected by your smartwatch's IMU sensors.

- **15 gestures**, covering navigation, the pointer, drawing, recording and the timer
- **Two-Stage Recognition**: Stage 1 detects gesture start, Stage 2 classifies gesture type
- **Haptic Feedback**: Real-time vibration feedback on smartwatch for gesture confirmation
- **Recognition takes about 2.5 seconds**, which is the length of the buffer the
  classifier reads after the detector fires

## 2. Hand Tracking Overlay

- **Pointer Mode**: Use your index finger as a laser pointer with visual cursor
- **Drawing Mode**: Draw annotations on screen using pinch gesture (thumb + index finger)
- **Double-Tap Calibration**: Use double-tap gesture to trigger 4-corner screen calibration
- **Calibration Persistence**: Calibration data persists across hand tracking restarts
- **Color Palette**: 6 colors (Red, Yellow, Green, Blue, Purple, Black) with hover-dwell selection
- **Line Width**: 4 thickness options (2px, 4px, 8px, 12px)
- **Control Panel**: On-screen tool panel accessible via hand pointer hover-dwell

## 3. OCR & Calculation

- **Text OCR**: Convert handwritten text to digital text using Google Vision API
- **Math OCR**: Recognize LaTeX mathematical expressions using SimpleTex API
- **Calculator**: Evaluate mathematical expressions with SymPy
- **Graph Plotter**: Generate function graphs with Matplotlib
- **OCR Session**: Draw → OCR → Result display workflow with undo support

## 4. Speech-to-Text (STT) & Q&A Summarization

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
- **Ollama LLM (gemma2:9b)**: High-quality abstractive summarization using local LLM
- **Q/A Pair Extraction**: Automatically groups questions with presenter answers
- **Full Context Summarization**: Both questions and answers are summarized preserving all key topics
- **Bullet-point Format**: Clean, readable summary output (Q1/A1, Q2/A2 format)
- **Fallback Mode**: Rule-based summarization when Ollama unavailable

**STT Workflow:**
1. **Circle CW** → Initialize STT session (loads Whisper model)
2. **Down Swipe** → Start/stop recording (toggle)
3. Use hand pointer to select speaker for each transcription
4. **Circle CCW** → Generate summary and exit STT mode

## 5. Sticky Note Mode

Voice-to-text sticky notes with integrated dictionary lookup:

- **Voice Recording**: Press + button or use hand pointer hover-dwell to record
- **STT Integration**: Automatic transcription using Whisper large-v3
- **Dictionary Lookup**: Built-in Korean/English dictionary for word definitions
- **Draggable Notes**: Drag notes anywhere on screen with mouse or hand pointer
- **Hand Tracking Support**: Full hover-dwell interaction with hand pointer

**Dictionary Features:**
- **Korean Dictionary**: 국립국어원 Open API (requires API key in `.env`)
- **English Dictionary**: Free Dictionary API (no key required)
- **Auto Language Detection**: Automatically detects Korean or English input
- **Korean Particle Removal**: Intelligently strips particles (은/는/이/가/을/를) for better lookup
- **Multi-word Support**: Looks up each word in a sentence with page navigation
- **Punctuation Handling**: Automatically removes punctuation from words

**Sticky Note Workflow:**
1. **Circle CCW** → Enter sticky note mode
2. Press **+** button (hover-dwell) → Start recording
3. Speak → Press **+** again → Creates note with transcription
4. Press **** button → View dictionary definitions
5. Use **◀ ▶** buttons to navigate between words
6. **Circle CCW** again → Exit sticky note mode

## 6. Presentation Timer

- **Visual Display**: Large, readable timer overlay
- **Figure 8 Toggle**: Start/stop timer with figure-8 gesture
- **Elapsed Time**: Shows presentation duration in MM:SS format

## 7. Blackout Mode

- **Triangle Gesture**: Toggle full-screen black overlay
- **Presentation Pause**: Temporarily hide screen content during Q&A or breaks

## 8. Device Selection

The launcher allows selection of specific camera and microphone devices by name:

- **Camera Selection**: Choose webcam by device name for consistent hand tracking
- **Microphone Selection**: Choose microphone by device name for STT
- **Name-based Matching**: Devices are matched by name, not index (handles USB port changes)
- **Persistent Settings**: Selected devices are remembered across sessions

---
