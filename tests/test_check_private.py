"""scripts/check-private.py on throwaway git repos: clean passes, each kind of private data fails."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.support import REPO

SCRIPT = REPO / "scripts/check-private.py"
NOREPLY = "1+test@users.noreply.github.com"
WORD = "Zarandaja"  # stands in for a private name
# Built from pieces so that this file passes the filter when it checks the repo itself.
BAD_EMAIL = "ana@" "empresa.es"
BAD_HOME = "/Users/" "pepe"


class CheckPrivate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="orq-private-")
        self.repo = Path(self.tmp.name)
        self.git("init", "-q", "-b", "main")
        self.commit({"README.md": "hola\n"})
        self.base = self.head()

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args, email=NOREPLY, name="tester"):
        env = {**os.environ, "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_COMMITTER_NAME": name,
               "GIT_COMMITTER_EMAIL": email, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
        return subprocess.run(["git", "-C", str(self.repo), *args], env=env, check=True, capture_output=True,
                              text=True).stdout

    def head(self):
        return self.git("rev-parse", "HEAD").strip()

    def commit(self, files, **who):
        for rel, text in files.items():
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / rel).write_text(text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "change", **who)

    def check(self, *args, words=WORD):
        env = {k: v for k, v in os.environ.items() if k != "ORQ_FORBIDDEN_WORDS"}
        if words is not None:
            env["ORQ_FORBIDDEN_WORDS"] = words
        return subprocess.run([sys.executable, str(SCRIPT), "--repo", str(self.repo),
                               "--range", f"{self.base}..HEAD", *args], env=env, capture_output=True, text=True)

    def assertFinds(self, kind):
        r = self.check()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(kind, r.stdout)
        self.assertNotIn(WORD, r.stdout)  # never echoed: CI logs of a public repo are public
        return r

    def test_clean_repo_passes(self):
        self.commit({"docs/a.md": "Escribe a 1+x@users.noreply.github.com o a alguien@example.com o a b@foo.test.\n"
                                  "Ruta: /Users/<nombre>/proyecto y /home/runner/work\n"})
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("2 archivos y 1 commits", r.stdout)

    def test_private_word_in_a_file_and_in_its_name(self):
        self.commit({"notas.md": f"saludos de {WORD.lower()}\n", f"{WORD}.txt": "x\n"})
        r = self.assertFinds("palabra privada")
        self.assertIn("notas.md:1: palabra privada (n.º 1 de la lista)", r.stdout)
        self.assertIn("palabra privada en el nombre del archivo", r.stdout)

    def test_author_email_that_is_not_noreply(self):
        self.commit({"a.txt": "x\n"}, email=BAD_EMAIL)
        r = self.assertFinds("correo del autor no es noreply de GitHub")
        self.assertNotIn(BAD_EMAIL, r.stdout)

    def test_private_word_in_author_name(self):
        self.commit({"a.txt": "x\n"}, name=f"{WORD} Pérez")
        self.assertFinds("palabra privada en el nombre de autor")

    def test_email_in_a_file(self):
        self.commit({"a.txt": f"contacto: {BAD_EMAIL}\n"})
        self.assertFinds("a.txt:1: correo")

    def test_personal_path(self):
        self.commit({"a.sh": f"cd {BAD_HOME}/Documents\n"})
        self.assertFinds("a.sh:1: ruta personal")

    def test_fake_tokens(self):
        fake = {"gh.txt": "ghp_" + "a1B2" * 9, "ant.txt": "sk-ant-" + "x" * 30,
                "pem.txt": "-----BEGIN OPENSSH " + "PRIVATE KEY-----"}
        self.commit(fake)
        r = self.assertFinds("token de GitHub")
        self.assertIn("clave de Anthropic", r.stdout)
        self.assertIn("clave privada", r.stdout)
        self.assertNotIn(fake["gh.txt"], r.stdout)

    def test_commit_message(self):
        (self.repo / "a.txt").write_text("x\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "fix\n\nvisto en /home/" "pepe/x")
        self.assertFinds("(mensaje, línea 3): ruta personal")

    def test_old_commits_outside_the_range_are_not_checked(self):
        self.commit({"a.txt": "x\n"}, email=BAD_EMAIL)
        self.base = self.head()
        self.commit({"b.txt": "y\n"})
        self.assertEqual(self.check().returncode, 0)

    def test_symlink_target_and_binary_file(self):
        (self.repo / "enlace").symlink_to(f"{BAD_HOME}/notas")
        (self.repo / "datos.bin").write_bytes(b"\0\1" + WORD.encode() + b"\0")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "binary and link")
        r = self.assertFinds("enlace (enlace):1: ruta personal")
        self.assertIn("datos.bin:1: palabra privada", r.stdout)

    def test_checks_what_is_committed_not_the_working_copy(self):
        self.commit({"a.txt": f"hola {WORD}\n"})
        (self.repo / "a.txt").write_text("hola\n")  # cleaned, but not committed: the push still sends it
        r = self.assertFinds("a.txt:1: palabra privada")
        self.assertIn("cambios sin commitear", r.stdout)

    def test_local_default_range_and_files_only(self):
        remote = Path(self.tmp.name) / "remote.git"
        self.git("init", "-q", "--bare", str(remote))
        self.git("push", "-q", str(remote), "main")
        self.git("remote", "add", "origin", str(remote))
        self.git("fetch", "-q", "origin")
        self.commit({"a.txt": "x\n"}, email=BAD_EMAIL)  # not pushed yet
        env = {**os.environ, "ORQ_FORBIDDEN_WORDS": WORD}
        r = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(self.repo)], env=env, capture_output=True,
                           text=True)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("correo del autor", r.stdout)
        r = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(self.repo), "--range", "none"], env=env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("0 commits", r.stdout)

    def test_words_required_in_ci(self):
        r = self.check("--require-words", words=None)
        self.assertEqual(r.returncode, 2)
        self.assertIn("FORBIDDEN_WORDS", r.stderr)
        self.assertEqual(self.check(words=None).returncode, 0)


if __name__ == "__main__":
    unittest.main()
