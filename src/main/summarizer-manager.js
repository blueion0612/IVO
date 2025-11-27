// Summarizer Manager - Local KoBART-based QA Summarization process manager
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");
const readline = require("readline");
const { app } = require("electron");

const isWin = process.platform === "win32";

class SummarizerManager {
    constructor(config) {
        this.config = config;
        this.process = null;
        this.stdin = null;
        this.messageHandler = null;
        this.isModelReady = false;
        this.pendingRequests = new Map(); // requestId -> { resolve, reject }
        this.requestCounter = 0;
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
                console.log(`[Summarizer] Found Python at: ${candidate}`);
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
                console.log(`[Summarizer] Found Python via ${isWin ? 'where' : 'which'}: ${result}`);
                return result;
            }
        } catch (e) {
            // Command failed
        }

        console.error("[Summarizer] Python not found!");
        return null;
    }

    /**
     * Find script path (supports both dev and packaged environments)
     */
    findScriptPath(basePath) {
        const scriptName = this.config.paths?.summarizer_script || "qa_summarizer_server.py";

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
                console.log(`[Summarizer] Found script at: ${p}`);
                return p;
            }
        }

        console.error("[Summarizer] Script not found!");
        return null;
    }

    /**
     * Start Summarizer service (loads KoBART model)
     * @param {string} basePath - Base path for script lookup
     */
    start(basePath) {
        if (this.process) {
            console.log("[Summarizer] Already running");
            return Promise.resolve(true);
        }

        return new Promise((resolve, reject) => {
            console.log("[Summarizer] Starting summarization service...");

            const pythonCmd = this.findPythonPath();
            if (!pythonCmd) {
                console.error("[Summarizer] Cannot start - Python not found");
                reject(new Error("Python not found"));
                return;
            }

            const scriptPath = this.findScriptPath(basePath);
            if (!scriptPath) {
                console.error("[Summarizer] Cannot start - Script not found");
                reject(new Error("Script not found"));
                return;
            }

            const scriptDir = path.dirname(scriptPath);

            // Set environment variables
            const env = { ...process.env };
            env.PYTHONIOENCODING = "utf-8";
            env.PYTHONUNBUFFERED = "1";
            env.KMP_DUPLICATE_LIB_OK = "TRUE";

            console.log(`[Summarizer] Python: ${pythonCmd}`);
            console.log(`[Summarizer] Script: ${scriptPath}`);

            try {
                this.process = spawn(pythonCmd, [scriptPath], {
                    cwd: scriptDir,
                    windowsHide: true,
                    env: env,
                    stdio: ['pipe', 'pipe', 'pipe']
                });
            } catch (err) {
                console.error("[Summarizer] Failed to spawn:", err.message);
                reject(err);
                return;
            }

            this.process.on("error", (err) => {
                console.error("[Summarizer] Process error:", err.message);
                this.process = null;
                this.stdin = null;
                reject(err);
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
                    this.handleMessage(msg);

                    // Resolve start promise when ready
                    if (msg.type === "ready") {
                        resolve(true);
                    }
                } catch (e) {
                    console.log("[Summarizer] Raw:", line);
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
                        line.includes("FutureWarning") ||
                        line.includes("UserWarning")) {
                        return;
                    }
                    console.error("[Summarizer stderr]", line);
                });
            });

            this.process.on("close", (code) => {
                console.log(`[Summarizer] Process exited with code ${code}`);
                this.process = null;
                this.stdin = null;
                this.isModelReady = false;

                // Reject all pending requests
                for (const [reqId, { reject }] of this.pendingRequests) {
                    reject(new Error("Summarizer process terminated"));
                }
                this.pendingRequests.clear();
            });

            // Timeout for initialization
            setTimeout(() => {
                if (!this.isModelReady && this.process) {
                    // Still waiting, but don't reject - model loading can take time
                    console.log("[Summarizer] Model still loading...");
                }
            }, 30000);
        });
    }

    /**
     * Handle summarizer messages
     */
    handleMessage(msg) {
        switch (msg.type) {
            case "ready":
                console.log("[Summarizer] Service ready - KoBART model loaded");
                this.isModelReady = true;
                break;

            case "info":
                console.log("[Summarizer] Info:", msg.message);
                break;

            case "summary":
                console.log(`[Summarizer] Summary generated (${msg.count} conversations)`);
                // Resolve the most recent pending request
                const lastReqId = Array.from(this.pendingRequests.keys()).pop();
                if (lastReqId !== undefined) {
                    const { resolve } = this.pendingRequests.get(lastReqId);
                    this.pendingRequests.delete(lastReqId);
                    resolve({ summary: msg.summary });
                }
                break;

            case "warning":
                console.warn("[Summarizer] Warning:", msg.message);
                break;

            case "error":
                console.error("[Summarizer] Error:", msg.message);
                // Reject the most recent pending request
                const errReqId = Array.from(this.pendingRequests.keys()).pop();
                if (errReqId !== undefined) {
                    const { reject } = this.pendingRequests.get(errReqId);
                    this.pendingRequests.delete(errReqId);
                    reject(new Error(msg.message));
                }
                break;
        }

        if (this.messageHandler) {
            this.messageHandler(msg);
        }
    }

    /**
     * Stop Summarizer service
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

        this.isModelReady = false;
    }

    /**
     * Request summary for conversations
     * @param {Array} conversations - Array of conversation objects
     * @returns {Promise<{summary: string}>}
     */
    async summarize(conversations) {
        if (!this.stdin) {
            throw new Error("Summarizer process not running");
        }

        if (!this.isModelReady) {
            throw new Error("Summarizer model not ready");
        }

        return new Promise((resolve, reject) => {
            const reqId = ++this.requestCounter;
            this.pendingRequests.set(reqId, { resolve, reject });

            const cmd = JSON.stringify({
                command: "summarize",
                conversations: conversations
            }) + '\n';

            this.stdin.write(cmd);

            // Timeout for summarization
            setTimeout(() => {
                if (this.pendingRequests.has(reqId)) {
                    this.pendingRequests.delete(reqId);
                    reject(new Error("Summarization timeout"));
                }
            }, 60000); // 60 second timeout
        });
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
     * Check if model is ready
     */
    isReady() {
        return this.isModelReady;
    }
}

module.exports = SummarizerManager;
