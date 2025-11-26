// src/renderer/modules/overlay-ui.js
// 오버레이 UI 요소 관리 모듈 (타이머, 블랙아웃, 포인터 등)

export class OverlayUI {
    constructor() {
        this.blackoutEnabled = false;
        this.pointerMode = false;
        
        this.createTimer();
        this.createBlackout();
        this.createPointer();
        this.addStyles();
    }

    createTimer() {
        this.timer = document.createElement("div");
        this.timer.id = "presentation-timer";
        this.timer.style.cssText = `
            position: fixed;
            bottom: 30px;
            left: 30px;
            padding: 15px 25px;
            background: linear-gradient(135deg, #1a3a6e, #4a9fd4);
            color: white;
            border-radius: 12px;
            font-family: 'Segoe UI', 'Courier New', monospace;
            font-size: 32px;
            font-weight: bold;
            z-index: 99998;
            display: none;
            border: 2px solid rgba(74, 159, 212, 0.5);
            box-shadow: 0 4px 20px rgba(0,0,0,0.4);
        `;
        document.body.appendChild(this.timer);
    }

    createBlackout() {
        this.blackout = document.createElement("div");
        this.blackout.id = "blackout-overlay";
        this.blackout.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: black;
            z-index: 1;
            display: none;
            pointer-events: none;
        `;
        document.body.appendChild(this.blackout);
    }

    createPointer() {
        this.pointer = document.createElement("div");
        this.pointer.id = "pointer";
        this.pointer.style.cssText = `
            position: fixed;
            width: 20px;
            height: 20px;
            background: rgba(255, 0, 0, 0.7);
            border: 3px solid white;
            border-radius: 50%;
            display: none;
            transform: translate(-50%, -50%);
            z-index: 100;
            pointer-events: none;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.3);
        `;
        document.body.appendChild(this.pointer);
    }

    addStyles() {
        const style = document.createElement("style");
        style.textContent = `
            #presentation-timer.pulse {
                animation: pulse 2s infinite;
            }
            
            @keyframes pulse {
                0%, 100% { transform: scale(1); }
                50% { transform: scale(1.05); }
            }
            
            #overlay {
                z-index: 10;
            }
        `;
        document.head.appendChild(style);
    }

    // ===== Timer =====

    updateTimer(time) {
        this.timer.textContent = time;
        this.timer.style.display = "block";
        
        const [minutes, seconds] = time.split(':').map(Number);
        if (minutes > 0 && minutes % 10 === 0 && seconds === 0) {
            this.timer.classList.add('pulse');
            setTimeout(() => this.timer.classList.remove('pulse'), 2000);
        }
    }

    hideTimer() {
        this.timer.style.display = "none";
    }

    // ===== Blackout =====

    toggleBlackout(enabled) {
        if (enabled !== undefined) {
            this.blackoutEnabled = enabled;
        } else {
            this.blackoutEnabled = !this.blackoutEnabled;
        }
        this.blackout.style.display = this.blackoutEnabled ? "block" : "none";
        return this.blackoutEnabled;
    }

    isBlackoutEnabled() {
        return this.blackoutEnabled;
    }

    // ===== Pointer =====

    togglePointer() {
        this.pointerMode = !this.pointerMode;
        this.pointer.style.display = this.pointerMode ? "block" : "none";
        return this.pointerMode;
    }

    setPointerMode(enabled) {
        this.pointerMode = enabled;
        this.pointer.style.display = enabled ? "block" : "none";
    }

    updatePointerPosition(x, y) {
        if (this.pointerMode) {
            this.pointer.style.left = x + "px";
            this.pointer.style.top = y + "px";
        }
    }

    hidePointer() {
        this.pointer.style.display = "none";
        this.pointerMode = false;
    }

    isPointerMode() {
        return this.pointerMode;
    }
}
