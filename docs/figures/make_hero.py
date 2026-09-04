"""Render the system figure used at the top of the README.

    python docs/figures/make_hero.py

Writes hero_system.png and hero_system-dark.png.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

THEMES = {
    "light": dict(bg="white", ink="#1c2530", muted="#5b6875", line="#b9c3cf",
                  fill="#eef2f6", imu="#4a7fb5", vis="#52a0b5", out="#3f7d5a",
                  fimu="#eaf1f8", fvis="#e8f2f5", fout="#e9f2ec"),
    "dark": dict(bg="#0d1117", ink="#e6edf3", muted="#9198a1", line="#3d444d",
                 fill="#161b22", imu="#6ea8dd", vis="#6fbcd0", out="#5aa87a",
                 fimu="#12202f", fvis="#10222a", fout="#12241a"),
}

HERE = os.path.dirname(os.path.abspath(__file__))


def render(theme, out):
    T = THEMES[theme]
    fig, ax = plt.subplots(figsize=(9.4, 4.4), dpi=170)
    ax.set_xlim(0, 94)
    ax.set_ylim(-5, 44)
    ax.axis("off")
    fig.patch.set_facecolor(T["bg"])

    def box(x, y, w, h, title, sub, edge=None, face=None, tcol=None):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.4",
                                    linewidth=1.4, edgecolor=edge or T["line"],
                                    facecolor=face or T["fill"], zorder=2))
        ax.text(x + w / 2, y + h / 2 + 1.8, title, ha="center", va="center",
                fontsize=11.2, color=tcol or T["ink"], fontweight="bold", zorder=3)
        ax.text(x + w / 2, y + h / 2 - 2.3, sub, ha="center", va="center",
                fontsize=8.9, color=T["muted"], zorder=3)

    def arrow(x0, y0, x1, y1, c=None):
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=12,
                                     linewidth=1.5, color=c or T["line"], shrinkA=0, shrinkB=0, zorder=1))

    W, H = 24.0, 11.0
    TOP, MID, BOT = 30.0, 30.0, 4.0

    # gesture path along the top
    box(2.0, TOP, W, H, "Smartwatch", "IMU, haptics", T["imu"], T["fimu"])
    arrow(26.0, TOP + H / 2, 29.5, TOP + H / 2, T["imu"])
    box(29.5, TOP, W, H, "Phone", "relays over UDP", T["imu"], T["fimu"])
    arrow(53.5, TOP + H / 2, 57.0, TOP + H / 2, T["imu"])

    # vision path along the bottom
    box(29.5, BOT, W, H, "Webcam", "hand landmarks", T["vis"], T["fvis"])
    arrow(53.5, BOT + H / 2, 57.0, BOT + H / 2, T["vis"])

    # the desktop app, spanning both input paths; drawn by hand so the title can
    # sit at the top of a tall box instead of at its centre
    bx, bw = 57.0, 35.0
    by, bh = BOT, TOP + H - BOT
    ax.add_patch(FancyBboxPatch((bx, by), bw, bh, boxstyle="round,pad=0,rounding_size=1.4",
                                linewidth=1.4, edgecolor=T["out"], facecolor=T["fout"], zorder=2))
    ax.text(bx + bw / 2, by + bh - 4.2, "IVO desktop", ha="center", va="center",
            fontsize=11.6, color=T["out"], fontweight="bold", zorder=3)
    for i, line in enumerate([
        "two-stage gesture model",
        "overlay, pointer, drawing",
        "speech to text, summaries",
        "handwriting OCR, dictionary",
    ]):
        ax.text(bx + bw / 2, by + bh - 11.0 - i * 5.2, line, ha="center", va="center",
                fontsize=9.2, color=T["muted"], zorder=3)

    ax.text(41.5, TOP + H + 2.6, "gesture path", ha="center", fontsize=9.4,
            color=T["imu"], fontweight="bold")
    ax.text(41.5, BOT + H + 2.6, "vision path", ha="center", fontsize=9.4,
            color=T["vis"], fontweight="bold")

    # haptic acknowledgement returns to the wrist, below everything
    yh = 1.4
    ax.plot([bx + bw / 2, bx + bw / 2], [BOT, yh], color=T["out"], lw=1.4, ls=(0, (4, 3)), zorder=1)
    ax.plot([14.0, bx + bw / 2], [yh, yh], color=T["out"], lw=1.4, ls=(0, (4, 3)), zorder=1)
    arrow(14.0, yh, 14.0, TOP - 0.4, T["out"])
    ax.text(44.0, yh - 2.8, "haptic acknowledgement", ha="center", fontsize=8.6,
            color=T["muted"])

    fig.tight_layout(pad=0.2)
    fig.savefig(out, dpi=170, bbox_inches="tight", facecolor=T["bg"])
    plt.close(fig)
    print("wrote", out)


if __name__ == "__main__":
    render("light", os.path.join(HERE, "hero_system.png"))
    render("dark", os.path.join(HERE, "hero_system-dark.png"))
