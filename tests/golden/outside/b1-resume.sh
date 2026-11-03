#!/bin/bash
cd <HOME>/ws || exit 1
exec claude --resume <SID:b1> -n b1 --model opus --effort medium --append-system-prompt-file <HOME>/estado/r2/agents/b1/system.md --settings <HOME>/estado/r2/agents/b1/settings.json
