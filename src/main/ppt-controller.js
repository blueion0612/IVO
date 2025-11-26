// PPT/Keynote slide controller
const { exec } = require("child_process");

const isWin = process.platform === "win32";

function pressKeyWin(direction) {
    if (!isWin) return;

    const keyMap = { left: "{LEFT}", right: "{RIGHT}" };
    const sendKey = keyMap[direction];
    if (!sendKey) return;

    const psScript =
        `Add-Type -AssemblyName System.Windows.Forms; ` +
        `[System.Windows.Forms.SendKeys]::SendWait('${sendKey}')`;

    exec(`powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command "${psScript}"`);
}

function pressKeyMac(direction) {
    if (isWin) {
        pressKeyWin(direction);
        return;
    }

    const keyCode = direction === "left" ? 123 : 124;
    exec(`osascript -e 'tell application "System Events" to key code ${keyCode}'`);
}

function pptPrev() {
    pressKeyMac("left");
}

function pptNext() {
    pressKeyMac("right");
}

function jumpSlides(count) {
    const direction = count > 0 ? "right" : "left";
    const absCount = Math.abs(count);

    for (let i = 0; i < absCount; i++) {
        setTimeout(() => {
            pressKeyMac(direction);
        }, i * 100);
    }

    return `${count > 0 ? '→' : '←'} Jump ${absCount} slides`;
}

module.exports = {
    pptPrev,
    pptNext,
    jumpSlides,
    pressKeyWin,
    pressKeyMac
};
