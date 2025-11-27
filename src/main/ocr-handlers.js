// OCR, calculation, and graph IPC handlers
const path = require("path");
const fs = require("fs");
const { spawn, execSync } = require("child_process");
const { app } = require("electron");

const isWin = process.platform === "win32";

function findPythonPath() {
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
            return result;
        }
    } catch (e) {
        // Command failed
    }

    console.error("[OCR] Python not found!");
    return null;
}

/**
 * Find script path (supports both dev and packaged environments)
 */
function findScriptPath(basePath, configPath) {
    const scriptName = configPath.replace(/^\.\//, '');

    // Possible paths in priority order
    const possiblePaths = [
        // 1. Dev environment: direct reference from basePath
        path.join(basePath, scriptName),
        path.join(basePath, configPath),
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
            return p;
        }
    }

    console.error(`[OCR] Script not found: ${configPath}`);
    return null;
}

/**
 * Execute Python script
 * @param {string} scriptPath - Script path
 * @param {string[]} args - Argument array
 * @param {string} cwd - Working directory
 * @returns {Promise<string>} stdout result
 */
function runPython(scriptPath, args, cwd) {
    return new Promise((resolve, reject) => {
        const pythonCmd = findPythonPath();
        if (!pythonCmd) {
            reject(new Error("Python not found"));
            return;
        }

        const pythonArgs = [scriptPath, ...args];
        const scriptDir = path.dirname(scriptPath);

        console.log(`[OCR] Running: ${pythonCmd} ${scriptPath}`);

        const py = spawn(pythonCmd, pythonArgs, {
            cwd: scriptDir,
            windowsHide: true,
            env: {
                ...process.env,
                PYTHONIOENCODING: "utf-8",
                PYTHONUNBUFFERED: "1"
            },
            stdio: ['pipe', 'pipe', 'pipe']
        });

        py.on("error", (err) => {
            console.error("[OCR] Spawn error:", err.message);
            reject(err);
        });

        let stdout = "";
        let stderr = "";

        py.stdout.on("data", (data) => {
            stdout += data.toString("utf8");
        });

        py.stderr.on("data", (data) => {
            stderr += data.toString("utf8");
        });

        py.on("close", (code) => {
            if (code === 0) {
                resolve(stdout.trim());
            } else {
                reject(new Error(`Python exit ${code}: ${stderr}`));
            }
        });
    });
}

/**
 * Setup OCR handlers
 * @param {Electron.IpcMain} ipcMain
 * @param {BrowserWindow} win
 * @param {string} basePath
 * @param {Object} config
 */
function setupOCRHandlers(ipcMain, getWindow, basePath, config) {
    // ===== Legacy OCR handler (screen capture method) =====
    ipcMain.handle("do-ocr", async (event, { mode, bbox }) => {
        const win = getWindow();
        if (!win) throw new Error("overlay window not ready");

        try {
            // Canvas 내용만 캡쳐하기 위한 코드 실행
            const canvasDataUrl = await win.webContents.executeJavaScript(`
                (() => {
                    const canvas = document.getElementById('overlay');
                    if (!canvas) return null;
                    
                    const tempCanvas = document.createElement('canvas');
                    const ctx = tempCanvas.getContext('2d');
                    tempCanvas.width = ${bbox.width};
                    tempCanvas.height = ${bbox.height};
                    
                    ctx.drawImage(canvas, 
                        ${bbox.x}, ${bbox.y}, ${bbox.width}, ${bbox.height},
                        0, 0, ${bbox.width}, ${bbox.height}
                    );
                    
                    const newCanvas = document.createElement('canvas');
                    newCanvas.width = tempCanvas.width;
                    newCanvas.height = tempCanvas.height;
                    const newCtx = newCanvas.getContext('2d');
                    
                    newCtx.fillStyle = 'white';
                    newCtx.fillRect(0, 0, newCanvas.width, newCanvas.height);
                    newCtx.drawImage(tempCanvas, 0, 0);
                    
                    return newCanvas.toDataURL('image/png');
                })();
            `);

            if (!canvasDataUrl) {
                throw new Error("Canvas capture failed");
            }

            const base64Data = canvasDataUrl.replace(/^data:image\/png;base64,/, '');
            const tempDir = app.getPath("temp");
            const filePath = path.join(tempDir, `ink_ocr_canvas_${Date.now()}.png`);
            fs.writeFileSync(filePath, Buffer.from(base64Data, 'base64'));

            console.log(`[OCR] Canvas capture saved to: ${filePath}, mode=${mode}`);

            const scriptPath = findScriptPath(basePath, config.paths.ocr_script);
            if (!scriptPath) throw new Error("OCR script not found");
            const resultText = await runPython(scriptPath, [mode, filePath], basePath);

            return { text: resultText };
        } catch (err) {
            console.error("[OCR] Canvas capture error:", err);

            // Fallback: Full page capture
            const image = await win.capturePage(bbox);
            const tempDir = app.getPath("temp");
            const filePath = path.join(tempDir, `ink_ocr_fallback_${Date.now()}.png`);
            fs.writeFileSync(filePath, image.toPNG());

            console.log(`[OCR] Fallback capture to: ${filePath}, mode=${mode}`);
            const scriptPath = findScriptPath(basePath, config.paths.ocr_script);
            if (!scriptPath) throw new Error("OCR script not found");
            const resultText = await runPython(scriptPath, [mode, filePath], basePath);

            return { text: resultText };
        }
    });

    // ===== New OCR handler (direct session canvas DataURL transfer) =====
    ipcMain.handle("do-ocr-with-image", async (event, { mode, dataURL }) => {
        console.log(`[OCR] Request with session image, mode=${mode}`);
        
        try {
            // Extract base64 data from DataURL
            const base64Data = dataURL.replace(/^data:image\/png;base64,/, '');
            
            // Save to temporary file
            const tempDir = app.getPath("temp");
            const filePath = path.join(tempDir, `ocr_session_${Date.now()}.png`);
            fs.writeFileSync(filePath, Buffer.from(base64Data, 'base64'));

            console.log(`[OCR] Session image saved to: ${filePath}`);

            // Execute Python OCR script
            const scriptPath = findScriptPath(basePath, config.paths.ocr_script);
            if (!scriptPath) throw new Error("OCR script not found");
            const resultText = await runPython(scriptPath, [mode, filePath], basePath);
            
            // Delete temporary file
            try {
                fs.unlinkSync(filePath);
                console.log(`[OCR] Temp file deleted: ${filePath}`);
            } catch (e) {
                console.warn('[OCR] Failed to delete temp file:', e.message);
            }
            
            return { text: resultText };
            
        } catch (err) {
            console.error('[OCR] Error processing session image:', err);
            return { text: 'ERROR: ' + err.message };
        }
    });

    // ===== Calculation handler =====
    ipcMain.handle("do-calc", async (event, { expr }) => {
        const scriptPath = findScriptPath(basePath, config.paths.calc_script);
        if (!scriptPath) throw new Error("Calc script not found");
        const result = await runPython(scriptPath, [expr], basePath);
        return { result };
    });

    // ===== Graph handler =====
    ipcMain.handle("do-graph", async (event, { expr }) => {
        const win = getWindow();
        if (!win) throw new Error("overlay window not ready");

        const tempDir = app.getPath("temp");
        const graphPath = path.join(tempDir, `ink_graph_${Date.now()}.png`);

        const scriptPath = findScriptPath(basePath, config.paths.graph_script);
        if (!scriptPath) throw new Error("Graph script not found");

        try {
            console.log(`[GRAPH] Creating graph for: "${expr}"`);
            console.log(`[GRAPH] Output path: ${graphPath}`);

            await runPython(scriptPath, [expr, graphPath], basePath);

            if (!fs.existsSync(graphPath)) {
                throw new Error("Graph file was not created");
            }

            const stats = fs.statSync(graphPath);
            console.log(`[GRAPH] Graph created successfully, size: ${stats.size} bytes`);

            return { filePath: graphPath };
        } catch (err) {
            console.error("[GRAPH] Error creating graph:", err);
            throw err;
        }
    });

    // ===== File to base64 conversion handler =====
    ipcMain.handle("file-to-base64", async (event, { filePath }) => {
        try {
            if (!fs.existsSync(filePath)) {
                throw new Error("File not found: " + filePath);
            }
            const fileBuffer = fs.readFileSync(filePath);
            const base64 = fileBuffer.toString('base64');
            console.log(`[File] Converted to base64: ${filePath}, size: ${base64.length}`);
            return base64;
        } catch (err) {
            console.error("[File] Error converting to base64:", err);
            throw err;
        }
    });
}

module.exports = {
    setupOCRHandlers,
    runPython,
    findPythonPath,
    findScriptPath
};
