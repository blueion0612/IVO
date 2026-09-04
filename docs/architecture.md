# Architecture


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

IVO uses a two-stage model, so that detecting a gesture and naming it are separate problems:

1. **Stage 1 - Entry Detection**: LSTM-based model that detects when a gesture motion begins
2. **Stage 2 - Gesture Classification**: TCN (Temporal Convolutional Network) that classifies the specific gesture type

This architecture minimizes false positives while maintaining responsiveness.

>  **Training framework**: The gesture recognition models were developed using our custom [IMU Gesture Classifier](https://github.com/blueion0612/IMU_Gesture_Classifier) framework, which supports various architectures (MLP, LSTM, GRU, TCN) for IMU-based gesture recognition.

---
