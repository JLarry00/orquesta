"""Harness adapters. A run uses the harness its director runs in (board.json `harness`); missing means `claude`.

Each adapter provides: NAME, DEFAULT_MODEL, models() (None = any), efforts(), LIVENESS ("sessions": it can list
live sessions with live_sessions(); "signal": it can't, so liveness is the last orq call), texts for orq's
messages (LIVE_SOURCE, OPENED, FIND_LIVE, color_hint), and the launch steps: prepare(job) before the board
records the agent (returns its session id, or "" if it arrives later), open_new(job, sid) to open it,
reopen(...) and show(...). Opening windows or chats is the adapter's business, not the CLI's.
"""
from orq import core
from orq.harness import claude, codex

HARNESSES = {"claude": claude, "codex": codex}


def get(name):
    return HARNESSES.get(name or "claude")


def require(name, what):
    h = get(name)
    if h is None:
        core.die(f"las orquestas de {core.harness_label(name)} todavía no están disponibles: orq aún no sabe "
                 f"{what} en ese arnés")
    return h
