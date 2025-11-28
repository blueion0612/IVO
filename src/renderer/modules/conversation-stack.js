// STT Conversation Stack - Speaker selection, delete, and summary features
export class ConversationStack {
    constructor() {
        this.conversations = [];
        this.container = null;
        this.currentSpeaker = "presenter";
        this.isRecordingMode = false;
        this.isRecording = false;

        // Hover state tracking for dwell-click
        this.currentHoverElement = null;
        this.hoverTimer = null;
        this.hoverProgressElement = null;

        // Speaker colors
        this.speakerColors = {
            presenter: { bg: "rgba(26, 58, 110, 0.95)", border: "rgba(74, 159, 212, 0.5)", name: "Presenter" },
            questioner1: { bg: "rgba(139, 69, 19, 0.95)", border: "rgba(210, 105, 30, 0.5)", name: "Q1" },
            questioner2: { bg: "rgba(85, 26, 139, 0.95)", border: "rgba(148, 103, 189, 0.5)", name: "Q2" },
            questioner3: { bg: "rgba(0, 100, 0, 0.95)", border: "rgba(50, 205, 50, 0.5)", name: "Q3" }
        };

        this.createContainer();
    }

    createContainer() {
        this.container = document.createElement("div");
        this.container.id = "conversation-stack-container";
        this.container.style.cssText = `
            position: fixed;
            top: 80px;
            right: 20px;
            width: 380px;
            max-height: 75vh;
            padding: 0;
            overflow-y: auto;
            overflow-x: hidden;
            z-index: 9997;
            display: none;
            pointer-events: auto;
        `;

        // Add styles
        const style = document.createElement("style");
        style.textContent = `
            #conversation-stack-container::-webkit-scrollbar {
                width: 6px;
            }
            #conversation-stack-container::-webkit-scrollbar-track {
                background: rgba(0,0,0,0.1);
                border-radius: 3px;
            }
            #conversation-stack-container::-webkit-scrollbar-thumb {
                background: rgba(74, 159, 212, 0.5);
                border-radius: 3px;
            }
            #conversation-stack-container::-webkit-scrollbar-thumb:hover {
                background: rgba(74, 159, 212, 0.7);
            }

            @keyframes conversationSlideIn {
                from {
                    transform: translateX(100px);
                    opacity: 0;
                }
                to {
                    transform: translateX(0);
                    opacity: 1;
                }
            }

            @keyframes conversationFadeOut {
                from {
                    transform: translateX(0);
                    opacity: 1;
                }
                to {
                    transform: translateX(100px);
                    opacity: 0;
                }
            }

            .speaker-btn {
                padding: 8px 12px;
                border: 2px solid transparent;
                border-radius: 8px;
                cursor: pointer;
                font-size: 12px;
                font-weight: 600;
                transition: all 0.2s ease;
            }

            .speaker-btn:hover {
                transform: scale(1.05);
            }

            .speaker-btn.active {
                border-color: white;
                box-shadow: 0 0 10px rgba(255,255,255,0.3);
            }

            .conversation-item {
                transition: all 0.3s ease;
            }

            .conversation-item:hover .delete-btn,
            .conversation-item:hover .speaker-change-btn {
                opacity: 1;
            }

            .delete-btn, .speaker-change-btn {
                opacity: 0.5;
                transition: opacity 0.2s ease;
            }

            .speaker-change-btn:hover {
                opacity: 1 !important;
                transform: scale(1.1);
            }

            .recording-indicator {
                animation: pulse 1.5s infinite;
            }

            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.5; }
            }
        `;
        document.head.appendChild(style);

        // Create header with speaker selection
        const header = this.createHeader();
        this.container.appendChild(header);

        // Create conversation list
        const conversationList = document.createElement("div");
        conversationList.id = "conversation-list";
        conversationList.style.cssText = `
            display: flex;
            flex-direction: column;
            gap: 10px;
            padding: 10px;
        `;
        this.container.appendChild(conversationList);

        document.body.appendChild(this.container);
    }

    createHeader() {
        const header = document.createElement("div");
        header.id = "conversation-header";
        header.style.cssText = `
            padding: 12px;
            background: linear-gradient(135deg, rgba(30, 30, 30, 0.98), rgba(50, 50, 50, 0.95));
            border-bottom: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px 12px 0 0;
            position: sticky;
            top: 0;
            z-index: 10;
        `;

        // Title and status row
        const titleRow = document.createElement("div");
        titleRow.style.cssText = `
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        `;

        const title = document.createElement("span");
        title.textContent = "STT Recording";
        title.style.cssText = `
            font-size: 14px;
            font-weight: 600;
            color: white;
            text-transform: uppercase;
            letter-spacing: 1px;
        `;

        this.statusIndicator = document.createElement("div");
        this.statusIndicator.style.cssText = `
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
            color: rgba(255,255,255,0.7);
        `;
        this.updateStatusIndicator();

        titleRow.appendChild(title);
        titleRow.appendChild(this.statusIndicator);
        header.appendChild(titleRow);

        // Action buttons row (no pre-selection of speaker)
        const actionRow = document.createElement("div");
        actionRow.style.cssText = `
            display: flex;
            gap: 8px;
        `;

        // Summary button
        this.summaryBtn = document.createElement("button");
        this.summaryBtn.id = "summary-btn";
        this.summaryBtn.textContent = "Summarize";
        this.summaryBtn.style.cssText = `
            flex: 1;
            padding: 10px;
            background: linear-gradient(135deg, #4a9fd4, #1a3a6e);
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 600;
            transition: all 0.2s ease;
        `;
        this.summaryBtn.onmouseover = () => this.summaryBtn.style.transform = "scale(1.02)";
        this.summaryBtn.onmouseout = () => this.summaryBtn.style.transform = "scale(1)";
        this.summaryBtn.onclick = () => this.requestSummary();

        // Clear all button
        this.clearBtn = document.createElement("button");
        this.clearBtn.id = "clear-btn";
        this.clearBtn.textContent = "Clear All";
        this.clearBtn.style.cssText = `
            padding: 10px 15px;
            background: rgba(200, 50, 50, 0.8);
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 600;
            transition: all 0.2s ease;
        `;
        this.clearBtn.onmouseover = () => this.clearBtn.style.transform = "scale(1.02)";
        this.clearBtn.onmouseout = () => this.clearBtn.style.transform = "scale(1)";
        this.clearBtn.onclick = () => this.clearAll();

        actionRow.appendChild(this.summaryBtn);
        actionRow.appendChild(this.clearBtn);
        header.appendChild(actionRow);

        return header;
    }

    updateStatusIndicator() {
        if (!this.statusIndicator) return;

        let statusText = "Standby";
        let statusColor = "rgba(255,255,255,0.5)";
        let dotClass = "";

        if (this.isRecording) {
            statusText = "Recording...";
            statusColor = "#ff4444";
            dotClass = "recording-indicator";
        } else if (this.isRecordingMode) {
            statusText = "Ready";
            statusColor = "#44ff44";
        }

        this.statusIndicator.innerHTML = `
            <span class="${dotClass}" style="
                width: 8px;
                height: 8px;
                background: ${statusColor};
                border-radius: 50%;
                display: inline-block;
            "></span>
            <span>${statusText}</span>
        `;
    }

    selectSpeaker(speaker) {
        this.currentSpeaker = speaker;

        // Update button states
        document.querySelectorAll('.speaker-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.speaker === speaker);
        });

        // Notify main process
        if (window.electronAPI) {
            window.electronAPI.sttSetSpeaker(speaker);
        }

        console.log("[ConversationStack] Speaker selected:", speaker);
    }

    addConversation(text, speaker = null) {
        const speakerKey = speaker || this.currentSpeaker;
        const speakerInfo = this.speakerColors[speakerKey];
        const timestamp = new Date().toLocaleTimeString('ko-KR', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });

        const id = Date.now().toString();
        const conversation = {
            id,
            text,
            speaker: speakerKey,
            speakerName: speakerInfo.name,
            timestamp,
            isSummary: false
        };

        this.conversations.push(conversation);
        this.renderConversation(conversation);
        this.scrollToBottom();

        console.log("[ConversationStack] Added conversation:", speakerInfo.name, text.substring(0, 50));
    }

    addSummary(text) {
        const timestamp = new Date().toLocaleTimeString('ko-KR', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });

        const id = Date.now().toString();
        const summary = {
            id,
            text,
            speaker: "summary",
            speakerName: "Summary",
            timestamp,
            isSummary: true
        };

        this.conversations.push(summary);
        this.renderSummary(summary);
        this.scrollToBottom();

        console.log("[ConversationStack] Added summary");
    }

    renderConversation(conversation) {
        const list = document.getElementById("conversation-list");
        const speakerInfo = this.speakerColors[conversation.speaker];

        // Main container - horizontal layout with speaker buttons on left
        const item = document.createElement("div");
        item.className = "conversation-item";
        item.dataset.id = conversation.id;
        item.dataset.speaker = conversation.speaker;
        item.style.cssText = `
            display: flex;
            gap: 8px;
            animation: conversationSlideIn 0.3s ease-out;
            position: relative;
        `;

        // Left side: Large speaker selection buttons (vertical stack)
        const speakerPanel = document.createElement("div");
        speakerPanel.className = "speaker-panel";
        speakerPanel.style.cssText = `
            display: flex;
            flex-direction: column;
            gap: 4px;
            flex-shrink: 0;
        `;

        // Create large speaker buttons
        Object.entries(this.speakerColors).forEach(([key, info]) => {
            const btn = document.createElement("button");
            btn.className = "speaker-change-btn";
            btn.dataset.speaker = key;
            btn.dataset.conversationId = conversation.id;
            btn.textContent = info.name;
            btn.title = `Change to ${info.name}`;

            const isActive = key === conversation.speaker;
            btn.style.cssText = `
                width: 50px;
                height: 32px;
                border: 2px solid ${isActive ? 'white' : info.border};
                background: ${isActive ? info.bg : 'rgba(40,40,40,0.9)'};
                color: white;
                border-radius: 6px;
                cursor: pointer;
                font-size: 11px;
                font-weight: 600;
                transition: all 0.2s ease;
                opacity: ${isActive ? '1' : '0.7'};
            `;

            // Mouse click handler
            btn.onclick = (e) => {
                e.stopPropagation();
                this.changeSpeaker(conversation.id, key);
            };

            speakerPanel.appendChild(btn);
        });

        // Right side: Content box
        const contentBox = document.createElement("div");
        contentBox.className = "content-box";
        contentBox.style.cssText = `
            flex: 1;
            padding: 10px 12px;
            background: ${speakerInfo.bg};
            border: 1px solid ${speakerInfo.border};
            border-radius: 10px;
            color: white;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
        `;

        // Header row: speaker label + time + delete
        const header = document.createElement("div");
        header.style.cssText = `
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;
        `;

        const speakerLabel = document.createElement("span");
        speakerLabel.className = "speaker-label";
        speakerLabel.textContent = speakerInfo.name;
        speakerLabel.style.cssText = `
            font-size: 11px;
            font-weight: 600;
            color: rgba(255,255,255,0.9);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        `;

        const rightSection = document.createElement("div");
        rightSection.style.cssText = `
            display: flex;
            align-items: center;
            gap: 8px;
        `;

        const timeLabel = document.createElement("span");
        timeLabel.textContent = conversation.timestamp;
        timeLabel.style.cssText = `
            font-size: 10px;
            color: rgba(255,255,255,0.6);
        `;

        const deleteBtn = document.createElement("button");
        deleteBtn.className = "delete-btn";
        deleteBtn.dataset.conversationId = conversation.id;
        deleteBtn.textContent = "×";
        deleteBtn.style.cssText = `
            width: 22px;
            height: 22px;
            border: none;
            background: rgba(255,255,255,0.2);
            color: white;
            border-radius: 50%;
            cursor: pointer;
            font-size: 14px;
            line-height: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s ease;
        `;
        deleteBtn.onclick = (e) => {
            e.stopPropagation();
            this.deleteConversation(conversation.id);
        };

        rightSection.appendChild(timeLabel);
        rightSection.appendChild(deleteBtn);
        header.appendChild(speakerLabel);
        header.appendChild(rightSection);

        // Content text
        const content = document.createElement("div");
        content.textContent = conversation.text;
        content.style.cssText = `
            font-size: 14px;
            line-height: 1.5;
            word-break: keep-all;
            white-space: pre-wrap;
        `;

        contentBox.appendChild(header);
        contentBox.appendChild(content);

        item.appendChild(speakerPanel);
        item.appendChild(contentBox);
        list.appendChild(item);
    }

    renderSummary(summary) {
        const list = document.getElementById("conversation-list");

        const item = document.createElement("div");
        item.className = "conversation-item summary-item";
        item.dataset.id = summary.id;
        item.style.cssText = `
            padding: 14px;
            background: linear-gradient(135deg, rgba(255, 193, 7, 0.9), rgba(255, 152, 0, 0.85));
            border: 2px solid rgba(255, 215, 0, 0.6);
            border-radius: 12px;
            color: #1a1a1a;
            box-shadow: 0 4px 15px rgba(255, 193, 7, 0.3);
            animation: conversationSlideIn 0.3s ease-out;
            position: relative;
        `;

        // Header
        const header = document.createElement("div");
        header.style.cssText = `
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
            padding-bottom: 8px;
            border-bottom: 1px solid rgba(0,0,0,0.15);
        `;

        const label = document.createElement("span");
        label.textContent = "LLM Summary";
        label.style.cssText = `
            font-size: 12px;
            font-weight: 700;
            color: #1a1a1a;
            text-transform: uppercase;
            letter-spacing: 1px;
        `;

        const rightSection = document.createElement("div");
        rightSection.style.cssText = `
            display: flex;
            align-items: center;
            gap: 8px;
        `;

        const timeLabel = document.createElement("span");
        timeLabel.textContent = summary.timestamp;
        timeLabel.style.cssText = `
            font-size: 10px;
            color: rgba(0,0,0,0.6);
        `;

        const deleteBtn = document.createElement("button");
        deleteBtn.className = "delete-btn";
        deleteBtn.textContent = "×";
        deleteBtn.style.cssText = `
            width: 20px;
            height: 20px;
            border: none;
            background: rgba(0,0,0,0.2);
            color: #1a1a1a;
            border-radius: 50%;
            cursor: pointer;
            font-size: 14px;
            line-height: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            opacity: 0.5;
        `;
        deleteBtn.onclick = (e) => {
            e.stopPropagation();
            this.deleteConversation(summary.id);
        };

        rightSection.appendChild(timeLabel);
        rightSection.appendChild(deleteBtn);
        header.appendChild(label);
        header.appendChild(rightSection);

        // Content
        const content = document.createElement("div");
        content.textContent = summary.text;
        content.style.cssText = `
            font-size: 14px;
            line-height: 1.6;
            word-break: keep-all;
            white-space: pre-wrap;
            color: #1a1a1a;
        `;

        item.appendChild(header);
        item.appendChild(content);
        list.appendChild(item);
    }

    deleteConversation(id) {
        const item = document.querySelector(`[data-id="${id}"]`);
        if (item) {
            item.style.animation = "conversationFadeOut 0.3s ease-out forwards";
            setTimeout(() => {
                item.remove();
                this.conversations = this.conversations.filter(c => c.id !== id);
                console.log("[ConversationStack] Deleted conversation:", id);
            }, 300);
        }
    }

    changeSpeaker(id, newSpeaker) {
        // Update data
        const conversation = this.conversations.find(c => c.id === id);
        if (!conversation) return;

        const speakerInfo = this.speakerColors[newSpeaker];
        conversation.speaker = newSpeaker;
        conversation.speakerName = speakerInfo.name;

        // Update UI
        const item = document.querySelector(`[data-id="${id}"]`);
        if (item) {
            item.dataset.speaker = newSpeaker;

            // Update content box background
            const contentBox = item.querySelector('.content-box');
            if (contentBox) {
                contentBox.style.background = speakerInfo.bg;
                contentBox.style.borderColor = speakerInfo.border;
            }

            // Update speaker label
            const label = item.querySelector('.speaker-label');
            if (label) {
                label.textContent = speakerInfo.name;
            }

            // Update button states
            const btns = item.querySelectorAll('.speaker-change-btn');
            btns.forEach(btn => {
                const btnSpeaker = btn.dataset.speaker;
                const btnInfo = this.speakerColors[btnSpeaker];
                if (btnSpeaker === newSpeaker) {
                    btn.style.background = btnInfo.bg;
                    btn.style.border = "2px solid white";
                    btn.style.opacity = "1";
                } else {
                    btn.style.background = "rgba(40,40,40,0.9)";
                    btn.style.border = `2px solid ${btnInfo.border}`;
                    btn.style.opacity = "0.7";
                }
            });
        }

        console.log("[ConversationStack] Changed speaker for", id, "to", newSpeaker);
    }

    /**
     * Check if point is hovering over any interactive element
     * Uses hover-dwell selection like Drawing mode (hover and wait)
     */
    checkHover(x, y) {
        if (!this.isVisible()) return null;

        const containerRect = this.container.getBoundingClientRect();

        // Check if inside container at all
        if (x < containerRect.left || x > containerRect.right ||
            y < containerRect.top || y > containerRect.bottom) {
            this.clearHoverStates();
            this.cancelHoverTimer();
            return null;
        }

        // Get element at point
        const element = document.elementFromPoint(x, y);
        if (!element) {
            this.clearHoverStates();
            this.cancelHoverTimer();
            return null;
        }

        // Check for clickable elements
        const clickable = element.closest('button, .conversation-item');
        if (clickable && clickable.tagName === 'BUTTON') {
            // Check if hovering same element
            if (this.currentHoverElement === clickable) {
                // Already tracking this element
                return { type: 'button', element: clickable };
            }

            // New element - start hover timer
            this.clearHoverStates();
            this.cancelHoverTimer();
            this.setHoverState(clickable);
            this.startHoverTimer(clickable);

            return { type: 'button', element: clickable };
        }

        // Not hovering a button
        this.clearHoverStates();
        this.cancelHoverTimer();

        if (clickable && clickable.classList.contains('conversation-item')) {
            return { type: 'item', element: clickable };
        }

        return { type: 'container', element: this.container };
    }

    /**
     * Start hover timer for dwell-click
     */
    startHoverTimer(element) {
        const hoverDuration = 700; // ms - same as control panel

        // Show progress indicator on button
        element.style.position = "relative";
        element.style.overflow = "hidden";

        // Create progress bar
        const progress = document.createElement("div");
        progress.className = "hover-progress";
        progress.style.cssText = `
            position: absolute;
            bottom: 0;
            left: 0;
            height: 3px;
            background: white;
            width: 0%;
            transition: width ${hoverDuration}ms linear;
        `;
        element.appendChild(progress);

        // Trigger animation
        requestAnimationFrame(() => {
            progress.style.width = "100%";
        });

        // Set timer for click
        this.hoverTimer = setTimeout(() => {
            // Remove progress bar
            progress.remove();

            // Send strong haptic feedback on selection
            if (window.electronAPI && window.electronAPI.sendHaptic) {
                window.electronAPI.sendHaptic("selection_tick");
            }

            // Trigger click action
            element.click();

            // Visual feedback
            element.style.transform = "scale(0.95)";
            setTimeout(() => {
                element.style.transform = "scale(1.05)";
            }, 100);

            console.log("[ConversationStack] Hover-click triggered");
        }, hoverDuration);

        this.hoverProgressElement = progress;
    }

    /**
     * Cancel hover timer
     */
    cancelHoverTimer() {
        if (this.hoverTimer) {
            clearTimeout(this.hoverTimer);
            this.hoverTimer = null;
        }
        if (this.hoverProgressElement) {
            this.hoverProgressElement.remove();
            this.hoverProgressElement = null;
        }
    }

    /**
     * Trigger click on element at position (legacy - kept for compatibility)
     */
    triggerClick(x, y) {
        const hoverInfo = this.checkHover(x, y);
        if (hoverInfo && hoverInfo.type === 'button') {
            hoverInfo.element.click();
            return true;
        }
        return false;
    }

    setHoverState(element) {
        // Clear previous hover states
        this.clearHoverStates();

        // Add hover effect
        if (element.classList.contains('speaker-change-btn')) {
            element.style.transform = "scale(1.05)";
            element.style.opacity = "1";
            element.style.boxShadow = "0 0 10px rgba(255,255,255,0.5)";
        } else if (element.classList.contains('delete-btn')) {
            element.style.opacity = "1";
            element.style.transform = "scale(1.1)";
            element.style.background = "rgba(255,100,100,0.8)";
        } else {
            element.style.transform = "scale(1.02)";
        }

        this.currentHoverElement = element;

        // Send weak haptic feedback when hover starts
        if (window.electronAPI && window.electronAPI.sendHaptic) {
            window.electronAPI.sendHaptic("hover_tick");
        }
    }

    clearHoverStates() {
        if (this.currentHoverElement) {
            this.currentHoverElement.style.transform = "";
            this.currentHoverElement.style.boxShadow = "";
            if (this.currentHoverElement.classList.contains('delete-btn')) {
                this.currentHoverElement.style.background = "rgba(255,255,255,0.2)";
            }
            if (!this.currentHoverElement.classList.contains('active')) {
                this.currentHoverElement.style.opacity = "";
            }
            this.currentHoverElement = null;
        }
    }

    async requestSummary() {
        // Filter only non-summary conversations
        const toSummarize = this.conversations.filter(c => !c.isSummary);

        if (toSummarize.length === 0) {
            console.log("[ConversationStack] No conversations to summarize");
            return;
        }

        // Prepare conversation data for API
        const conversationData = toSummarize.map(c => ({
            speaker: c.speakerName,
            text: c.text,
            timestamp: c.timestamp
        }));

        console.log("[ConversationStack] Requesting summary for", toSummarize.length, "conversations");

        try {
            // Call summary API through IPC
            if (window.electronAPI && window.electronAPI.sttRequestSummary) {
                const result = await window.electronAPI.sttRequestSummary(conversationData);

                if (result && result.summary) {
                    // Remove summarized conversations with animation
                    const idsToRemove = toSummarize.map(c => c.id);
                    idsToRemove.forEach((id, index) => {
                        setTimeout(() => {
                            this.deleteConversation(id);
                        }, index * 50);
                    });

                    // Add summary after animations complete
                    setTimeout(() => {
                        this.addSummary(result.summary);
                    }, idsToRemove.length * 50 + 300);
                } else {
                    console.error("[ConversationStack] Summary failed:", result?.error || "Unknown error");
                }
            }
        } catch (err) {
            console.error("[ConversationStack] Summary request error:", err);
        }
    }

    clearAll() {
        const items = [...document.querySelectorAll('.conversation-item')];
        items.forEach((item, index) => {
            setTimeout(() => {
                item.style.animation = "conversationFadeOut 0.3s ease-out forwards";
            }, index * 30);
        });

        setTimeout(() => {
            this.conversations = [];
            const list = document.getElementById("conversation-list");
            if (list) {
                list.innerHTML = "";
            }
            console.log("[ConversationStack] All conversations cleared");
        }, items.length * 30 + 300);
    }

    scrollToBottom() {
        setTimeout(() => {
            this.container.scrollTop = this.container.scrollHeight;
        }, 50);
    }

    // Recording mode management
    enterRecordingMode() {
        this.isRecordingMode = true;
        this.container.style.display = "block";
        this.updateStatusIndicator();
        console.log("[ConversationStack] Entered recording mode");
    }

    exitRecordingMode() {
        this.isRecordingMode = false;
        this.isRecording = false;
        this.updateStatusIndicator();
        console.log("[ConversationStack] Exited recording mode");
    }

    setRecordingState(recording) {
        this.isRecording = recording;
        this.updateStatusIndicator();
    }

    show() {
        this.container.style.display = "block";
    }

    hide() {
        this.container.style.display = "none";
    }

    isVisible() {
        return this.container.style.display !== "none";
    }

    getCount() {
        return this.conversations.length;
    }
}
