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
     * Find script path (supports both dev and packaged environments)
     */
    findScriptPath(basePath) {
        const scriptName = this.config.paths.gesture_controller.replace(/^\.\//, '');

        // Possible paths in priority order
        const possiblePaths = [
            // 1. Dev environment: direct reference from basePath
            path.join(basePath, scriptName),
            path.join(basePath, this.config.paths.gesture_controller),
            // 2. Packaged: extraResources folder
            path.join(process.resourcesPath || '', scriptName),
            // 3. Packaged: next to app folder
            path.join(app.getAppPath(), '..', scriptName),
            // 4. Same folder as executable
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
     * Start Gesture Controller
     * @param {string} basePath - Base path for script lookup
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

        // Set environment variables
        const env = { ...process.env };
        env.PYTHONIOENCODING = "utf-8";
        env.PYTHONUNBUFFERED = "1";

        // Use script directory as cwd
        const scriptDir = path.dirname(scriptPath);

        // Find models directory (in project root or resources)
        const modelsPaths = [
            path.join(basePath, 'models'),
            path.join(process.resourcesPath || '', 'models'),
            path.join(app.getAppPath(), '..', 'models'),
        ];

        let modelsDir = null;
        for (const p of modelsPaths) {
            if (fs.existsSync(p)) {
                modelsDir = p;
                break;
            }
        }

        const stage1Path = modelsDir ? path.join(modelsDir, 'stage1_best.pt') : './models/stage1_best.pt';
        const stage2Path = modelsDir ? path.join(modelsDir, 'stage2_best.pt') : './models/stage2_best.pt';

        console.log(`[Gesture] Python: ${pythonCmd}`);
        console.log(`[Gesture] Script: ${scriptPath}`);
        console.log(`[Gesture] Working dir: ${scriptDir}`);
        console.log(`[Gesture] Models dir: ${modelsDir}`);

        // Build command line arguments with model paths
        const args = [
            scriptPath,
            '--stage1_ckpt', stage1Path,
            '--stage2_ckpt', stage2Path
        ];

        try {
            // Direct execution with absolute paths (shell: false)
            this.process = spawn(pythonCmd, args, {
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

        // Add error event handler
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
                // Only output Python errors
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
     * Stop Gesture Controller
     */
    stop() {
        if (this.process) {
            this.process.kill();
            this.process = null;
            console.log("[Gesture] Stopped");
        }
    }

    /**
     * Restart Gesture Controller
     * @param {string} basePath - Base path for script lookup
     */
    restart(basePath) {
        this.stop();
        setTimeout(() => {
            this.start(basePath);
        }, 1000);
    }

    /**
     * Check if process is running
     */
    isRunning() {
        return this.process !== null;
    }
}

module.exports = GestureControllerManager;
