// LLM Summary display stack
export class SummaryStack {
    constructor() {
        this.results = [];
        this.container = null;
        this.createContainer();
    }

    createContainer() {
        this.container = document.createElement("div");
        this.container.id = "summary-stack-container";
        this.container.style.cssText = `
            position: fixed;
            top: 80px;
            right: 20px;
            width: 350px;
            max-height: 70vh;
            padding: 0;
            overflow-y: auto;
            overflow-x: hidden;
            z-index: 9997;
            display: none;
            pointer-events: none;
        `;

        // 스크롤바 스타일 추가
        const style = document.createElement("style");
        style.textContent = `
            #summary-stack-container::-webkit-scrollbar {
                width: 6px;
            }
            #summary-stack-container::-webkit-scrollbar-track {
                background: rgba(0,0,0,0.1);
                border-radius: 3px;
            }
            #summary-stack-container::-webkit-scrollbar-thumb {
                background: rgba(74, 159, 212, 0.5);
                border-radius: 3px;
            }
            #summary-stack-container::-webkit-scrollbar-thumb:hover {
                background: rgba(74, 159, 212, 0.7);
            }

            @keyframes summarySlideIn {
                from {
                    transform: translateX(100px);
                    opacity: 0;
                }
                to {
                    transform: translateX(0);
                    opacity: 1;
                }
            }
        `;
        document.head.appendChild(style);

        const resultsList = document.createElement("div");
        resultsList.id = "summary-results-list";
        resultsList.style.cssText = `
            display: flex;
            flex-direction: column;
            gap: 12px;
        `;

        this.container.appendChild(resultsList);
        document.body.appendChild(this.container);
    }

    addSummary(text, timestamp = null) {
        this.container.style.display = "block";
        const resultsList = document.getElementById("summary-results-list");

        const item = document.createElement("div");
        item.className = "summary-item";

        const time = timestamp || new Date().toLocaleTimeString('ko-KR', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });

        item.style.cssText = `
            padding: 16px;
            background: linear-gradient(135deg, rgba(26, 58, 110, 0.95), rgba(74, 159, 212, 0.9));
            backdrop-filter: blur(10px);
            border: 1px solid rgba(74, 159, 212, 0.3);
            border-radius: 12px;
            color: white;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
            animation: summarySlideIn 0.3s ease-out;
        `;

        // 헤더 (시간 + 라벨)
        const header = document.createElement("div");
        header.style.cssText = `
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
            padding-bottom: 8px;
            border-bottom: 1px solid rgba(255,255,255,0.2);
        `;

        const label = document.createElement("span");
        label.textContent = "LLM Summary";
        label.style.cssText = `
            font-size: 12px;
            font-weight: 600;
            color: rgba(255,255,255,0.8);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        `;

        const timeLabel = document.createElement("span");
        timeLabel.textContent = time;
        timeLabel.style.cssText = `
            font-size: 11px;
            color: rgba(255,255,255,0.6);
        `;

        header.appendChild(label);
        header.appendChild(timeLabel);

        // 내용
        const content = document.createElement("div");
        content.textContent = text;
        content.style.cssText = `
            font-size: 15px;
            line-height: 1.5;
            word-break: keep-all;
            white-space: pre-wrap;
        `;

        item.appendChild(header);
        item.appendChild(content);

        resultsList.appendChild(item);
        this.results.push(item);

        // 자동 스크롤 (가장 아래로)
        setTimeout(() => {
            this.container.scrollTop = this.container.scrollHeight;
        }, 50);

        console.log("[Summary] Added summary, total:", this.results.length);
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
        return this.results.length;
    }

    clearAll() {
        const items = [...this.results];
        items.forEach((item, index) => {
            setTimeout(() => {
                item.style.transform = "translateX(100px)";
                item.style.opacity = "0";
            }, index * 30);
        });

        setTimeout(() => {
            this.results = [];
            const resultsList = document.getElementById("summary-results-list");
            if (resultsList) {
                resultsList.innerHTML = "";
            }
            this.container.style.display = "none";
            console.log("[Summary] All summaries cleared");
        }, items.length * 30 + 200);
    }
}
