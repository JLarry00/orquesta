"""scripts/release_notes.py: the version and its CHANGELOG section, as the publish and release workflows read them."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.support import REPO

sys.path.insert(0, str(REPO / "scripts"))
import release_notes as rn  # noqa: E402

SCRIPT = REPO / "scripts/release_notes.py"

CHANGELOG = """# Cambios

## 0.9.10 (sin publicar)

- Lo siguiente.

## 0.9.1 (2026-11-05)

Solo el flujo ([guía](docs/flujo-de-trabajo.md)).

- **Publicar:** con un tag ([AGENTS.md](./AGENTS.md), [web](https://example.com), [arriba](#cambios)).

## 0.9.0 (sin publicar; para la prueba)

- Codex.
"""


class Section(unittest.TestCase):
    def test_version_of(self):
        self.assertEqual(rn.version_of('"""x"""\n__version__ = "0.9.1"\n'), "0.9.1")
        with self.assertRaises(rn.NotesError):
            rn.version_of("VERSION = 1\n")

    def test_section_is_the_body_up_to_the_next_version(self):
        body = rn.release_section(CHANGELOG, "0.9.1")
        self.assertTrue(body.startswith("Solo el flujo"))
        self.assertTrue(body.endswith("[arriba](#cambios))."))
        self.assertNotIn("0.9.0", body)
        self.assertNotIn("Lo siguiente", body)  # 0.9.10 is another version, not a prefix match

    def test_missing_section(self):
        with self.assertRaisesRegex(rn.NotesError, "no tiene la sección «## 0.9.2"):
            rn.release_section(CHANGELOG, "0.9.2")
        with self.assertRaisesRegex(rn.NotesError, "no tiene la sección"):
            rn.release_section(CHANGELOG, "0.9")

    def test_unpublished_or_undated_header_is_refused(self):
        with self.assertRaisesRegex(rn.NotesError, "sigue diciendo «sin publicar»"):
            rn.release_section(CHANGELOG, "0.9.10")
        with self.assertRaisesRegex(rn.NotesError, "tiene que ser «## 0.9.1 \\(AAAA-MM-DD\\)»"):
            rn.release_section("## 0.9.1 (noviembre)\n\n- x\n", "0.9.1")
        with self.assertRaisesRegex(rn.NotesError, "tiene que ser"):
            rn.release_section("## 0.9.1\n\n- x\n", "0.9.1")
        with self.assertRaisesRegex(rn.NotesError, "está vacía"):
            rn.release_section("## 0.9.1 (2026-11-05)\n\n## 0.9.0 (2026-10-01)\n- x\n", "0.9.1")

    def test_absolute_links(self):
        out = rn.absolute_links(rn.release_section(CHANGELOG, "0.9.1"), "https://github.com/o/r/blob/v0.9.1/")
        self.assertIn("[guía](https://github.com/o/r/blob/v0.9.1/docs/flujo-de-trabajo.md)", out)
        self.assertIn("[AGENTS.md](https://github.com/o/r/blob/v0.9.1/AGENTS.md)", out)
        self.assertIn("[web](https://example.com)", out)
        self.assertIn("[arriba](#cambios)", out)


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="orq-notes-")
        self.repo = Path(self.tmp.name)
        (self.repo / "orq").mkdir()
        (self.repo / "orq/__init__.py").write_text('__version__ = "0.9.1"\n')
        (self.repo / "CHANGELOG.md").write_text(CHANGELOG)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.repo, capture_output=True, text=True)

    def test_version_and_notes_from_disk(self):
        self.assertEqual(self.run_cli("version").stdout, "0.9.1\n")
        r = self.run_cli("notes", "0.9.1", "--link-base", "https://github.com/o/r/blob/v0.9.1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("(https://github.com/o/r/blob/v0.9.1/docs/flujo-de-trabajo.md)", r.stdout)

    def test_notes_from_a_commit(self):
        git = ["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@users.noreply.github.com"]
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "-q", "-m", "x"], check=True)
        (self.repo / "CHANGELOG.md").write_text("# Cambios\n")  # the disk differs from the commit
        self.assertEqual(self.run_cli("notes", "0.9.1").returncode, 1)
        r = self.run_cli("notes", "0.9.1", "--rev", "HEAD")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("Solo el flujo"))
        self.assertEqual(self.run_cli("version", "--rev", "HEAD").stdout, "0.9.1\n")

    def test_errors_are_messages_not_tracebacks(self):
        r = self.run_cli("notes", "0.9.10")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stderr.splitlines()[0][:22], "release_notes: la cabe")
        self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
