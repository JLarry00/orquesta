"""scripts/publish.py against throwaway repos: a development repo and a bare "public" one."""
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


def git(cwd, *args, email="dev@users.noreply.github.com"):
    env = {**os.environ, "GIT_AUTHOR_NAME": "dev", "GIT_AUTHOR_EMAIL": email, "GIT_COMMITTER_NAME": "dev",
           "GIT_COMMITTER_EMAIL": email, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    return subprocess.run(["git", "-C", str(cwd), *args], env=env, check=True, capture_output=True,
                          text=True).stdout.strip()


class Publish(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="orq-publish-")
        t = Path(self.tmp.name)
        self.dev, self.pub, self.seed = t / "dev", t / "public.git", t / "seed"
        # public repo: one clean commit on main (like the first public import)
        git(t, "init", "-q", "--bare", "-b", "main", str(self.pub))
        git(t, "init", "-q", "-b", "main", str(self.seed))
        self.write(self.seed, {"README.md": "v0\n", "orq/__init__.py": '__version__ = "0.9.0"\n'})
        git(self.seed, "add", "-A")
        git(self.seed, "commit", "-q", "-m", "Initial public release")
        git(self.seed, "push", "-q", str(self.pub), "main")
        # development repo: its own history, with a commit by a non-noreply identity that must not travel
        git(t, "init", "-q", "-b", "main", str(self.dev))
        self.write(self.dev, {"README.md": "v0\n", "orq/__init__.py": '__version__ = "0.9.0"\n'})
        git(self.dev, "add", "-A")
        git(self.dev, "commit", "-q", "-m", "old work", email="someone@" "company.es")
        self.change({"README.md": "v1\n", "orq/__init__.py": '__version__ = "0.9.1"\n', "docs/new.md": "nuevo\n"})

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, repo, files):
        for rel, text in files.items():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text(text)

    def change(self, files, msg="work"):
        self.write(self.dev, files)
        git(self.dev, "add", "-A")
        git(self.dev, "commit", "-q", "-m", msg)

    def publish(self, *args, email=NOREPLY):
        """Runs the script; its GITHUB_OUTPUT values end up in self.out."""
        out = Path(self.tmp.name) / "github-output"
        out.write_text("")
        env = {**os.environ, "PUBLISH_NAME": "pub", "PUBLISH_EMAIL": email, "GIT_CONFIG_GLOBAL": os.devnull,
               "GITHUB_OUTPUT": str(out)}
        r = subprocess.run([sys.executable, str(SCRIPT), "--public", str(self.pub), *args], cwd=self.dev,
                              env=env, capture_output=True, text=True)
        self.out = dict(line.split("=", 1) for line in out.read_text().splitlines())
        return r

    def merge_release(self, v):
        """What merging the release PR does on GitHub: a merge commit on the public main."""
        git(self.seed, "fetch", "-q", str(self.pub), f"release/{v}")
        git(self.seed, "merge", "-q", "--no-ff", "-m", f"Merge pull request #1 from someone/release/{v}", "FETCH_HEAD")
        git(self.seed, "push", "-q", str(self.pub), "main")

    def test_release_commit_has_dev_tree_and_public_parent(self):
        r = self.publish("--push")
        self.assertEqual(r.returncode, 0, r.stderr)
        c = git(self.pub, "rev-parse", "release/0.9.1")
        self.assertEqual(git(self.pub, "rev-parse", f"{c}^{{tree}}"), git(self.dev, "rev-parse", "HEAD^{tree}"))
        self.assertEqual(git(self.pub, "rev-parse", f"{c}^@"), git(self.pub, "rev-parse", "main"))
        self.assertEqual(git(self.pub, "log", "-1", "--format=%an <%ae>|%cn <%ce>|%s", c),
                         f"pub <{NOREPLY}>|pub <{NOREPLY}>|Release 0.9.1")
        self.assertEqual(git(self.pub, "rev-list", "--count", c), "2")  # no development history
        # what the workflow reads to open the pull request
        self.assertEqual(self.out, {"version": "0.9.1", "branch": "release/0.9.1", "commit": c, "changed": "true",
                                    "pushed": "true"})
        self.assertNotIn("company", git(self.pub, "log", "--format=%ae%n%ce", c))
        # the public checks would pass on the new commit
        clone = Path(self.tmp.name) / "clone"
        git(self.tmp.name, "clone", "-q", "-b", "release/0.9.1", str(self.pub), str(clone))
        chk = subprocess.run([sys.executable, str(CHECK), "--repo", str(clone), "--range", "origin/main..HEAD"],
                             capture_output=True, text=True, env={**os.environ, "ORQ_FORBIDDEN_WORDS": "Zarandaja"})
        self.assertEqual(chk.returncode, 0, chk.stdout + chk.stderr)

    def test_rerun_is_idempotent_and_updates_the_branch(self):
        self.assertEqual(self.publish("--push").returncode, 0)
        first = git(self.pub, "rev-parse", "release/0.9.1")
        r = self.publish("--push")
        self.assertIn("ya tiene este contenido", r.stdout)
        self.assertEqual((self.out["changed"], self.out["pushed"]), ("true", "false"))  # the PR must still exist
        self.assertEqual(git(self.pub, "rev-parse", "release/0.9.1"), first)
        self.change({"docs/new.md": "otra vez\n"})  # more work before the release PR is merged
        self.assertEqual(self.publish("--push").returncode, 0)
        self.assertEqual(git(self.pub, "rev-parse", "release/0.9.1^{tree}"), git(self.dev, "rev-parse", "HEAD^{tree}"))

    def test_same_version_twice_is_refused(self):
        self.assertEqual(self.publish("--push").returncode, 0)
        self.merge_release("0.9.1")
        r = self.publish("--push")
        self.assertIn("Nada que publicar", r.stdout)
        self.assertEqual(self.out["changed"], "false")
        self.change({"docs/new.md": "cambio sin subir versión\n"})
        r = self.publish("--push")
        self.assertEqual(r.returncode, 1)
        self.assertIn("ya está publicada", r.stderr)
        self.change({"orq/__init__.py": '__version__ = "0.9.2"\n'})
        r = self.publish("--push")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(git(self.pub, "rev-parse", "release/0.9.2^"), git(self.pub, "rev-parse", "main"))

    def test_older_version_is_refused(self):
        self.change({"orq/__init__.py": '__version__ = "0.8.9"\n'})
        r = self.publish("--push")
        self.assertEqual(r.returncode, 1)
        self.assertIn("anterior a la publicada", r.stderr)
        self.assertEqual(git(self.pub, "branch", "--list", "release/*"), "")

    def test_identity_must_be_noreply(self):
        r = self.publish("--push", email="pub@" "company.es")
        self.assertEqual(r.returncode, 1)
        self.assertIn("noreply", r.stderr)
        self.assertEqual(git(self.pub, "branch", "--list", "release/*"), "")

    def test_without_push_nothing_is_uploaded(self):
        r = self.publish()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Sin --push", r.stdout)
        self.assertEqual(git(self.pub, "branch", "--list", "release/*"), "")


if __name__ == "__main__":
    unittest.main()
