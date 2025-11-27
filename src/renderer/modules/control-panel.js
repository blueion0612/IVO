// src/renderer/modules/control-panel.js
// Control panel module - Color palette and tool selection

export class ControlPanel {
    constructor(config, onAction) {
        this.config = config;
        this.onAction = onAction;
        
        this.hoveredElement = null;
        this.hoverStartTime = null;
        this.hoverDuration = config.overlay.hover_duration_ms;
        this.currentLineWidth = config.overlay.line_width;
        
        this.createPanel();
    }

    createPanel() {
        this.panel = document.createElement("div");
        this.panel.id = "control-panel";
        this.panel.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            display: none;
            flex-direction: column;
            gap: 12px;
            z-index: 10001;
            padding: 10px;
            background: rgba(0, 0, 0, 0.3);
            border-radius: 12px;
        `;
        
        const controlItems = this.config.colors.control_panel;
        
        controlItems.forEach((item, index) => {
            if (item.type === "divider") {
                const divider = document.createElement("div");
                divider.style.cssText = `
                    width: 100%;
                    height: 2px;
                    background: rgba(255, 255, 255, 0.3);
                    margin: 4px 0;
                `;
                this.panel.appendChild(divider);
                return;
            }
            
            const element = document.createElement("div");
            element.className = "control-item";
            element.dataset.index = index;
            element.dataset.type = item.type;
            element.dataset.action = item.action || '';
            element.dataset.color = item.color || '';
            element.dataset.width = item.width || '';
            
            // Common style (size increased: 36px -> 48px)
            const baseStyle = `
                width: 48px;
                height: 48px;
                border-radius: 8px;
                border: 3px solid rgba(255, 255, 255, 0.4);
                cursor: pointer;
                transition: all 0.3s ease;
                position: relative;
                overflow: hidden;
                display: flex;
                align-items: center;
                justify-content: center;
            `;
            
            if (item.type === "color") {
                element.style.cssText = baseStyle + `
                    background: ${item.color};
                `;
            } else if (item.type === "linewidth") {
                // Line width selection button
                element.style.cssText = baseStyle + `
                    background: rgba(80, 80, 80, 0.9);
                    flex-direction: column;
                `;

                // Line preview showing thickness
                const linePreview = document.createElement("div");
                linePreview.style.cssText = `
                    width: 30px;
                    height: ${item.width}px;
                    background: white;
                    border-radius: ${item.width / 2}px;
                `;
                element.appendChild(linePreview);
                
                element.title = item.title || `${item.width}px`;
            } else {
                element.style.cssText = baseStyle + `
                    background: rgba(50, 50, 50, 0.9);
                    color: white;
                    font-family: Arial, sans-serif;
                    font-size: ${item.name.length > 4 ? '11px' : '14px'};
                    font-weight: bold;
                `;
                
                const textSpan = document.createElement("span");
                textSpan.innerText = item.name;
                element.appendChild(textSpan);
                element.title = item.title || item.name;
            }
            
            // Hover progress bar
            const progress = document.createElement("div");
            progress.className = "hover-progress";
            progress.style.cssText = `
                position: absolute;
                bottom: 0;
                left: 0;
                width: 0%;
                height: 4px;
                background: ${item.type === 'color' ? 'rgba(255,255,255,0.9)' : 'rgba(100,200,255,0.9)'};
                transition: width 0.1s linear;
            `;
            element.appendChild(progress);
            this.panel.appendChild(element);
        });
        
        document.body.appendChild(this.panel);
    }

    show() {
        this.panel.style.display = "flex";
    }

    hide() {
        this.panel.style.display = "none";
    }

    checkHover(cursorX, cursorY) {
        const allItems = this.panel.querySelectorAll(".control-item");
        let isHovering = false;
        let currentHovered = null;

        allItems.forEach((item) => {
            const rect = item.getBoundingClientRect();
            const progress = item.querySelector(".hover-progress");
            if (!progress) return;

            // Add padding for easier targeting
            const padding = 2;
            if (cursorX >= rect.left + padding && cursorX <= rect.right - padding &&
                cursorY >= rect.top + padding && cursorY <= rect.bottom - padding) {
                isHovering = true;
                currentHovered = item;

                if (this.hoveredElement !== currentHovered) {
                    this.hoveredElement = currentHovered;
                    this.hoverStartTime = Date.now();
                }

                const elapsed = Date.now() - this.hoverStartTime;
                const progressPercent = Math.min(100, (elapsed / this.hoverDuration) * 100);
                progress.style.width = progressPercent + "%";

                item.style.transform = "scale(1.12)";
                item.style.borderColor = "rgba(255, 255, 255, 0.9)";

                if (elapsed >= this.hoverDuration) {
                    // Execute action
                    if (item.dataset.type === "color") {
                        if (this.onAction) {
                            this.onAction("COLOR_SELECT", { color: item.dataset.color });
                        }
                    } else if (item.dataset.type === "linewidth") {
                        if (this.onAction) {
                            this.onAction("LINEWIDTH_SELECT", { width: parseInt(item.dataset.width) });
                        }
                        // Show currently selected line width
                        this.updateLineWidthSelection(item);
                    } else if (item.dataset.type === "function") {
                        if (this.onAction) {
                            this.onAction(item.dataset.action);
                        }
                    }

                    this.hoverStartTime = Date.now();
                    progress.style.width = "0%";
                }
            } else {
                progress.style.width = "0%";
                item.style.transform = "scale(1)";
                item.style.borderColor = "rgba(255, 255, 255, 0.4)";
            }
        });

        if (!isHovering) {
            this.hoveredElement = null;
            this.hoverStartTime = null;
        }
    }

    updateLineWidthSelection(selectedItem) {
        // Remove selection highlight from all line width items
        const allItems = this.panel.querySelectorAll('.control-item[data-type="linewidth"]');
        allItems.forEach(item => {
            item.style.boxShadow = "none";
        });
        // Highlight selected item
        selectedItem.style.boxShadow = "0 0 0 3px rgba(100, 200, 255, 0.8)";
    }
}
