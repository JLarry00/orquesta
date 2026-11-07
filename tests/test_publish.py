"""scripts/publish.py against throwaway repos: a development repo, a bare "public" one and a fake `gh`."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.support import REPO

SCRIPT = REPO / "scripts/publish.py"
CHECK = REPO / "scripts/check-private.py"
NOREPLY = "1+pub@users.noreply.github.com"
NOTES = ("Solo el flujo ([guía](docs/flujo-de-trabajo.md)).\n\n"
         "- **Publicar:** con un tag.")
CHANGELOG = f"# Cambios\n\n## 0.9.1 (2026-11-05)\n\n{NOTES}\n\n## 0.9.0 (2026-10-01)\n\n- Primera.\n"

FAKE_GH = """#!{python}
import json, os, sys
args = sys.argv[1:]
rec = {{"args": args}}
if "--body-file" in args:
    rec["body"] = open(args[args.index("--body-file") + 1]).read()
for a in args:
    if a.startswith("body=@"):
        rec["body"] = open(a[len("body=@"):]).read()
with open(os.environ["FAKE_GH_LOG"], "a") as f:
    f.write(json.dumps(rec) + "\\n")
if args[:2] == ["pr", "list"]:
    print(os.environ.get("FAKE_GH_OPEN", ""))
elif args[:2] == ["pr", "create"]:
    print("https://github.com/o/public/pull/2")
elif args[:3] == ["api", "-X", "PATCH"]:
    print("https://github.com/o/public/pull/" + args[3].rsplit("/", 1)[1])
"""


def git(cwd, *args, email="dev@users.noreply.github.com"):
    env = {**os.environ, "GIT_AUTHOR_NAME": "dev", "GIT_AUTHOR_EMAIL": email, "GIT_COMMITTER_NAME": "dev",
           "GIT_COMMITTER_EMAIL": email, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    return subprocess.run(["git", "-C", str(cwd), *args], env=env, check=True, capture_output=True,
                          text=True).stdout.strip()


class Publish(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="orq-publish-")
        t = self.t = Path(self.tmp.name)
        self.dev, self.pub, self.seed = t / "dev", t / "public.git", t / "seed"
        # public repo: one clean commit on main (like the first public import)
        git(t, "init", "-q", "--bare", "-b", "main", str(self.pub))
        git(t, "init", "-q", "-b", "main", str(self.seed))
        self.write(self.seed, {"README.md": "v0\n", "orq/__init__.py": '__version__ = "0.9.0"\n'})
        git(self.seed, "add", "-A")
        git(self.seed, "commit", "-q", "-m", "Initial public release")
        git(self.seed, "push", "-q", str(self.pub), "main")
        # development repo, on `dev`: its own history, with a commit by a non-noreply identity that must not travel
        git(t, "init", "-q", "-b", "dev", str(self.dev))
        self.write(self.dev, {"README.md": "v0\n", "orq/__init__.py": '__version__ = "0.9.0"\n'})
        git(self.dev, "add", "-A")
        git(self.dev, "commit", "-q", "-m", "old work", email="someone@" "company.es")
        self.change({"README.md": "v1\n", "orq/__init__.py": '__version__ = "0.9.1"\n', "docs/new.md": "nuevo\n",
                     "CHANGELOG.md": CHANGELOG})
        self.tag("v0.9.1")
        # a fake gh that records each call
        bin_dir = t / "bin"
        bin_dir.mkdir()
        (bin_dir / "gh").write_text(FAKE_GH.format(python=sys.executable))
        (bin_dir / "gh").chmod(0o755)
        self.gh_log = t / "gh.log"
        self.path = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, repo, files):
        for rel, text in files.items():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text(text)

    def change(self, files, msg="work"):
        """A commit on dev, already on the remote dev branch (origin/dev)."""
        self.write(self.dev, files)
        git(self.dev, "add", "-A")
        git(self.dev, "commit", "-q", "-m", msg)
        git(self.dev, "update-ref", "refs/remotes/origin/dev", "HEAD")

    def tag(self, name, annotated=True, rev="HEAD"):
        if annotated:
            git(self.dev, "tag", "-f", "-a", name, "-m", f"orquesta {name}", rev)
        else:
            git(self.dev, "tag", "-f", name, rev)

    def publish(self, *args, tag="v0.9.1", email=NOREPLY, open_pr=""):
        """Runs the script; its GITHUB_OUTPUT values end up in self.out and the gh calls in self.gh()."""
        out = self.t / "github-output"
        out.write_text("")
        env = {**os.environ, "PUBLISH_NAME": "pub", "PUBLISH_EMAIL": email, "GIT_CONFIG_GLOBAL": os.devnull,
               "GITHUB_OUTPUT": str(out), "PATH": self.path, "FAKE_GH_LOG": str(self.gh_log),
               "FAKE_GH_OPEN": open_pr}
        r = subprocess.run([sys.executable, str(SCRIPT), "--public", str(self.pub), "--tag", tag, *args],
                           cwd=self.dev, env=env, capture_output=True, text=True)
        self.out = dict(line.split("=", 1) for line in out.read_text().splitlines())
        return r

    def gh(self):
        if not self.gh_log.exists():
            return []
        return [json.loads(line) for line in self.gh_log.read_text().splitlines()]

    def refused(self, r, text):
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn(text, r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(git(self.pub, "branch", "--list", "release/*"), "")

    def merge_release(self, v):
        """What merging the release PR does on GitHub: a merge commit on the public main."""
        git(self.seed, "fetch", "-q", str(self.pub), f"release/{v}")
        git(self.seed, "merge", "-q", "--no-ff", "-m", f"Merge pull request #1 from someone/release/{v}", "FETCH_HEAD")
        git(self.seed, "push", "-q", str(self.pub), "main")

    def test_release_commit_has_dev_tree_public_parent_and_the_notes(self):
        r = self.publish("--push")
        self.assertEqual(r.returncode, 0, r.stderr)
        c = git(self.pub, "rev-parse", "release/0.9.1")
        self.assertEqual(git(self.pub, "rev-parse", f"{c}^{{tree}}"), git(self.dev, "rev-parse", "v0.9.1^{tree}"))
        self.assertEqual(git(self.pub, "rev-parse", f"{c}^@"), git(self.pub, "rev-parse", "main"))
        self.assertEqual(git(self.pub, "log", "-1", "--format=%an <%ae>|%cn <%ce>", c),
                         f"pub <{NOREPLY}>|pub <{NOREPLY}>")
        self.assertEqual(git(self.pub, "log", "-1", "--format=%B", c), f"Release 0.9.1\n\n{NOTES}")
        self.assertNotIn(git(self.dev, "rev-parse", "HEAD"), git(self.pub, "log", "-1", "--format=%B", c))
        self.assertEqual(git(self.pub, "rev-list", "--count", c), "2")  # no development history
        self.assertEqual(self.out, {"version": "0.9.1", "branch": "release/0.9.1", "commit": c, "changed": "true",
                                    "pushed": "true", "pr": ""})
        self.assertNotIn("company", git(self.pub, "log", "--format=%ae%n%ce", c))
        self.assertEqual(self.gh(), [])  # no --pr, no gh
        # the public checks would pass on the new commit
        clone = self.t / "clone"
        git(self.t, "clone", "-q", "-b", "release/0.9.1", str(self.pub), str(clone))
        chk = subprocess.run([sys.executable, str(CHECK), "--repo", str(clone), "--range", "origin/main..HEAD"],
                             capture_output=True, text=True, env={**os.environ, "ORQ_FORBIDDEN_WORDS": "Zarandaja"})
        self.assertEqual(chk.returncode, 0, chk.stdout + chk.stderr)

    def test_opens_the_pull_request_with_the_notes(self):
        r = self.publish("--push", "--pr", "o/public")
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.gh()
        self.assertEqual([c["args"][:2] for c in calls], [["pr", "list"], ["pr", "create"]])
        create = calls[1]
        self.assertIn("release/0.9.1", create["args"])
        self.assertEqual(create["args"][create["args"].index("--title") + 1], "Release 0.9.1")
        c = self.out["commit"]
        self.assertTrue(create["body"].startswith(
            f"Solo el flujo ([guía](https://github.com/o/public/blob/{c}/docs/flujo-de-trabajo.md))."))
        self.assertIn("Previous public version: 0.9.0.", create["body"])
        self.assertIn("merge commit", create["body"])
        self.assertEqual(self.out["pr"], "https://github.com/o/public/pull/2")

    def test_an_open_pull_request_gets_the_new_title_and_body(self):
        self.assertEqual(self.publish("--push").returncode, 0)
        self.change({"CHANGELOG.md": CHANGELOG.replace("con un tag.", "con un tag anotado.")})
        self.tag("v0.9.1")
        r = self.publish("--push", "--pr", "o/public", open_pr="7")
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.gh()
        self.assertEqual([c["args"][:4] for c in calls[1:]], [["api", "-X", "PATCH", "repos/o/public/pulls/7"]])
        edit = calls[1]
        self.assertIn("title=Release 0.9.1", edit["args"])
        self.assertIn("con un tag anotado.", edit["body"])
        self.assertEqual(self.out["pr"], "https://github.com/o/public/pull/7")
        self.assertIn("con un tag anotado.", git(self.pub, "log", "-1", "--format=%B", "release/0.9.1"))

    def test_rerun_is_idempotent(self):
        self.assertEqual(self.publish("--push").returncode, 0)
        first = git(self.pub, "rev-parse", "release/0.9.1")
        r = self.publish("--push", "--pr", "o/public", open_pr="7")
        self.assertIn("ya tiene este contenido", r.stdout)
        self.assertEqual((self.out["changed"], self.out["pushed"], self.out["commit"]), ("true", "false", first))
        self.assertEqual(git(self.pub, "rev-parse", "release/0.9.1"), first)
        self.assertEqual(self.gh()[1]["args"][3], "repos/o/public/pulls/7")  # the PR is still refreshed

    def test_tag_must_match_the_version(self):
        self.tag("v0.9.2")
        self.refused(self.publish("--push", tag="v0.9.2"), "no coincide con la versión de su commit (0.9.1")

    def test_lightweight_tag_is_refused(self):
        self.tag("v0.9.1", annotated=False)
        self.refused(self.publish("--push"), "es ligero: tiene que ser anotado")

    def test_tag_must_exist_and_look_like_a_version(self):
        self.refused(self.publish("--push", tag="v0.9.3"), "el tag v0.9.3 no existe")
        self.refused(self.publish("--push", tag="0.9.1"), "no es un tag de versión")

    def test_tag_must_be_on_dev(self):
        git(self.dev, "switch", "-q", "-c", "feat/x")
        self.write(self.dev, {"docs/new.md": "sin mergear\n"})
        git(self.dev, "commit", "-q", "-am", "unmerged")
        self.tag("v0.9.1")
        self.refused(self.publish("--push"), "no está en origin/dev")
        self.refused(self.publish("--push", "--dev-ref", "origin/nope"), "no encuentro la rama origin/nope")

    def test_changelog_section_must_be_there_and_dated(self):
        self.change({"CHANGELOG.md": CHANGELOG.replace("## 0.9.1 (2026-11-05)", "## 0.9.1 (sin publicar)")})
        self.tag("v0.9.1")
        self.refused(self.publish("--push"), "sigue diciendo «sin publicar»")
        self.change({"CHANGELOG.md": "# Cambios\n\n## 0.9.0 (2026-10-01)\n\n- Primera.\n"})
        self.tag("v0.9.1")
        self.refused(self.publish("--push"), "no tiene la sección «## 0.9.1")

    def test_same_version_twice_is_refused(self):
        self.assertEqual(self.publish("--push").returncode, 0)
        self.merge_release("0.9.1")
        r = self.publish("--push")
        self.assertIn("Nada que publicar", r.stdout)
        self.assertEqual(self.out["changed"], "false")
        self.change({"docs/new.md": "cambio sin subir versión\n"})
        self.tag("v0.9.1")
        r = self.publish("--push")
        self.assertEqual(r.returncode, 1)
        self.assertIn("ya está publicada", r.stderr)
        self.change({"orq/__init__.py": '__version__ = "0.9.2"\n',
                     "CHANGELOG.md": CHANGELOG.replace("# Cambios\n", "# Cambios\n\n## 0.9.2 (2026-11-06)\n\n- Más.\n")})
        self.tag("v0.9.2")
        r = self.publish("--push", tag="v0.9.2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(git(self.pub, "rev-parse", "release/0.9.2^"), git(self.pub, "rev-parse", "main"))

    def test_older_version_is_refused(self):
        self.change({"orq/__init__.py": '__version__ = "0.8.9"\n',
                     "CHANGELOG.md": "# Cambios\n\n## 0.8.9 (2026-11-05)\n\n- Vieja.\n"})
        self.tag("v0.8.9")
        self.refused(self.publish("--push", tag="v0.8.9"), "anterior a la publicada")

    def test_identity_must_be_noreply(self):
        self.refused(self.publish("--push", email="pub@" "company.es"), "noreply")

    def test_without_push_nothing_is_uploaded(self):
        r = self.publish()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Sin --push", r.stdout)
        self.assertEqual(git(self.pub, "branch", "--list", "release/*"), "")
        r = self.publish("--pr", "o/public")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--pr necesita --push", r.stderr)
        self.assertEqual(self.gh(), [])


if __name__ == "__main__":
    unittest.main()
