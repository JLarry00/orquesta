#!/usr/bin/env python3
"""Puerta de comunicación de la orquesta para Codex (hooks globales en ~/.codex/hooks.json).

Codex no deja instalar hooks por sesión, así que esta puerta es global: no hace nada con los chats que no son
de ninguna orquesta. Mira solo la herramienta nativa `send_message_to_thread` (`mcp__codex_app__…` en la app,
`mcp__codex_tui__…` en la CLI). El remitente es `session_id` (el id del hilo raíz = el chat del agente) y el
destinatario, `tool_input.threadId`; los dos se buscan en el registro de orquestas.

  PreToolUse:        destinatario de otra orquesta o desconocido -> deny; si no, apunta el intento en
                     messages.log (con su modo) y no decide nada.
  PermissionRequest: libre -> allow (sin aviso); manual -> sin decisión, así que Codex enseña su aviso de
                     aprobación en el chat de quien envía.
  PostToolUse:       apunta que se envió.

Formatos (rust-v0.166.0, codex-rs/hooks/src/engine/output_parser.rs): en PreToolUse solo bloquea
`permissionDecision: "deny"` con motivo («ask» no está soportado); en PermissionRequest,
`decision.behavior: "allow" | "deny"`. Si algo falla, sale sin decidir: Codex pregunta como siempre.

Sonda (`orq doctor --sonda on|permitir|off`): con `on`, apunta cada entrada en <ORQ_HOME>/sonda.log y no decide
nada; con `permitir`, además aprueba en PermissionRequest todo `send_message_to_thread`. Es para la prueba.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orq import comms, core, msglog  # noqa: E402

SEND_RE = re.compile(r"^(mcp__)?codex_(app|tui)_*send_message_to_thread$")


def is_send(tool_name):
    return bool(SEND_RE.match(tool_name or ""))


def emit(event, **fields):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, **fields}}, ensure_ascii=False))
    sys.exit(0)


def allow():
    emit("PermissionRequest", decision={"behavior": "allow"})


def deny(reason):
    emit("PreToolUse", permissionDecision="deny", permissionDecisionReason="[orquesta] " + reason)


def probe_mode():
    p = core.home() / "sonda"
    try:
        return p.read_text().strip() if p.exists() else ""
    except OSError:
        return ""


def probe(data, mode):
    try:
        with open(core.home() / "sonda.log", "a") as f:
            f.write(json.dumps({"ts": core.now(), "sonda": mode, **data}, ensure_ascii=False) + "\n")
    except OSError:
        pass
    if mode == "permitir" and data.get("hook_event_name") == "PermissionRequest" and is_send(data.get("tool_name")):
        allow()
    sys.exit(0)


def participant(board, sid):
    if sid and sid == board.get("coordinator_session"):
        return board["coordinator"]
    for n, ag in board["agents"].items():
        if sid and ag.get("session_id") == sid:
            return n
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="decidir sin escribir en messages.log (orq doctor)")
    a = p.parse_args()
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    mode = probe_mode()
    if mode in ("on", "permitir"):
        probe(data, mode)
    event = data.get("hook_event_name")
    if not is_send(data.get("tool_name")):
        sys.exit(0)
    try:
        found = core.find_session(data.get("session_id"))
        if not found:
            sys.exit(0)  # a chat outside every orchestra: not our business
        run, d, board, who = found
        sender = board["coordinator"] if who == "coordinator" else who
        ti = data.get("tool_input") or {}
        recipient = participant(board, ti.get("threadId"))
        if recipient is None:
            if event == "PreToolUse":
                deny(f"ese chat no es de la orquesta «{run}». Pide su id con `orq to <nombre>`")
            sys.exit(0)
        msg_mode, why = comms.mode_for(board, json.loads((d / "comms.json").read_text()), sender, recipient)
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # no decision: Codex asks as usual

    if event == "PreToolUse":
        if not a.dry_run:
            msglog.attempt(d, sender, recipient, msg_mode, "", ti.get("prompt", ""))
            if who != "coordinator":
                core.touch_signal(d, who)
        else:
            print(f"{sender} -> {recipient}: {msg_mode} ({why})")
        sys.exit(0)
    if event == "PermissionRequest":
        if a.dry_run:
            print(f"{sender} -> {recipient}: {'allow' if msg_mode == 'libre' else 'sin decisión (aviso)'}")
            sys.exit(0)
        if msg_mode == "libre":
            allow()
        sys.exit(0)
    if event == "PostToolUse" and not a.dry_run:
        msglog.sent(d, sender, recipient, data.get("tool_response"))
    sys.exit(0)


if __name__ == "__main__":
    main()
