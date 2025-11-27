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
        // Action toast (top right)
        this.actionToast = document.createElement("div");
        this.actionToast.id = "action-toast";
        document.body.appendChild(this.actionToast);

        // Gesture detection border
        this.detectBorder = document.createElement("div");
        this.detectBorder.className = "gesture-detect-active";
        this.detectBorder.style.display = "none";
        document.body.appendChild(this.detectBorder);

        // Gesture detection message
        this.detectMessage = document.createElement("div");
        this.detectMessage.id = "detect-message";
        this.detectMessage.textContent = "Perform gesture now";
        document.body.appendChild(this.detectMessage);

        // Gesture list panel
        this.listPanel = document.createElement("div");
        this.listPanel.id = "gesture-list-panel";
        this.buildGestureList();
        document.body.appendChild(this.listPanel);

        // Warning message (legacy compatibility)
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

        // Legacy indicator (compatibility)
        this.indicator = document.createElement("div");
        this.indicator.id = "gesture-indicator";
        this.indicator.style.display = "none";
        document.body.appendChild(this.indicator);

        // Legacy notice (compatibility)
        this.notice = document.createElement("div");
        this.notice.className = "gesture-notification";
        this.notice.style.display = "none";
        document.body.appendChild(this.notice);
    }

    buildGestureList() {
        // Full 15 gesture list
        // Emoji + gesture name | action to execute
        const actionList = [
            { gesture: "⬅️ Left", action: "Previous Slide" },
            { gesture: "➡️ Right", action: "Next Slide" },
            { gesture: "⬆️ Up", action: "Pointer Mode" },
            { gesture: "⬇️ Down", action: "Record Toggle" },
            { gesture: "🔃 Circle CW", action: "Recording Mode" },
            { gesture: "🔄 Circle CCW", action: "Exit Recording" },
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

    // ===== Action Toast (top right notification) =====

    showActionToast(message, type = "default", duration = 2000) {
        // Cancel existing timeout
        if (this.toastTimeout) {
            clearTimeout(this.toastTimeout);
        }

        // Reset class
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
     * Hold state for indefinite wait
     * @param {number} remaining - Remaining time (seconds), -1 for infinite wait
     */
    extendDetecting(remaining = -1) {
        if (!this.isDetectingGesture) {
            // Show again if already hidden
            this.isDetectingGesture = true;
            this.detectBorder.style.display = "block";
            this.detectMessage.style.display = "block";
            this.listPanel.style.display = "block";
        }

        // Cancel existing timer (infinite wait)
        if (this.gestureTimeout) {
            clearTimeout(this.gestureTimeout);
            this.gestureTimeout = null;
        }

        // Show "Hold" state - without timer
        this.detectMessage.textContent = "Holding... perform gesture when ready";
    }

    /**
     * Stage2 cancelled (max hold time exceeded, etc.)
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

    // ===== Legacy Methods (compatibility) =====

    showIndicator(text) {
        // Use new toast system
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
        // Determine type based on color
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
