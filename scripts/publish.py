#!/usr/bin/env python3
"""Publica una versión etiquetada del repo de desarrollo en el repo público, como un commit nuevo y sin historial.

  1. comprueba el tag: `vX.Y.Z`, anotado, igual a `v` + __version__ de su commit, y ese commit en la rama `dev`;
  2. saca las notas de la sección `## X.Y.Z (AAAA-MM-DD)` del CHANGELOG.md (si sigue «sin publicar», se niega);
  3. trae la `main` pública; si su árbol ya es el del tag, no hay nada que publicar;
  4. si la `main` pública ya tiene esa versión con otro contenido, o una posterior, se niega;
  5. crea un commit con el árbol del tag y como único padre la `main` pública, a nombre de
     PUBLISH_NAME <PUBLISH_EMAIL> (un correo noreply de GitHub), con el mensaje «Release X.Y.Z» + las notas;
  6. con --push, lo sube a la rama `release/X.Y.Z` del público;
  7. con --pr OWNER/REPO, abre con `gh` la PR `release/X.Y.Z` → `main` o, si ya está abierta, le pone el título y
     el cuerpo de ahora.

Uso (desde la copia del repo de desarrollo, con el tag y la rama `dev` traídos):
  scripts/publish.py --tag vX.Y.Z --public <url o carpeta del repo público> [--dev-ref origin/dev]
                     [--push [--pr OWNER/REPO]]

Si existe la variable GITHUB_OUTPUT (GitHub Actions), escribe en ella version, branch, commit, changed (hay algo
que publicar), pushed (se ha subido la rama ahora) y pr (la URL de la PR), para los tests y para pasos que se
añadan después.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_notes import NotesError, absolute_links, release_section, version_of  # noqa: E402

NOREPLY = re.compile(r"^[A-Za-z0-9._+-]+@users\.noreply\.github\.com$", re.I)
TAG = re.compile(r"^v\d+\.\d+\.\d+$")
PUBLIC_MAIN = "refs/publish/public-main"


def fail(msg):
    sys.exit(f"publish: {msg}")


def safe(url):
    """The URL without credentials, for messages."""
    return re.sub(r"//[^/@]+@", "//", url)


def run(cmd, env=None, check=True):
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if check and r.returncode:
        fail(f"falló `{' '.join(safe(a) for a in cmd)}`:\n{safe(r.stderr.strip())}")
    return r


def git(*args, env=None, check=True):
    return run(["git", *args], env=env, check=check).stdout.strip()


def gh(*args):
    return run(["gh", *args]).stdout.strip()


def show(rev, path):
    r = run(["git", "show", f"{rev}:{path}"], check=False)
    if r.returncode:
        fail(f"no encuentro {path} en {rev}")
    return r.stdout


def version(rev):
    try:
        return version_of(show(rev, "orq/__init__.py"))
    except NotesError as e:
        fail(f"{e} ({rev})")


def as_tuple(v):
    """"0.9.1" -> (0, 9, 1); anything that is not a number counts as 0."""
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.+-]", v))


def check_tag(tag, dev_ref):
    """The commit of a tag that may be published: vX.Y.Z, annotated, matching __version__, on the dev branch."""
    if not TAG.match(tag):
        fail(f"«{tag}» no es un tag de versión: tiene que ser vX.Y.Z (por ejemplo, v0.9.1)")
    ref = f"refs/tags/{tag}"
    if not git("rev-parse", "--verify", "--quiet", ref, check=False):
        fail(f"el tag {tag} no existe en esta copia")
    if git("cat-file", "-t", ref) != "tag":
        fail(f"el tag {tag} es ligero: tiene que ser anotado (git tag -a {tag} -m \"orquesta {tag[1:]}\")")
    commit = git("rev-parse", f"{ref}^{{commit}}")
    v = version(commit)
    if tag != f"v{v}":
        fail(f"el tag {tag} no coincide con la versión de su commit ({v} en orq/__init__.py): tendría que ser v{v}")
    if not git("rev-parse", "--verify", "--quiet", f"{dev_ref}^{{commit}}", check=False):
        fail(f"no encuentro la rama {dev_ref}: hace falta para comprobar que el tag está en ella")
    if run(["git", "merge-base", "--is-ancestor", commit, dev_ref], check=False).returncode:
        fail(f"el commit del tag {tag} ({commit[:10]}) no está en {dev_ref}: se etiqueta el merge de la PR de "
             f"versión, ya en dev")
    return commit, v


def identity():
    name = os.environ.get("PUBLISH_NAME") or git("config", "user.name", check=False)
    email = os.environ.get("PUBLISH_EMAIL") or git("config", "user.email", check=False)
    if not name or not NOREPLY.match(email or ""):
        fail("el commit público tiene que ir a nombre de un correo …@users.noreply.github.com "
             "(PUBLISH_NAME y PUBLISH_EMAIL)")
    return name, email


def output(**kw):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            for k, val in kw.items():
                f.write(f"{k}={val}\n")


def pr_body(notes, v, public_v, repo, commit):
    """The release notes with links that work on GitHub, the previous public version and how to merge."""
    links = absolute_links(notes, f"https://github.com/{repo}/blob/{commit}")
    return (f"{links}\n\n---\n\nPrevious public version: {public_v}.\n\n"
            f"Merge with a merge commit (not squash or rebase) once `tests` and `private-data` pass. Merging creates "
            f"the tag `v{v}` and its GitHub Release with these notes.\n")


def open_pr(repo, branch, v, body):
    """Opens the release pull request or, if it is already open, refreshes its title and body. Returns its URL."""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(body)
    try:
        open_prs = gh("pr", "list", "-R", repo, "--head", branch, "--base", "main", "--state", "open",
                      "--json", "number", "--jq", ".[].number").split()
        number = open_prs[0] if open_prs else ""
        title = f"Release {v}"
        if number:
            # REST rather than `gh pr edit`, which has failed with fine-grained tokens in some gh versions.
            url = gh("api", "-X", "PATCH", f"repos/{repo}/pulls/{number}", "-f", f"title={title}",
                     "-F", f"body=@{f.name}", "--jq", ".html_url")
            print(f"PR {url} actualizada (título y notas).")
        else:
            url = gh("pr", "create", "-R", repo, "--base", "main", "--head", branch, "--title", title,
                     "--body-file", f.name)
            print(f"PR abierta: {url}")
        return url
    finally:
        os.unlink(f.name)


def main(argv=None):
    p = argparse.ArgumentParser(prog="publish.py", description="Publica una versión etiquetada en el repo público.")
    p.add_argument("--tag", required=True, help="tag anotado vX.Y.Z del repo de desarrollo")
    p.add_argument("--public", required=True, help="URL o carpeta del repo público")
    p.add_argument("--dev-ref", default="origin/dev", help="rama en la que tiene que estar el tag (origin/dev)")
    p.add_argument("--push", action="store_true", help="subir la rama release/<versión> (si no, solo la prepara)")
    p.add_argument("--pr", metavar="OWNER/REPO", help="abrir o actualizar la PR en ese repo (con gh; pide --push)")
    a = p.parse_args(argv)
    if a.pr and not a.push:
        p.error("--pr necesita --push")

    src, v = check_tag(a.tag, a.dev_ref)
    try:
        notes = release_section(show(src, "CHANGELOG.md"), v)
    except NotesError as e:
        fail(str(e))
    branch = f"release/{v}"
    git("fetch", "--quiet", "--no-tags", a.public, f"+refs/heads/main:{PUBLIC_MAIN}")
    tree = git("rev-parse", f"{src}^{{tree}}")
    if tree == git("rev-parse", f"{PUBLIC_MAIN}^{{tree}}"):
        print(f"Nada que publicar: la main pública ya tiene el contenido de {a.tag}.")
        output(version=v, branch=branch, commit="", changed="false", pushed="false", pr="")
        return 0
    public_v = version(PUBLIC_MAIN)
    if public_v == v:
        fail(f"la versión {v} ya está publicada y el contenido ha cambiado: nunca se reutiliza un número; "
             f"saca la siguiente (orq/__init__.py, CHANGELOG.md y un tag nuevo)")
    if as_tuple(v) < as_tuple(public_v):
        fail(f"la versión {v} es anterior a la publicada ({public_v}): no se publica hacia atrás")

    name, email = identity()
    env = {**os.environ, "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
           "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email}
    commit = git("commit-tree", tree, "-p", PUBLIC_MAIN, "-m", f"Release {v}\n\n{notes}", env=env)
    print(f"Commit {commit[:10]}: árbol de {a.tag} sobre la main pública ({git('rev-parse', '--short', PUBLIC_MAIN)}).")

    pushed = False
    if a.push:
        remote = git("ls-remote", a.public, f"refs/heads/{branch}")
        old = remote.split()[0] if remote else ""
        same = False
        if old:
            git("fetch", "--quiet", "--no-tags", a.public, f"refs/heads/{branch}")
            same = (git("rev-parse", "FETCH_HEAD^{tree}") == tree
                    and git("rev-parse", "FETCH_HEAD^") == git("rev-parse", PUBLIC_MAIN)
                    and git("log", "-1", "--format=%B", "FETCH_HEAD") == git("log", "-1", "--format=%B", commit))
        if same:
            commit = git("rev-parse", "FETCH_HEAD")
            print(f"{branch} ya tiene este contenido: no se sube nada.")
        else:
            # The branch is ours (one per version): replace it, but only if nobody moved it since we looked.
            git("push", "--quiet", f"--force-with-lease=refs/heads/{branch}:{old}", a.public,
                f"{commit}:refs/heads/{branch}")
            pushed = True
            print(f"Subido a {safe(a.public)} como {branch}.")
    else:
        print(f"Sin --push: no se sube nada (se subiría como {branch}).")
    url = open_pr(a.pr, branch, v, pr_body(notes, v, public_v, a.pr, commit)) if a.pr else ""
    output(version=v, branch=branch, commit=commit, changed="true", pushed="true" if pushed else "false", pr=url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
