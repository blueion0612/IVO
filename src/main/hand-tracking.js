// Hand tracking Python process manager
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");
const readline = require("readline");
const { app } = require("electron");

const isWin = process.platform === "win32";

class HandTrackingManager {
    constructor(config) {
        this.config = config;
        this.process = null;
        this.stdin = null;
        this.messageHandler = null;
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
                console.log(`[HandTracking] Found Python at: ${candidate}`);
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
                console.log(`[HandTracking] Found Python via ${isWin ? 'where' : 'which'}: ${result}`);
                return result;
            }
        } catch (e) {
            // Command failed
        }

        console.error("[HandTracking] Python not found!");
        return null;
    }

    /**
     * Find script path (supports both dev and packaged environments)
     */
    findScriptPath(basePath) {
        const scriptName = this.config.paths.hand_tracker.replace(/^\.\//, '');

        // Possible paths in priority order
        const possiblePaths = [
            // 1. Dev environment: direct reference from basePath
            path.join(basePath, scriptName),
            path.join(basePath, this.config.paths.hand_tracker),
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
                console.log(`[HandTracking] Found script at: ${p}`);
                return p;
            }
        }

        console.error("[HandTracking] Script not found!");
        return null;
    }

    /**
     * Start hand tracking
     * @param {string} basePath - Base path for script lookup
     */
    start(basePath) {
        if (this.process) {
            console.log("[HandTracking] Already running");
            return;
        }

        console.log("[HandTracking] Starting Python process...");

        const pythonCmd = this.findPythonPath();
        if (!pythonCmd) {
            console.error("[HandTracking] Cannot start - Python not found");
            return;
        }

        const scriptPath = this.findScriptPath(basePath);
        if (!scriptPath) {
            console.error("[HandTracking] Cannot start - Script not found");
            return;
        }

        const scriptDir = path.dirname(scriptPath);

        // Set environment variables
        const env = { ...process.env, ...this.config.python.env };
        env.PYTHONIOENCODING = "utf-8";
        env.PYTHONUNBUFFERED = "1";

        console.log(`[HandTracking] Python: ${pythonCmd}`);
        console.log(`[HandTracking] Script: ${scriptPath}`);

        try {
            this.process = spawn(pythonCmd, [scriptPath], {
                cwd: scriptDir,
                windowsHide: true,
                env: env,
                stdio: ['pipe', 'pipe', 'pipe']
            });
        } catch (err) {
            console.error("[HandTracking] Failed to spawn:", err.message);
            return;
        }

        this.process.on("error", (err) => {
            console.error("[HandTracking] Process error:", err.message);
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
                if (this.messageHandler) {
                    this.messageHandler(msg);
                }
            } catch (e) {
                console.log("[HandTracking] Raw:", line);
            }
        });

        this.process.stderr.on("data", (data) => {
            const stderr = data.toString();
            const lines = stderr.split('\n');
            lines.forEach(line => {
                line = line.trim();
                if (!line) return;

                // Filter MediaPipe warnings
                if (line.includes("WARNING") ||
                    line.includes("INFO") ||
                    line.includes("I0000") ||
                    line.includes("mediapipe") ||
                    line.includes("Feedback")) {
                    return;
                }
                console.error("[HandTracking stderr]", line);
            });
        });

        this.process.on("close", (code) => {
            console.log(`[HandTracking] Process exited with code ${code}`);
            this.process = null;
            this.stdin = null;
        });
    }

    /**
     * Stop hand tracking
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
    }

    /**
     * Send command to hand tracker
     * @param {Object} command - Command object to send
     */
    send(command) {
        if (!this.stdin) {
            console.log("[HandTracking] Process not running");
            return false;
        }
        const cmd = JSON.stringify(command) + '\n';
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
}

module.exports = HandTrackingManager;
