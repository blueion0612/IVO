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
const colorPalette = config.colors.palette;
let currentColorIndex = 0;

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
            bringOverlayToFront();
            break;

        case "1":
            hideOverlay();
            break;

        case "2":
            if (win && win.webContents) {
                win.webContents.send("cmd", { type: "resetAll" });
            }
            setClickThrough(true);
            activeFeature = null;
            handTracking.stop();
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
            if (activeFeature && activeFeature !== "caption") {
                showOverlayMessage("⚠️ Reset first");
                return;
            }
            activeFeature = "caption";
            win.webContents.send("cmd", { type: "captionStart" });
            setClickThrough(true);
            showOverlayMessage("🎙️ Caption Recording Started");
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
            if (activeFeature !== "caption") {
                showOverlayMessage("⚠️ Not in caption mode");
                return;
            }
            win.webContents.send("cmd", { type: "captionStopAndSummarize" });
            setClickThrough(true);
            showOverlayMessage("⏹ Caption Stop & Summarize");
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
            if (handTracking.isRunning()) {
                win.webContents.send("cmd", { type: "CALIBRATE" });
                showOverlayMessage("📐 Calibration");
                wsServer.sendHaptic("calibration_point");
            } else {
                showOverlayMessage("⚠️ Start hand tracking first (H)");
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
