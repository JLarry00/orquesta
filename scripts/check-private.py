#!/usr/bin/env python3
"""Filtro de datos privados: lo que no debe llegar a un repo público.

Revisa los archivos de HEAD tal como están commiteados (lo que se sube; también enlaces y binarios) y los
commits nuevos:

  - palabras privadas (nombres, empresas…): de ORQ_FORBIDDEN_WORDS (separadas por comas; en CI, el secreto
    FORBIDDEN_WORDS) y del archivo `.forbidden-words` de la raíz del repo (ignorado por git, una por línea);
  - correos: el autor y quien hace el commit tienen que ser `…@users.noreply.github.com` (o el de GitHub en
    los merges hechos desde la web); en archivos y mensajes, solo se aceptan correos que no son de nadie;
  - rutas personales, tipo /Users/<nombre>/ o /home/<nombre>/;
  - patrones de secretos: tokens de GitHub, claves de Anthropic, OpenAI, AWS, Slack, Google, claves privadas…

Nunca escribe en la salida lo que encuentra (los logs de un repo público son públicos): dice dónde y de qué
tipo, y enmascara el resto.

Uso:
  scripts/check-private.py                        antes de un push: archivos + commits que aún no están en remoto
  scripts/check-private.py --range A..B           commits de un rango (CI)
  scripts/check-private.py --range none           solo los archivos
  scripts/check-private.py --require-words        falla si no hay ninguna palabra privada cargada (CI)

Sale con 0 si no hay nada, 1 si encuentra algo y 2 si no puede revisar.
"""
import argparse
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

NOREPLY = re.compile(r"^[A-Za-z0-9._+-]+@users\.noreply\.github\.com$", re.I)
GITHUB_WEB = "noreply@github.com"  # committer of merges and edits made on github.com
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
# Addresses that belong to nobody: GitHub's noreply ones, the AI co-author line and the reserved example domains.
ALLOWED_EMAIL = re.compile(r"^(?:[A-Za-z0-9._+-]+@users\.noreply\.github\.com|noreply@github\.com|"
                           r"noreply@anthropic\.com|git@github\.com|[^@]+@example\.(?:com|org|net)|"
                           r"[^@]+@(?:[A-Za-z0-9-]+\.)*(?:test|example|invalid))$", re.I)
PERSONAL_PATH = re.compile(r"(?:/Users|/home)/([A-Za-z0-9._-]+)")
GENERIC_USERS = {"runner", "shared", "usuario", "tu-usuario", "nombre", "user", "you"}
SECRETS = [
    ("token de GitHub", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}")),
    ("token de GitHub", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}")),
    ("clave de Anthropic", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("clave de OpenAI", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}")),
    ("clave de AWS", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("token de Slack", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("clave de Google", re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
    ("token de Atlassian", re.compile(r"\bATATT[A-Za-z0-9_=-]{40,}")),
    ("clave privada", re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----")),
]


def git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if r.returncode:
        sys.stderr.write(r.stderr.decode(errors="replace"))
        sys.exit(f"check-private: falló `git {' '.join(args)}`")
    return r.stdout


def load_words(repo):
    words = [w.strip() for w in os.environ.get("ORQ_FORBIDDEN_WORDS", "").split(",") if w.strip()]
    f = repo / ".forbidden-words"
    if f.exists():
        words += [w.strip() for w in f.read_text().splitlines() if w.strip() and not w.strip().startswith("#")]
    return list(dict.fromkeys(words))


def mask(s):
    s = str(s)
    return s[:2] + "…" if len(s) > 4 else "…"


class Report:
    def __init__(self):
        self.found = []

    def add(self, where, kind, detail=""):
        self.found.append(f"{where}: {kind}" + (f" ({detail})" if detail else ""))


def scan_text(text, where, words_re, words, rep, emails=True):
    """Every finding in `text`; `where` is a function line -> location."""
    for no, line in enumerate(text.splitlines(), 1):
        if words_re:
            for m in words_re.finditer(line):
                i = next(i for i, w in enumerate(words) if w.lower() == m.group(0).lower())
                rep.add(where(no), "palabra privada", f"n.º {i + 1} de la lista")
        if emails:
            for m in EMAIL.finditer(line):
                if not ALLOWED_EMAIL.match(m.group(0)):
                    rep.add(where(no), "correo", mask(m.group(0)))
        for m in PERSONAL_PATH.finditer(line):
            if m.group(1).lower() not in GENERIC_USERS:
                rep.add(where(no), "ruta personal", m.group(0).split("/")[1] + "/" + mask(m.group(1)))
        for kind, rx in SECRETS:
            for m in rx.finditer(line):
                rep.add(where(no), kind, mask(m.group(0)))


def scan_files(repo, words_re, words, rep):
    """Every file of HEAD as committed (what a push sends), not the working copy. A symbolic link's blob is its
    target and is checked as text; binary files are checked too, decoded as well as possible."""
    entries = []
    for e in git(repo, "ls-tree", "-r", "-z", "--full-tree", "HEAD").split(b"\0"):
        if not e:
            continue
        meta, rel = e.split(b"\t", 1)
        mode, kind, sha = meta.decode().split()
        if kind == "blob":
            entries.append((mode, sha, rel.decode("utf-8", errors="replace")))
    r = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch"], capture_output=True,
                       input="".join(f"{sha}\n" for _m, sha, _r in entries).encode())
    if r.returncode:
        sys.exit("check-private: falló `git cat-file --batch`")
    out, pos = r.stdout, 0
    for mode, sha, rel in entries:
        nl = out.index(b"\n", pos)
        size = int(out[pos:nl].split()[2])
        data = out[nl + 1:nl + 1 + size]
        pos = nl + 1 + size + 1
        shown = words_re.sub("…", rel) if words_re else rel  # the path itself may hold the word
        if shown != rel:
            rep.add(shown, "palabra privada en el nombre del archivo")
        label = f"{shown} (enlace)" if mode == "120000" else shown
        scan_text(data.decode("utf-8", errors="replace"), lambda no, label=label: f"{label}:{no}", words_re, words,
                  rep)
    return len(entries)


def uncommitted(repo):
    return bool(git(repo, "status", "--porcelain", "--untracked-files=no").strip())


def default_range(repo):
    up = subprocess.run(["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "@{upstream}"], capture_output=True)
    return ["@{upstream}..HEAD"] if up.returncode == 0 else ["HEAD", "--not", "--remotes"]


def scan_commits(repo, spec, words_re, words, rep):
    fmt = "%H%x00%an%x00%ae%x00%cn%x00%ce%x00%B%x1e"
    out = git(repo, "log", f"--format={fmt}", *spec).decode("utf-8", errors="replace")
    n = 0
    for rec in out.split("\x1e"):
        rec = rec.lstrip("\n")
        if not rec:
            continue
        sha, an, ae, cn, ce, body = rec.split("\0", 5)
        n += 1
        c = sha[:10]
        if not NOREPLY.match(ae):
            rep.add(f"commit {c}", "correo del autor no es noreply de GitHub", mask(ae))
        if not (NOREPLY.match(ce) or ce.lower() == GITHUB_WEB):
            rep.add(f"commit {c}", "correo de quien hace el commit no es noreply de GitHub", mask(ce))
        for label, name in (("autor", an), ("quien hace el commit", cn)):
            if words_re and words_re.search(name):
                rep.add(f"commit {c}", f"palabra privada en el nombre de {label}")
        scan_text(body, lambda no, c=c: f"commit {c} (mensaje, línea {no})", words_re, words, rep)
    return n


def main(argv=None):
    p = argparse.ArgumentParser(prog="check-private.py", description="Filtro de datos privados del repo.")
    p.add_argument("--repo", default=".", help="carpeta del repo (por defecto, la actual)")
    p.add_argument("--range", help="commits a revisar, como en `git log` (A..B); `none` para no revisar commits")
    p.add_argument("--require-words", action="store_true",
                   help="falla si no hay palabras privadas (ORQ_FORBIDDEN_WORDS o .forbidden-words)")
    a = p.parse_args(argv)
    top = subprocess.run(["git", "-C", a.repo, "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if top.returncode:
        print(f"check-private: {a.repo} no es un repo de git", file=sys.stderr)
        return 2
    repo = Path(top.stdout.strip())
    words = load_words(repo)
    if not words:
        msg = "no hay palabras privadas (ORQ_FORBIDDEN_WORDS o .forbidden-words)"
        if a.require_words:
            print(f"check-private: {msg}: en CI, revisa el secreto FORBIDDEN_WORDS", file=sys.stderr)
            return 2
        print(f"Aviso: {msg}; solo se revisan correos, rutas y secretos.")
    words_re = re.compile("|".join(re.escape(w) for w in words), re.I) if words else None
    rep = Report()
    if uncommitted(repo):
        print("Aviso: hay cambios sin commitear; se revisa lo commiteado (HEAD), que es lo que se sube.")
    nfiles = scan_files(repo, words_re, words, rep)
    if a.range == "none":
        ncommits = 0
    else:
        ncommits = scan_commits(repo, shlex.split(a.range) if a.range else default_range(repo), words_re, words, rep)
    if rep.found:
        print(f"Datos privados: {len(rep.found)} hallazgos (el contenido va enmascarado):")
        for f in rep.found:
            print(f"  {f}")
        return 1
    print(f"Sin datos privados: {nfiles} archivos y {ncommits} commits revisados, {len(words)} palabras privadas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
