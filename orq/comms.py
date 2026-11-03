"""The communication matrix: is a message from `sender` to `recipient` free (libre) or manual?

  - coordinator <-> worker (parent <-> child): always libre (it is the channel results travel on)
  - a pair listed in comms.json: its mode (libre | manual)
  - everything else: comms.json's default

Every gate (one per harness) uses this one function.
"""
import json
from pathlib import Path

MODES = ("libre", "manual")


def pair_key(a, b):
    return "<->".join(sorted([a, b]))


def mode_for(board, comms, sender, recipient, is_coordinator=None):
    """(mode, why). `is_coordinator(name)` says whether `name` is the coordinator's session under a new
    name (names change when a session restarts; the session id does not)."""
    coord = board["coordinator"]
    if recipient != coord and board.get("coordinator_session") and is_coordinator and is_coordinator(recipient):
        recipient = coord
    parent_of = {n: ag["parent"] for n, ag in board["agents"].items()}
    if parent_of.get(sender) == recipient or parent_of.get(recipient) == sender:
        return "libre", "coordinador<->worker"
    pair = comms["pairs"].get(pair_key(sender, recipient))
    if pair:
        return pair, "pareja"
    return comms["default"], "por defecto"


def load_run(run_dir):
    run_dir = Path(run_dir)
    return (json.loads((run_dir / "board.json").read_text()),
            json.loads((run_dir / "comms.json").read_text()))
