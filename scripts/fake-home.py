#!/usr/bin/env python3
"""Build a throwaway HOME holding a *copy* of this machine's v1 orquesta and its registered runs.

  python3 scripts/fake-home.py <dest>          # dest must not exist

Copies ~/.claude/orquesta, ~/.claude/skills/orquesta-*, recreates ~/.local/bin/orq as a link into the copy,
and copies every run folder listed in runs.json to the same path relative to $HOME inside <dest>, rewriting
runs.json to point at the copies. Nothing in the real HOME is modified. Also writes <dest>/stubs/claude (a fake
`claude agents --json` that reports no live sessions) and prints the environment to use.
"""
import json
import os
import shutil
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    real = Path.home()
    dest = Path(sys.argv[1]).expanduser().resolve()
    if dest.exists():
        sys.exit(f"{dest} ya existe")
    if real in dest.parents and dest.parent == real:
        sys.exit("elige una carpeta que no esté directamente en tu HOME")
    leg = real / ".claude/orquesta"
    shutil.copytree(leg, dest / ".claude/orquesta", symlinks=True)
    for s in ("orquesta-launch", "orquesta-resume"):
        if (real / ".claude/skills" / s).exists():
            shutil.copytree(real / ".claude/skills" / s, dest / ".claude/skills" / s, symlinks=True)
    reg = json.loads((leg / "runs.json").read_text())
    new = {}
    for name, p in reg.items():
        p = Path(p)
        rel = p.relative_to(real) if real in p.parents else Path("fuera-de-home") / p.relative_to("/")
        target = dest / rel
        if p.exists():
            shutil.copytree(p, target, symlinks=True)
            gi = p.parent / ".gitignore"
            if gi.exists() and not (target.parent / ".gitignore").exists():
                shutil.copy2(gi, target.parent / ".gitignore")
        new[name] = str(target)
    (dest / ".claude/orquesta/runs.json").write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n")
    (dest / ".local/bin").mkdir(parents=True)
    os.symlink(dest / ".claude/orquesta/bin/orq", dest / ".local/bin/orq")
    (dest / "stubs").mkdir()
    (dest / "stubs/claude").write_text('#!/bin/sh\necho "[]"\n')
    (dest / "stubs/claude").chmod(0o755)
    print(f"HOME={dest} PATH={dest}/.local/bin:{dest}/stubs:/usr/bin:/bin:/usr/sbin:/sbin")


if __name__ == "__main__":
    main()
