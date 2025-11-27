// src/renderer/overlay.js
// ======================================================================
// Production-ready integrated overlay - Modular version v3.0.0
// ======================================================================

// Module imports
import { CanvasDrawing } from './modules/canvas-drawing.js';
import { GestureUI } from './modules/gesture-ui.js';
import { HandCursor } from './modules/hand-cursor.js';
import { ControlPanel } from './modules/control-panel.js';
import { OCRManager } from './modules/ocr-manager.js';
import { CalibrationManager } from './modules/calibration.js';
import { RecordingManager } from './modules/recording.js';
import { OverlayUI } from './modules/overlay-ui.js';
import { SummaryStack } from './modules/summary-stack.js';
import { ConversationStack } from './modules/conversation-stack.js';

// Load configuration
const config = {
    overlay: {
        default_color: "rgba(255, 0, 0, 0.8)",
        line_width: 4,
        hover_duration_ms: 700,
        gesture_detect_duration_sec: 2.5
    },
    api: {
        summary_url: "http://127.0.0.1:8000/summarize"
    },
    gesture_display_names: {
        "left": "Previous Slide",
        "right": "Next Slide",
        "up": "Pointer Mode",
        "down": "Record Toggle",
        "circle_cw": "Recording Mode",
        "circle_ccw": "Exit Recording",
        "double_tap": "Hand Drawing",
        "x": "Reset All",
        "square": "Calibration",
        "double_left": "Jump -3 Slides",
        "double_right": "Jump +3 Slides",
        "90_left": "OCR Start",
        "90_right": "Toggle Draw/Pointer",
        "figure_eight": "Timer Toggle",
        "triangle": "Blackout"
    },
    gesture_list: [
        { icon: "⬅️", name: "Left", desc: "Previous Slide" },
        { icon: "➡️", name: "Right", desc: "Next Slide" },
        { icon: "⬆️", name: "Up", desc: "Pointer Mode" },
        { icon: "⬇️", name: "Down", desc: "Record Toggle" },
        { icon: "🔃", name: "Circle CW", desc: "Recording Mode" },
        { icon: "🔄", name: "Circle CCW", desc: "Exit Recording" },
        { icon: "⏪", name: "Double Left", desc: "Jump -3 slides" },
        { icon: "⏩", name: "Double Right", desc: "Jump +3 slides" },
        { icon: "❌", name: "X", desc: "Reset All" },
        { icon: "👆👆", name: "Double Tap", desc: "Hand Drawing" },
        { icon: "↩️", name: "90° Left", desc: "OCR Start" },
        { icon: "↪️", name: "90° Right", desc: "Toggle Draw/Pointer" },
        { icon: "♾️", name: "Figure 8", desc: "Timer Toggle" },
        { icon: "⬜", name: "Square", desc: "Calibrate" },
        { icon: "🔺", name: "Triangle", desc: "Blackout" }
    ],
    colors: {
        control_panel: [
            { type: "color", name: "Red", color: "rgba(255, 0, 0, 0.8)" },
            { type: "color", name: "Yellow", color: "rgba(255, 200, 0, 0.8)" },
            { type: "color", name: "Green", color: "rgba(0, 200, 0, 0.8)" },
            { type: "color", name: "Blue", color: "rgba(0, 100, 255, 0.8)" },
            { type: "color", name: "Purple", color: "rgba(200, 0, 255, 0.8)" },
            { type: "color", name: "Black", color: "rgba(0, 0, 0, 0.8)" },
            { type: "divider" },
            { type: "linewidth", name: "2", width: 2, title: "Thin" },
            { type: "linewidth", name: "4", width: 4, title: "Normal" },
            { type: "linewidth", name: "8", width: 8, title: "Thick" },
            { type: "linewidth", name: "12", width: 12, title: "Extra Thick" },
            { type: "divider" },
            { type: "function", name: "🧹", action: "ERASER", title: "Eraser" },
            { type: "function", name: "🗑️", action: "CLEAR_ALL", title: "Clear All" },
            { type: "divider" },
            { type: "function", name: "📝", action: "OCR_START", title: "Start OCR Session" },
            { type: "function", name: "TEXT", action: "TEXT_OCR", title: "Text OCR" },
            { type: "function", name: "MATH", action: "MATH_OCR", title: "Math OCR" },
            { type: "divider" },
            { type: "function", name: "👉", action: "POINTER", title: "Toggle Pointer/Drawing" },
            { type: "function", name: "📐", action: "CALIBRATE", title: "Calibration" }
        ]
    }
};

// DOM elements
const canvas = document.getElementById("overlay");
const caption = document.getElementById("caption");
const overlayRoot = document.getElementById("overlay-root");

// State
let handDrawingMode = false;
let handPointerMode = false;  // Hand tracking pointer-only mode (no drawing)
let isProcessingCommand = false;
let activeMode = null;

// Module instances
const canvasDrawing = new CanvasDrawing(canvas, config);
const gestureUI = new GestureUI(config);
const handCursor = new HandCursor(config);
const calibration = new CalibrationManager();
const overlayUI = new OverlayUI();
const ocrManager = new OCRManager(overlayRoot, (msg) => gestureUI.showWarning(msg), config);
const recording = new RecordingManager(config, caption, (msg) => gestureUI.showWarning(msg));
const summaryStack = new SummaryStack();
const conversationStack = new ConversationStack();

// ===== OCR Manager callback setup (ID-based) =====

// Stroke clearing callback
ocrManager.setOnClearStrokes((pathIds) => {
    if (pathIds && pathIds.length > 0) {
        canvasDrawing.clearPathsByIds(pathIds);
        console.log(`[OCR Callback] Cleared strokes by IDs: [${pathIds.join(',')}]`);
    }
});

// Stroke color change callback
ocrManager.setOnChangeStrokesColor((pathIds, newColor) => {
    if (pathIds && pathIds.length > 0) {
        canvasDrawing.changePathsColorByIds(pathIds, newColor);
        console.log(`[OCR Callback] Changed strokes color by IDs: [${pathIds.join(',')}]`);
    }
});

// ===== Recording Summary callback setup =====
recording.setOnSummaryReceived((summary) => {
    summaryStack.addSummary(summary);
    gestureUI.showActionToast("Summary Received", "success", 2000);
});

// ===== OCR session status indicator UI =====
let ocrSessionIndicator = null;

function showOCRSessionIndicator() {
    if (!ocrSessionIndicator) {
        ocrSessionIndicator = document.createElement("div");
        ocrSessionIndicator.id = "ocr-session-indicator";
        ocrSessionIndicator.style.cssText = `
            position: fixed;
            top: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: linear-gradient(135deg, #2196F3, #1976D2);
            color: white;
            padding: 10px 24px;
            border-radius: 25px;
            font-size: 14px;
            font-weight: bold;
            z-index: 10002;
            box-shadow: 0 4px 15px rgba(33, 150, 243, 0.4);
            display: flex;
            align-items: center;
            gap: 10px;
            animation: pulse-blue 1.5s ease-in-out infinite;
        `;
        ocrSessionIndicator.innerHTML = `
            <span style="font-size: 18px;">📝</span>
            <span>OCR Session Active - Draw and select TEXT or MATH</span>
        `;
        
        const style = document.createElement("style");
        style.textContent = `
            @keyframes pulse-blue {
                0%, 100% { box-shadow: 0 4px 15px rgba(33, 150, 243, 0.4); }
                50% { box-shadow: 0 4px 25px rgba(33, 150, 243, 0.7); }
            }
        `;
        document.head.appendChild(style);
        
        document.body.appendChild(ocrSessionIndicator);
    }
    ocrSessionIndicator.style.display = "flex";
}

function hideOCRSessionIndicator() {
    if (ocrSessionIndicator) {
        ocrSessionIndicator.style.display = "none";
    }
}

// ===== Control panel action handler =====
function handleControlAction(action, data) {
    switch (action) {
        case "COLOR_SELECT":
            canvasDrawing.setColor(data.color);
            handCursor.setColor(data.color);
            canvasDrawing.setEraserMode(false);
            handCursor.setEraserMode(false);
            console.log("[Control] Color changed to", data.color);
            break;

        case "LINEWIDTH_SELECT":
            canvasDrawing.currentLineWidth = data.width;
            console.log("[Control] Line width changed to", data.width);
            break;

        case "ERASER":
            canvasDrawing.setEraserMode(true);
            handCursor.setEraserMode(true);
            console.log("[Control] Eraser mode activated");
            break;

        case "CLEAR_ALL":
            canvasDrawing.clear();
            if (overlayRoot) overlayRoot.innerHTML = "";
            hideOCRSessionIndicator();
            console.log("[Control] Canvas cleared");
            break;

        case "POINTER":
            const newMode = !handCursor.pointerMode;
            handCursor.setPointerMode(newMode);
            canvasDrawing.setEraserMode(false);
            gestureUI.showNotice(newMode ? "Pointer Mode" : "Drawing Mode", newMode ? "#2196F3" : "#4CAF50");
            console.log(`[Control] ${newMode ? "Pointer" : "Drawing"} mode`);
            break;

        case "CALIBRATE":
            if (window.electronAPI && window.electronAPI.sendToHandTracker) {
                if (calibration.isActive() || calibration.getRegion()) {
                    window.electronAPI.sendToHandTracker({ command: "reset_calibration" });
                    calibration.reset();
                } else {
                    window.electronAPI.sendToHandTracker({ command: "start_calibration" });
                }
            }
            break;

        case "OCR_START":
            handleOCRStart();
            break;

        case "TEXT_OCR":
            handleTextOCR();
            break;

        case "MATH_OCR":
            handleMathOCR();
            break;

        case "EVAL_EXPR":
            handleEvalExpr();
            break;

        case "DRAW_GRAPH":
            handleDrawGraph();
            break;
    }
}

const controlPanel = new ControlPanel(config, handleControlAction);

// ===== OCR session start handler =====

function handleOCRStart() {
    if (canvasDrawing.isOCRSessionActive()) {
        canvasDrawing.endOCRSession();
        hideOCRSessionIndicator();
        gestureUI.showNotice("OCR Session Ended", "#FF9800");
        console.log("[OCR] Session ended manually");
    } else {
        canvasDrawing.startOCRSession();
        showOCRSessionIndicator();
        gestureUI.showNotice("OCR Session Started - Draw now!", "#2196F3");
        console.log("[OCR] Session started");
    }
}

// ===== OCR handlers =====

async function handleTextOCR() {
    const hasSession = canvasDrawing.isOCRSessionActive() || canvasDrawing.sessionCanvas;
    const bounds = hasSession 
        ? canvasDrawing.getSessionBounds() 
        : canvasDrawing.getAllBounds();
    
    if (!bounds) {
        gestureUI.showWarning("Draw something first!");
        return;
    }

    // Get session path ID list
    let pathIds = null;
    if (hasSession) {
        pathIds = canvasDrawing.getSessionPathIds();
    }

    try {
        console.log("[OCR] Text OCR requested, session active:", hasSession, "pathIds:", pathIds);
        
        let res;
        if (hasSession) {
            const dataURL = canvasDrawing.getSessionCanvasDataURL(bounds);
            if (dataURL) {
                console.log("[OCR] Using session canvas DataURL");
                res = await window.electronAPI.requestOCRWithImage("text", dataURL);
            } else {
                gestureUI.showWarning("Failed to capture session drawing");
                return;
            }
        } else {
            const captureRect = {
                x: Math.max(Math.floor(bounds.xMin - 10), 0),
                y: Math.max(Math.floor(bounds.yMin - 10), 0),
                width: Math.ceil(bounds.xMax - bounds.xMin + 20),
                height: Math.ceil(bounds.yMax - bounds.yMin + 20)
            };
            res = await window.electronAPI.requestOCR("text", captureRect);
        }
        
        const text = res.text || "";

        if (text && !text.includes("not set") && !text.includes("ERROR")) {
            // Pass pathIds together
            ocrManager.addResult('text', text, bounds, pathIds);
            gestureUI.showNotice("Text recognized!", "#4CAF50");
        } else {
            gestureUI.showWarning("No text recognized or API key not set");
        }

        // End session
        if (hasSession) {
            canvasDrawing.endOCRSession();
            canvasDrawing.destroySessionCanvas();
            hideOCRSessionIndicator();
        }
    } catch (err) {
        console.error("[OCR] Text OCR error:", err);
        gestureUI.showWarning("Text OCR failed");
    }
}

async function handleMathOCR() {
    const hasSession = canvasDrawing.isOCRSessionActive() || canvasDrawing.sessionCanvas;
    const bounds = hasSession
        ? canvasDrawing.getSessionBounds()
        : canvasDrawing.getAllBounds();

    if (!bounds) {
        gestureUI.showWarning("Draw a formula first!");
        return;
    }

    // Get session path ID list
    let pathIds = null;
    if (hasSession) {
        pathIds = canvasDrawing.getSessionPathIds();
    }

    try {
        console.log("[OCR] Math OCR requested, session active:", hasSession, "pathIds:", pathIds);
        
        let res;
        if (hasSession) {
            const dataURL = canvasDrawing.getSessionCanvasDataURL(bounds);
            if (dataURL) {
                console.log("[OCR] Using session canvas DataURL");
                res = await window.electronAPI.requestOCRWithImage("math", dataURL);
            } else {
                gestureUI.showWarning("Failed to capture session drawing");
                return;
            }
        } else {
            const captureRect = {
                x: Math.max(Math.floor(bounds.xMin - 10), 0),
                y: Math.max(Math.floor(bounds.yMin - 10), 0),
                width: Math.ceil(bounds.xMax - bounds.xMin + 20),
                height: Math.ceil(bounds.yMax - bounds.yMin + 20)
            };
            res = await window.electronAPI.requestOCR("math", captureRect);
        }
        
        const expr = res.text || "";
        ocrManager.setLastMathExpr(expr);

        if (expr && !expr.includes("ERROR")) {
            // Pass pathIds together
            ocrManager.addResult('math', expr, bounds, pathIds);
            gestureUI.showNotice("Formula recognized!", "#2196F3");
        } else {
            gestureUI.showWarning("No formula recognized");
        }

        // End session
        if (hasSession) {
            canvasDrawing.endOCRSession();
            canvasDrawing.destroySessionCanvas();
            hideOCRSessionIndicator();
        }
    } catch (err) {
        console.error("[OCR] Math OCR error:", err);
        gestureUI.showWarning("Math OCR failed");
    }
}

async function handleEvalExpr() {
    const expr = ocrManager.getLastMathExpr();
    if (!expr) {
        gestureUI.showWarning("No formula to calculate!");
        return;
    }

    const mathItems = document.querySelectorAll('.ocr-result-item');
    for (let i = mathItems.length - 1; i >= 0; i--) {
        if (mathItems[i].dataset.mathExpr === expr) {
            await ocrManager.evaluateExprInBox(mathItems[i]);
            return;
        }
    }
}

async function handleDrawGraph() {
    const expr = ocrManager.getLastMathExpr();
    if (!expr) {
        gestureUI.showWarning("No formula to graph!");
        return;
    }

    const mathItems = document.querySelectorAll('.ocr-result-item');
    for (let i = mathItems.length - 1; i >= 0; i--) {
        if (mathItems[i].dataset.mathExpr === expr) {
            await ocrManager.drawGraphInline(mathItems[i]);
            return;
        }
    }
}

// ===== Mouse events =====

canvas.addEventListener("mousemove", (e) => {
    if (overlayUI.isPointerMode() && !handDrawingMode) {
        overlayUI.updatePointerPosition(e.pageX, e.pageY);
    }
});

// ===== Main command handler =====

window.electronAPI?.onCmd((data) => {
    console.log("[overlay] received:", data);

    if (isProcessingCommand && data.type !== "resetAll") {
        console.log("[overlay] Command ignored - processing another");
        return;
    }

    switch (data.type) {
        case "gestureDetecting":
            gestureUI.showDetecting(data.duration || 2.5);
            break;

        case "gestureRecognized":
            gestureUI.hideDetecting();
            if (data.gesture) {
                const commandName = gestureUI.getCommandName(data.gesture);
                gestureUI.showIndicator(commandName);
            }
            break;

        case "holdExtended":
            // Hold state - extend gesture list UI display
            gestureUI.extendDetecting(data.remaining || 2.5);
            break;

        case "stage2Cancelled":
            // Stage2 cancelled (max hold duration exceeded)
            gestureUI.cancelDetecting();
            break;

        case "showNotice":
            gestureUI.showNotice(data.text, data.color);
            break;

        case "resetAll":
            isProcessingCommand = false;
            activeMode = null;
            handDrawingMode = false;
            handPointerMode = false;

            canvasDrawing.setDrawingMode(false);
            canvasDrawing.clear();

            handCursor.hide();
            handCursor.setPointerMode(false);
            handCursor.setDrawingEnabled(false);

            controlPanel.hide();
            calibration.reset();
            recording.stop();
            recording.hideIndicator();

            overlayUI.hidePointer();
            hideOCRSessionIndicator();

            caption.style.display = "none";
            ocrManager.clearAll();
            summaryStack.clearAll();
            conversationStack.exitRecordingMode();
            conversationStack.hide();

            console.log("[Control] All reset");
            break;

        case "toggleDrawing":
        case "toggleDraw":
            if (handDrawingMode) {
                gestureUI.showWarning("⚠️ Hand Drawing active! Reset first (X gesture)");
                return;
            }
            const drawingEnabled = !canvasDrawing.drawing;
            canvasDrawing.setDrawingMode(drawingEnabled);
            activeMode = drawingEnabled ? "drawing" : null;
            console.log(`[Control] Drawing mode: ${drawingEnabled}`);
            break;

        case "togglePointer":
            if (handDrawingMode) {
                const isPointer = !handCursor.pointerMode;
                handCursor.setPointerMode(isPointer);
                console.log(`[Control] Hand tracking: ${isPointer ? "Pointer" : "Drawing"} mode`);
            } else {
                overlayUI.togglePointer();
                console.log(`[Control] Pointer mode: ${overlayUI.isPointerMode()}`);
            }
            break;

        case "toggleHandDraw":
            if (canvasDrawing.drawing || calibration.isActive()) {
                gestureUI.showWarning("⚠️ Another mode active! Reset first (X gesture)");
                return;
            }

            isProcessingCommand = true;
            handDrawingMode = !handDrawingMode;

            if (handDrawingMode) {
                activeMode = "handDrawing";
                controlPanel.show();
                handCursor.setPointerMode(true);
                handCursor.show();
                console.log("[Control] Hand drawing mode activated (pointer)");
            } else {
                activeMode = null;
                controlPanel.hide();
                handCursor.hide();
                handCursor.setPointerMode(false);
                console.log("[Control] Hand drawing mode deactivated");
            }

            setTimeout(() => {
                isProcessingCommand = false;
            }, 500);
            break;

        case "handCursor":
            // Allow hand cursor in both drawing mode and pointer-only mode
            if (!handDrawingMode && !handPointerMode) return;

            const screenPos = handCursor.updatePosition(data.position);

            if (data.calibrating) {
                return;
            }

            // In pointer-only mode, enable UI interaction via hover-dwell (no drawing)
            if (handPointerMode) {
                if (screenPos) {
                    // Check hover on conversation stack (STT panel) - uses dwell-click
                    conversationStack.checkHover(screenPos.x, screenPos.y);
                    // Check hover on OCR elements
                    ocrManager.checkHoverElements(screenPos.x, screenPos.y);
                }
                return;
            }

            // Drawing mode logic
            if (!handCursor.pointerMode) {
                if (data.drawing !== handCursor.isDrawingEnabled) {
                    handCursor.setDrawingEnabled(data.drawing);

                    if (data.drawing && data.position) {
                        canvasDrawing.startNewPath(data.position);
                    } else {
                        canvasDrawing.endCurrentPath();
                    }
                } else if (handCursor.isDrawingEnabled && data.position) {
                    canvasDrawing.addPointToPath(data.position);
                }
            }

            if (screenPos && !handCursor.isDrawingEnabled) {
                controlPanel.checkHover(screenPos.x, screenPos.y);
                ocrManager.checkHoverElements(screenPos.x, screenPos.y);
                conversationStack.checkHover(screenPos.x, screenPos.y);
            }
            break;

        case "handTrackingReady":
            console.log("[HandTracking] Ready");
            break;

        case "calibrationStarted":
            calibration.start();
            break;

        case "calibrationPoint":
            calibration.addPoint(data.position);
            console.log(`[Calibration] Point ${data.index}/${data.total}`);
            break;

        case "calibrationDone":
            calibration.complete(data.region);
            break;

        case "calibrationReset":
            calibration.reset();
            break;

        // ===== Calibration gesture/command =====
        case "CALIBRATE":
            if (window.electronAPI && window.electronAPI.sendToHandTracker) {
                if (calibration.isActive() || calibration.getRegion()) {
                    window.electronAPI.sendToHandTracker({ command: "reset_calibration" });
                    calibration.reset();
                    gestureUI.showNotice("Calibration Reset", "#FF9800");
                } else {
                    window.electronAPI.sendToHandTracker({ command: "start_calibration" });
                    gestureUI.showNotice("Calibration Started", "#2196F3");
                }
            }
            break;

        case "setPointerMode":
            if (data.enabled !== undefined && handDrawingMode) {
                handCursor.setPointerMode(data.enabled);
                console.log(`[Control] Set pointer mode: ${data.enabled}`);
            }
            break;

        case "updateTimer":
            overlayUI.updateTimer(data.time);
            break;

        case "hideTimer":
            overlayUI.hideTimer();
            break;

        case "toggleBlackout":
            overlayUI.toggleBlackout(data.enabled);
            break;

        case "changeColor":
            canvasDrawing.setColor(data.color);
            handCursor.setColor(data.color);
            console.log(`[Control] Color changed to ${data.color}`);
            break;

        case "clearCanvas":
            canvasDrawing.clear();
            break;

        case "captionStart":
            if (recording.isActive()) {
                gestureUI.showWarning("⚠️ Already recording!");
                return;
            }
            recording.start();
            break;

        case "captionStopAndSummarize":
            if (!recording.isActive()) {
                gestureUI.showWarning("⚠️ Not recording!");
                return;
            }
            recording.stop();
            break;

        case "summaryTest":
            // M key: LLM summary test - display in right stack
            summaryStack.addSummary(data.text || "Test sentence.");
            gestureUI.showActionToast("Summary Received", "success", 2000);
            console.log("[Debug] Summary added to stack:", data.text);
            break;

        case "handTrackingStopped":
            handDrawingMode = false;
            handCursor.hide();
            controlPanel.hide();
            hideOCRSessionIndicator();
            console.log("[HandTracking] Stopped");
            break;

        case "OCR_START":
            handleOCRStart();
            break;

        case "TEXT_OCR":
            handleTextOCR();
            break;

        case "MATH_OCR":
            handleMathOCR();
            break;

        case "EVAL_EXPR":
            handleEvalExpr();
            break;

        case "DRAW_GRAPH":
            handleDrawGraph();
            break;

        case "TOGGLE_DRAW_POINTER":
            if (handDrawingMode) {
                const isPointer = !handCursor.pointerMode;
                handCursor.setPointerMode(isPointer);
                canvasDrawing.setEraserMode(false);
                handCursor.setEraserMode(false);
                gestureUI.showNotice(isPointer ? "Pointer Mode" : "Drawing Mode", isPointer ? "#2196F3" : "#4CAF50");
                console.log(`[Control] Toggle: ${isPointer ? "Pointer" : "Drawing"} mode`);
            }
            break;

        // ===== Global Hand Pointer Mode (Up gesture) =====
        case "startHandPointer":
            // Start hand tracking in pointer-only mode (no drawing)
            handPointerMode = true;
            handCursor.show();
            handCursor.setPointerMode(true);
            handCursor.setDrawingEnabled(false);
            gestureUI.showNotice("👆 Hand Pointer Mode ON", "#2196F3");
            console.log("[Control] Hand pointer mode started");
            break;

        case "stopHandPointer":
            // Stop hand tracking pointer mode
            handPointerMode = false;
            handCursor.hide();
            handCursor.setPointerMode(false);
            overlayUI.hidePointer();
            gestureUI.showNotice("👆 Hand Pointer Mode OFF", "#FF9800");
            console.log("[Control] Hand pointer mode stopped");
            break;

        case "toggleGlobalPointer":
            // Legacy: mouse-based pointer toggle
            overlayUI.togglePointer();
            const globalPointerEnabled = overlayUI.isPointerMode();
            gestureUI.showNotice(globalPointerEnabled ? "👆 Pointer Mode ON" : "👆 Pointer Mode OFF", "#2196F3");
            console.log(`[Control] Global pointer mode: ${globalPointerEnabled}`);
            break;

        // ===== STT Recording Mode Events =====
        case "recordingModeEnter":
            conversationStack.enterRecordingMode();
            gestureUI.showNotice("🎙️ Recording Mode Ready", "#4CAF50");
            console.log("[STT] Recording mode entered");
            break;

        case "recordingModeExit":
            conversationStack.exitRecordingMode();
            gestureUI.showNotice("⏹ Recording Mode Exit", "#FF9800");
            console.log("[STT] Recording mode exited");
            break;

        case "sttReady":
            gestureUI.showNotice("🎙️ STT Service Ready", "#4CAF50");
            console.log("[STT] Service ready");
            break;

        case "sttRecordingStarted":
            conversationStack.setRecordingState(true);
            gestureUI.showNotice("🔴 Recording...", "#f44336");
            console.log("[STT] Recording started");
            break;

        case "sttRecordingStopped":
            conversationStack.setRecordingState(false);
            gestureUI.showNotice("⏹ Recording Stopped", "#FF9800");
            console.log("[STT] Recording stopped");
            break;

        case "sttTranscription":
            // Add transcription to conversation stack with speaker info
            if (data.text && data.text.trim()) {
                conversationStack.addConversation(data.text, data.speaker);
                gestureUI.showActionToast("STT Complete", "success", 1500);
                console.log(`[STT] Transcription: [${data.speaker}] ${data.text}`);
            } else {
                gestureUI.showWarning("No speech detected");
            }
            break;

        case "sttError":
            gestureUI.showWarning(`STT Error: ${data.message}`);
            console.error("[STT] Error:", data.message);
            break;
    }
});

console.log("[Overlay] Modular version v3.0.0 loaded");
