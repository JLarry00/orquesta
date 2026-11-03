"""Unit tests for orq.core and orq.comms (what the golden tests cannot see)."""
import os
import unittest
from pathlib import Path
from unittest import mock

from orq import comms, core

BOARD = {"run": "r", "coordinator": "coord", "coordinator_session": "S-coord",
         "agents": {"a": {"parent": "coord", "session_id": "S-a"},
                    "c": {"parent": "a", "session_id": "S-c"}}}


def env(**kw):
    clean = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "ORQ_HOME")}
    clean.update(kw)
    return mock.patch.dict(os.environ, clean, clear=True)


class TestCaller(unittest.TestCase):
    def test_claude_session(self):
        with env(CLAUDE_CODE_SESSION_ID="S-a"):
            self.assertEqual(core.caller(BOARD), "a")

    def test_codex_thread(self):
        with env(CODEX_THREAD_ID="S-c"):
            self.assertEqual(core.caller(BOARD), "c")

    def test_codex_board_prefers_codex_var(self):
        with env(CLAUDE_CODE_SESSION_ID="S-a", CODEX_THREAD_ID="S-c"):
            self.assertEqual(core.caller({**BOARD, "harness": "codex"}), "c")
            self.assertEqual(core.caller(BOARD), "a")

    def test_plain_shell_is_coordinator(self):
        with env():
            self.assertEqual(core.caller(BOARD), "coordinator")

    def test_stranger(self):
        with env(CLAUDE_CODE_SESSION_ID="S-x"):
            self.assertIsNone(core.caller(BOARD))


class TestHome(unittest.TestCase):
    def test_env_wins(self):
        with env(ORQ_HOME="/tmp/x"):
            self.assertEqual(core.home(), Path("/tmp/x"))

    def test_checkout_defaults_to_dot_orquesta(self):
        with env():
            self.assertEqual(core.home(), Path.home() / ".orquesta")

    def test_installed_layout(self):
        with env(), mock.patch.object(core, "LIB_DIR", Path("/h/.orq/lib")):
            self.assertEqual(core.home(), Path("/h/.orq"))

    def test_tilde(self):
        with mock.patch.object(Path, "home", return_value=Path("/u")):
            self.assertEqual(core.tilde("/u/.orquesta"), "~/.orquesta")
            self.assertEqual(core.tilde("/u2/x"), "/u2/x")


class TestSchema(unittest.TestCase):
    def test_old_board_is_claude(self):
        self.assertEqual(core.harness_of({}), "claude")
        self.assertEqual(core.harness_of({"harness": "codex"}), "codex")


class TestModeFor(unittest.TestCase):
    MATRIX = {"default": "manual", "pairs": {"a<->x": "libre"}}

    def test_renamed_coordinator_needs_session(self):
        board = {**BOARD, "coordinator_session": ""}
        self.assertEqual(comms.mode_for(board, self.MATRIX, "a", "nuevo", lambda n: True)[0], "manual")
        self.assertEqual(comms.mode_for(BOARD, self.MATRIX, "a", "nuevo", lambda n: True)[0], "libre")

    def test_pair_key_is_sorted(self):
        self.assertEqual(comms.pair_key("x", "a"), "a<->x")


if __name__ == "__main__":
    unittest.main()
