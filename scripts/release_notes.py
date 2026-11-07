#!/usr/bin/env python3
"""Versión y notas de una publicación, sacadas de orq/__init__.py y de la sección del CHANGELOG.md.

Una versión está lista para publicar cuando su cabecera en el CHANGELOG lleva fecha: `## X.Y.Z (AAAA-MM-DD)`.

Uso (desde la raíz de una copia del repo):
  scripts/release_notes.py version [--rev REV]
      escribe la versión de orq/__init__.py (en REV; sin --rev, la del disco)
  scripts/release_notes.py notes VERSION [--rev REV] [--link-base URL]
      escribe la sección de VERSION del CHANGELOG.md, sin la cabecera. Con --link-base, los enlaces relativos
      pasan a ser URL/<ruta> (en una Release o una PR, los relativos no llevan al archivo).

Sale con 1 y un mensaje si la versión o la sección no están, o si la sección sigue sin fecha.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

VERSION_LINE = re.compile(r'^__version__ = "([^"]+)"', re.M)
# [text](target) or ![alt](target), where target is not a URL, an absolute path or an in-page anchor
RELATIVE_LINK = re.compile(r"(!?\[[^\]]*\]\()(?![a-zA-Z][a-zA-Z0-9+.-]*:|/|#)([^)\s]+)\)")
DOT_SLASH = re.compile(r"^(?:\./)+")


class NotesError(Exception):
    """Something the person publishing has to fix; the message says what."""


def version_of(init_text):
    m = VERSION_LINE.search(init_text)
    if not m:
        raise NotesError("no encuentro __version__ en orq/__init__.py")
    return m.group(1)


def section(changelog, version):
    """(header, body) of `## <version> …` in the changelog text; body without surrounding blank lines."""
    lines = changelog.splitlines()
    head = re.compile(r"^## " + re.escape(version) + r"(\s|$)")
    start = next((i for i, line in enumerate(lines) if head.match(line)), None)
    if start is None:
        raise NotesError(f"el CHANGELOG.md no tiene la sección «## {version} (AAAA-MM-DD)»")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    body = "\n".join(lines[start + 1:end]).strip("\n")
    return lines[start], body


def release_section(changelog, version):
    """The body of a version that is ready to publish: its header has a date and nothing else."""
    header, body = section(changelog, version)
    if "sin publicar" in header:
        raise NotesError(f"la cabecera de {version} en el CHANGELOG.md sigue diciendo «sin publicar»: "
                         f"pon la fecha, «## {version} (AAAA-MM-DD)»")
    if not re.fullmatch(r"## " + re.escape(version) + r" \(\d{4}-\d{2}-\d{2}\)\s*", header):
        raise NotesError(f"la cabecera de {version} en el CHANGELOG.md tiene que ser «## {version} (AAAA-MM-DD)», "
                         f"y es «{header}»")
    if not body.strip():
        raise NotesError(f"la sección de {version} en el CHANGELOG.md está vacía")
    return body


def absolute_links(text, base):
    """Relative Markdown links and images rewritten as <base>/<target>."""
    base = base.rstrip("/")

    def fix(m):
        return f"{m.group(1)}{base}/{DOT_SLASH.sub('', m.group(2))})"
    return RELATIVE_LINK.sub(fix, text)


def read(path, rev=None):
    if rev is None:
        return Path(path).read_text(encoding="utf-8")
    r = subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True, text=True)
    if r.returncode:
        raise NotesError(f"no puedo leer {path} en {rev}: {r.stderr.strip()}")
    return r.stdout


def main(argv=None):
    p = argparse.ArgumentParser(prog="release_notes.py", description="Versión y notas de una publicación.")
    sub = p.add_subparsers(dest="cmd", required=True)
    pv = sub.add_parser("version", help="la versión de orq/__init__.py")
    pv.add_argument("--rev", help="commit (por defecto, el disco)")
    pn = sub.add_parser("notes", help="la sección de una versión del CHANGELOG.md")
    pn.add_argument("version")
    pn.add_argument("--rev", help="commit (por defecto, el disco)")
    pn.add_argument("--link-base", help="URL para los enlaces relativos")
    a = p.parse_args(argv)
    try:
        if a.cmd == "version":
            print(version_of(read("orq/__init__.py", a.rev)))
        else:
            body = release_section(read("CHANGELOG.md", a.rev), a.version)
            print(absolute_links(body, a.link_base) if a.link_base else body)
    except NotesError as e:
        print(f"release_notes: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
