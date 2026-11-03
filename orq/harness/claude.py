"""Claude Code adapter: liveness, per-agent settings.json, the start/resume launchers and their windows."""
import json
import os
import shlex
import subprocess
import uuid
from pathlib import Path

from orq import core, windows

NAME = "claude"
SESSION_ENV = "CLAUDE_CODE_SESSION_ID"
MODELS = ["haiku", "sonnet", "opus", "fable"]
EFFORTS = ["low", "medium", "high"]  # orchestra policy: high is the cap
DEFAULT_MODEL = "opus"
LIVENESS = "sessions"  # live_sessions() lists the live sessions

# Texts of orq messages that depend on the harness.
LIVE_SOURCE = "`claude agents --json`"
OPENED = "en una ventana nueva"
FIND_LIVE = "búscalo en sus ventanas abiertas"


def color_hint(color):
    return f"Para que la ventana del director también lo lleve, escribe en ella: /color {color}"


def models():
    return set(core.config().get("models", {}).get(NAME) or MODELS)


def efforts():
    return set(core.config().get("efforts", {}).get(NAME) or EFFORTS)


def live_sessions(timeout=30):
    """sessionId -> name of the Claude sessions alive on this machine; None if it can't be known."""
    try:
        out = subprocess.run(["claude", "agents", "--json"], capture_output=True, text=True, timeout=timeout).stdout
        return {s["sessionId"]: s.get("name", "") for s in json.loads(out)}
    except Exception:
        return None


def is_live_name(sid, name, timeout=10):
    """Is session `sid` alive and currently called `name`? False if it can't be known."""
    try:
        out = subprocess.run(["claude", "agents", "--json"], capture_output=True, text=True, timeout=timeout).stdout
        return any(s["sessionId"] == sid and s.get("name") == name for s in json.loads(out))
    except Exception:
        return False


def settings(d, ws, name, extra_dirs):
    """Per-agent settings.json: extra dirs, orq allowed, shared run files denied, the gate as hooks."""
    h = core.home()
    gate = (f"python3 {shlex.quote(str(core.gate_path()))} --run-dir {shlex.quote(str(d))} "
            f"--agent {shlex.quote(name)}")
    # Agents write under agents/** (their own folder and their children's briefs), never the shared files:
    # the matrix and the board change only through orq, which checks who is calling.
    shared = [d / "board.json", d / "comms.json", d / "messages.log"]
    # Extra dirs go in settings (not as --add-dir) so the command stays short.
    dirs = ([] if d.is_relative_to(ws) else [str(d)]) + [str(h)] + list(extra_dirs)
    bins = []
    for b in (f"Bash({h}/bin/orq *)", f"Bash({core.tilde(h)}/bin/orq *)", "Bash(orq *)"):
        if b not in bins:
            bins.append(b)
    return {
        "permissions": {
            "additionalDirectories": dirs,
            "allow": bins + [f"Edit(/{d}/agents/**)", f"Read({h}/**)"],  # Edit rules cover every file-writing tool
            "deny": [f"Edit(/{p})" for p in shared]},
        "hooks": {
            "PreToolUse": [{"matcher": "SendMessage", "hooks": [
                {"type": "command", "command": gate, "timeout": 15, "statusMessage": "orquesta: revisando mensaje…"}]}],
            "PostToolUse": [{"matcher": "SendMessage", "hooks": [
                {"type": "command", "command": gate + " --post", "timeout": 15}]}]}}


def create_session(sid, name, model, color, cwd):
    """Create session `sid` with its colour before the window opens: `claude -p … "/color <c>"`.

    `/color` is handled by Claude Code itself (no model call) and is saved in the transcript, so the window
    that later resumes the session shows the colour. `cwd` must be the workspace: --resume looks the session
    up by project folder. Returns (ok, output).
    """
    try:
        r = subprocess.run(["claude", "-p", "--session-id", sid, "-n", name, "--model", model, f"/color {color}"],
                           cwd=cwd, capture_output=True, text=True, timeout=120)
    except Exception as e:
        return False, str(e)
    out = (r.stdout + r.stderr).strip()
    return r.returncode == 0 and "Session color set to" in r.stdout, out


def launch_args(sid, name, model, effort, system_md, settings_json, created=False):
    """(start argv, resume argv) for `claude`. Paths are relative to the workspace when inside it.

    With `created` (the session already exists, made by create_session), start.sh resumes it.
    """
    common = ["-n", name, "--model", model, "--effort", effort,
              "--append-system-prompt-file", system_md, "--settings", settings_json]
    first = "--resume" if created else "--session-id"
    return [first, sid, *common, "Empieza."], ["--resume", sid, *common]


def write_launcher(path, cwd, claude_args):
    path.write_text("#!/bin/bash\n"
                    f"cd {shlex.quote(cwd)} || exit 1\n"
                    f"exec claude {' '.join(shlex.quote(a) for a in claude_args)}\n")
    path.chmod(0o755)


def rel(p, ws):
    """Path relative to the workspace when inside it (keeps the command, and the window title, short)."""
    return os.path.relpath(p, ws) if Path(p).is_relative_to(ws) else str(p)


def write_system_prompt(ad, d, run, name, parent):
    """Identity + protocol, in a file that goes to the system prompt (rewritten when the agent is reopened)."""
    (ad / "system.md").write_text(core.identity_head(d, run, name, parent) + core.protocol_path("claude").read_text())


def prepare(j):
    """Everything specific to Claude Code before the board records the agent. Returns its session id."""
    sid = str(uuid.uuid4())
    if j.color:
        ok, out = create_session(sid, j.name, j.model, j.color, str(j.ws))
        if not ok:
            core.die(f"no he podido crear la sesión de '{j.name}' con el color {j.color} en {j.ws}: "
                     f"{out or 'sin salida'}")
    core.save(j.ad / "settings.json", settings(j.d, j.ws, j.name, j.extra))
    # Identity and protocol go in the system prompt: sent every turn, never lost when compacting.
    # The command stays short on purpose: Terminal shows all of it in the window title.
    write_system_prompt(j.ad, j.d, j.run, j.name, j.parent)
    start, resume = launch_args(sid, j.name, j.model, j.effort, rel(j.ad / "system.md", j.ws),
                                rel(j.ad / "settings.json", j.ws), created=bool(j.color))
    write_launcher(j.ad / "start.sh", str(j.ws), start)
    write_launcher(j.ad / "resume.sh", str(j.ws), resume)
    return sid


def open_new(j, sid):
    if j.no_window:
        print(f"preparado sin abrir: {j.ad / 'start.sh'}")
    else:
        windows.open_terminal(j.ad / "start.sh")
        print(f"lanzado '{j.name}' {OPENED} (sesión {sid})")


def reopen(d, board, run, name):
    ad = d / "agents" / name
    if (ad / "system.md").exists():  # agents with system.md: the protocol is refreshed on reopening
        write_system_prompt(ad, d, run, name, board["agents"][name]["parent"])
    windows.open_terminal(ad / "resume.sh")
    print(f"reabierto '{name}' {OPENED}")


def show(d, board, name):
    core.die("en Claude Code cada worker vive en su ventana de Terminal; si está cerrado, ábrelo con `orq resume`")
