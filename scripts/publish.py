#!/usr/bin/env python3
"""Lleva el contenido de la `main` de desarrollo al repo público, como un commit nuevo y sin historial.

  1. trae la `main` pública;
  2. si su árbol ya es el de la fuente, no hay nada que publicar;
  3. si la `main` pública ya tiene esa versión (orq/__init__.py) con otro contenido, se niega: hay que subirla;
  4. crea un commit con el árbol de la fuente y como único padre la `main` pública, a nombre de
     PUBLISH_NAME <PUBLISH_EMAIL> (tiene que ser un correo noreply de GitHub);
  5. con --push, lo sube a la rama `release/<versión>` del público. La PR la abre el workflow.

Uso (desde la copia del repo de desarrollo):
  scripts/publish.py --public <url o carpeta del repo público> [--source main] [--push]

Si existe la variable GITHUB_OUTPUT (GitHub Actions), escribe en ella version, branch, commit, changed (hay algo
que publicar: la PR tiene que existir) y pushed (se ha subido la rama ahora).
"""
import argparse
import os
import re
import subprocess
import sys

NOREPLY = re.compile(r"^[A-Za-z0-9._+-]+@users\.noreply\.github\.com$", re.I)
PUBLIC_MAIN = "refs/publish/public-main"


def safe(url):
    """The URL without credentials, for messages."""
    return re.sub(r"//[^/@]+@", "//", url)


def git(*args, env=None, check=True):
    r = subprocess.run(["git", *args], capture_output=True, text=True, env=env)
    if check and r.returncode:
        cmd = " ".join(safe(a) for a in args)
        sys.exit(f"publish: falló `git {cmd}`:\n{safe(r.stderr.strip())}")
    return r.stdout.strip()


def version(source):
    text = git("show", f"{source}:orq/__init__.py")
    m = re.search(r'^__version__ = "([^"]+)"', text, re.M)
    if not m:
        sys.exit("publish: no encuentro __version__ en orq/__init__.py")
    return m.group(1)


def as_tuple(v):
    """"0.9.1" -> (0, 9, 1); anything that is not a number counts as 0."""
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.+-]", v))


def identity():
    name = os.environ.get("PUBLISH_NAME") or git("config", "user.name", check=False)
    email = os.environ.get("PUBLISH_EMAIL") or git("config", "user.email", check=False)
    if not name or not NOREPLY.match(email or ""):
        sys.exit("publish: el commit público tiene que ir a nombre de un correo …@users.noreply.github.com "
                 "(PUBLISH_NAME y PUBLISH_EMAIL)")
    return name, email


def output(**kw):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            for k, val in kw.items():
                f.write(f"{k}={val}\n")


def main(argv=None):
    p = argparse.ArgumentParser(prog="publish.py", description="Publica la main de desarrollo en el repo público.")
    p.add_argument("--public", required=True, help="URL o carpeta del repo público")
    p.add_argument("--source", default="HEAD", help="commit cuyo contenido se publica (por defecto, HEAD)")
    p.add_argument("--push", action="store_true", help="subir la rama release/<versión> (si no, solo la prepara)")
    a = p.parse_args(argv)

    src = git("rev-parse", "--verify", f"{a.source}^{{commit}}")
    v = version(src)
    branch = f"release/{v}"
    git("fetch", "--quiet", "--no-tags", a.public, f"+refs/heads/main:{PUBLIC_MAIN}")
    tree = git("rev-parse", f"{src}^{{tree}}")
    if tree == git("rev-parse", f"{PUBLIC_MAIN}^{{tree}}"):
        print(f"Nada que publicar: la main pública ya tiene el contenido de {src[:10]}.")
        output(version=v, branch=branch, commit="", changed="false", pushed="false")
        return 0
    public_v = version(PUBLIC_MAIN)
    if public_v == v:
        sys.exit(f"publish: la versión {v} ya está publicada y el contenido ha cambiado: sube la versión "
                 f"(orq/__init__.py y CHANGELOG.md) y vuelve a intentarlo")
    if as_tuple(v) < as_tuple(public_v):
        sys.exit(f"publish: la versión {v} es anterior a la publicada ({public_v}): no se publica hacia atrás")

    name, email = identity()
    env = {**os.environ, "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
           "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email}
    msg = f"Release {v}\n\nContent of the development main branch at {src}."
    commit = git("commit-tree", tree, "-p", PUBLIC_MAIN, "-m", msg, env=env)
    print(f"Commit {commit[:10]}: árbol de {src[:10]} sobre la main pública ({git('rev-parse', '--short', PUBLIC_MAIN)}).")

    if a.push:
        remote = git("ls-remote", a.public, f"refs/heads/{branch}")
        old = remote.split()[0] if remote else ""
        if old:
            git("fetch", "--quiet", "--no-tags", a.public, f"refs/heads/{branch}")
            if git("rev-parse", "FETCH_HEAD^{tree}") == tree and git("rev-parse", "FETCH_HEAD^") == git(
                    "rev-parse", PUBLIC_MAIN):
                print(f"{branch} ya tiene este contenido: no se sube nada.")
                output(version=v, branch=branch, commit=git("rev-parse", "FETCH_HEAD"), changed="true",
                       pushed="false")
                return 0
        # The branch is ours (one per version): replace it, but only if nobody moved it since we looked.
        git("push", "--quiet", f"--force-with-lease=refs/heads/{branch}:{old}", a.public,
            f"{commit}:refs/heads/{branch}")
        print(f"Subido a {safe(a.public)} como {branch}.")
    else:
        print(f"Sin --push: no se sube nada (se subiría como {branch}).")
    output(version=v, branch=branch, commit=commit, changed="true", pushed="true" if a.push else "false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
