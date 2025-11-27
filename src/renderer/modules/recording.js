// src/renderer/modules/recording.js
// Caption recording management module

export class RecordingManager {
    constructor(config, captionElement, showWarning) {
        this.config = config;
        this.captionElement = captionElement;
        this.showWarning = showWarning;
        this.onSummaryReceived = null;  // Callback: pass summary text to external handler

        this.mediaRecorder = null;
        this.recordedChunks = [];
        this.isRecording = false;

        this.createIndicator();
    }

    setOnSummaryReceived(callback) {
        this.onSummaryReceived = callback;
    }

    createIndicator() {
        this.indicator = document.createElement("div");
        this.indicator.id = "recording-indicator";
        this.indicator.style.cssText = `
            position: fixed;
            top: 30px;
            right: 30px;
            padding: 12px 20px;
            background: linear-gradient(135deg, #c62828, #f44336);
            color: white;
            border-radius: 12px;
            font-size: 16px;
            font-weight: bold;
            z-index: 99998;
            display: none;
            animation: recording-pulse 1.5s ease-in-out infinite;
            box-shadow: 0 4px 20px rgba(0,0,0,0.4);
            border: 2px solid rgba(255,255,255,0.2);
        `;
        this.indicator.innerHTML = 'REC';
        document.body.appendChild(this.indicator);
        
        // Add animation style
        const style = document.createElement("style");
        style.textContent = `
            @keyframes recording-pulse {
                0%, 100% { 
                    opacity: 0.8;
                    transform: scale(1);
                }
                50% { 
                    opacity: 1;
                    transform: scale(1.05);
                }
            }
        `;
        document.head.appendChild(style);
    }

    async start() {
        if (this.isRecording) {
            if (this.showWarning) this.showWarning("Already recording");
            return false;
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            this.recordedChunks = [];
            this.mediaRecorder = new MediaRecorder(stream);

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.recordedChunks.push(event.data);
                }
            };

            this.mediaRecorder.onstop = async () => {
                stream.getTracks().forEach((t) => t.stop());
                this.indicator.style.display = "none";

                if (this.recordedChunks.length === 0) {
                    if (this.showWarning) this.showWarning("No data recorded");
                    return;
                }
                
                const blob = new Blob(this.recordedChunks, { type: "audio/webm" });
                await this.sendToSummaryAPI(blob);
            };

            this.mediaRecorder.start();
            this.isRecording = true;
            this.indicator.style.display = "block";
            console.log("[REC] Recording started");
            return true;
        } catch (err) {
            console.error("[REC] Error:", err);
            if (this.showWarning) this.showWarning("Failed to access microphone");
            return false;
        }
    }

    stop() {
        if (this.mediaRecorder && this.mediaRecorder.state !== "inactive") {
            this.mediaRecorder.stop();
            this.isRecording = false;
            this.indicator.style.display = "none";
            console.log("[REC] Recording stopped");
        }
    }

    async sendToSummaryAPI(blob) {
        const formData = new FormData();
        formData.append("file", blob, "audio.webm");

        try {
            const res = await fetch(this.config.api.summary_url, {
                method: "POST",
                body: formData,
            });

            if (!res.ok) throw new Error(`HTTP ${res.status}`);

            const data = await res.json();
            const summary = data.summary || data.text || "No summary";

            // Add to stack if callback exists
            if (this.onSummaryReceived) {
                this.onSummaryReceived(summary);
            }

            console.log("[REC] Summary received:", summary);
        } catch (err) {
            console.error("[REC] Summary API error:", err);
            if (this.showWarning) this.showWarning("Summary API failed");
        }
    }

    isActive() {
        return this.isRecording;
    }

    hideIndicator() {
        this.indicator.style.display = "none";
    }
}
