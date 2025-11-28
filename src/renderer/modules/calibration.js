// src/renderer/modules/calibration.js
// Calibration management module

export class CalibrationManager {
    constructor() {
        this.isCalibrating = false;
        this.points = [];
        this.region = null;
        
        this.createOverlay();
    }

    createOverlay() {
        this.overlay = document.createElement("div");
        this.overlay.id = "calibration-overlay";
        this.overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            pointer-events: none;
            z-index: 9999;
            display: none;
        `;
        document.body.appendChild(this.overlay);
    }

    start() {
        this.isCalibrating = true;
        this.points = [];
        this.overlay.style.display = "block";
        console.log("[Calibration] Started");
    }

    addPoint(position) {
        this.points.push(position);
        this.showPoints();

        // Send haptic feedback for each calibration point
        if (window.electronAPI && window.electronAPI.sendHaptic) {
            window.electronAPI.sendHaptic("calibration_point");
        }
    }

    complete(region) {
        this.isCalibrating = false;
        this.region = region;
        this.showPoints();

        // Send strong haptic feedback on calibration complete
        if (window.electronAPI && window.electronAPI.sendHaptic) {
            window.electronAPI.sendHaptic("calibration_done");
        }

        setTimeout(() => {
            this.overlay.style.display = "none";
        }, 2000);

        console.log("[Calibration] Complete");
    }

    reset() {
        this.region = null;
        this.points = [];
        this.overlay.style.display = "none";
        this.isCalibrating = false;
        console.log("[Calibration] Reset");
    }

    showPoints() {
        this.overlay.style.display = "block";
        this.overlay.innerHTML = "";

        this.points.forEach((point, index) => {
            const dot = document.createElement("div");
            dot.style.cssText = `
                position: absolute;
                width: 20px;
                height: 20px;
                background: rgba(255, 100, 0, 0.8);
                border: 2px solid white;
                border-radius: 50%;
                transform: translate(-50%, -50%);
                left: ${point.x * 100}%;
                top: ${point.y * 100}%;
            `;
            this.overlay.appendChild(dot);

            const label = document.createElement("div");
            label.style.cssText = `
                position: absolute;
                color: white;
                font-size: 16px;
                font-weight: bold;
                transform: translate(-50%, -150%);
                left: ${point.x * 100}%;
                top: ${point.y * 100}%;
            `;
            label.textContent = index + 1;
            this.overlay.appendChild(label);
        });

        if (this.region) {
            const regionDiv = document.createElement("div");
            regionDiv.style.cssText = `
                position: absolute;
                border: 2px dashed rgba(0, 255, 0, 0.5);
                background: rgba(0, 255, 0, 0.05);
                left: ${this.region.min_x * 100}%;
                top: ${this.region.min_y * 100}%;
                width: ${this.region.width * 100}%;
                height: ${this.region.height * 100}%;
            `;
            this.overlay.appendChild(regionDiv);
        }
    }

    isActive() {
        return this.isCalibrating;
    }

    getRegion() {
        return this.region;
    }
}
