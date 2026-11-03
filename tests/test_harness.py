"""The harness of an orchestra is the one its director runs in: detected from the session, never chosen."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

from tests.support import Pkg, Sandbox

CLAUDE_SID = "c0000000-0000-4000-8000-0000000000aa"
CODEX_TID = "019a0000-0000-7000-8000-0000000000bb"


class HarnessCase(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(Pkg)

    def tearDown(self):
        self.sb.close()

    def orq(self, *args, claude=None, codex=None):
        extra = dict(self.sb.impl.extra_env())
        if codex:
            extra["CODEX_THREAD_ID"] = codex
        return subprocess.run([sys.executable, "-m", "orq", *args], cwd=self.sb.ws, capture_output=True, text=True,
                              env=self.sb.impl.env(claude, extra), timeout=60)

    def board(self, run):
        return json.loads((Path(self.orq("where", run).stdout.strip()) / "board.json").read_text())

    def test_detected_from_the_session(self):
        r = self.orq("init", "c", "--coordinator", "dir-c", claude=CLAUDE_SID)
        self.assertEqual(r.returncode, 0, r.stderr)
        b = self.board("c")
        self.assertEqual((b["harness"], b["coordinator_session"]), ("claude", CLAUDE_SID))
        r = self.orq("init", "x", "--coordinator", "dir-x", codex=CODEX_TID)
        self.assertEqual(r.returncode, 0, r.stderr)
        b = self.board("x")
        self.assertEqual((b["harness"], b["coordinator_session"]), ("codex", CODEX_TID))

    def test_no_option_to_choose_it(self):
        r = self.orq("init", "c", "--coordinator", "d", "--harness", "codex", claude=CLAUDE_SID)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--harness", r.stderr)

    def test_plain_shell_is_refused(self):
        r = self.orq("init", "c", "--coordinator", "d")
        self.assertEqual(r.returncode, 1)
        self.assertIn("se ejecuta desde la sesión que va a ser el director", r.stderr)
        self.assertEqual(self.orq("runs").stdout.strip(), "")
        self.assertFalse((self.sb.ws / ".orquesta/c").exists())

    def test_both_variables_are_ambiguous(self):
        r = self.orq("init", "c", "--coordinator", "d", claude=CLAUDE_SID, codex=CODEX_TID)
        self.assertEqual(r.returncode, 1)
        self.assertIn("dos arneses", r.stderr)

    def test_relay_needs_the_same_harness(self):
        self.assertEqual(self.orq("init", "c", "--coordinator", "dir-c", claude=CLAUDE_SID).returncode, 0)
        r = self.orq("coordinator", "c", "otro", codex=CODEX_TID)
        self.assertEqual(r.returncode, 1)
        self.assertIn("esta orquesta es de Claude Code y esta sesión es de Codex", r.stderr)
        self.assertEqual(self.board("c")["coordinator"], "dir-c")
        r = self.orq("coordinator", "c", "otro", claude="c0000000-0000-4000-8000-0000000000cc")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.board("c")["coordinator"], "otro")


if __name__ == "__main__":
    unittest.main()
