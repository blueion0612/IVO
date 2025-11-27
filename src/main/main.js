// IVO Main Process - v3.0.0
const { app, BrowserWindow, globalShortcut, ipcMain } = require("electron");
const path = require("path");
const fs = require("fs");
const os = require("os");
const { exec } = require("child_process");

const HandTrackingManager = require("./hand-tracking");
const GestureControllerManager = require("./gesture-controller");
const GestureWebSocketServer = require("./websocket-server");
const PresentationTimer = require("./timer");
const STTManager = require("./stt-manager");
const SummarizerManager = require("./summarizer-manager");
const { pptPrev, pptNext, jumpSlides } = require("./ppt-controller");
const { setupOCRHandlers } = require("./ocr-handlers");

const configPath = path.join(__dirname, "../../config/config.json");
const config = JSON.parse(fs.readFileSync(configPath, "utf-8"));
const basePath = path.join(__dirname, "../..");

let win = null;
let launcherWin = null;
let overlayVisible = true;
let activeFeature = null;

const handTracking = new HandTrackingManager(config);
const gestureController = new GestureControllerManager(config);
const wsServer = new GestureWebSocketServer(config);
const timer = new PresentationTimer();
const sttManager = new STTManager(config);
const summarizerManager = new SummarizerManager(config);
const colorPalette = config.colors.palette;
let currentColorIndex = 0;
let currentSpeaker = "presenter";  // Current speaker selection
let summarizerStarted = false;  // Track if summarizer has been started

function getWindow() {
    return win;
}

function bringOverlayToFront() {
    if (!win) return;
    win.setAlwaysOnTop(true, "screen-saver");
    win.showInactive();
    overlayVisible = true;
    showOverlayMessage("🟢 Overlay Activated");
}

function hideOverlay() {
    if (!win) return;
    win.setAlwaysOnTop(false);
    win.hide();
    overlayVisible = false;
    showOverlayMessage("🔴 Overlay Hidden");
}

function setClickThrough(isThrough) {
    if (!win) return;
    win.setIgnoreMouseEvents(isThrough, { forward: isThrough });
    console.log(`[overlay] click-through ${isThrough ? "ON" : "OFF"}`);
}

function showOverlayMessage(text, color = "rgba(0,0,0,0.7)") {
    if (win && win.webContents) {
        win.webContents.send("cmd", { type: "showNotice", text, color });
    }
}

handTracking.onMessage((msg) => {
    switch (msg.type) {
        case "ready":
            console.log("[HandTracking] Ready:", msg);
            win.webContents.send("cmd", {
                type: "handTrackingReady",
                camera: msg.camera
            });
            break;

        case "cursor":
            win.webContents.send("cmd", {
                type: "handCursor",
                position: msg.position,
                drawing: msg.drawing,
                calibrating: msg.calibrating,
                pinkyState: msg.pinkyState !== undefined ? msg.pinkyState : (msg.drawing ? 0 : 1)
            });
            break;

        case "calibration_started":
            showOverlayMessage("Calibration: Show 4 corners");
            win.webContents.send("cmd", { type: "calibrationStarted" });
            break;

        case "calibration_point":
            showOverlayMessage(`Point ${msg.index}/${msg.total} recorded`);
            win.webContents.send("cmd", {
                type: "calibrationPoint",
                index: msg.index,
                position: msg.position,
                total: msg.total
            });
            wsServer.sendHaptic("calibration_point");              break;

        case "calibration_done":
            showOverlayMessage("Calibration complete!");
            win.webContents.send("cmd", {
                type: "calibrationDone",
                region: msg.region
            });
            wsServer.sendHaptic("calibration_done");
            break;

        case "calibration_reset":
            showOverlayMessage("Calibration reset");
            win.webContents.send("cmd", { type: "calibrationReset" });
            break;

        case "error":
            console.log(`[HandTracking] Error:`, msg.message);
            showOverlayMessage(msg.message, "rgba(200,0,0,0.7)");
            break;

        case "shutdown":
            console.log("[HandTracking] Shutdown");
            break;
    }
});

timer.setUpdateCallback((timeStr) => {
    if (win && win.webContents) {
        win.webContents.send("cmd", { type: "updateTimer", time: timeStr });
    }
});

timer.setStopCallback(() => {
    if (win && win.webContents) {
        win.webContents.send("cmd", { type: "hideTimer" });
    }
});

// ===== STT Manager message handler =====
sttManager.onMessage((msg) => {
    switch (msg.type) {
        case "ready":
            console.log("[STT] Service ready");
            if (win && win.webContents) {
                win.webContents.send("cmd", { type: "sttReady" });
            }
            break;

        case "recording_started":
            if (win && win.webContents) {
                win.webContents.send("cmd", { type: "sttRecordingStarted" });
            }
            break;

        case "recording_stopped":
            if (win && win.webContents) {
                win.webContents.send("cmd", { type: "sttRecordingStopped" });
            }
            break;

        case "transcription":
            console.log(`[STT] Text: ${msg.text}`);
            if (win && win.webContents) {
                win.webContents.send("cmd", {
                    type: "sttTranscription",
                    text: msg.text,
                    lang: msg.lang,
                    prob: msg.prob,
                    duration: msg.duration,
                    speaker: currentSpeaker
                });
            }
            break;

        case "error":
            console.error("[STT] Error:", msg.message);
            if (win && win.webContents) {
                win.webContents.send("cmd", {
                    type: "sttError",
                    message: msg.message
                });
            }
            break;
    }
});

function changeColor(direction) {
    if (direction === "prev") {
        currentColorIndex = (currentColorIndex - 1 + colorPalette.length) % colorPalette.length;
    } else {
        currentColorIndex = (currentColorIndex + 1) % colorPalette.length;
    }

    const newColor = colorPalette[currentColorIndex].value;
    win.webContents.send("cmd", {
        type: "changeColor",
        color: newColor
    });

    showOverlayMessage(`Color: ${colorPalette[currentColorIndex].name}`);
}

let lastCodeTime = 0;
let lastCode = null;
const CODE_DEBOUNCE_MS = 300;

function handleCode(code, payload = {}) {
    const now = Date.now();

    if (code === lastCode && (now - lastCodeTime) < CODE_DEBOUNCE_MS) {
        console.log(`[Control] ✗ Debounced: ${code}`);
        return;
    }

    lastCode = code;
    lastCodeTime = now;

    console.log(`[Control] ✓ Execute: ${code}`);

    switch (code) {
        case "0":
            // Up gesture - Toggle hand tracking pointer mode (works globally)
            if (!handTracking.isRunning()) {
                // Start hand tracking with pointer mode
                handTracking.start(basePath);
                if (win && win.webContents) {
                    win.webContents.send("cmd", { type: "startHandPointer" });
                }
                setClickThrough(false);
                showOverlayMessage("👆 Hand Pointer Mode ON");
            } else {
                // Stop hand tracking
                handTracking.stop();
                if (win && win.webContents) {
                    win.webContents.send("cmd", { type: "stopHandPointer" });
                }
                setClickThrough(true);
                showOverlayMessage("👆 Hand Pointer Mode OFF");
            }
            wsServer.sendHaptic("mode_pointer");
            break;

        case "1":
            // Down gesture - Recording toggle (only in recording mode)
            if (activeFeature === "recording") {
                if (sttManager.isRecording()) {
                    sttManager.stopRecording();
                    showOverlayMessage("⏹ Recording Stopped");
                } else {
                    sttManager.startRecording();
                    showOverlayMessage("🔴 Recording...");
                }
                wsServer.sendHaptic("recording_toggle");
            } else {
                showOverlayMessage("⚠️ Not in recording mode");
            }
            break;

        case "2":
            if (win && win.webContents) {
                win.webContents.send("cmd", { type: "resetAll" });
            }
            setClickThrough(true);
            activeFeature = null;
            handTracking.stop();
            // Stop STT if running
            if (sttManager.isRecording()) {
                sttManager.stopRecording();
            }
            sttManager.stop();
            if (timer.isRunning()) {
                timer.stop();
            }
            showOverlayMessage("🔄 All Features Disabled");
            break;

        case "3":
            pptPrev();
            showOverlayMessage("◀ Previous Slide");
            wsServer.sendHaptic("slide_change");
            break;

        case "4":
            pptNext();
            showOverlayMessage("▶ Next Slide");
            wsServer.sendHaptic("slide_change");
            break;

        case "5":
            // Circle CW - Enter recording mode (start STT service)
            if (activeFeature && activeFeature !== "recording") {
                showOverlayMessage("⚠️ Reset first");
                return;
            }
            activeFeature = "recording";
            sttManager.start(basePath);
            win.webContents.send("cmd", { type: "recordingModeEnter" });
            setClickThrough(true);
            showOverlayMessage("🎙️ Recording Mode - Ready");
            wsServer.sendHaptic("recording_toggle");
            break;

        case "6":
            if (activeFeature && activeFeature !== "handDraw") {
                showOverlayMessage("⚠️ Reset first");
                return;
            }
            activeFeature = "handDraw";
            handTracking.start(basePath);
            win.webContents.send("cmd", { type: "toggleHandDraw" });
            win.webContents.send("cmd", { type: "setPointerMode", enabled: true });
            setClickThrough(true);
            showOverlayMessage("✋ Hand Tracking - Pointer Mode");
            wsServer.sendHaptic("mode_pointer");
            break;

        case "7":
            if (activeFeature && activeFeature !== "drawing") {
                showOverlayMessage("⚠️ Reset first");
                return;
            }
            activeFeature = "drawing";
            setClickThrough(false);
            win.webContents.send("cmd", { type: "toggleDrawing" });
            showOverlayMessage("✏️ Drawing Mode (Mouse)");
            wsServer.sendHaptic("mode_drawing");
            break;

        case "8":
            // Circle CCW - Exit recording mode (stop STT service)
            if (activeFeature !== "recording") {
                showOverlayMessage("⚠️ Not in recording mode");
                return;
            }
            // Stop recording if active
            if (sttManager.isRecording()) {
                sttManager.stopRecording();
            }
            sttManager.stop();
            win.webContents.send("cmd", { type: "recordingModeExit" });
            setClickThrough(true);
            activeFeature = null;
            showOverlayMessage("⏹ Recording Mode Exit");
            wsServer.sendHaptic("recording_toggle");
            break;

        case "9":
            if (activeFeature && activeFeature !== "pointer") {
                showOverlayMessage("⚠️ Reset first");
                return;
            }
            activeFeature = "pointer";
            setClickThrough(false);
            win.webContents.send("cmd", { type: "togglePointer" });
            showOverlayMessage("👆 Pointer Mode (Mouse)");
            wsServer.sendHaptic("mode_pointer");
            break;

        case "TIMER_TOGGLE":
            if (timer.isRunning()) {
                timer.stop();
                showOverlayMessage("⏱️ Timer Stopped");
            } else {
                timer.start();
                showOverlayMessage("⏱️ Timer Started");
            }
            wsServer.sendHaptic("selection_tick");
            break;

        case "BLACKOUT":
            win.webContents.send("cmd", { type: "toggleBlackout" });
            showOverlayMessage("⚫ Blackout Toggle");
            wsServer.sendHaptic("selection_tick");
            break;

        case "OCR_START":
            if (win && win.webContents) {
                win.webContents.send("cmd", { type: "OCR_START" });
            }
            wsServer.sendHaptic("ocr_start");
            break;

        case "T":
        case "TEXT_OCR":
            if (win && win.webContents) {
                win.webContents.send("cmd", { type: "TEXT_OCR" });
            }
            break;

        case "Y":
        case "MATH_OCR":
            if (win && win.webContents) {
                win.webContents.send("cmd", { type: "MATH_OCR" });
            }
            break;

        case "=":
        case "EVAL_EXPR":
            if (win && win.webContents) {
                win.webContents.send("cmd", { type: "EVAL_EXPR" });
            }
            break;

        case "G":
        case "g":
        case "DRAW_GRAPH":
            if (win && win.webContents) {
                win.webContents.send("cmd", { type: "DRAW_GRAPH" });
            }
            break;

        case "JUMP_3_PREV":
        case "JUMP_BACK":
            const msgPrev = jumpSlides(-3);
            showOverlayMessage(msgPrev);
            wsServer.sendHaptic("slide_change");
            break;

        case "JUMP_3_NEXT":
        case "JUMP_FORWARD":
            const msgNext = jumpSlides(3);
            showOverlayMessage(msgNext);
            wsServer.sendHaptic("slide_change");
            break;

        case "COLOR_PREV":
            changeColor("prev");
            wsServer.sendHaptic("selection_tick");
            break;

        case "COLOR_NEXT":
            changeColor("next");
            wsServer.sendHaptic("selection_tick");
            break;

        case "TOGGLE_DRAW_POINTER":
            if (win && win.webContents) {
                win.webContents.send("cmd", { type: "TOGGLE_DRAW_POINTER" });
            }
            wsServer.sendHaptic("mode_drawing");
            break;

        case "H":
        case "h":
            activeFeature = "handDraw";
            handTracking.start(basePath);
            win.webContents.send("cmd", { type: "toggleHandDraw" });
            setClickThrough(true);
            showOverlayMessage("✋ Hand Drawing Mode");
            wsServer.sendHaptic("mode_drawing");
            break;

        case "C":
        case "c":
        case "CALIBRATE":
            // Clear saved calibration when user explicitly requests new calibration
            handTracking.clearSavedCalibration();

            // Start hand tracking if not running, then calibrate
            if (!handTracking.isRunning()) {
                handTracking.start(basePath);
                // Wait a bit for hand tracking to initialize
                setTimeout(() => {
                    win.webContents.send("cmd", { type: "CALIBRATE" });
                    showOverlayMessage("📐 Calibration Started");
                    wsServer.sendHaptic("calibration_point");
                }, 1000);
            } else {
                win.webContents.send("cmd", { type: "CALIBRATE" });
                showOverlayMessage("📐 Calibration");
                wsServer.sendHaptic("calibration_point");
            }
            break;

        case "P":
        case "p":
            if (handTracking.isRunning()) {
                handTracking.send({ command: "toggle_pointer" });
                const isPointer = !win.webContents.isIgnoreMouseEvents;
                win.webContents.send("cmd", { type: "setPointerMode", enabled: !isPointer });
                wsServer.sendHaptic("mode_pointer");
            }
            break;

        case "Z":
        case "z":
            if (handTracking.isRunning()) {
                handTracking.send({ command: "reset_calibration" });
            }
            break;

        default:
            console.log(`[Control] Unknown code: ${code}`);
    }
}

wsServer.setGestureDetectedCallback((duration) => {
    if (win && win.webContents) {
        win.webContents.send("cmd", {
            type: "gestureDetecting",
            duration: duration
        });
    }
});

wsServer.setGestureRecognizedCallback((gesture, confidence) => {
    if (win && win.webContents) {
        win.webContents.send("cmd", {
            type: "gestureRecognized",
            gesture: gesture,
            confidence: confidence
        });
    }
});

wsServer.setHoldExtendedCallback((remaining) => {
    if (win && win.webContents) {
        win.webContents.send("cmd", {
            type: "holdExtended",
            remaining: remaining
        });
    }
});

wsServer.setStage2CancelledCallback(() => {
    if (win && win.webContents) {
        win.webContents.send("cmd", {
            type: "stage2Cancelled"
        });
    }
});

wsServer.setCodeCallback((code, payload) => {
    handleCode(code, payload || {});
});

ipcMain.handle("send-to-handtracker", async (event, command) => {
    if (!handTracking.isRunning()) {
        throw new Error("Hand tracking not active");
    }
    handTracking.send(command);
    return true;
});

// ===== STT IPC handlers =====
ipcMain.handle("stt-set-speaker", async (event, speaker) => {
    currentSpeaker = speaker;
    console.log(`[STT] Speaker changed to: ${speaker}`);
    return true;
});

ipcMain.handle("stt-start-recording", async (event) => {
    if (!sttManager.isRunning()) {
        throw new Error("STT service not running");
    }
    return sttManager.startRecording();
});

ipcMain.handle("stt-stop-recording", async (event) => {
    if (!sttManager.isRunning()) {
        throw new Error("STT service not running");
    }
    return sttManager.stopRecording();
});

ipcMain.handle("stt-is-recording", async (event) => {
    return sttManager.isRecording();
});

ipcMain.handle("stt-is-ready", async (event) => {
    return sttManager.isMicReady();
});

ipcMain.handle("stt-request-summary", async (event, conversations) => {
    try {
        // Use local KoBART summarizer
        console.log("[Summarizer] Requesting local summary for", conversations.length, "conversations");

        // Start summarizer if not already running
        if (!summarizerManager.isRunning()) {
            console.log("[Summarizer] Starting summarizer service...");
            await summarizerManager.start(basePath);
            summarizerStarted = true;
        }

        // Wait for model to be ready
        if (!summarizerManager.isReady()) {
            console.log("[Summarizer] Waiting for model to load...");
            // Give it some time
            await new Promise(resolve => setTimeout(resolve, 2000));
            if (!summarizerManager.isReady()) {
                throw new Error("Summarizer model not ready");
            }
        }

        const result = await summarizerManager.summarize(conversations);
        console.log("[Summarizer] Summary received:", result.summary?.substring(0, 50));
        return result;
    } catch (err) {
        console.error("[Summarizer] Local summary failed:", err);

        // Fallback to external API if local fails
        try {
            console.log("[Summarizer] Falling back to external API...");
            const summaryUrl = config.api.summary_url;
            const response = await fetch(summaryUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ conversations })
            });

            if (!response.ok) {
                throw new Error(`HTTP error: ${response.status}`);
            }

            const result = await response.json();
            console.log("[Summarizer] API fallback summary received");
            return result;
        } catch (apiErr) {
            console.error("[Summarizer] API fallback also failed:", apiErr);
            return { error: `Local: ${err.message}, API: ${apiErr.message}` };
        }
    }
});

function registerDebugShortcuts() {
    const shortcuts = config.debug.shortcuts;
    const specialShortcuts = config.debug.special_shortcuts;

    Object.keys(shortcuts).forEach(key => {
        const shortcut = shortcuts[key];
        globalShortcut.register(key, () => {
            console.log(`[Debug] ${key} - ${shortcut.name}`);
            if (win && win.webContents) {
                win.webContents.send("cmd", {
                    type: "gestureRecognized",
                    gesture: shortcut.gesture,
                    confidence: 1.0
                });
            }
            handleCode(shortcut.code);
        });
    });

    if (specialShortcuts) {
        if (specialShortcuts["Ctrl+Shift+1"]) {
            globalShortcut.register("Ctrl+Shift+1", () => {
                if (win && win.webContents) {
                    win.webContents.send("cmd", { type: "gestureDetecting", duration: 3 });
                }
            });
        }

        if (specialShortcuts["Ctrl+Shift+R"]) {
            globalShortcut.register("Ctrl+Shift+R", () => {
                gestureController.restart(basePath);
            });
        }
    }

    globalShortcut.register("M", () => {
        if (win && win.webContents) {
            win.webContents.send("cmd", {
                type: "summaryTest",
                text: "This is a test summary message."
            });
        }
    });

    globalShortcut.register("Escape", () => app.quit());
    globalShortcut.register("Ctrl+Q", () => app.quit());

    console.log("[Debug] Shortcuts registered");
}

function getLocalIP() {
    const interfaces = os.networkInterfaces();
    for (const name of Object.keys(interfaces)) {
        for (const iface of interfaces[name]) {
            // Skip internal and non-IPv4 addresses
            if (!iface.internal && iface.family === "IPv4") {
                return iface.address;
            }
        }
    }
    return "127.0.0.1";
}

function getWiFiName() {
    return new Promise((resolve) => {
        if (process.platform === "win32") {
            exec("netsh wlan show interfaces", { encoding: "utf8" }, (err, stdout) => {
                if (err) {
                    resolve("Unknown");
                    return;
                }
                const match = stdout.match(/SSID\s*:\s*(.+)/);
                if (match && match[1]) {
                    resolve(match[1].trim());
                } else {
                    resolve("Not Connected");
                }
            });
        } else if (process.platform === "darwin") {
            exec("/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport -I | grep ' SSID'",
                { encoding: "utf8" }, (err, stdout) => {
                if (err) {
                    resolve("Unknown");
                    return;
                }
                const match = stdout.match(/SSID:\s*(.+)/);
                resolve(match ? match[1].trim() : "Unknown");
            });
        } else {
            exec("iwgetid -r", { encoding: "utf8" }, (err, stdout) => {
                resolve(err ? "Unknown" : stdout.trim() || "Not Connected");
            });
        }
    });
}

function createLauncherWindow() {
    launcherWin = new BrowserWindow({
        width: 500,
        height: 520,
        resizable: false,
        frame: true,
        backgroundColor: "#0d1f3c",
        webPreferences: {
            preload: path.join(__dirname, "../preload/preload.js"),
            contextIsolation: false,
            nodeIntegration: true
        },
        show: false
    });

    const launcherPath = path.join(__dirname, "../renderer/launcher.html");
    launcherWin.loadFile(launcherPath);

    launcherWin.once("ready-to-show", () => {
        launcherWin.show();
    });

    launcherWin.on("closed", () => {
        launcherWin = null;
        // If overlay is not started, quit app
        if (!win) {
            app.quit();
        }
    });
}

ipcMain.handle("get-network-info", async () => {
    const ip = getLocalIP();
    const wifi = await getWiFiName();
    return { ip, wifi };
});

ipcMain.on("start-overlay", (event, networkInfo) => {
    if (launcherWin) {
        launcherWin.close();
    }

    if (networkInfo && networkInfo.ip) {
        config.imu.udp_ip = networkInfo.ip;
        try {
            fs.writeFileSync(configPath, JSON.stringify(config, null, 2), "utf-8");
        } catch (err) {
            console.error("[App] Failed to save config:", err);
        }
    }

    wsServer.start();
    createWindow();
    setupOCRHandlers(ipcMain, getWindow, basePath, config);
    registerDebugShortcuts();
});

function createWindow() {
    win = new BrowserWindow({
        transparent: true,
        backgroundColor: "#00000000",
        frame: false,
        fullscreen: false,
        hasShadow: false,
        alwaysOnTop: true,
        focusable: false,
        webPreferences: {
            preload: path.join(__dirname, "../preload/preload.js"),
            contextIsolation: true,
        },
        show: false,
    });

    win.setFullScreen(true);
    win.setVisibleOnAllWorkspaces(true);

    const htmlPath = path.join(__dirname, "../renderer/index.html");
    win.loadFile(htmlPath);

    win.once("ready-to-show", () => {
        win.show();
        setClickThrough(true);
        setTimeout(() => gestureController.start(basePath), 2000);
    });

    win.on("closed", () => {
        handTracking.stop();
        gestureController.stop();
    });
}

app.whenReady().then(() => {
    const skipLauncher = process.argv.includes("--direct");

    if (skipLauncher) {
        wsServer.start();
        createWindow();
        setupOCRHandlers(ipcMain, getWindow, basePath, config);
        registerDebugShortcuts();
    } else {
        createLauncherWindow();
    }
});

app.on("will-quit", () => {
    globalShortcut.unregisterAll();
    handTracking.stop();
    gestureController.stop();
    sttManager.stop();
    summarizerManager.stop();
    wsServer.stop();
});

app.on("window-all-closed", () => {
    if (process.platform !== "darwin") {
        app.quit();
    }
});

app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
    }
});
