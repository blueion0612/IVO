// Preload script - Electron context bridge
const { contextBridge, ipcRenderer } = require("electron");

function toFileUrl(filePath) {
    if (process.platform === "win32") {
        return "file:///" + filePath.replace(/\\/g, "/");
    }
    return "file://" + filePath;
}

contextBridge.exposeInMainWorld("electronAPI", {
    onCmd: (callback) => ipcRenderer.on("cmd", (event, data) => callback(data)),
    sendToHandTracker: (command) => ipcRenderer.invoke("send-to-handtracker", command),
    requestOCR: (mode, bbox) => ipcRenderer.invoke("do-ocr", { mode, bbox }),
    requestOCRWithImage: (mode, dataURL) => ipcRenderer.invoke("do-ocr-with-image", { mode, dataURL }),
    requestCalc: (expr) => ipcRenderer.invoke("do-calc", { expr }),
    requestGraph: (expr) => ipcRenderer.invoke("do-graph", { expr }),
    requestMathOp: (op, latex) => ipcRenderer.invoke("math-op", { op, latex }),
    toFileUrl: (filePath) => toFileUrl(filePath),
    fileToBase64: async (filePath) => {
        try {
            const base64 = await ipcRenderer.invoke("file-to-base64", { filePath });
            return `data:image/png;base64,${base64}`;
        } catch (err) {
            console.error("[fileToBase64] Error:", err);
            return null;
        }
    },
});
