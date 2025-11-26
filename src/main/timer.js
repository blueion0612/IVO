// Presentation timer
class PresentationTimer {
    constructor() {
        this.timer = null;
        this.seconds = 0;
        this.onUpdate = null;
        this.onStop = null;
    }

    toggle() {
        return this.timer ? this.stop() : this.start();
    }

    start() {
        if (this.timer) this.stop();
        this.seconds = 0;
        this.timer = setInterval(() => {
            this.seconds++;
            if (this.onUpdate) this.onUpdate(this.getFormattedTime());
        }, 1000);
        return true;
    }

    stop() {
        if (this.timer) {
            clearInterval(this.timer);
            this.timer = null;
            this.seconds = 0;
            if (this.onStop) this.onStop();
        }
        return false;
    }

    getFormattedTime() {
        const minutes = Math.floor(this.seconds / 60);
        const secs = this.seconds % 60;
        return `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }

    getSeconds() {
        return this.seconds;
    }

    isRunning() {
        return this.timer !== null;
    }

    setUpdateCallback(callback) {
        this.onUpdate = callback;
    }

    setStopCallback(callback) {
        this.onStop = callback;
    }
}

module.exports = PresentationTimer;
