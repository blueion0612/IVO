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
     * 모든 연결된 클라이언트에게 메시지 브로드캐스트
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
     * 햅틱 피드백 요청 전송 (Python gesture_controller로 전달)
     * @param {string} preset - 햅틱 프리셋 이름 (예: "slide_change", "selection_tick")
     */
    sendHaptic(preset) {
        this.broadcast({
            type: "haptic_request",
            preset: preset
        });
        console.log(`[WS] Haptic request sent: ${preset}`);
    }

    /**
     * 제스처 이름 정규화
     * "90 left" → "90_left"
     * "double tap" → "double_tap"
     * "circle_clockwise" → "circle_cw"
     * "circle_counter_clockwise" → "circle_ccw"
     */
    normalizeGestureName(name) {
        if (!name) return name;

        // 먼저 기본 정규화: 소문자 + 공백을 언더스코어로
        let normalized = name.toLowerCase().replace(/\s+/g, '_');

        // 모델 출력 이름을 config 이름으로 매핑
        const aliasMap = {
            'circle_clockwise': 'circle_cw',
            'circle_counter_clockwise': 'circle_ccw',
            'circle_counterclockwise': 'circle_ccw'
        };

        return aliasMap[normalized] || normalized;
    }

    /**
     * 처리 잠금 상태 확인
     */
    isLocked() {
        const now = Date.now();
        if ((now - this.lastProcessedTime) < this.LOCK_MS) {
            return true;
        }
        return false;
    }

    /**
     * 처리 잠금 설정
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
     * 메시지 처리
     * @param {string} msg - 수신된 메시지
     */
    handleMessage(msg) {
        // ===== 디버그: 원본 메시지 출력 =====
        console.log(`[WS] Received: ${msg}`);

        // JSON 형태 처리
        if (msg.startsWith("{") || msg.startsWith("[")) {
            try {
                const j = JSON.parse(msg);

                // ===== Stage1 감지 알림 =====
                if (j.type === "stage1_detected") {
                    console.log(`[WS] Stage1 detected - collecting gesture data...`);
                    if (this.onGestureDetected) {
                        this.onGestureDetected(j.duration || this.config.overlay.gesture_detect_duration_sec);
                    }
                    return;
                }

                // ===== Hold 상태 - 제스처 목록 유지 연장 =====
                if (j.type === "hold_extended") {
                    console.log(`[WS] Hold extended - remaining: ${j.remaining?.toFixed(1)}s`);
                    if (this.onHoldExtended) {
                        this.onHoldExtended(j.remaining || 2.5);
                    }
                    return;
                }

                // ===== Stage2 취소 (최대 hold 시간 초과) =====
                if (j.type === "stage2_cancelled") {
                    console.log(`[WS] Stage2 cancelled (max hold duration exceeded)`);
                    if (this.onStage2Cancelled) {
                        this.onStage2Cancelled();
                    }
                    return;
                }

                // ===== Stage2 제스처 인식 결과 (이것만 처리!) =====
                if (j.type === "gesture_recognized") {
                    // 제스처 이름 정규화 ("90 left" → "90_left")
                    const rawGestureName = j.gesture;
                    const gestureName = this.normalizeGestureName(rawGestureName);
                    const confidence = j.confidence || 0;
                    
                    console.log(`[WS] ★ Gesture: "${rawGestureName}" → normalized: "${gestureName}" (${(confidence * 100).toFixed(1)}%)`);
                    
                    if (this.onGestureRecognized) {
                        this.onGestureRecognized(gestureName, confidence);
                    }

                    // 제스처 이름을 명령으로 매핑
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
                    
                    // 매핑 성공 여부와 관계없이 항상 잠금! (후속 code 메시지 방지)
                    this.setLock();
                    return;
                }

                // ===== 다른 메시지는 잠금 상태면 무시 =====
                if (this.isLocked()) {
                    console.log(`[WS] Ignored (locked): ${msg.substring(0, 50)}...`);
                    return;
                }

                // ===== 일반 code 처리 (잠금 해제 상태에서만) =====
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

        // 잠금 상태면 무시
        if (this.isLocked()) {
            console.log(`[WS] Ignored (locked): ${msg}`);
            return;
        }

        // 단일 코드 처리
        if (this.onCode && !this.shouldDebounce(msg)) {
            console.log(`[WS] Raw command: ${msg}`);
            this.onCode(msg);
        }
    }

    /**
     * 제스처 감지 콜백 설정
     */
    setGestureDetectedCallback(callback) {
        this.onGestureDetected = callback;
    }

    /**
     * 제스처 인식 콜백 설정
     */
    setGestureRecognizedCallback(callback) {
        this.onGestureRecognized = callback;
    }

    /**
     * Hold 연장 콜백 설정
     */
    setHoldExtendedCallback(callback) {
        this.onHoldExtended = callback;
    }

    /**
     * Stage2 취소 콜백 설정
     */
    setStage2CancelledCallback(callback) {
        this.onStage2Cancelled = callback;
    }

    /**
     * 코드 처리 콜백 설정
     */
    setCodeCallback(callback) {
        this.onCode = callback;
    }

    /**
     * 서버 중지
     */
    stop() {
        if (this.wss) {
            this.wss.close();
            this.wss = null;
        }
    }
}

module.exports = GestureWebSocketServer;
