// src/renderer/modules/canvas-drawing.js
// 캔버스 드로잉 기능 모듈 - 고유 ID 기반 궤적 관리

export class CanvasDrawing {
    constructor(canvas, config) {
        this.canvas = canvas;
        this.ctx = canvas.getContext("2d");
        this.config = config;
        
        // 상태
        this.paths = [];
        this.currentPath = null;
        this.lastPoint = null;
        this.inkBounds = null;
        this.lastMathExpr = null;
        
        // 고유 ID 카운터
        this.pathIdCounter = 0;
        
        // OCR 세션 관리
        this.ocrSessionActive = false;
        this.ocrSessionPathIds = [];  // 현재 세션에서 생성된 path ID 목록
        
        // OCR 세션 전용 오프스크린 캔버스 (레이어)
        this.sessionCanvas = null;
        this.sessionCtx = null;
        
        // 마우스 드로잉 상태
        this.isMouseDown = false;
        this.lastX = 0;
        this.lastY = 0;
        this.drawing = false;
        
        // 설정
        this.currentColor = config.overlay.default_color;
        this.currentLineWidth = config.overlay.line_width;
        this.isEraserMode = false;
        
        this.setupCanvas();
        this.setupMouseEvents();
    }

    // 고유 ID 생성
    generatePathId() {
        return ++this.pathIdCounter;
    }

    setupCanvas() {
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
        
        window.addEventListener("resize", () => {
            this.canvas.width = window.innerWidth;
            this.canvas.height = window.innerHeight;
            this.redrawAllPaths();
            
            if (this.sessionCanvas) {
                this.resizeSessionCanvas();
            }
        });
    }

    // ===== 세션 캔버스 관리 =====
    
    createSessionCanvas() {
        this.sessionCanvas = document.createElement('canvas');
        this.sessionCanvas.width = this.canvas.width;
        this.sessionCanvas.height = this.canvas.height;
        this.sessionCtx = this.sessionCanvas.getContext('2d');
        console.log("[Session Canvas] Created");
    }
    
    resizeSessionCanvas() {
        if (!this.sessionCanvas) return;
        this.sessionCanvas.width = this.canvas.width;
        this.sessionCanvas.height = this.canvas.height;
        this.redrawSessionPaths();
    }
    
    clearSessionCanvas() {
        if (this.sessionCtx) {
            this.sessionCtx.clearRect(0, 0, this.sessionCanvas.width, this.sessionCanvas.height);
        }
    }
    
    destroySessionCanvas() {
        this.sessionCanvas = null;
        this.sessionCtx = null;
    }

    drawToSessionCanvas(fromPoint, toPoint, color, lineWidth) {
        if (!this.sessionCtx) return;
        
        const canvasWidth = this.sessionCanvas.width;
        const canvasHeight = this.sessionCanvas.height;
        
        this.sessionCtx.strokeStyle = color;
        this.sessionCtx.lineWidth = lineWidth;
        this.sessionCtx.lineCap = "round";
        this.sessionCtx.lineJoin = "round";
        this.sessionCtx.beginPath();
        this.sessionCtx.moveTo(fromPoint.x * canvasWidth, fromPoint.y * canvasHeight);
        this.sessionCtx.lineTo(toPoint.x * canvasWidth, toPoint.y * canvasHeight);
        this.sessionCtx.stroke();
    }
    
    drawToSessionCanvasAbsolute(fromX, fromY, toX, toY, color, lineWidth) {
        if (!this.sessionCtx) return;
        
        this.sessionCtx.strokeStyle = color;
        this.sessionCtx.lineWidth = lineWidth;
        this.sessionCtx.lineCap = "round";
        this.sessionCtx.lineJoin = "round";
        this.sessionCtx.beginPath();
        this.sessionCtx.moveTo(fromX, fromY);
        this.sessionCtx.lineTo(toX, toY);
        this.sessionCtx.stroke();
    }
    
    redrawSessionPaths() {
        if (!this.sessionCtx) return;
        
        this.sessionCtx.clearRect(0, 0, this.sessionCanvas.width, this.sessionCanvas.height);
        
        const canvasWidth = this.sessionCanvas.width;
        const canvasHeight = this.sessionCanvas.height;
        
        // 현재 세션의 path ID에 해당하는 paths만 그리기
        const sessionPaths = this.paths.filter(p => this.ocrSessionPathIds.includes(p.id));
        
        for (const path of sessionPaths) {
            if (path.points.length < 2 || path.isEraser) continue;
            
            this.sessionCtx.strokeStyle = path.color;
            this.sessionCtx.lineWidth = path.lineWidth;
            this.sessionCtx.lineCap = "round";
            this.sessionCtx.lineJoin = "round";
            this.sessionCtx.beginPath();
            
            const firstPoint = path.points[0];
            if (path.isAbsolute) {
                this.sessionCtx.moveTo(firstPoint.x, firstPoint.y);
                for (let i = 1; i < path.points.length; i++) {
                    this.sessionCtx.lineTo(path.points[i].x, path.points[i].y);
                }
            } else {
                this.sessionCtx.moveTo(firstPoint.x * canvasWidth, firstPoint.y * canvasHeight);
                for (let i = 1; i < path.points.length; i++) {
                    const point = path.points[i];
                    this.sessionCtx.lineTo(point.x * canvasWidth, point.y * canvasHeight);
                }
            }
            
            this.sessionCtx.stroke();
        }
    }

    getSessionCanvasDataURL(bounds) {
        if (!this.sessionCanvas || !bounds) {
            console.warn("[Session Canvas] No session canvas or bounds");
            return null;
        }
        
        const padding = 15;
        const x = Math.max(Math.floor(bounds.xMin - padding), 0);
        const y = Math.max(Math.floor(bounds.yMin - padding), 0);
        const width = Math.min(
            Math.ceil(bounds.xMax - bounds.xMin + padding * 2),
            this.sessionCanvas.width - x
        );
        const height = Math.min(
            Math.ceil(bounds.yMax - bounds.yMin + padding * 2),
            this.sessionCanvas.height - y
        );
        
        const tempCanvas = document.createElement('canvas');
        tempCanvas.width = width;
        tempCanvas.height = height;
        const tempCtx = tempCanvas.getContext('2d');
        
        tempCtx.fillStyle = 'white';
        tempCtx.fillRect(0, 0, width, height);
        
        tempCtx.drawImage(
            this.sessionCanvas,
            x, y, width, height,
            0, 0, width, height
        );
        
        console.log(`[Session Canvas] Captured region: ${x},${y} ${width}x${height}`);
        return tempCanvas.toDataURL('image/png');
    }

    setupMouseEvents() {
        let currentMousePath = null;
        
        this.canvas.addEventListener("mousedown", (e) => {
            if (this.drawing) {
                this.isMouseDown = true;
                this.lastX = e.offsetX;
                this.lastY = e.offsetY;
                this.updateInkBounds(e.offsetX, e.offsetY);
                
                const pathId = this.generatePathId();
                currentMousePath = {
                    id: pathId,
                    points: [{ x: e.offsetX, y: e.offsetY }],
                    color: this.currentColor,
                    lineWidth: this.currentLineWidth,
                    isAbsolute: true,
                    isEraser: this.isEraserMode
                };
                
                // 세션 중이면 ID 기록
                if (this.ocrSessionActive) {
                    this.ocrSessionPathIds.push(pathId);
                }
            }
        });

        this.canvas.addEventListener("mouseup", () => {
            this.isMouseDown = false;
            
            if (currentMousePath && currentMousePath.points.length > 1 && !currentMousePath.isEraser) {
                this.paths.push(currentMousePath);
            }
            currentMousePath = null;
        });

        this.canvas.addEventListener("mousemove", (e) => {
            if (this.drawing && this.isMouseDown) {
                if (this.isEraserMode) {
                    this.ctx.save();
                    this.ctx.globalCompositeOperation = "destination-out";
                    this.ctx.lineWidth = 20;
                    this.ctx.lineCap = "round";
                    this.ctx.beginPath();
                    this.ctx.moveTo(this.lastX, this.lastY);
                    this.ctx.lineTo(e.offsetX, e.offsetY);
                    this.ctx.stroke();
                    this.ctx.restore();
                } else {
                    this.ctx.strokeStyle = this.currentColor;
                    this.ctx.lineWidth = this.currentLineWidth;
                    this.ctx.lineCap = "round";
                    this.ctx.beginPath();
                    this.ctx.moveTo(this.lastX, this.lastY);
                    this.ctx.lineTo(e.offsetX, e.offsetY);
                    this.ctx.stroke();
                    
                    if (currentMousePath) {
                        currentMousePath.points.push({ x: e.offsetX, y: e.offsetY });
                    }
                    
                    if (this.ocrSessionActive && this.sessionCtx) {
                        this.drawToSessionCanvasAbsolute(
                            this.lastX, this.lastY,
                            e.offsetX, e.offsetY,
                            this.currentColor, this.currentLineWidth
                        );
                    }
                }
                
                this.lastX = e.offsetX;
                this.lastY = e.offsetY;
                this.updateInkBounds(e.offsetX, e.offsetY);
            }
        });
    }

    // ===== OCR 세션 관리 =====

    startOCRSession() {
        this.ocrSessionActive = true;
        this.ocrSessionPathIds = [];  // 새 세션 시작 시 ID 목록 초기화
        
        this.createSessionCanvas();
        
        console.log("[OCR Session] Started");
        return true;
    }

    endOCRSession() {
        this.ocrSessionActive = false;
        console.log(`[OCR Session] Ended, path IDs: [${this.ocrSessionPathIds.join(', ')}]`);
    }

    isOCRSessionActive() {
        return this.ocrSessionActive;
    }
    
    // 현재 세션의 path ID 목록 반환
    getSessionPathIds() {
        return [...this.ocrSessionPathIds];  // 복사본 반환
    }

    // 세션 paths의 bounds 계산
    getSessionBounds() {
        const sessionPaths = this.paths.filter(p => this.ocrSessionPathIds.includes(p.id));
        
        if (sessionPaths.length === 0) {
            return null;
        }
        
        let minX = Infinity, minY = Infinity;
        let maxX = -Infinity, maxY = -Infinity;
        
        const canvasWidth = this.canvas.width;
        const canvasHeight = this.canvas.height;
        
        for (const path of sessionPaths) {
            for (const point of path.points) {
                let x, y;
                if (path.isAbsolute) {
                    x = point.x;
                    y = point.y;
                } else {
                    x = point.x * canvasWidth;
                    y = point.y * canvasHeight;
                }
                minX = Math.min(minX, x);
                minY = Math.min(minY, y);
                maxX = Math.max(maxX, x);
                maxY = Math.max(maxY, y);
            }
        }

        if (minX === Infinity) {
            return null;
        }

        return { xMin: minX, yMin: minY, xMax: maxX, yMax: maxY };
    }

    // ===== ID 기반 궤적 색상 변경 =====
    changePathsColorByIds(pathIds, newColor) {
        if (!pathIds || pathIds.length === 0) return 0;
        
        let changed = 0;
        for (const path of this.paths) {
            if (pathIds.includes(path.id) && !path.isEraser) {
                path.color = newColor;
                changed++;
            }
        }
        
        if (changed > 0) {
            this.redrawAllPaths();
            console.log(`[Canvas] Changed color for ${changed} paths (IDs: ${pathIds.join(',')}) to ${newColor}`);
        }
        
        return changed;
    }

    // ===== ID 기반 궤적 삭제 =====
    clearPathsByIds(pathIds) {
        if (!pathIds || pathIds.length === 0) return 0;
        
        const beforeCount = this.paths.length;
        this.paths = this.paths.filter(p => !pathIds.includes(p.id));
        const removedCount = beforeCount - this.paths.length;
        
        if (removedCount > 0) {
            this.redrawAllPaths();
            console.log(`[Canvas] Removed ${removedCount} paths (IDs: ${pathIds.join(',')})`);
        }
        
        return removedCount;
    }

    // 현재 세션 궤적만 지우기 (세션 중 취소용)
    clearSessionPaths() {
        this.clearPathsByIds(this.ocrSessionPathIds);
        this.ocrSessionPathIds = [];
        
        this.clearSessionCanvas();
        this.destroySessionCanvas();
        
        this.ocrSessionActive = false;
    }
    
    finalizeSession() {
        this.destroySessionCanvas();
    }

    // ===== Hand Drawing 관련 =====

    startNewPath(point) {
        if (!point) return;
        
        const pathId = this.generatePathId();
        
        this.currentPath = {
            id: pathId,
            points: [point],
            color: this.isEraserMode ? null : this.currentColor,
            lineWidth: this.isEraserMode ? 20 : this.currentLineWidth,
            isEraser: this.isEraserMode,
            isAbsolute: false
        };
        
        // 세션 중이면 ID 기록
        if (this.ocrSessionActive && !this.isEraserMode) {
            this.ocrSessionPathIds.push(pathId);
        }
        
        this.lastPoint = point;
    }

    addPointToPath(point) {
        if (!this.currentPath || !point) return;
        
        this.currentPath.points.push(point);
        const canvasWidth = this.canvas.width;
        const canvasHeight = this.canvas.height;
        
        if (this.currentPath.isEraser) {
            this.ctx.save();
            this.ctx.globalCompositeOperation = "destination-out";
            this.ctx.lineWidth = this.currentPath.lineWidth;
            this.ctx.lineCap = "round";
            this.ctx.lineJoin = "round";
            this.ctx.beginPath();
            
            if (this.lastPoint) {
                this.ctx.moveTo(this.lastPoint.x * canvasWidth, this.lastPoint.y * canvasHeight);
                this.ctx.lineTo(point.x * canvasWidth, point.y * canvasHeight);
                this.ctx.stroke();
            }
            this.ctx.restore();
        } else {
            this.ctx.strokeStyle = this.currentPath.color;
            this.ctx.lineWidth = this.currentPath.lineWidth;
            this.ctx.lineCap = "round";
            this.ctx.lineJoin = "round";
            this.ctx.beginPath();
            
            if (this.lastPoint) {
                this.ctx.moveTo(this.lastPoint.x * canvasWidth, this.lastPoint.y * canvasHeight);
                this.ctx.lineTo(point.x * canvasWidth, point.y * canvasHeight);
                this.ctx.stroke();
            }
            
            if (this.ocrSessionActive && this.lastPoint) {
                this.drawToSessionCanvas(
                    this.lastPoint, point,
                    this.currentPath.color, this.currentPath.lineWidth
                );
            }
        }
        
        this.lastPoint = point;
    }

    endCurrentPath() {
        if (!this.currentPath || this.currentPath.points.length === 0) return;
        
        if (!this.currentPath.isEraser) {
            this.paths.push(this.currentPath);
        }
        
        this.currentPath = null;
        this.lastPoint = null;
    }

    redrawAllPaths() {
        const canvasWidth = this.canvas.width;
        const canvasHeight = this.canvas.height;
        
        this.ctx.clearRect(0, 0, canvasWidth, canvasHeight);
        
        for (const path of this.paths) {
            if (path.points.length < 2 || path.isEraser) continue;
            
            this.ctx.strokeStyle = path.color;
            this.ctx.lineWidth = path.lineWidth;
            this.ctx.lineCap = "round";
            this.ctx.lineJoin = "round";
            this.ctx.beginPath();
            
            const firstPoint = path.points[0];
            
            if (path.isAbsolute) {
                this.ctx.moveTo(firstPoint.x, firstPoint.y);
                for (let i = 1; i < path.points.length; i++) {
                    this.ctx.lineTo(path.points[i].x, path.points[i].y);
                }
            } else {
                this.ctx.moveTo(firstPoint.x * canvasWidth, firstPoint.y * canvasHeight);
                for (let i = 1; i < path.points.length; i++) {
                    const point = path.points[i];
                    this.ctx.lineTo(point.x * canvasWidth, point.y * canvasHeight);
                }
            }
            
            this.ctx.stroke();
        }
    }

    // ===== Ink Bounds =====

    updateInkBounds(x, y) {
        if (!this.inkBounds) {
            this.inkBounds = { xMin: x, yMin: y, xMax: x, yMax: y };
        } else {
            if (x < this.inkBounds.xMin) this.inkBounds.xMin = x;
            if (y < this.inkBounds.yMin) this.inkBounds.yMin = y;
            if (x > this.inkBounds.xMax) this.inkBounds.xMax = x;
            if (y > this.inkBounds.yMax) this.inkBounds.yMax = y;
        }
    }

    clearCurrentInk() {
        if (!this.inkBounds) return;
        const pad = 10;
        const x = Math.max(0, this.inkBounds.xMin - pad);
        const y = Math.max(0, this.inkBounds.yMin - pad);
        const w = Math.min(this.canvas.width - x, (this.inkBounds.xMax - this.inkBounds.xMin) + pad * 2);
        const h = Math.min(this.canvas.height - y, (this.inkBounds.yMax - this.inkBounds.yMin) + pad * 2);
        this.ctx.clearRect(x, y, w, h);
    }

    getCaptureRect() {
        if (!this.inkBounds) return null;
        const margin = 10;
        const x = Math.max(this.inkBounds.xMin - margin, 0);
        const y = Math.max(this.inkBounds.yMin - margin, 0);
        const width = Math.min(this.inkBounds.xMax - this.inkBounds.xMin + 2 * margin, window.innerWidth - x);
        const height = Math.min(this.inkBounds.yMax - this.inkBounds.yMin + 2 * margin, window.innerHeight - y);
        return { x: Math.floor(x), y: Math.floor(y), width: Math.ceil(width), height: Math.ceil(height) };
    }

    getAllBounds() {
        if (this.inkBounds) {
            return this.inkBounds;
        }
        
        if (this.paths && this.paths.length > 0) {
            let minX = Infinity, minY = Infinity;
            let maxX = -Infinity, maxY = -Infinity;
            
            const canvasWidth = this.canvas.width;
            const canvasHeight = this.canvas.height;
            
            for (const path of this.paths) {
                for (const point of path.points) {
                    let x, y;
                    if (path.isAbsolute) {
                        x = point.x;
                        y = point.y;
                    } else {
                        x = point.x * canvasWidth;
                        y = point.y * canvasHeight;
                    }
                    minX = Math.min(minX, x);
                    minY = Math.min(minY, y);
                    maxX = Math.max(maxX, x);
                    maxY = Math.max(maxY, y);
                }
            }
            
            if (minX !== Infinity) {
                return { xMin: minX, yMin: minY, xMax: maxX, yMax: maxY };
            }
        }
        
        const imageData = this.ctx.getImageData(0, 0, this.canvas.width, this.canvas.height);
        const data = imageData.data;
        
        for (let i = 3; i < data.length; i += 4) {
            if (data[i] > 0) {
                return { xMin: 0, yMin: 0, xMax: this.canvas.width, yMax: this.canvas.height };
            }
        }
        
        return null;
    }

    // ===== 설정 변경 =====

    setColor(color) {
        this.currentColor = color;
        this.isEraserMode = false;
    }

    setEraserMode(enabled) {
        this.isEraserMode = enabled;
    }

    setDrawingMode(enabled) {
        this.drawing = enabled;
    }

    // ===== Clear =====

    clear() {
        this.paths = [];
        this.currentPath = null;
        this.lastPoint = null;
        this.inkBounds = null;
        this.lastMathExpr = null;
        this.ocrSessionActive = false;
        this.ocrSessionPathIds = [];
        this.destroySessionCanvas();
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    }

    clearPaths() {
        this.paths = [];
        this.ocrSessionPathIds = [];
        this.redrawAllPaths();
    }
}
