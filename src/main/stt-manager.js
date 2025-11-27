// STT Manager - Local Whisper-based Speech-to-Text process manager
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");
const readline = require("readline");
const { app } = require("electron");

const isWin = process.platform === "win32";

class STTManager {
    constructor(config) {
        this.config = config;
        this.process = null;
        this.stdin = null;
        this.messageHandler = null;
        this.isRecordingActive = false;
        this.isMicrophoneReady = false;
    }

    findPythonPath() {
        const { execSync } = require("child_process");

        const absoluteCandidates = isWin ? [
            "C:\\Python312\\python.exe",
            "C:\\Python311\\python.exe",
            "C:\\Python310\\python.exe",
            "C:\\Python39\\python.exe",
            "C:\\Python38\\python.exe",
            (process.env.LOCALAPPDATA || "") + "\\Programs\\Python\\Python312\\python.exe",
            (process.env.LOCALAPPDATA || "") + "\\Programs\\Python\\Python311\\python.exe",
            (process.env.LOCALAPPDATA || "") + "\\Programs\\Python\\Python310\\python.exe",
            (process.env.LOCALAPPDATA || "") + "\\Programs\\Python\\Python39\\python.exe",
            (process.env.USERPROFILE || "") + "\\AppData\\Local\\Programs\\Python\\Python312\\python.exe",
            (process.env.USERPROFILE || "") + "\\AppData\\Local\\Programs\\Python\\Python311\\python.exe",
            (process.env.USERPROFILE || "") + "\\AppData\\Local\\Programs\\Python\\Python310\\python.exe",
        ] : [
            "/usr/bin/python3",
            "/usr/local/bin/python3",
            "/opt/homebrew/bin/python3",
            "/opt/homebrew/bin/python3.12",
            "/opt/homebrew/bin/python3.11",
            "/usr/bin/python"
        ];

        for (const candidate of absoluteCandidates) {
            if (candidate && fs.existsSync(candidate)) {
                console.log(`[STT] Found Python at: ${candidate}`);
                return candidate;
            }
        }

        // Find via system command
        try {
            const cmd = isWin ? "where python" : "which python3";
            const result = execSync(cmd, {
                encoding: 'utf8',
                windowsHide: true,
                timeout: 5000
            }).trim().split('\n')[0].trim();
            if (result && fs.existsSync(result)) {
                console.log(`[STT] Found Python via ${isWin ? 'where' : 'which'}: ${result}`);
                return result;
            }
        } catch (e) {
            // Command failed
        }

        console.error("[STT] Python not found!");
        return null;
    }

    /**
     * Find script path (supports both dev and packaged environments)
     */
    findScriptPath(basePath) {
        const scriptName = this.config.paths?.stt_script || "stt_server.py";

        // Possible paths in priority order
        const possiblePaths = [
            // 1. Dev environment: direct reference from basePath
            path.join(basePath, scriptName),
            // 2. Packaged: extraResources folder
            path.join(process.resourcesPath || '', scriptName),
            // 3. Packaged: next to app folder
            path.join(app.getAppPath(), '..', scriptName),
            // 4. Same folder as executable
            path.join(path.dirname(process.execPath), scriptName),
            path.join(path.dirname(process.execPath), 'resources', scriptName),
        ];

        for (const p of possiblePaths) {
            if (fs.existsSync(p)) {
                console.log(`[STT] Found script at: ${p}`);
                return p;
            }
        }

        console.error("[STT] Script not found!");
        return null;
    }

    /**
     * Start STT service (loads Whisper model)
     * @param {string} basePath - Base path for script lookup
     */
    start(basePath) {
        if (this.process) {
            console.log("[STT] Already running");
            return;
        }

        console.log("[STT] Starting STT service...");

        const pythonCmd = this.findPythonPath();
        if (!pythonCmd) {
            console.error("[STT] Cannot start - Python not found");
            return;
        }

        const scriptPath = this.findScriptPath(basePath);
        if (!scriptPath) {
            console.error("[STT] Cannot start - Script not found");
            return;
        }

        const scriptDir = path.dirname(scriptPath);

        // Set environment variables
        const env = { ...process.env };
        env.PYTHONIOENCODING = "utf-8";
        env.PYTHONUNBUFFERED = "1";
        env.KMP_DUPLICATE_LIB_OK = "TRUE";

        console.log(`[STT] Python: ${pythonCmd}`);
        console.log(`[STT] Script: ${scriptPath}`);

        try {
            this.process = spawn(pythonCmd, [scriptPath], {
                cwd: scriptDir,
                windowsHide: true,
                env: env,
                stdio: ['pipe', 'pipe', 'pipe']
            });
        } catch (err) {
            console.error("[STT] Failed to spawn:", err.message);
            return;
        }

        this.process.on("error", (err) => {
            console.error("[STT] Process error:", err.message);
            this.process = null;
            this.stdin = null;
        });

        this.stdin = this.process.stdin;

        const rl = readline.createInterface({
            input: this.process.stdout,
            crlfDelay: Infinity,
        });

        rl.on("line", (line) => {
            line = line.trim();
            if (!line) return;

            try {
                const msg = JSON.parse(line);
                this.handleSTTMessage(msg);
            } catch (e) {
                console.log("[STT] Raw:", line);
            }
        });

        this.process.stderr.on("data", (data) => {
            const stderr = data.toString();
            const lines = stderr.split('\n');
            lines.forEach(line => {
                line = line.trim();
                if (!line) return;
                // Filter common warnings
                if (line.includes("WARNING") ||
                    line.includes("INFO") ||
                    line.includes("FutureWarning")) {
                    return;
                }
                console.error("[STT stderr]", line);
            });
        });

        this.process.on("close", (code) => {
            console.log(`[STT] Process exited with code ${code}`);
            this.process = null;
            this.stdin = null;
            this.isMicrophoneReady = false;
        });
    }

    /**
     * Handle STT messages
     */
    handleSTTMessage(msg) {
        switch (msg.type) {
            case "ready":
                console.log("[STT] Service ready - Whisper model loaded");
                this.isMicrophoneReady = true;
                break;

            case "recording_started":
                console.log("[STT] Recording started");
                this.isRecordingActive = true;
                break;

            case "recording_stopped":
                console.log("[STT] Recording stopped");
                this.isRecordingActive = false;
                break;

            case "transcription":
                console.log(`[STT] Transcription: ${msg.text} (${msg.lang}, ${(msg.prob * 100).toFixed(1)}%)`);
                break;

            case "error":
                console.error("[STT] Error:", msg.message);
                break;
        }

        if (this.messageHandler) {
            this.messageHandler(msg);
        }
    }

    /**
     * Stop STT service
     */
    stop() {
        if (!this.process) return;

        if (this.stdin) {
            this.stdin.write('{"command": "quit"}\n');
        }

        setTimeout(() => {
            if (this.process) {
                this.process.kill();
                this.process = null;
                this.stdin = null;
            }
        }, 500);

        this.isMicrophoneReady = false;
        this.isRecordingActive = false;
    }

    /**
     * Start recording (microphone capture)
     */
    startRecording() {
        if (!this.stdin) {
            console.log("[STT] Process not running");
            return false;
        }

        if (this.isRecordingActive) {
            console.log("[STT] Already recording");
            return false;
        }

        const cmd = JSON.stringify({ command: "start" }) + '\n';
        this.stdin.write(cmd);
        return true;
    }

    /**
     * Stop recording and get transcription
     */
    stopRecording() {
        if (!this.stdin) {
            console.log("[STT] Process not running");
            return false;
        }

        if (!this.isRecordingActive) {
            console.log("[STT] Not recording");
            return false;
        }

        const cmd = JSON.stringify({ command: "stop" }) + '\n';
        this.stdin.write(cmd);
        return true;
    }

    /**
     * Set message handler callback
     * @param {Function} handler - Message handler function
     */
    onMessage(handler) {
        this.messageHandler = handler;
    }

    /**
     * Check if process is running
     */
    isRunning() {
        return this.process !== null;
    }

    /**
     * Check if recording is active
     */
    isRecording() {
        return this.isRecordingActive;
    }

    /**
     * Check if microphone is ready
     */
    isMicReady() {
        return this.isMicrophoneReady;
    }
}

module.exports = STTManager;
