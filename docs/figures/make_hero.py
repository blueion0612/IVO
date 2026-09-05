"""Draw the README hero: the system, two input paths into the desktop app.

    python docs/figures/make_hero.py

Writes hero_system.png and hero_system-dark.png.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__)) + os.sep
sys.path.insert(0, HERE)

import figstyle  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402


def system(T):
    fig, ax = plt.subplots(figsize=(figstyle.WIDTH, 4.4))
    ax.set_xlim(0, 94)
    ax.set_ylim(-5, 44)
    ax.axis("off")
    G, GF, D, DF = T["green"], T["green_fill"], T["gold"], T["gold_fill"]

    def box(x, y, w, h, title, sub, edge=None, face=None, tcol=None):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.4",
                                    linewidth=1.4, edgecolor=edge or T["line"],
                                    facecolor=face or T["fill"], zorder=2))
        ax.text(x + w / 2, y + h / 2 + 1.8, title, ha="center", va="center",
                fontsize=figstyle.TITLE, color=tcol or T["ink"], fontweight="bold", zorder=3)
        ax.text(x + w / 2, y + h / 2 - 2.3, sub, ha="center", va="center",
                fontsize=figstyle.SMALL, color=T["muted"], zorder=3)

    def arrow(x0, y0, x1, y1, c=None):
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=12,
                                     linewidth=1.5, color=c or T["line"], shrinkA=0, shrinkB=0, zorder=1))

    W, H = 24.0, 11.0
    TOP, BOT = 30.0, 4.0

    # gesture path along the top, green
    box(2.0, TOP, W, H, "Smartwatch", "IMU, haptics", G, GF)
    arrow(26.0, TOP + H / 2, 29.5, TOP + H / 2, G)
    box(29.5, TOP, W, H, "Phone", "relays over UDP", G, GF)
    arrow(53.5, TOP + H / 2, 57.0, TOP + H / 2, G)

    # vision path along the bottom, gold
    box(29.5, BOT, W, H, "Webcam", "hand landmarks", D, DF)
    arrow(53.5, BOT + H / 2, 57.0, BOT + H / 2, D)

    # the desktop app spans both input paths; drawn by hand so the title can sit
    # at the top of a tall box instead of at its center
    bx, bw = 57.0, 35.0
    by, bh = BOT, TOP + H - BOT
    ax.add_patch(FancyBboxPatch((bx, by), bw, bh, boxstyle="round,pad=0,rounding_size=1.4",
                                linewidth=1.4, edgecolor=T["ink"], facecolor=T["fill"], zorder=2))
    ax.text(bx + bw / 2, by + bh - 4.2, "IVO desktop", ha="center", va="center",
            fontsize=figstyle.TITLE, color=T["ink"], fontweight="bold", zorder=3)
    for i, line in enumerate([
        "two-stage gesture model",
        "overlay, pointer, drawing",
        "speech to text, summaries",
        "handwriting OCR, dictionary",
    ]):
        ax.text(bx + bw / 2, by + bh - 11.0 - i * 5.2, line, ha="center", va="center",
                fontsize=figstyle.SMALL, color=T["muted"], zorder=3)

    ax.text(41.5, TOP + H + 2.6, "gesture path", ha="center", fontsize=figstyle.BODY,
            color=G, fontweight="bold")
    ax.text(41.5, BOT + H + 2.6, "vision path", ha="center", fontsize=figstyle.BODY,
            color=D, fontweight="bold")

    # haptic acknowledgement returns to the wrist, below everything
    yh = 1.4
    ax.plot([bx + bw / 2, bx + bw / 2], [BOT, yh], color=G, lw=1.4, ls=(0, (4, 3)), zorder=1)
    ax.plot([14.0, bx + bw / 2], [yh, yh], color=G, lw=1.4, ls=(0, (4, 3)), zorder=1)
    arrow(14.0, yh, 14.0, TOP - 0.4, G)
    ax.text(44.0, yh - 2.8, "haptic acknowledgement", ha="center", fontsize=figstyle.SMALL,
            color=T["muted"])
    return fig


if __name__ == "__main__":
    figstyle.save_both(system, HERE + "hero_system")
