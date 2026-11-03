"""What the installer puts into Codex's own config, and how --deshacer takes it out again.

Codex has no per-session settings, so orquesta's pieces are global (rust-v0.166.0):
  - a marked block in the global AGENTS.md ($CODEX_HOME/AGENTS.md, or AGENTS.override.md when that exists,
    because then Codex ignores AGENTS.md): it tells orchestra chats to run `orq whoami`;
  - three handler groups in $CODEX_HOME/hooks.json (PreToolUse, PermissionRequest, PostToolUse, matcher
    `send_message_to_thread$`) running hooks/codex_gate.py; existing hooks are left alone;
  - $CODEX_HOME/rules/orquesta.rules: `orq` runs outside the sandbox without asking; `codex queue` is forbidden.

Undo: a file nobody touched since our last write gets its original bytes back (or is deleted if we created it).
If the user changed it in between, only our block or our hook groups are removed. The originals are kept in
<ORQ_HOME>/backup/codex/, and install.json["codex"] records what was written.
"""
import json
import os
import re
import shlex
import sys
from pathlib import Path

from orq import core, render

BLOCK_RE = re.compile(r"\n*<!-- orquesta:start.*?<!-- orquesta:end -->\n?", re.S)
GATE_MARK = "/hooks/codex_gate.py"
EVENTS = ("PreToolUse", "PermissionRequest", "PostToolUse")
MATCHER = "send_message_to_thread$"  # a regex: matches mcp__codex_app__… and mcp__codex_tui__…


def codex_home():
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()


def agents_md():
    o = codex_home() / "AGENTS.override.md"
    return o if o.exists() else codex_home() / "AGENTS.md"


def hooks_json():
    return codex_home() / "hooks.json"


def rules_file():
    return codex_home() / "rules" / "orquesta.rules"


def gate_command():
    """Stable on purpose: Codex trusts a hook by a hash of its definition, so a new command means re-trusting."""
    # Absolute python: the app's hooks don't get the user's shell PATH.
    py = sys.executable or "python3"
    return f"{shlex.quote(py)} {shlex.quote(str(core.home() / 'lib' / 'hooks' / 'codex_gate.py'))}"


def fill(text):
    h = core.home()
    return text.replace("{{orq_bin}}", str(h / "bin/orq")).replace("{{orq_home}}", str(h))


def block_text():
    return fill((render.TEMPLATES / "codex" / "AGENTS.block.md").read_text())


def rules_text():
    return fill((render.TEMPLATES / "codex" / "orquesta.rules").read_text())


def ours(group):
    return any(GATE_MARK in (h.get("command") or "") for h in group.get("hooks", []))


def our_groups():
    cmd = gate_command()
    pre = {"type": "command", "command": cmd, "timeout": 15, "statusMessage": "orquesta: revisando mensaje…"}
    plain = {"type": "command", "command": cmd, "timeout": 15}
    return {"PreToolUse": {"matcher": MATCHER, "hooks": [pre]},
            "PermissionRequest": {"matcher": MATCHER, "hooks": [plain]},
            "PostToolUse": {"matcher": MATCHER, "hooks": [plain]}}


def without_our_hooks(data):
    hooks = data.get("hooks") or {}
    for ev in list(hooks):
        if isinstance(hooks[ev], list):
            hooks[ev] = [g for g in hooks[ev] if not (isinstance(g, dict) and ours(g))]
            if not hooks[ev]:
                del hooks[ev]
    return data


def hooks_with_ours(text):
    data = json.loads(text) if text and text.strip() else {}
    data = without_our_hooks(data)
    hooks = data.setdefault("hooks", {})
    for ev, group in our_groups().items():
        hooks.setdefault(ev, []).append(group)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def agents_with_block(text):
    base = BLOCK_RE.sub("", text or "").rstrip("\n")
    return (base + "\n\n" if base else "") + block_text()


def backup_dir():
    return core.home() / "backup" / "codex"


def install(manifest, note_missing_dirs, say):
    """Write the three pieces. On the first Codex install, keep the originals for undo."""
    rec = manifest.setdefault("codex", {})
    for key, path, make in (("agents_md", agents_md(), agents_with_block),
                            ("hooks_json", hooks_json(), hooks_with_ours),
                            ("rules", rules_file(), lambda _old: rules_text())):
        entry = rec.get(key)
        if entry is None or entry["path"] != str(path):
            entry = {"path": str(path), "existed": path.exists()}
            if entry["existed"]:
                backup_dir().mkdir(parents=True, exist_ok=True)
                orig = backup_dir() / f"{key}.orig"
                orig.write_bytes(path.read_bytes())
                entry["original"] = str(orig.relative_to(core.home()))
            note_missing_dirs(manifest, path)
            rec[key] = entry
        new = make(path.read_text() if path.exists() else "")
        core.write_atomic(path, new)
        entry["written"] = new
        say(f"Escrito {path}")


def undo(manifest, say):
    for key, entry in (manifest.get("codex") or {}).items():
        path = Path(entry["path"])
        if not path.exists():
            continue
        current = path.read_text()
        if current == entry.get("written"):
            if entry.get("existed"):
                path.write_bytes((core.home() / entry["original"]).read_bytes())
            else:
                path.unlink()
        elif key == "agents_md":
            path.write_text(BLOCK_RE.sub("\n", current).rstrip("\n") + "\n")
        elif key == "hooks_json":
            try:
                path.write_text(json.dumps(without_our_hooks(json.loads(current)), indent=2, ensure_ascii=False) + "\n")
            except ValueError:
                say(f"Aviso: {path} no es JSON válido; quita a mano los hooks de orquesta (codex_gate.py)")
                continue
        else:
            path.unlink()
        say(f"Restaurado {path}")


def check(rep):
    """orq doctor: Codex's pieces are in place."""
    ch = codex_home()
    a = agents_md()
    if a.exists() and "<!-- orquesta:start" in a.read_text():
        rep.ok(f"bloque de orquesta en {a}")
    else:
        rep.err(f"falta el bloque de orquesta en {a}: ejecuta ./install.sh")
    try:
        data = json.loads(hooks_json().read_text())
        have = [ev for ev in EVENTS if any(ours(g) and g.get("matcher") == MATCHER
                                           for g in (data.get("hooks") or {}).get(ev, []))]
    except (OSError, ValueError):
        have = []
    if len(have) == len(EVENTS):
        rep.ok(f"hooks de la puerta en {hooks_json()} (Codex pide confirmarlos una vez: `/hooks` en la CLI)")
    else:
        rep.err(f"faltan hooks de la puerta en {hooks_json()} ({', '.join(e for e in EVENTS if e not in have)})")
    (rep.ok if rules_file().exists() else rep.err)(f"reglas {rules_file()}")
    if not ch.exists():
        rep.err(f"no existe {ch}")
