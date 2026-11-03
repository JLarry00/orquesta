"""messages.log: one JSON object per line.

  {"event": "attempt", "from", "to", "mode", "summary", "message"}   written before a message goes out
  {"event": "sent", "from", "to", "response"}                         written after it went out
An attempt with no `sent` after it is a message that was rejected or failed.
"""
import datetime as dt
import json
from pathlib import Path


def append(run_dir, entry):
    entry = {"ts": dt.datetime.now().astimezone().isoformat(timespec="seconds"), **entry}
    with open(Path(run_dir) / "messages.log", "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def attempt(run_dir, sender, recipient, mode, summary, message):
    append(run_dir, {"event": "attempt", "from": sender, "to": recipient, "mode": mode,
                     "summary": summary, "message": message})


def sent(run_dir, sender, recipient, response):
    append(run_dir, {"event": "sent", "from": sender, "to": recipient,
                     "response": response if isinstance(response, (str, dict)) else str(response)})
