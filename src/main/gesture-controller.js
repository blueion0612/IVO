// IMU Gesture Controller process manager
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");
const { app } = require("electron");

const isWin = process.platform === "win32";

class GestureControllerManager {
    constructor(config) {
        this.config = config;
        this.process = null;
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
            "C:\\Users\\bluei\\AppData\\Local\\Programs\\Python\\Python312\\python.exe",
            "C:\\Users\\bluei\\AppData\\Local\\Programs\\Python\\Python311\\python.exe",
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
                console.log(`[Gesture] Found Python at: ${candidate}`);
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
                console.log(`[Gesture] Found Python via ${isWin ? 'where' : 'which'}: ${result}`);
                return result;
            }
        } catch (e) {
            // Command failed
        }

        console.error("[Gesture] Python not found! Please install Python and add to PATH.");
        return null;
    }

    /**
     * 스크립트 경로 찾기 (개발/패키징 환경 모두 지원)
     */
    findScriptPath(basePath) {
        const scriptName = this.config.paths.gesture_controller.replace(/^\.\//, '');

        // 가능한 경로들 (우선순위 순)
        const possiblePaths = [
            // 1. 개발 환경: basePath에서 직접 참조
            path.join(basePath, scriptName),
            path.join(basePath, this.config.paths.gesture_controller),
            // 2. 패키징 환경: extraResources 폴더
            path.join(process.resourcesPath || '', scriptName),
            // 3. 패키징 환경: app 폴더 옆
            path.join(app.getAppPath(), '..', scriptName),
            // 4. 실행 파일과 같은 폴더
            path.join(path.dirname(process.execPath), scriptName),
            path.join(path.dirname(process.execPath), 'resources', scriptName),
        ];

        console.log("[Gesture] Searching for script in:");
        for (const p of possiblePaths) {
            console.log(`[Gesture]   - ${p}`);
            if (fs.existsSync(p)) {
                console.log(`[Gesture] Found script at: ${p}`);
                return p;
            }
        }

        console.error("[Gesture] Script not found in any location!");
        return null;
    }

    /**
     * Gesture Controller 시작
     * @param {string} basePath - 기본 경로
     */
    start(basePath) {
        if (this.process) {
            console.log("[Gesture] Already running");
            return;
        }

        console.log("[Gesture] Starting IMU Gesture Controller...");

        const pythonCmd = this.findPythonPath();

        if (!pythonCmd) {
            console.error("[Gesture] Cannot start - Python not found");
            return;
        }

        const scriptPath = this.findScriptPath(basePath);

        if (!scriptPath) {
            console.error("[Gesture] Cannot start - Script not found");
            return;
        }

        // 환경 변수 설정
        const env = { ...process.env };
        env.PYTHONIOENCODING = "utf-8";
        env.PYTHONUNBUFFERED = "1";

        // 스크립트가 위치한 디렉토리를 cwd로 사용 (models 폴더 등 상대경로 참조용)
        const scriptDir = path.dirname(scriptPath);

        console.log(`[Gesture] Python: ${pythonCmd}`);
        console.log(`[Gesture] Script: ${scriptPath}`);
        console.log(`[Gesture] Working dir: ${scriptDir}`);

        try {
            // shell: false로 직접 실행 (절대 경로 사용)
            this.process = spawn(pythonCmd, [scriptPath], {
                cwd: scriptDir,
                windowsHide: true,
                env: env,
                stdio: ['pipe', 'pipe', 'pipe']
            });
        } catch (err) {
            console.error("[Gesture] Failed to spawn Python process:", err.message);
            console.error("[Gesture] Please ensure Python is installed and in PATH");
            return;
        }

        // 에러 이벤트 핸들러 추가
        this.process.on("error", (err) => {
            console.error("[Gesture] Process error:", err.message);
            this.process = null;
        });

        this.process.stdout.setEncoding('utf8');
        this.process.stdout.on("data", (data) => {
            const lines = data.split('\n');
            lines.forEach(line => {
                line = line.trim();
                if (!line) return;
                console.log("[Gesture stdout]", line);
            });
        });

        this.process.stderr.setEncoding('utf8');
        this.process.stderr.on("data", (data) => {
            const lines = data.split('\n');
            lines.forEach(line => {
                line = line.trim();
                if (!line) return;
                // Python 에러만 출력
                if (line.includes("Traceback") || line.includes("Error")) {
                    console.error("[Gesture stderr]", line);
                }
            });
        });

        this.process.on("close", (code) => {
            console.log(`[Gesture] Process exited with code ${code}`);
            this.process = null;
        });
    }

    /**
     * Gesture Controller 중지
     */
    stop() {
        if (this.process) {
            this.process.kill();
            this.process = null;
            console.log("[Gesture] Stopped");
        }
    }

    /**
     * 재시작
     * @param {string} basePath - 기본 경로
     */
    restart(basePath) {
        this.stop();
        setTimeout(() => {
            this.start(basePath);
        }, 1000);
    }

    /**
     * 실행 중인지 확인
     */
    isRunning() {
        return this.process !== null;
    }
}

module.exports = GestureControllerManager;
