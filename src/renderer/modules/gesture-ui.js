// Gesture UI module for IMU gesture recognition

export class GestureUI {
    constructor(config) {
        this.config = config;
        this.isDetectingGesture = false;
        this.gestureTimeout = null;
        this.toastTimeout = null;

        this.createElements();
    }

    createElements() {
        // 동작 알림 토스트 (우측 상단)
        this.actionToast = document.createElement("div");
        this.actionToast.id = "action-toast";
        document.body.appendChild(this.actionToast);

        // 제스처 감지 테두리
        this.detectBorder = document.createElement("div");
        this.detectBorder.className = "gesture-detect-active";
        this.detectBorder.style.display = "none";
        document.body.appendChild(this.detectBorder);

        // 제스처 감지 메시지
        this.detectMessage = document.createElement("div");
        this.detectMessage.id = "detect-message";
        this.detectMessage.textContent = "Perform gesture now";
        document.body.appendChild(this.detectMessage);

        // 제스처 목록 패널
        this.listPanel = document.createElement("div");
        this.listPanel.id = "gesture-list-panel";
        this.buildGestureList();
        document.body.appendChild(this.listPanel);

        // 경고 메시지 (기존 호환성)
        this.warningMessage = document.createElement("div");
        this.warningMessage.id = "warning-message";
        this.warningMessage.style.cssText = `
            position: fixed;
            top: 80px;
            right: 20px;
            padding: 12px 20px;
            background: linear-gradient(135deg, #c62828, #f44336);
            color: white;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
            z-index: 100001;
            display: none;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        `;
        document.body.appendChild(this.warningMessage);

        // 기존 indicator (호환성 유지)
        this.indicator = document.createElement("div");
        this.indicator.id = "gesture-indicator";
        this.indicator.style.display = "none";
        document.body.appendChild(this.indicator);

        // 기존 notice (호환성 유지)
        this.notice = document.createElement("div");
        this.notice.className = "gesture-notification";
        this.notice.style.display = "none";
        document.body.appendChild(this.notice);
    }

    buildGestureList() {
        // 전체 15개 제스처 목록
        // 이모지 + 영문 동작명 | 실행될 기능
        const actionList = [
            { gesture: "⬅️ Left", action: "Previous Slide" },
            { gesture: "➡️ Right", action: "Next Slide" },
            { gesture: "⬆️ Up", action: "Overlay ON" },
            { gesture: "⬇️ Down", action: "Overlay OFF" },
            { gesture: "🔃 Circle CW", action: "Start Recording" },
            { gesture: "🔄 Circle CCW", action: "Stop Recording" },
            { gesture: "⏪ Double Left", action: "Jump -3 Slides" },
            { gesture: "⏩ Double Right", action: "Jump +3 Slides" },
            { gesture: "✖️ X Shape", action: "Reset All" },
            { gesture: "👆 Double Tap", action: "Hand Tracking" },
            { gesture: "↩️ 90° Left", action: "OCR Start" },
            { gesture: "↪️ 90° Right", action: "Draw/Pointer" },
            { gesture: "∞ Figure 8", action: "Timer Toggle" },
            { gesture: "⬜ Square", action: "Calibration" },
            { gesture: "🔺 Triangle", action: "Blackout" }
        ];

        let listHTML = '<div class="panel-title">🎯 Gesture Guide</div>';

        actionList.forEach(item => {
            listHTML += `
                <div class="gesture-item">
                    <span class="gesture-name">${item.gesture}</span>
                    <span class="gesture-action">${item.action}</span>
                </div>
            `;
        });

        this.listPanel.innerHTML = listHTML;
    }

    // ===== Action Toast (우측 상단 알림) =====

    showActionToast(message, type = "default", duration = 2000) {
        // 기존 타임아웃 취소
        if (this.toastTimeout) {
            clearTimeout(this.toastTimeout);
        }

        // 클래스 초기화
        this.actionToast.className = "";
        if (type !== "default") {
            this.actionToast.classList.add(type);
        }

        this.actionToast.textContent = message;
        this.actionToast.style.display = "block";
        this.actionToast.style.animation = "none";
        this.actionToast.offsetHeight; // Force reflow
        this.actionToast.style.animation = "slideInRight 0.3s ease-out";

        this.toastTimeout = setTimeout(() => {
            this.actionToast.style.animation = "slideOutRight 0.3s ease-out";
            setTimeout(() => {
                this.actionToast.style.display = "none";
            }, 280);
        }, duration);
    }

    // ===== Gesture Detection UI =====

    showDetecting(duration = 2.5) {
        this.isDetectingGesture = true;
        this.detectBorder.style.display = "block";
        this.detectMessage.style.display = "block";
        this.detectMessage.textContent = "Perform gesture now";
        this.listPanel.style.display = "block";

        if (this.gestureTimeout) clearTimeout(this.gestureTimeout);

        this.gestureTimeout = setTimeout(() => {
            this.hideDetecting();
        }, duration * 1000);
    }

    /**
     * Hold 상태로 무한 대기
     * @param {number} remaining - 남은 시간 (초), -1이면 무한 대기
     */
    extendDetecting(remaining = -1) {
        if (!this.isDetectingGesture) {
            // 이미 숨겨진 경우 다시 표시
            this.isDetectingGesture = true;
            this.detectBorder.style.display = "block";
            this.detectMessage.style.display = "block";
            this.listPanel.style.display = "block";
        }

        // 기존 타이머 취소 (무한 대기)
        if (this.gestureTimeout) {
            clearTimeout(this.gestureTimeout);
            this.gestureTimeout = null;
        }

        // "Hold" 상태 표시 - 타이머 없이
        this.detectMessage.textContent = "Holding... perform gesture when ready";
    }

    /**
     * Stage2 취소 (최대 hold 시간 초과 등)
     */
    cancelDetecting() {
        this.detectMessage.textContent = "Cancelled";
        setTimeout(() => {
            this.hideDetecting();
        }, 500);
    }

    hideDetecting() {
        this.isDetectingGesture = false;
        this.detectBorder.style.display = "none";
        this.detectMessage.style.display = "none";
        this.listPanel.style.display = "none";

        if (this.gestureTimeout) {
            clearTimeout(this.gestureTimeout);
            this.gestureTimeout = null;
        }
    }

    // ===== Legacy Methods (호환성) =====

    showIndicator(text) {
        // 새로운 토스트 시스템 사용
        this.showActionToast(text, "default", 1500);
    }

    showWarning(message, duration = 3000) {
        this.warningMessage.textContent = message;
        this.warningMessage.style.display = "block";

        setTimeout(() => {
            this.warningMessage.style.display = "none";
        }, duration);
    }

    showNotice(text, color = "rgba(0,0,0,0.7)") {
        // 색상에 따라 type 결정
        let type = "default";
        if (color.includes("0,200,0") || color.includes("0,255,0")) {
            type = "success";
        } else if (color.includes("200,0,0") || color.includes("255,0,0")) {
            type = "error";
        } else if (color.includes("255,200,0") || color.includes("255,165,0")) {
            type = "warning";
        }

        this.showActionToast(text, type, 2000);
    }

    getCommandName(gesture) {
        return this.config.gesture_display_names[gesture] || gesture.toUpperCase();
    }
}
