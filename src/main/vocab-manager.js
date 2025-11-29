// src/main/vocab-manager.js
// Vocabulary Dictionary Manager - handles dictionary lookup subprocess

const { spawn } = require("child_process");
const path = require("path");

class VocabManager {
    constructor() {
        this.process = null;
        this.isRunning = false;
        this.pendingRequests = new Map();
        this.requestIdCounter = 0;
        this.onMessage = null;
    }

    start(basePath) {
        if (this.isRunning) {
            console.log("[Vocab] Already running");
            return;
        }

        const scriptPath = path.join(basePath, "py", "vocab", "vocab_server.py");
        console.log(`[Vocab] Starting: ${scriptPath}`);

        this.process = spawn("python", ["-u", scriptPath], {
            cwd: basePath,
            stdio: ['pipe', 'pipe', 'pipe'],
            env: {
                ...process.env,
                PYTHONIOENCODING: "utf-8",
                PYTHONUNBUFFERED: "1",
                PYTHONUTF8: "1"
            }
        });

        // Set encoding for stdin/stdout
        this.process.stdin.setDefaultEncoding('utf8');
        this.process.stdout.setEncoding('utf8');
        this.process.stderr.setEncoding('utf8');

        this.isRunning = true;

        this.process.stdout.on("data", (data) => {
            const lines = data.toString().split("\n").filter(l => l.trim());
            for (const line of lines) {
                try {
                    const msg = JSON.parse(line);
                    this.handleMessage(msg);
                } catch (e) {
                    console.log(`[Vocab] stdout: ${line}`);
                }
            }
        });

        this.process.stderr.on("data", (data) => {
            console.error(`[Vocab] stderr: ${data}`);
        });

        this.process.on("close", (code) => {
            console.log(`[Vocab] Process exited with code ${code}`);
            this.isRunning = false;
            this.process = null;

            // Reject pending requests
            for (const [id, resolver] of this.pendingRequests) {
                resolver.reject(new Error("Process exited"));
            }
            this.pendingRequests.clear();
        });

        this.process.on("error", (err) => {
            console.error("[Vocab] Process error:", err);
            this.isRunning = false;
        });
    }

    stop() {
        if (!this.isRunning || !this.process) {
            return;
        }

        console.log("[Vocab] Stopping...");
        this.sendCommand({ type: "quit" });

        setTimeout(() => {
            if (this.process) {
                this.process.kill();
                this.process = null;
            }
            this.isRunning = false;
        }, 1000);
    }

    handleMessage(msg) {
        if (msg.type === "ready") {
            console.log("[Vocab] Server ready");
        } else if (msg.type === "definition") {
            // Handle definition response
            if (this.onMessage) {
                this.onMessage(msg);
            }
        } else if (msg.type === "error") {
            console.error("[Vocab] Error:", msg.error);
            if (this.onMessage) {
                this.onMessage(msg);
            }
        } else if (msg.type === "shutdown") {
            console.log("[Vocab] Server shutdown");
        }
    }

    sendCommand(cmd) {
        if (!this.isRunning || !this.process) {
            console.warn("[Vocab] Cannot send command - not running");
            return false;
        }

        try {
            this.process.stdin.write(JSON.stringify(cmd) + "\n");
            return true;
        } catch (e) {
            console.error("[Vocab] Send error:", e);
            return false;
        }
    }

    lookup(word) {
        return new Promise((resolve, reject) => {
            if (!this.isRunning) {
                reject(new Error("Vocab server not running"));
                return;
            }

            // Set up one-time handler
            const originalHandler = this.onMessage;
            this.onMessage = (msg) => {
                if (msg.type === "definition" && msg.word === word) {
                    this.onMessage = originalHandler;
                    resolve(msg);
                } else if (msg.type === "error") {
                    this.onMessage = originalHandler;
                    resolve({ error: msg.error, word });
                }
            };

            this.sendCommand({ type: "lookup", word });

            // Timeout
            setTimeout(() => {
                if (this.onMessage !== originalHandler) {
                    this.onMessage = originalHandler;
                    resolve({ error: "Timeout", word });
                }
            }, 10000);
        });
    }

    setOnMessage(callback) {
        this.onMessage = callback;
    }
}

module.exports = { VocabManager };
