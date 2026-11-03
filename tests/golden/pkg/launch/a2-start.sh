#!/bin/bash
cd <HOME>/ws || exit 1
exec claude --resume <SID:a2> -n a2 --model sonnet --effort medium --append-system-prompt-file .orquesta/r1/agents/a2/system.md --settings .orquesta/r1/agents/a2/settings.json Empieza.
