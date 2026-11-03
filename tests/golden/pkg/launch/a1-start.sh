#!/bin/bash
cd <HOME>/ws || exit 1
exec claude --resume <SID:a1> -n a1 --model opus --effort high --append-system-prompt-file .orquesta/r1/agents/a1/system.md --settings .orquesta/r1/agents/a1/settings.json Empieza.
