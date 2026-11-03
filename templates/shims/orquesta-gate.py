#!/usr/bin/env python3
"""orquesta-shim: capa de compatibilidad con la versión anterior.

Los agentes lanzados con la versión anterior llaman a este archivo desde su settings.json (formato
--run <nombre> o --run-dir <carpeta>). Reenvía todo, entrada incluida, a la puerta instalada.
"""
import json
import os
import sys

GATE = "{{gate}}"

try:
    os.execv(sys.executable, [sys.executable, GATE] + sys.argv[1:])
except OSError as e:
    if "--post" in sys.argv:
        sys.exit(0)
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "ask",
        "permissionDecisionReason": f"[orquesta] no encuentro la puerta ({GATE}: {e}); confirma tú"}}))
