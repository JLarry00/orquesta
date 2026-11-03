#!/usr/bin/env python3
"""Puerta de comunicación de la orquesta para Claude Code (PreToolUse y PostToolUse, matcher SendMessage).

`orq launch` la instala en cada worker con --settings, incrustando --run-dir y --agent, porque la entrada
del hook trae el destinatario pero no el remitente. La regla (coordinador<->worker libre, parejas, por defecto)
está en orq/comms.py.
  libre -> allow; manual -> ask (quien aprueba lo decide en la ventana del remitente).
El director se reconoce también por su id de sesión, porque su nombre cambia al reiniciarse.
En messages.log: en Pre, el intento y su modo ("event": "attempt"); en Post (--post), que se envió
("event": "sent") con la respuesta. Un intento sin "sent" detrás es un mensaje rechazado o fallido.
--run <nombre> es el formato antiguo (v1): busca la orquesta en runs.json.
Si algo falla, pide confirmación (falla hacia "ask").
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orq import comms, core, msglog  # noqa: E402
from orq.harness import claude  # noqa: E402


def resolve_run_dir(a):
    """--run-dir (formato nuevo) o --run (formato antiguo), buscado en el registro de orquestas."""
    if a.run_dir:
        return Path(a.run_dir)
    return Path(json.loads(core.registry_path().read_text())[a.run])


def decide(decision, reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": "[orquesta] " + reason,
        }
    }))
    sys.exit(0)


def mode_for(run_dir, sender, recipient):
    board, matrix = comms.load_run(run_dir)
    sid = board.get("coordinator_session")
    return comms.mode_for(board, matrix, sender, recipient, lambda name: claude.is_live_name(sid, name))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir")
    p.add_argument("--run", help="formato antiguo: nombre de la orquesta, buscado en runs.json")
    p.add_argument("--agent", required=True)
    p.add_argument("--post", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="decidir sin escribir en messages.log (orq doctor)")
    a = p.parse_args()
    try:
        run_dir = resolve_run_dir(a)
    except Exception as e:
        if a.post:
            sys.exit(0)
        decide("ask", f"no encuentro la orquesta ({e}); confirma tú")
    try:
        data = json.load(sys.stdin)
        ti = data.get("tool_input", {})
        recipient = re.sub(r"\s*\[[^\]]*\]$", "", (ti.get("to") or ti.get("recipient") or "").strip())
    except Exception as e:
        if a.post:
            sys.exit(0)
        decide("ask", f"no he podido leer el mensaje ({e}); confirma tú")

    if a.post:
        if not a.dry_run:
            msglog.sent(run_dir, a.agent, recipient, data.get("tool_response"))
        sys.exit(0)

    try:
        mode, why = mode_for(run_dir, a.agent, recipient)
    except Exception as e:
        decide("ask", f"no he podido evaluar el mensaje ({e}); confirma tú")
    if not a.dry_run:
        msglog.attempt(run_dir, a.agent, recipient, mode, ti.get("summary", ""), ti.get("message") or ti.get("content", ""))
    if mode == "libre":
        decide("allow", f"{a.agent} -> {recipient}: libre ({why})")
    decide("ask", f"{a.agent} -> {recipient}: manual ({why}). ¿Lo dejas pasar?")


if __name__ == "__main__":
    main()
