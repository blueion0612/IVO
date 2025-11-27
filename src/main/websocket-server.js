// WebSocket server for IMU gesture recognition
const WebSocket = require("ws");

class GestureWebSocketServer {
    constructor(config) {
        this.config = config;
        this.wss = null;
        this.clients = new Set();
        this.onGestureDetected = null;
        this.onGestureRecognized = null;
        this.onCode = null;
        this.lastProcessedTime = 0;
        this.LOCK_MS = 1000;
        this.lastCode = null;
        this.lastCodeTime = 0;
        this.DEBOUNCE_MS = 500;
    }

    start() {
        const port = this.config.websocket.port;
        this.wss = new WebSocket.Server({ port });
        console.log(`[WS] Server running on ws://127.0.0.1:${port}`);

        this.wss.on("connection", (ws) => {
            console.log("[WS] Client connected");
            this.clients.add(ws);

            ws.on("message", (raw) => {
                this.handleMessage(raw.toString().trim());
            });

            ws.on("close", () => {
                console.log("[WS] Client disconnected");
                this.clients.delete(ws);
            });

            ws.on("error", (err) => {
                console.log("[WS] Client error:", err.message);
                this.clients.delete(ws);
            });
        });
    }

    /**
     * Broadcast message to all connected clients
     */
    broadcast(message) {
        const msgStr = typeof message === "string" ? message : JSON.stringify(message);
        this.clients.forEach((client) => {
            if (client.readyState === WebSocket.OPEN) {
                try {
                    client.send(msgStr);
                } catch (e) {
                    console.log("[WS] Broadcast error:", e.message);
                }
            }
        });
    }

    /**
     * Send haptic feedback request (forwarded to Python gesture_controller)
     * @param {string} preset - Haptic preset name (e.g., "slide_change", "selection_tick")
     */
    sendHaptic(preset) {
        this.broadcast({
            type: "haptic_request",
            preset: preset
        });
        console.log(`[WS] Haptic request sent: ${preset}`);
    }

    /**
     * Normalize gesture name
     * "90 left" → "90_left"
     * "double tap" → "double_tap"
     * "circle_clockwise" → "circle_cw"
     * "circle_counter_clockwise" → "circle_ccw"
     */
    normalizeGestureName(name) {
        if (!name) return name;

        // Basic normalization: lowercase + spaces to underscores
        let normalized = name.toLowerCase().replace(/\s+/g, '_');

        // Map model output names to config names
        const aliasMap = {
            'circle_clockwise': 'circle_cw',
            'circle_counter_clockwise': 'circle_ccw',
            'circle_counterclockwise': 'circle_ccw'
        };

        return aliasMap[normalized] || normalized;
    }

    /**
     * Check if processing is locked
     */
    isLocked() {
        const now = Date.now();
        if ((now - this.lastProcessedTime) < this.LOCK_MS) {
            return true;
        }
        return false;
    }

    /**
     * Set processing lock
     */
    setLock() {
        this.lastProcessedTime = Date.now();
    }

    /**
     * Debounce 체크
     */
    shouldDebounce(code) {
        const now = Date.now();
        if (code === this.lastCode && (now - this.lastCodeTime) < this.DEBOUNCE_MS) {
            return true;
        }
        this.lastCode = code;
        this.lastCodeTime = now;
        return false;
    }

    /**
     * Handle incoming message
     * @param {string} msg - Received message
     */
    handleMessage(msg) {
        // ===== Debug: Print raw message =====
        console.log(`[WS] Received: ${msg}`);

        // Handle JSON format
        if (msg.startsWith("{") || msg.startsWith("[")) {
            try {
                const j = JSON.parse(msg);

                // ===== Stage1 detection notification =====
                if (j.type === "stage1_detected") {
                    console.log(`[WS] Stage1 detected - collecting gesture data...`);
                    if (this.onGestureDetected) {
                        this.onGestureDetected(j.duration || this.config.overlay.gesture_detect_duration_sec);
                    }
                    return;
                }

                // ===== Hold state - extend gesture list display =====
                if (j.type === "hold_extended") {
                    console.log(`[WS] Hold extended - remaining: ${j.remaining?.toFixed(1)}s`);
                    if (this.onHoldExtended) {
                        this.onHoldExtended(j.remaining || 2.5);
                    }
                    return;
                }

                // ===== Stage2 cancelled (max hold duration exceeded) =====
                if (j.type === "stage2_cancelled") {
                    console.log(`[WS] Stage2 cancelled (max hold duration exceeded)`);
                    if (this.onStage2Cancelled) {
                        this.onStage2Cancelled();
                    }
                    return;
                }

                // ===== Stage2 gesture recognition result (primary handler) =====
                if (j.type === "gesture_recognized") {
                    // Normalize gesture name ("90 left" → "90_left")
                    const rawGestureName = j.gesture;
                    const gestureName = this.normalizeGestureName(rawGestureName);
                    const confidence = j.confidence || 0;

                    console.log(`[WS] ★ Gesture: "${rawGestureName}" → normalized: "${gestureName}" (${(confidence * 100).toFixed(1)}%)`);

                    if (this.onGestureRecognized) {
                        this.onGestureRecognized(gestureName, confidence);
                    }

                    // Map gesture name to command
                    const command = this.config.gesture_to_command[gestureName];
                    if (command) {
                        if (!this.shouldDebounce(command)) {
                            console.log(`[WS] → Command: "${command}"`);
                            if (this.onCode) {
                                this.onCode(command);
                            }
                        } else {
                            console.log(`[WS] → Debounced (duplicate command)`);
                        }
                    } else {
                        console.log(`[WS] → WARNING: No mapping for "${gestureName}"`);
                    }

                    // Always lock regardless of mapping success (prevent subsequent code messages)
                    this.setLock();
                    return;
                }

                // ===== Ignore other messages if locked =====
                if (this.isLocked()) {
                    console.log(`[WS] Ignored (locked): ${msg.substring(0, 50)}...`);
                    return;
                }

                // ===== Handle general code (only when unlocked) =====
                if (j.code !== undefined) {
                    const codeStr = String(j.code);
                    console.log(`[WS] Code: ${codeStr}`);

                    if (this.onCode && !this.shouldDebounce(codeStr)) {
                        this.onCode(codeStr, j);
                    }
                    return;
                }

            } catch (e) {
                console.log("[WS] JSON parse error:", e.message);
            }
        }

        // Ignore if locked
        if (this.isLocked()) {
            console.log(`[WS] Ignored (locked): ${msg}`);
            return;
        }

        // Handle single code
        if (this.onCode && !this.shouldDebounce(msg)) {
            console.log(`[WS] Raw command: ${msg}`);
            this.onCode(msg);
        }
    }

    /**
     * Set gesture detection callback
     */
    setGestureDetectedCallback(callback) {
        this.onGestureDetected = callback;
    }

    /**
     * Set gesture recognition callback
     */
    setGestureRecognizedCallback(callback) {
        this.onGestureRecognized = callback;
    }

    /**
     * Set hold extended callback
     */
    setHoldExtendedCallback(callback) {
        this.onHoldExtended = callback;
    }

    /**
     * Set Stage2 cancelled callback
     */
    setStage2CancelledCallback(callback) {
        this.onStage2Cancelled = callback;
    }

    /**
     * Set code handler callback
     */
    setCodeCallback(callback) {
        this.onCode = callback;
    }

    /**
     * Stop server
     */
    stop() {
        if (this.wss) {
            this.wss.close();
            this.wss = null;
        }
    }
}

module.exports = GestureWebSocketServer;
