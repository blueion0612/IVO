// OCR results manager with stroke tracking
export class OCRManager {
    constructor(overlayRoot, showWarning, config) {
        this.overlayRoot = overlayRoot;
        this.showWarning = showWarning;
        this.config = config;
        this.results = [];
        this.container = null;
        this.lastMathExpr = null;
        this.hoveredElement = null;
        this.hoverStartTime = null;
        this.hoverDuration = config?.overlay?.hover_duration_ms || 700;
        this.onClearStrokes = null;
        this.onChangeStrokesColor = null;
        this.colorOptions = [
            { color: 'rgba(51, 51, 51, 0.9)', name: 'Black' },
            { color: 'rgba(211, 47, 47, 0.9)', name: 'Red' },
            { color: 'rgba(25, 118, 210, 0.9)', name: 'Blue' },
            { color: 'rgba(56, 142, 60, 0.9)', name: 'Green' }
        ];
        
        this.createContainer();
    }

    setOnClearStrokes(callback) {
        this.onClearStrokes = callback;
    }
    
    setOnChangeStrokesColor(callback) {
        this.onChangeStrokesColor = callback;
    }

    createContainer() {
        this.container = document.createElement("div");
        this.container.id = "ocr-results-container";
        this.container.style.cssText = `
            position: fixed;
            top: 80px;
            right: 90px;
            width: 380px;
            max-height: 80vh;
            padding: 0;
            overflow-y: auto;
            overflow-x: hidden;
            z-index: 9998;
            display: none;
            pointer-events: auto;
        `;

        const resultsList = document.createElement("div");
        resultsList.id = "ocr-results-list";
        resultsList.style.cssText = `
            display: flex;
            flex-direction: column;
            gap: 10px;
        `;

        this.container.appendChild(resultsList);
        document.body.appendChild(this.container);
    }

    checkHoverElements(cursorX, cursorY) {
        if (this.container.style.display === "none") return;

        const hoverableElements = this.container.querySelectorAll(".hoverable-btn");
        let isHovering = false;
        let currentHovered = null;

        hoverableElements.forEach((element) => {
            const rect = element.getBoundingClientRect();
            const progress = element.querySelector(".hover-progress");

            if (cursorX >= rect.left && cursorX <= rect.right &&
                cursorY >= rect.top && cursorY <= rect.bottom) {
                isHovering = true;
                currentHovered = element;

                if (this.hoveredElement !== currentHovered) {
                    this.hoveredElement = currentHovered;
                    this.hoverStartTime = Date.now();
                }

                const elapsed = Date.now() - this.hoverStartTime;
                const progressPercent = Math.min(100, (elapsed / this.hoverDuration) * 100);
                
                if (progress) {
                    progress.style.width = progressPercent + "%";
                }

                element.style.transform = "scale(1.08)";
                element.style.opacity = "1";

                if (elapsed >= this.hoverDuration) {
                    const action = element.dataset.action;
                    const resultItem = element.closest(".ocr-result-item");
                    
                    if (action === "calculate" && resultItem) {
                        this.evaluateExprInBox(resultItem);
                    } else if (action === "graph" && resultItem) {
                        this.drawGraphInline(resultItem);
                    } else if (action === "delete" && resultItem) {
                        this.removeResult(resultItem);
                    } else if (action === "clear-strokes" && resultItem) {
                        this.clearStrokesForResult(resultItem);
                    } else if (action === "scroll-up") {
                        this.container.scrollBy({ top: -100, behavior: 'smooth' });
                    } else if (action === "scroll-down") {
                        this.container.scrollBy({ top: 100, behavior: 'smooth' });
                    } else if (action === "clear-all") {
                        this.clearAll();
                    } else if (action?.startsWith("color-") && resultItem) {
                        const colorIndex = parseInt(action.split("-")[1]);
                        this.changeStrokesColor(resultItem, colorIndex);
                    }

                    this.hoverStartTime = Date.now();
                    if (progress) {
                        progress.style.width = "0%";
                    }
                }
            } else {
                if (progress) {
                    progress.style.width = "0%";
                }
                element.style.transform = "scale(1)";
                element.style.opacity = "0.9";
            }
        });

        if (!isHovering) {
            this.hoveredElement = null;
            this.hoverStartTime = null;
        }
    }

    createHoverableButton(text, action, bgColor, extraStyles = "") {
        const btn = document.createElement("button");
        btn.className = "hoverable-btn";
        btn.dataset.action = action;
        btn.style.cssText = `
            padding: 8px 14px;
            background: ${bgColor};
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            font-weight: bold;
            transition: all 0.2s;
            position: relative;
            overflow: hidden;
            opacity: 0.9;
            ${extraStyles}
        `;
        
        btn.innerHTML = `<span style="position: relative; z-index: 1;">${text}</span>`;
        
        const progress = document.createElement("div");
        progress.className = "hover-progress";
        progress.style.cssText = `
            position: absolute;
            bottom: 0;
            left: 0;
            width: 0%;
            height: 3px;
            background: rgba(255, 255, 255, 0.9);
            transition: width 0.1s linear;
        `;
        btn.appendChild(progress);
        
        return btn;
    }

    createColorButton(colorIndex) {
        const colorOption = this.colorOptions[colorIndex];
        const btn = document.createElement("button");
        btn.className = "hoverable-btn color-btn";
        btn.dataset.action = `color-${colorIndex}`;
        btn.style.cssText = `
            width: 28px;
            height: 28px;
            padding: 0;
            background: ${colorOption.color};
            border: 2px solid rgba(255,255,255,0.8);
            border-radius: 50%;
            cursor: pointer;
            transition: all 0.2s;
            position: relative;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        `;
        btn.title = colorOption.name;
        
        const progress = document.createElement("div");
        progress.className = "hover-progress";
        progress.style.cssText = `
            position: absolute;
            bottom: 0;
            left: 0;
            width: 0%;
            height: 100%;
            background: rgba(255, 255, 255, 0.4);
            transition: width 0.1s linear;
            border-radius: 50%;
        `;
        btn.appendChild(progress);
        
        return btn;
    }

    // ID-based stroke color change
    changeStrokesColor(resultItem, colorIndex) {
        const colorOption = this.colorOptions[colorIndex];

        // Change canvas stroke color by pathIds
        const pathIdsStr = resultItem.dataset.pathIds;
        if (pathIdsStr && this.onChangeStrokesColor) {
            const pathIds = JSON.parse(pathIdsStr);
            this.onChangeStrokesColor(pathIds, colorOption.color);
            console.log(`[OCR] Strokes color changed to ${colorOption.name}, IDs: [${pathIds.join(',')}]`);
        }

        // Also change text color
        const contentDiv = resultItem.querySelector('div[style*="word-wrap"]');
        if (contentDiv) {
            contentDiv.style.color = colorOption.color;
        }
    }

    // Add result (including pathIds)
    addResult(type, content, originalBounds, pathIds = null) {
        this.container.style.display = "block";
        const resultsList = document.getElementById("ocr-results-list");

        const resultItem = document.createElement("div");
        resultItem.className = "ocr-result-item";
        resultItem.dataset.type = type;

        if (originalBounds) {
            resultItem.dataset.bounds = JSON.stringify(originalBounds);
        }

        // Save path ID list
        if (pathIds && pathIds.length > 0) {
            resultItem.dataset.pathIds = JSON.stringify(pathIds);
        }
        
        resultItem.style.cssText = `
            padding: 14px;
            background: rgba(255, 255, 255, 0.92);
            backdrop-filter: blur(5px);
            border: 1px solid rgba(0, 0, 0, 0.15);
            border-radius: 10px;
            position: relative;
            box-shadow: 0 3px 8px rgba(0,0,0,0.12);
            transition: all 0.2s ease;
        `;

        // Header row
        const headerRow = document.createElement("div");
        headerRow.style.cssText = `
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 10px;
            padding-right: 30px;
        `;

        // Type label
        const typeLabel = document.createElement("div");
        typeLabel.style.cssText = `
            display: inline-block;
            padding: 3px 10px;
            background: ${type === 'text' ? '#4CAF50' : '#2196F3'};
            color: white;
            border-radius: 4px;
            font-size: 11px;
            font-weight: bold;
        `;
        typeLabel.textContent = type === 'text' ? 'TEXT' : 'MATH';

        // Color button container
        const colorContainer = document.createElement("div");
        colorContainer.style.cssText = `
            display: flex;
            gap: 6px;
            align-items: center;
        `;
        
        for (let i = 0; i < this.colorOptions.length; i++) {
            const colorBtn = this.createColorButton(i);
            colorContainer.appendChild(colorBtn);
        }

        headerRow.appendChild(typeLabel);
        headerRow.appendChild(colorContainer);

        // Content
        const contentDiv = document.createElement("div");
        contentDiv.style.cssText = `
            font-size: 14px;
            color: #333;
            word-wrap: break-word;
            line-height: 1.5;
            padding-right: 30px;
            transition: color 0.3s ease;
        `;

        if (type === 'math') {
            contentDiv.style.fontFamily = "'Courier New', monospace";
            contentDiv.style.background = "rgba(240, 240, 240, 0.5)";
            contentDiv.style.padding = "8px 10px";
            contentDiv.style.paddingRight = "35px";
            contentDiv.style.borderRadius = "5px";
            contentDiv.style.fontSize = "13px";
            contentDiv.textContent = content;
            resultItem.dataset.mathExpr = content;
            this.lastMathExpr = content;
        } else {
            contentDiv.textContent = content;
        }

        // Delete button
        const deleteBtn = this.createHoverableButton("×", "delete", 
            "rgba(200, 0, 0, 0.8)",
            `position: absolute;
             top: 10px;
             right: 10px;
             width: 26px;
             height: 26px;
             padding: 0;
             border-radius: 50%;
             font-size: 16px;
             display: flex;
             align-items: center;
             justify-content: center;`
        );

        resultItem.appendChild(headerRow);
        resultItem.appendChild(contentDiv);
        resultItem.appendChild(deleteBtn);

        // Button container
        const buttonContainer = document.createElement("div");
        buttonContainer.style.cssText = `
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 12px;
        `;

        // Clear Strokes 버튼
        const clearStrokesBtn = this.createHoverableButton("🧹 Clear Strokes", "clear-strokes",
            "linear-gradient(135deg, #9E9E9E, #757575)",
            "flex: 1; min-width: 100px;"
        );
        buttonContainer.appendChild(clearStrokesBtn);

        if (type === 'math') {
            const calcBtn = this.createHoverableButton("📊 Calc", "calculate",
                "linear-gradient(135deg, #4CAF50, #45a049)",
                "flex: 1;"
            );

            const graphBtn = this.createHoverableButton("📈 Graph", "graph",
                "linear-gradient(135deg, #FF9800, #F57C00)",
                "flex: 1;"
            );

            buttonContainer.appendChild(calcBtn);
            buttonContainer.appendChild(graphBtn);
            
            const resultDiv = document.createElement("div");
            resultDiv.className = 'calc-result';
            resultDiv.style.cssText = `
                margin-top: 12px;
                padding: 10px;
                background: linear-gradient(135deg, rgba(76, 175, 80, 0.15), rgba(76, 175, 80, 0.08));
                border-left: 4px solid #4CAF50;
                border-radius: 5px;
                font-weight: bold;
                color: #2e7d32;
                font-size: 18px;
                display: none;
            `;
            resultItem.appendChild(buttonContainer);
            resultItem.appendChild(resultDiv);

            const graphContainer = document.createElement("div");
            graphContainer.className = 'graph-container';
            graphContainer.style.cssText = `
                margin-top: 12px;
                display: none;
                border-radius: 8px;
                overflow: hidden;
                border: 1px solid rgba(0,0,0,0.1);
            `;
            resultItem.appendChild(graphContainer);
        } else {
            resultItem.appendChild(buttonContainer);
        }

        if (this.results.length === 0) {
            this.addScrollAndClearButtons(resultsList);
        }

        resultsList.appendChild(resultItem);
        this.results.push(resultItem);

        // Animation
        resultItem.style.opacity = "0";
        resultItem.style.transform = "translateX(50px)";
        setTimeout(() => {
            resultItem.style.transition = "all 0.3s ease";
            resultItem.style.opacity = "1";
            resultItem.style.transform = "translateX(0)";
        }, 10);

        // Auto scroll (to bottom)
        setTimeout(() => {
            this.container.scrollTop = this.container.scrollHeight;
        }, 50);
    }

    addScrollAndClearButtons(resultsList) {
        const controlContainer = document.createElement("div");
        controlContainer.id = "ocr-controls";
        controlContainer.style.cssText = `
            display: flex;
            gap: 8px;
            margin-bottom: 10px;
        `;

        const scrollUpBtn = this.createHoverableButton("⬆", "scroll-up",
            "rgba(100, 100, 100, 0.8)",
            "flex: 1; padding: 10px;"
        );

        const clearAllBtn = this.createHoverableButton("🗑️ Clear All", "clear-all",
            "rgba(244, 67, 54, 0.85)",
            "flex: 2; padding: 10px;"
        );

        const scrollDownBtn = this.createHoverableButton("⬇", "scroll-down",
            "rgba(100, 100, 100, 0.8)",
            "flex: 1; padding: 10px;"
        );

        controlContainer.appendChild(scrollUpBtn);
        controlContainer.appendChild(clearAllBtn);
        controlContainer.appendChild(scrollDownBtn);
        resultsList.insertBefore(controlContainer, resultsList.firstChild);
    }

    // ID-based stroke deletion
    clearStrokesForResult(resultItem) {
        const pathIdsStr = resultItem.dataset.pathIds;

        if (pathIdsStr && this.onClearStrokes) {
            const pathIds = JSON.parse(pathIdsStr);
            this.onClearStrokes(pathIds);
            console.log(`[OCR] Strokes cleared, IDs: [${pathIds.join(',')}]`);

            // Clear pathIds after deletion (prevent duplicate deletion)
            resultItem.dataset.pathIds = "[]";

            // Disable Clear Strokes button
            const clearBtn = resultItem.querySelector('[data-action="clear-strokes"]');
            if (clearBtn) {
                clearBtn.style.opacity = "0.4";
                clearBtn.style.pointerEvents = "none";
                const span = clearBtn.querySelector('span');
                if (span) span.textContent = "✓ Cleared";
            }
        }
    }

    removeResult(resultItem) {
        resultItem.style.transform = "translateX(400px)";
        resultItem.style.opacity = "0";
        setTimeout(() => {
            resultItem.remove();
            const index = this.results.indexOf(resultItem);
            if (index > -1) this.results.splice(index, 1);
            if (this.results.length === 0) {
                this.container.style.display = "none";
                const controls = document.getElementById("ocr-controls");
                if (controls) controls.remove();
            }
        }, 200);
    }

    clearAll() {
        console.log("[OCR] clearAll called, results count:", this.results.length);
        
        const items = [...this.results];
        items.forEach((item, index) => {
            setTimeout(() => {
                item.style.transform = "translateX(400px)";
                item.style.opacity = "0";
            }, index * 50);
        });

        setTimeout(() => {
            this.results = [];
            const resultsList = document.getElementById("ocr-results-list");
            if (resultsList) {
                resultsList.innerHTML = "";
            }
            this.container.style.display = "none";
            console.log("[OCR] All results cleared");
        }, items.length * 50 + 300);
    }

    async evaluateExprInBox(resultItem) {
        const expr = resultItem.dataset.mathExpr;
        if (!expr) return;

        try {
            console.log("[CALC] Calculating:", expr);

            let processedExpr = expr;
            if (processedExpr.startsWith("y=") || processedExpr.startsWith("y =")) {
                processedExpr = processedExpr.replace("y=", "").replace("y =", "").trim();
            }

            const { result } = await window.electronAPI.requestCalc(processedExpr);

            const resultDiv = resultItem.querySelector('.calc-result');
            if (resultDiv) {
                resultDiv.textContent = `= ${result}`;
                resultDiv.style.display = "block";

                resultDiv.style.opacity = "0";
                resultDiv.style.transform = "translateY(-10px)";
                setTimeout(() => {
                    resultDiv.style.transition = "all 0.3s ease";
                    resultDiv.style.opacity = "1";
                    resultDiv.style.transform = "translateY(0)";
                }, 10);
            }

            console.log("[CALC] Result:", result);
        } catch (err) {
            console.error("[CALC] Calculation error:", err);
            if (this.showWarning) this.showWarning("Calculation failed");
        }
    }

    async drawGraphInline(resultItem) {
        const expr = resultItem.dataset.mathExpr;
        if (!expr) {
            if (this.showWarning) this.showWarning("No formula to graph!");
            return;
        }

        const graphContainer = resultItem.querySelector('.graph-container');
        if (!graphContainer) return;

        if (graphContainer.style.display === "block") {
            graphContainer.style.display = "none";
            return;
        }

        try {
            console.log("[GRAPH] Drawing inline graph for:", expr);
            
            graphContainer.innerHTML = `
                <div style="padding: 20px; text-align: center; color: #666;">
                    <div style="font-size: 24px;">⏳</div>
                    <div style="margin-top: 8px; font-size: 12px;">Generating graph...</div>
                </div>
            `;
            graphContainer.style.display = "block";

            const { filePath } = await window.electronAPI.requestGraph(expr);
            const url = window.electronAPI.toFileUrl(filePath);

            graphContainer.innerHTML = `
                <div style="position: relative;">
                    <img src="${url}" style="width: 100%; border-radius: 6px;" alt="Graph of ${expr}">
                    <div style="
                        position: absolute;
                        top: 5px;
                        right: 5px;
                        background: rgba(0,0,0,0.6);
                        color: white;
                        padding: 4px 8px;
                        border-radius: 4px;
                        font-size: 10px;
                        cursor: pointer;
                    " onclick="this.parentElement.parentElement.style.display='none'">✕ Close</div>
                </div>
            `;

            console.log("[GRAPH] Inline graph displayed");
        } catch (err) {
            console.error("[GRAPH] Graph error:", err);
            graphContainer.innerHTML = `
                <div style="padding: 15px; text-align: center; color: #f44336;">
                    ❌ Graph creation failed
                </div>
            `;
            if (this.showWarning) this.showWarning("Graph creation failed");
        }
    }

    getLastMathExpr() {
        return this.lastMathExpr;
    }

    setLastMathExpr(expr) {
        this.lastMathExpr = expr;
    }
}
