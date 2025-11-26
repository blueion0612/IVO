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
     * 스크립트 경로 찾기 (개발/패키징 환경 모두 지원)
     */
    findScriptPath(basePath) {
        const scriptName = this.config.paths.hand_tracker.replace(/^\.\//, '');

        // 가능한 경로들 (우선순위 순)
        const possiblePaths = [
            // 1. 개발 환경: basePath에서 직접 참조
            path.join(basePath, scriptName),
            path.join(basePath, this.config.paths.hand_tracker),
            // 2. 패키징 환경: extraResources 폴더
            path.join(process.resourcesPath || '', scriptName),
            // 3. 패키징 환경: app 폴더 옆
            path.join(app.getAppPath(), '..', scriptName),
            // 4. 실행 파일과 같은 폴더
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
     * Hand tracking 시작
     * @param {string} basePath - 기본 경로
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

        // 환경 변수 설정
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

                // MediaPipe 경고 필터링
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
     * Hand tracking 중지
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
     * Hand tracker에 명령 전송
     * @param {Object} command - 전송할 명령 객체
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
     * 메시지 핸들러 설정
     * @param {Function} handler - 메시지 처리 함수
     */
    onMessage(handler) {
        this.messageHandler = handler;
    }

    /**
     * 실행 중인지 확인
     */
    isRunning() {
        return this.process !== null;
    }
}

module.exports = HandTrackingManager;
