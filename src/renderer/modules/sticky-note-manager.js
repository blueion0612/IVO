// src/renderer/modules/sticky-note-manager.js
// Sticky Note Manager - Voice-to-text sticky notes with dictionary lookup

export class StickyNoteManager {
    constructor(config) {
        this.config = config;
        this.notes = [];
        this.noteIdCounter = 0;
        this.isActive = false;

        // Recording state
        this.isRecording = false;
        this.addButton = null;

        // Drag state
        this.draggedNote = null;
        this.dragOffset = { x: 0, y: 0 };
        this.isDragging = false;

        // Hover-dwell state
        this.currentHoverElement = null;
        this.hoverTimer = null;
        this.hoverProgressElement = null;
        this.hoverProgressParent = null;
        this.hoverDuration = config.overlay.hover_duration_ms || 700;

        // Default sticky note color (Yellow)
        this.defaultColor = { name: "Yellow", bg: "rgba(255, 235, 59, 0.95)", border: "#FBC02D" };

        // Callbacks
        this.onStartRecording = null;
        this.onStopRecording = null;
        this.onHapticFeedback = null;
        this.onVocabLookup = null;

        // Active definition popup reference
        this.activeDefinitionPopup = null;
        this.activeDefinitionNote = null;
        this.definitionPages = [];
        this.currentDefinitionPage = 0;

        this.createContainer();
        this.createAddButton();
    }

    createContainer() {
        this.container = document.createElement("div");
        this.container.id = "sticky-note-container";
        this.container.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 9990;
            display: none;
        `;

        // Add styles
        const style = document.createElement("style");
        style.textContent = `
            .sticky-note {
                position: absolute;
                min-width: 240px;
                max-width: 400px;
                padding: 16px;
                border-radius: 10px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.2);
                cursor: grab;
                pointer-events: auto;
                user-select: none;
                transition: transform 0.1s ease, box-shadow 0.2s ease;
            }

            .sticky-note:hover {
                box-shadow: 0 6px 20px rgba(0,0,0,0.3);
            }

            .sticky-note.dragging {
                cursor: grabbing;
                transform: scale(1.05);
                box-shadow: 0 8px 25px rgba(0,0,0,0.35);
                z-index: 10001;
            }

            .sticky-note-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 8px;
                padding-bottom: 6px;
                border-bottom: 1px solid rgba(0,0,0,0.1);
                gap: 8px;
            }

            .sticky-note-time {
                font-size: 10px;
                color: rgba(0,0,0,0.5);
                flex: 1;
                text-align: center;
            }

            .sticky-note-btn {
                width: 36px;
                height: 36px;
                border: none;
                border-radius: 50%;
                cursor: pointer;
                font-size: 18px;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: transform 0.15s ease, opacity 0.15s ease;
                opacity: 0.8;
            }

            .sticky-note-btn:hover {
                transform: scale(1.15);
                opacity: 1;
            }

            .sticky-note-btn.dict-btn {
                background: rgba(33, 150, 243, 0.8);
                color: white;
            }

            .sticky-note-btn.delete-btn {
                background: rgba(244, 67, 54, 0.8);
                color: white;
            }

            .sticky-note-content {
                font-size: 16px;
                line-height: 1.6;
                color: #333;
                word-break: keep-all;
                white-space: pre-wrap;
            }

            .sticky-note-add-btn {
                position: fixed;
                top: 80px;
                right: 20px;
                width: 50px;
                height: 50px;
                border-radius: 50%;
                border: none;
                font-size: 28px;
                cursor: pointer;
                pointer-events: auto;
                transition: all 0.3s ease;
                box-shadow: 0 4px 15px rgba(0,0,0,0.2);
                z-index: 9995;
            }

            .sticky-note-add-btn.add-mode {
                background: linear-gradient(135deg, #4CAF50, #8BC34A);
                color: white;
            }

            .sticky-note-add-btn.recording-mode {
                background: linear-gradient(135deg, #f44336, #E91E63);
                color: white;
                animation: pulseRecord 1s infinite;
            }

            @keyframes pulseRecord {
                0%, 100% { transform: scale(1); box-shadow: 0 4px 15px rgba(244, 67, 54, 0.3); }
                50% { transform: scale(1.05); box-shadow: 0 4px 25px rgba(244, 67, 54, 0.5); }
            }

            .sticky-note-add-btn:hover {
                transform: scale(1.1);
            }

            .hover-progress-sticky {
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                border-radius: 50%;
                border: 3px solid transparent;
                border-top-color: white;
                pointer-events: none;
                animation: hoverSpin 0.7s linear forwards;
            }

            @keyframes hoverSpin {
                0% { transform: rotate(0deg); border-top-color: rgba(255,255,255,0.5); }
                100% { transform: rotate(360deg); border-top-color: white; }
            }

            @keyframes stickySlideIn {
                from {
                    opacity: 0;
                    transform: scale(0.8) translateY(-20px);
                }
                to {
                    opacity: 1;
                    transform: scale(1) translateY(0);
                }
            }

            @keyframes stickyFadeOut {
                from {
                    opacity: 1;
                    transform: scale(1);
                }
                to {
                    opacity: 0;
                    transform: scale(0.8);
                }
            }

            .definition-popup {
                position: absolute;
                min-width: 280px;
                max-width: 400px;
                padding: 14px;
                padding-top: 40px;
                background: linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(240, 248, 255, 0.95));
                border: 2px solid #2196F3;
                border-radius: 10px;
                box-shadow: 0 6px 20px rgba(33, 150, 243, 0.3);
                z-index: 10002;
                pointer-events: auto;
                animation: stickySlideIn 0.2s ease-out;
            }

            .definition-content {
                min-height: 100px;
            }

            .definition-page-controls {
                position: absolute;
                top: 10px;
                left: 50%;
                transform: translateX(-50%);
                display: flex;
                align-items: center;
                gap: 10px;
            }

            .definition-page-btn {
                width: 32px;
                height: 28px;
                border: none;
                border-radius: 6px;
                background: rgba(33, 150, 243, 0.8);
                color: white;
                font-size: 14px;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                opacity: 0.9;
                transition: opacity 0.15s ease, transform 0.15s ease;
            }

            .definition-page-btn:hover {
                opacity: 1;
                transform: scale(1.1);
            }

            .definition-page-btn:disabled {
                opacity: 0.3;
                cursor: not-allowed;
                transform: none;
            }

            .definition-page-indicator {
                font-size: 12px;
                color: #1976D2;
                font-weight: 600;
                min-width: 50px;
                text-align: center;
            }

            .definition-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
                padding-bottom: 8px;
                border-bottom: 1px solid rgba(33, 150, 243, 0.3);
            }

            .definition-word {
                font-size: 16px;
                font-weight: 700;
                color: #1565C0;
            }

            .definition-lang {
                font-size: 10px;
                padding: 2px 6px;
                background: rgba(33, 150, 243, 0.2);
                border-radius: 4px;
                color: #1976D2;
            }

            .definition-list {
                list-style: none;
                padding: 0;
                margin: 0;
            }

            .definition-item {
                font-size: 13px;
                line-height: 1.5;
                color: #333;
                padding: 6px 0;
                border-bottom: 1px dashed rgba(0,0,0,0.1);
            }

            .definition-item:last-child {
                border-bottom: none;
            }

            .definition-error {
                font-size: 13px;
                color: #f44336;
                font-style: italic;
            }

            .definition-loading {
                font-size: 13px;
                color: #666;
                display: flex;
                align-items: center;
                gap: 8px;
            }

            .definition-loading::before {
                content: "";
                width: 16px;
                height: 16px;
                border: 2px solid #2196F3;
                border-top-color: transparent;
                border-radius: 50%;
                animation: spin 1s linear infinite;
            }

            @keyframes spin {
                to { transform: rotate(360deg); }
            }

            .definition-close-btn {
                position: absolute;
                top: 8px;
                right: 8px;
                width: 20px;
                height: 20px;
                border: none;
                border-radius: 50%;
                background: rgba(244, 67, 54, 0.8);
                color: white;
                font-size: 12px;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                opacity: 0.7;
                transition: opacity 0.15s ease;
            }

            .definition-close-btn:hover {
                opacity: 1;
            }
        `;
        document.head.appendChild(style);
        document.body.appendChild(this.container);
    }

    createAddButton() {
        this.addButton = document.createElement("button");
        this.addButton.id = "sticky-add-btn";
        this.addButton.innerHTML = "+";
        // Use inline styles for reliable positioning
        this.updateAddButtonStyle(false);
        this.addButton.style.display = "none";

        // Click handler for mouse
        this.addButton.addEventListener("click", () => {
            this.toggleRecording();
        });

        // Add to document.body directly so fixed positioning works correctly
        document.body.appendChild(this.addButton);
    }

    updateAddButtonStyle(isRecording) {
        // Set individual style properties to preserve display state
        this.addButton.style.position = "fixed";
        this.addButton.style.top = "150px";  // Move down to avoid overlay notifications
        this.addButton.style.right = "20px";
        this.addButton.style.left = "auto";  // Explicitly set to avoid left positioning
        this.addButton.style.width = "50px";
        this.addButton.style.height = "50px";
        this.addButton.style.borderRadius = "50%";
        this.addButton.style.border = "none";
        this.addButton.style.fontSize = "28px";
        this.addButton.style.cursor = "pointer";
        this.addButton.style.pointerEvents = "auto";
        this.addButton.style.transition = "all 0.3s ease";
        this.addButton.style.boxShadow = "0 4px 15px rgba(0,0,0,0.2)";
        this.addButton.style.zIndex = "9995";
        this.addButton.style.color = "white";

        if (isRecording) {
            this.addButton.style.background = "linear-gradient(135deg, #f44336, #E91E63)";
            this.addButton.style.animation = "pulseRecord 1s infinite";
        } else {
            this.addButton.style.background = "linear-gradient(135deg, #4CAF50, #8BC34A)";
            this.addButton.style.animation = "none";
        }
    }

    toggleRecording() {
        if (this.isRecording) {
            this.stopRecording();
        } else {
            this.startRecording();
        }
    }

    startRecording() {
        this.isRecording = true;
        this.addButton.innerHTML = "×";
        this.updateAddButtonStyle(true);

        if (this.onStartRecording) {
            this.onStartRecording();
        }
        if (this.onHapticFeedback) {
            this.onHapticFeedback("recording_toggle");
        }

        console.log("[StickyNote] Recording started");
    }

    stopRecording() {
        this.isRecording = false;
        this.addButton.innerHTML = "+";
        this.updateAddButtonStyle(false);

        if (this.onStopRecording) {
            this.onStopRecording();
        }
        if (this.onHapticFeedback) {
            this.onHapticFeedback("recording_toggle");
        }

        console.log("[StickyNote] Recording stopped");
    }

    // Add note from STT transcription
    addNote(text, position = null) {
        if (!text || !text.trim()) {
            console.log("[StickyNote] Empty text, skipping");
            return null;
        }

        const id = ++this.noteIdCounter;

        // Default position: near the + button or random
        const pos = position || {
            x: 100 + (this.notes.length % 5) * 50,
            y: 150 + Math.floor(this.notes.length / 5) * 50
        };

        const timestamp = new Date().toLocaleTimeString('ko-KR', {
            hour: '2-digit',
            minute: '2-digit'
        });

        const note = {
            id,
            text: text.trim(),
            color: this.defaultColor,
            position: pos,
            timestamp,
            element: null,
            definitionPopup: null
        };

        this.notes.push(note);
        this.renderNote(note);

        console.log(`[StickyNote] Added note #${id}: ${text.substring(0, 30)}...`);
        return note;
    }

    renderNote(note) {
        const noteEl = document.createElement("div");
        noteEl.className = "sticky-note";
        noteEl.dataset.id = note.id;
        noteEl.style.cssText = `
            left: ${note.position.x}px;
            top: ${note.position.y}px;
            background: ${note.color.bg};
            border: 2px solid ${note.color.border};
            animation: stickySlideIn 0.3s ease-out;
        `;

        // Header
        const header = document.createElement("div");
        header.className = "sticky-note-header";

        // Left side: Dictionary button
        const dictBtn = document.createElement("button");
        dictBtn.className = "sticky-note-btn dict-btn";
        dictBtn.innerHTML = "📖";
        dictBtn.title = "Dictionary";
        dictBtn.dataset.action = "dict";
        dictBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            this.showDefinition(note);
        });

        // Center: Time label
        const timeLabel = document.createElement("span");
        timeLabel.className = "sticky-note-time";
        timeLabel.textContent = note.timestamp;

        // Right side: Delete button
        const deleteBtn = document.createElement("button");
        deleteBtn.className = "sticky-note-btn delete-btn";
        deleteBtn.innerHTML = "×";
        deleteBtn.title = "Delete";
        deleteBtn.dataset.action = "delete";
        deleteBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            this.deleteNote(note.id);
        });

        header.appendChild(dictBtn);
        header.appendChild(timeLabel);
        header.appendChild(deleteBtn);

        // Content
        const content = document.createElement("div");
        content.className = "sticky-note-content";
        content.textContent = note.text;

        noteEl.appendChild(header);
        noteEl.appendChild(content);

        // Drag handlers for mouse
        noteEl.addEventListener("mousedown", (e) => {
            if (e.target.dataset.action) return; // Skip if clicking button
            this.startDrag(note, noteEl, e.clientX, e.clientY);
        });

        note.element = noteEl;
        this.container.appendChild(noteEl);
    }

    closeDefinitionPopup() {
        if (this.activeDefinitionPopup) {
            this.activeDefinitionPopup.remove();
            this.activeDefinitionPopup = null;
        }
        if (this.activeDefinitionNote) {
            this.activeDefinitionNote.definitionPopup = null;
            this.activeDefinitionNote = null;
        }
        this.definitionPages = [];
        this.currentDefinitionPage = 0;
    }

    async showDefinition(note) {
        // Close existing popup
        this.closeDefinitionPopup();

        if (!note.element) return;

        // Store reference to note for page navigation
        this.activeDefinitionNote = note;
        this.definitionPages = [];
        this.currentDefinitionPage = 0;

        // Create popup attached to note element
        const popup = document.createElement("div");
        popup.className = "definition-popup";
        // Position relative to note - will be placed below the note
        popup.style.left = "0";
        popup.style.top = "100%";
        popup.style.marginTop = "8px";

        // Close button
        const closeBtn = document.createElement("button");
        closeBtn.className = "definition-close-btn";
        closeBtn.innerHTML = "×";
        closeBtn.dataset.action = "close-definition";
        closeBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            this.closeDefinitionPopup();
        });
        popup.appendChild(closeBtn);

        // Page controls container
        const pageControls = document.createElement("div");
        pageControls.className = "definition-page-controls";

        const prevBtn = document.createElement("button");
        prevBtn.className = "definition-page-btn page-prev-btn";
        prevBtn.innerHTML = "◀";
        prevBtn.title = "Previous";
        prevBtn.dataset.action = "page-prev";
        prevBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            this.goToDefinitionPage(this.currentDefinitionPage - 1);
        });

        const pageIndicator = document.createElement("span");
        pageIndicator.className = "definition-page-indicator";
        pageIndicator.textContent = "1 / 1";

        const nextBtn = document.createElement("button");
        nextBtn.className = "definition-page-btn page-next-btn";
        nextBtn.innerHTML = "▶";
        nextBtn.title = "Next";
        nextBtn.dataset.action = "page-next";
        nextBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            this.goToDefinitionPage(this.currentDefinitionPage + 1);
        });

        pageControls.appendChild(prevBtn);
        pageControls.appendChild(pageIndicator);
        pageControls.appendChild(nextBtn);
        popup.appendChild(pageControls);

        // Content container
        const contentContainer = document.createElement("div");
        contentContainer.className = "definition-content";
        popup.appendChild(contentContainer);

        // Loading state
        const loadingDiv = document.createElement("div");
        loadingDiv.className = "definition-loading";
        loadingDiv.textContent = "Loading...";
        contentContainer.appendChild(loadingDiv);

        this.activeDefinitionPopup = popup;
        note.definitionPopup = popup;

        // Append to note element so it moves with the note
        note.element.appendChild(popup);

        // Look up the word
        try {
            let result = null;
            if (this.onVocabLookup) {
                result = await this.onVocabLookup(note.text);
            }

            // Remove loading
            loadingDiv.remove();

            if (result && !result.error && result.results && result.results.length > 0) {
                // Store all word results as pages
                this.definitionPages = result.results;
                this.currentDefinitionPage = 0;

                // Show first page
                this.renderDefinitionPage(contentContainer);
                this.updatePageControls();

                if (this.onHapticFeedback) {
                    this.onHapticFeedback("selection_tick");
                }

                console.log(`[StickyNote] Definitions loaded: ${this.definitionPages.length} words`);
            } else {
                // Error state
                const errorDiv = document.createElement("div");
                errorDiv.className = "definition-error";
                errorDiv.textContent = result?.error || "Definition not found";
                contentContainer.appendChild(errorDiv);

                // Hide page controls on error
                pageControls.style.display = "none";
            }
        } catch (err) {
            loadingDiv.remove();
            const errorDiv = document.createElement("div");
            errorDiv.className = "definition-error";
            errorDiv.textContent = `Error: ${err.message}`;
            contentContainer.appendChild(errorDiv);

            // Hide page controls on error
            pageControls.style.display = "none";
        }
    }

    renderDefinitionPage(container) {
        if (!container || this.definitionPages.length === 0) return;

        // Clear existing content
        container.innerHTML = "";

        const wordResult = this.definitionPages[this.currentDefinitionPage];

        // Header with word and language
        const header = document.createElement("div");
        header.className = "definition-header";

        const wordSpan = document.createElement("span");
        wordSpan.className = "definition-word";
        wordSpan.textContent = wordResult.headword || wordResult.word;

        const langSpan = document.createElement("span");
        langSpan.className = "definition-lang";
        langSpan.textContent = wordResult.lang === "ko" ? "한국어" : "English";

        header.appendChild(wordSpan);
        header.appendChild(langSpan);
        container.appendChild(header);

        // Definitions list
        const list = document.createElement("ul");
        list.className = "definition-list";

        const definitions = wordResult.definitions || [];
        for (let i = 0; i < definitions.length; i++) {
            const item = document.createElement("li");
            item.className = "definition-item";
            item.textContent = `${i + 1}. ${definitions[i]}`;
            list.appendChild(item);
        }

        container.appendChild(list);
    }

    goToDefinitionPage(pageIndex) {
        if (!this.activeDefinitionPopup || this.definitionPages.length === 0) return;

        // Clamp page index
        pageIndex = Math.max(0, Math.min(pageIndex, this.definitionPages.length - 1));

        if (pageIndex === this.currentDefinitionPage) return;

        this.currentDefinitionPage = pageIndex;

        const container = this.activeDefinitionPopup.querySelector('.definition-content');
        this.renderDefinitionPage(container);
        this.updatePageControls();

        if (this.onHapticFeedback) {
            this.onHapticFeedback("selection_tick");
        }
    }

    updatePageControls() {
        if (!this.activeDefinitionPopup) return;

        const prevBtn = this.activeDefinitionPopup.querySelector('.page-prev-btn');
        const nextBtn = this.activeDefinitionPopup.querySelector('.page-next-btn');
        const indicator = this.activeDefinitionPopup.querySelector('.definition-page-indicator');

        if (!prevBtn || !nextBtn || !indicator) return;

        const totalPages = this.definitionPages.length;
        const currentPage = this.currentDefinitionPage + 1;

        indicator.textContent = `${currentPage} / ${totalPages}`;
        prevBtn.disabled = this.currentDefinitionPage <= 0;
        nextBtn.disabled = this.currentDefinitionPage >= totalPages - 1;
    }

    deleteNote(id) {
        const index = this.notes.findIndex(n => n.id === id);
        if (index === -1) return;

        // Close definition popup if open
        this.closeDefinitionPopup();

        const note = this.notes[index];
        if (note.element) {
            note.element.style.animation = "stickyFadeOut 0.3s ease-out forwards";
            setTimeout(() => {
                note.element.remove();
            }, 300);
        }

        this.notes.splice(index, 1);

        if (this.onHapticFeedback) {
            this.onHapticFeedback("selection_tick");
        }

        console.log(`[StickyNote] Note #${id} deleted`);
    }

    // ===== Drag functionality =====

    startDrag(note, element, startX, startY) {
        this.draggedNote = note;
        this.isDragging = true;

        const rect = element.getBoundingClientRect();
        this.dragOffset = {
            x: startX - rect.left,
            y: startY - rect.top
        };

        element.classList.add("dragging");

        // Mouse move/up handlers
        const moveHandler = (e) => {
            this.updateDragPosition(e.clientX, e.clientY);
        };

        const upHandler = () => {
            this.endDrag();
            document.removeEventListener("mousemove", moveHandler);
            document.removeEventListener("mouseup", upHandler);
        };

        document.addEventListener("mousemove", moveHandler);
        document.addEventListener("mouseup", upHandler);
    }

    updateDragPosition(x, y) {
        if (!this.draggedNote || !this.draggedNote.element) return;

        const newX = x - this.dragOffset.x;
        const newY = y - this.dragOffset.y;

        this.draggedNote.position = { x: newX, y: newY };
        this.draggedNote.element.style.left = `${newX}px`;
        this.draggedNote.element.style.top = `${newY}px`;
    }

    endDrag() {
        if (this.draggedNote && this.draggedNote.element) {
            this.draggedNote.element.classList.remove("dragging");
        }
        this.draggedNote = null;
        this.isDragging = false;
    }

    // ===== Hand tracking hover-dwell support =====

    checkHover(x, y) {
        if (!this.isActive) return null;

        // Check definition popup first (if open) - handle close and page buttons
        if (this.activeDefinitionPopup) {
            const popupRect = this.activeDefinitionPopup.getBoundingClientRect();
            if (x >= popupRect.left && x <= popupRect.right &&
                y >= popupRect.top && y <= popupRect.bottom) {

                // Check close button
                const closeBtn = this.activeDefinitionPopup.querySelector('.definition-close-btn');
                if (closeBtn) {
                    const btnRect = closeBtn.getBoundingClientRect();
                    if (x >= btnRect.left && x <= btnRect.right &&
                        y >= btnRect.top && y <= btnRect.bottom) {

                        if (this.currentHoverElement !== closeBtn) {
                            this.cancelHoverTimer();
                            this.currentHoverElement = closeBtn;
                            this.startHoverTimer(closeBtn, () => {
                                this.closeDefinitionPopup();
                            });

                            if (this.onHapticFeedback) {
                                this.onHapticFeedback("hover_tick");
                            }
                        }
                        return { type: "definitionClose" };
                    }
                }

                // Check previous page button
                const prevBtn = this.activeDefinitionPopup.querySelector('.page-prev-btn');
                if (prevBtn && !prevBtn.disabled) {
                    const btnRect = prevBtn.getBoundingClientRect();
                    if (x >= btnRect.left && x <= btnRect.right &&
                        y >= btnRect.top && y <= btnRect.bottom) {

                        if (this.currentHoverElement !== prevBtn) {
                            this.cancelHoverTimer();
                            this.currentHoverElement = prevBtn;
                            this.startHoverTimer(prevBtn, () => {
                                this.goToDefinitionPage(this.currentDefinitionPage - 1);
                            });

                            if (this.onHapticFeedback) {
                                this.onHapticFeedback("hover_tick");
                            }
                        }
                        return { type: "pagePrev" };
                    }
                }

                // Check next page button
                const nextBtn = this.activeDefinitionPopup.querySelector('.page-next-btn');
                if (nextBtn && !nextBtn.disabled) {
                    const btnRect = nextBtn.getBoundingClientRect();
                    if (x >= btnRect.left && x <= btnRect.right &&
                        y >= btnRect.top && y <= btnRect.bottom) {

                        if (this.currentHoverElement !== nextBtn) {
                            this.cancelHoverTimer();
                            this.currentHoverElement = nextBtn;
                            this.startHoverTimer(nextBtn, () => {
                                this.goToDefinitionPage(this.currentDefinitionPage + 1);
                            });

                            if (this.onHapticFeedback) {
                                this.onHapticFeedback("hover_tick");
                            }
                        }
                        return { type: "pageNext" };
                    }
                }

                return { type: "definitionPopup" };
            }
            // Outside popup - do NOT auto-close, keep it visible
        }

        // Check add button
        const addBtnRect = this.addButton.getBoundingClientRect();
        if (x >= addBtnRect.left && x <= addBtnRect.right &&
            y >= addBtnRect.top && y <= addBtnRect.bottom) {

            if (this.currentHoverElement !== this.addButton) {
                this.cancelHoverTimer();
                this.currentHoverElement = this.addButton;
                this.startHoverTimer(this.addButton, () => {
                    this.toggleRecording();
                });

                if (this.onHapticFeedback) {
                    this.onHapticFeedback("hover_tick");
                }
            }
            return { type: "addButton" };
        }

        // Check notes for drag
        for (const note of this.notes) {
            if (!note.element) continue;

            const rect = note.element.getBoundingClientRect();
            if (x >= rect.left && x <= rect.right &&
                y >= rect.top && y <= rect.bottom) {

                // Check buttons inside note
                const dictBtn = note.element.querySelector('.dict-btn');
                const deleteBtn = note.element.querySelector('.delete-btn');

                if (dictBtn) {
                    const btnRect = dictBtn.getBoundingClientRect();
                    if (x >= btnRect.left && x <= btnRect.right &&
                        y >= btnRect.top && y <= btnRect.bottom) {

                        if (this.currentHoverElement !== dictBtn) {
                            this.cancelHoverTimer();
                            this.currentHoverElement = dictBtn;
                            this.startHoverTimer(dictBtn, () => {
                                this.showDefinition(note);
                            });

                            if (this.onHapticFeedback) {
                                this.onHapticFeedback("hover_tick");
                            }
                        }
                        return { type: "dictBtn", noteId: note.id };
                    }
                }

                if (deleteBtn) {
                    const btnRect = deleteBtn.getBoundingClientRect();
                    if (x >= btnRect.left && x <= btnRect.right &&
                        y >= btnRect.top && y <= btnRect.bottom) {

                        if (this.currentHoverElement !== deleteBtn) {
                            this.cancelHoverTimer();
                            this.currentHoverElement = deleteBtn;
                            this.startHoverTimer(deleteBtn, () => {
                                this.deleteNote(note.id);
                            });

                            if (this.onHapticFeedback) {
                                this.onHapticFeedback("hover_tick");
                            }
                        }
                        return { type: "deleteBtn", noteId: note.id };
                    }
                }

                // Hovering on note body - potential drag target
                return { type: "note", noteId: note.id, note };
            }
        }

        // Not hovering on anything
        this.cancelHoverTimer();
        this.currentHoverElement = null;
        return null;
    }

    startHoverTimer(element, callback) {
        // Add visual progress indicator
        this.hoverProgressElement = document.createElement("div");
        this.hoverProgressElement.className = "hover-progress-sticky";
        this.hoverProgressElement.style.animationDuration = `${this.hoverDuration}ms`;

        const computedPosition = window.getComputedStyle(element).position;

        // For fixed/absolute elements (like add button), position the progress overlay absolutely
        if (computedPosition === "fixed" || computedPosition === "absolute") {
            // Position the progress indicator at the element's position
            const rect = element.getBoundingClientRect();
            this.hoverProgressElement.style.position = "fixed";
            this.hoverProgressElement.style.left = `${rect.left}px`;
            this.hoverProgressElement.style.top = `${rect.top}px`;
            this.hoverProgressElement.style.width = `${rect.width}px`;
            this.hoverProgressElement.style.height = `${rect.height}px`;
            this.hoverProgressElement.style.pointerEvents = "none";
            this.hoverProgressElement.style.zIndex = "99999";
            document.body.appendChild(this.hoverProgressElement);
            this.hoverProgressParent = document.body;
        } else {
            // For relative elements, add as child
            element.style.position = "relative";
            element.appendChild(this.hoverProgressElement);
            this.hoverProgressParent = element;
        }

        this.hoverTimer = setTimeout(() => {
            callback();
            this.cancelHoverTimer();

            if (this.onHapticFeedback) {
                this.onHapticFeedback("selection_tick");
            }
        }, this.hoverDuration);
    }

    cancelHoverTimer() {
        if (this.hoverTimer) {
            clearTimeout(this.hoverTimer);
            this.hoverTimer = null;
        }

        if (this.hoverProgressElement) {
            this.hoverProgressElement.remove();
            this.hoverProgressElement = null;
        }

        this.hoverProgressParent = null;
    }

    // ===== Hand tracking pinch-drag support =====

    // Called when pinch (drawing) starts on a note
    startHandDrag(noteId, x, y) {
        const note = this.notes.find(n => n.id === noteId);
        if (!note || !note.element) return false;

        this.draggedNote = note;
        this.isDragging = true;

        const rect = note.element.getBoundingClientRect();
        this.dragOffset = {
            x: x - rect.left,
            y: y - rect.top
        };

        note.element.classList.add("dragging");

        if (this.onHapticFeedback) {
            this.onHapticFeedback("selection_tick");
        }

        console.log(`[StickyNote] Hand drag started on note #${noteId}`);
        return true;
    }

    // Called during pinch drag
    updateHandDrag(x, y) {
        if (!this.isDragging || !this.draggedNote) return;
        this.updateDragPosition(x, y);
    }

    // Called when pinch ends
    endHandDrag() {
        if (this.isDragging) {
            this.endDrag();
            console.log("[StickyNote] Hand drag ended");
        }
    }

    // ===== Mode control =====

    activate() {
        this.isActive = true;
        this.container.style.display = "block";
        this.addButton.style.display = "block";
        console.log("[StickyNote] Mode activated");
    }

    deactivate() {
        this.isActive = false;
        this.container.style.display = "none";
        this.addButton.style.display = "none";

        // Stop recording if active
        if (this.isRecording) {
            this.stopRecording();
        }

        // End any drag
        this.endDrag();
        this.cancelHoverTimer();

        // Close definition popup if open
        this.closeDefinitionPopup();

        console.log("[StickyNote] Mode deactivated");
    }

    isActiveMode() {
        return this.isActive;
    }

    isRecordingActive() {
        return this.isRecording;
    }

    clearAll() {
        // Close definition popup first
        this.closeDefinitionPopup();

        this.notes.forEach(note => {
            if (note.element) {
                note.element.remove();
            }
        });
        this.notes = [];
        this.noteIdCounter = 0;
        console.log("[StickyNote] All notes cleared");
    }

    getCount() {
        return this.notes.length;
    }

    // Set callbacks
    setOnStartRecording(callback) {
        this.onStartRecording = callback;
    }

    setOnStopRecording(callback) {
        this.onStopRecording = callback;
    }

    setOnHapticFeedback(callback) {
        this.onHapticFeedback = callback;
    }

    setOnVocabLookup(callback) {
        this.onVocabLookup = callback;
    }
}
