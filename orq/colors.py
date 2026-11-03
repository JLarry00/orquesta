"""One colour per open orchestra, shared by every harness.

The palette is Claude Code's `/color` list (2.1.316: the error of `/color xyz` lists them) minus pink and cyan,
whose only emoji are hearts (decided 2026-11-02: six colours with a circle emoji each). `orq init` picks
the first colour that no *open* registered orchestra uses; if all are taken, the least used one (and warns).
Closing an orchestra frees its colour, because only open ones count. Boards without `color` (v1) take none.

Claude Code: `orq launch` creates the session with `claude -p … "/color <c>"` and start.sh resumes it, so the
prompt bar has the colour. Codex has no per-thread colour (openai/codex rust-v0.166.0): the Codex adapter
(step 5) will prefix the thread name with EMOJI[c], e.g. «🟣 builder · orquesta-export», which shows in the
CLI and the app. The app may also take a sidebar section with color/icon (`thread/section/*`, PR #37898);
whether the app paints it is a test item.
"""
import json
from collections import Counter
from pathlib import Path

PALETTE = ["red", "blue", "green", "yellow", "purple", "orange"]
EMOJI = {"red": "🔴", "blue": "🔵", "green": "🟢", "yellow": "🟡", "purple": "🟣", "orange": "🟠"}


def label(color):
    return f"{EMOJI.get(color, '')} {color}".strip() if color else "sin color"


def in_use(registry, except_run=None):
    """Counter of colours of the open, registered orchestras."""
    used = Counter()
    for name, p in registry.items():
        if name == except_run:
            continue
        try:
            b = json.loads((Path(p) / "board.json").read_text())
        except (OSError, ValueError):
            continue
        if b.get("color") and not b.get("closed"):
            used[b["color"]] += 1
    return used


def pick(used):
    """(colour, warning or None): the first free colour, else the least used one."""
    for c in PALETTE:
        if not used.get(c):
            return c, None
    c = min(PALETTE, key=lambda x: (used[x], PALETTE.index(x)))
    return c, f"los {len(PALETTE)} colores están en uso; repito {c}, el menos usado"
