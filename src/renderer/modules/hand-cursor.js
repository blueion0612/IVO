// src/renderer/modules/hand-cursor.js
// Hand Tracking 커서 관리 모듈

export class HandCursor {
    constructor(config) {
        this.config = config;
        
        // 상태
        this.pointerMode = false;
        this.isDrawingEnabled = false;
        this.isEraserMode = false;
        this.currentColor = config.overlay.default_color;
        
        this.createCursor();
    }

    createCursor() {
        this.cursor = document.createElement("div");
        this.cursor.id = "hand-cursor";
        this.cursor.style.cssText = `
            position: fixed;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: rgba(0, 255, 0, 0.3);
            border: 2px solid rgba(0, 255, 0, 0.8);
            pointer-events: none;
            display: none;
            transform: translate(-50%, -50%);
            z-index: 10000;
            transition: all 0.08s ease;
        `;
        document.body.appendChild(this.cursor);
    }

    updatePosition(position) {
        if (!position) {
            this.cursor.style.display = "none";
            return null;
        }

        const screenX = position.x * window.innerWidth;
        const screenY = position.y * window.innerHeight;

        this.cursor.style.left = screenX + "px";
        this.cursor.style.top = screenY + "px";
        this.cursor.style.display = "block";

        return { x: screenX, y: screenY };
    }

    updateStyle() {
        if (this.isEraserMode) {
            this.cursor.style.background = "rgba(255, 255, 255, 0.5)";
            this.cursor.style.borderColor = "rgba(100, 100, 100, 0.9)";
            this.cursor.style.width = "18px";
            this.cursor.style.height = "18px";
        } else if (this.isDrawingEnabled) {
            this.cursor.style.background = this.currentColor.replace("0.8", "0.4");
            this.cursor.style.borderColor = this.currentColor;
            this.cursor.style.width = "10px";
            this.cursor.style.height = "10px";
        } else if (this.pointerMode) {
            this.cursor.style.background = "rgba(255, 0, 0, 0.5)";
            this.cursor.style.borderColor = "rgba(255, 0, 0, 0.9)";
            this.cursor.style.width = "14px";
            this.cursor.style.height = "14px";
        } else {
            this.cursor.style.background = "rgba(255, 200, 0, 0.3)";
            this.cursor.style.borderColor = "rgba(255, 200, 0, 0.8)";
            this.cursor.style.width = "12px";
            this.cursor.style.height = "12px";
        }
    }

    setPointerMode(enabled) {
        this.pointerMode = enabled;
        this.isDrawingEnabled = !enabled;
        this.updateStyle();
    }

    setDrawingEnabled(enabled) {
        this.isDrawingEnabled = enabled;
        this.updateStyle();
    }

    setEraserMode(enabled) {
        this.isEraserMode = enabled;
        this.updateStyle();
    }

    setColor(color) {
        this.currentColor = color;
        this.isEraserMode = false;
        this.updateStyle();
    }

    show() {
        this.cursor.style.display = "block";
    }

    hide() {
        this.cursor.style.display = "none";
    }
}
