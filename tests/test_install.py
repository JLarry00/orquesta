"""Installer, migration, shims, doctor and undo, on throwaway HOMEs (never the real one)."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.support import REPO, v1_source, write_exec


# Apple's python3 writes bytecode under ~/Library/Caches/com.apple.python: Python's doing, not the installer's.
IGNORED = ("Library",)


def snapshot(root):
    """{relative path: description} of a tree; symlinks are not followed."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        if Path(dirpath) == Path(root):
            dirnames[:] = [d for d in dirnames if d not in IGNORED]
        for n in dirnames + filenames:
            p = Path(dirpath) / n
            rel = str(p.relative_to(root))
            st = p.lstat()
            if p.is_symlink():
                out[rel] = ("link", os.readlink(p))
            elif p.is_dir():
                out[rel] = ("dir", oct(st.st_mode & 0o777))
            else:
                out[rel] = ("file", oct(st.st_mode & 0o777), hashlib.sha256(p.read_bytes()).hexdigest())
    return out


OLD_BOARD = {"run": "vieja", "created": "2026-10-01T10:00:00+02:00", "goal": "una orquesta de la v1",
             "coordinator": "coord", "agents": {"w1": {"parent": "coord", "topic": "t", "model": "opus",
                                                        "effort": "medium", "cwd": "/x", "session_id": "S1",
                                                        "state": "done"}},
             "coordinator_session": "C1"}


class FakeHome:
    def __init__(self, with_v1):
        self.tmp = tempfile.TemporaryDirectory(prefix="orq-install-")
        self.home = Path(self.tmp.name).resolve()
        stubs = self.home / "stubs"
        stubs.mkdir()
        write_exec(stubs / "claude", '#!/bin/sh\necho "[]"\n')
        if with_v1:
            self.make_v1()

    def make_v1(self):
        h = self.home
        leg = h / ".claude/orquesta"
        src = v1_source()
        for rel in ("bin/orq", "hooks/orquesta-gate.py"):
            (leg / rel).parent.mkdir(parents=True, exist_ok=True)
            if src:
                (leg / rel).write_text((src / rel).read_text())
            else:
                (leg / rel).write_text("#!/usr/bin/env python3\n# v1 (simulada)\n")
            (leg / rel).chmod(0o755)
        (leg / "PROTOCOL.md").write_text("# Protocolo v1\n")
        (leg / "config.json").write_text('{\n  "state_dir": "workspace"\n}\n')
        ws = h / "proyecto"
        d = ws / ".orquesta/vieja"
        (d / "agents/w1").mkdir(parents=True)
        (ws / ".orquesta/.gitignore").write_text("*\n")
        (d / "board.json").write_text(json.dumps(OLD_BOARD, indent=2, ensure_ascii=False) + "\n")
        (d / "comms.json").write_text('{"default": "manual", "pairs": {}}\n')
        (d / "messages.log").write_text("")
        (d / "agents/w1/settings.json").write_text('{"hooks": "v1"}\n')
        (leg / "runs.json").write_text(json.dumps({"vieja": str(d), "perdida": str(h / "no-existe")}, indent=2) + "\n")
        for s in ("orquesta-launch", "orquesta-resume"):
            (h / ".claude/skills" / s).mkdir(parents=True)
            (h / ".claude/skills" / s / "SKILL.md").write_text(f"v1 {s}\n")
        (h / ".claude/skills/otra").mkdir()
        (h / ".claude/skills/otra/SKILL.md").write_text("no es nuestra\n")
        (h / ".local/bin").mkdir(parents=True)
        (h / ".local/bin/orq").symlink_to(leg / "bin/orq")
        self.run_dir = d

    def env(self, **kw):
        env = {k: v for k, v in os.environ.items()
               if k not in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "ORQ_HOME", "PYTHONPATH")}
        env.update(HOME=str(self.home), PATH=f"{self.home}/.local/bin:{self.home}/stubs:/usr/bin:/bin:/usr/sbin:/sbin")
        env.update(kw)
        return env

    def run(self, *argv, stdin=None, **env):
        return subprocess.run(list(argv), env=self.env(**env), capture_output=True, text=True, input=stdin,
                              cwd=self.home, timeout=120)

    def install(self, *extra):
        # --arneses fixed so the result doesn't depend on what this machine has installed (later wins)
        return self.run("sh", str(REPO / "install.sh"), "--no-interactivo", "--nombre", "Ana", "--arneses", "claude",
                        *extra)

    def undo(self):
        return self.run("sh", str(REPO / "uninstall.sh"))

    def close(self):
        self.tmp.cleanup()


class TestInstall(unittest.TestCase):
    def setUp(self):
        self.fh = None

    def tearDown(self):
        if self.fh:
            self.fh.close()

    def ok(self, r):
        self.assertEqual(r.returncode, 0, f"\n--- stdout\n{r.stdout}\n--- stderr\n{r.stderr}")
        return r

    def test_empty_home(self):
        fh = self.fh = FakeHome(with_v1=False)
        before = snapshot(fh.home)
        r = self.ok(fh.install())
        self.assertIn("0 errores", r.stdout)
        h = fh.home
        self.assertTrue((h / ".orquesta/lib/orq/cli.py").exists())
        self.assertEqual(os.readlink(h / ".local/bin/orq"), str(h / ".orquesta/bin/orq"))
        self.assertFalse((h / ".claude/orquesta").exists())
        cfg = json.loads((h / ".orquesta/config.json").read_text())
        self.assertEqual((cfg["user"], cfg["approver"], cfg["state_dir"]), ("Ana", "Ana", "workspace"))
        self.assertIn("Ana", (h / ".claude/skills/orquesta-launch/SKILL.md").read_text())
        # the installed orq works from PATH and creates a schema-2 run
        ws = h / "w"
        ws.mkdir()
        r = self.ok(fh.run("orq", "init", "nueva", "--coordinator", "yo", "--workspace", str(ws),
                           CLAUDE_CODE_SESSION_ID="d0000000-0000-4000-8000-000000000001"))
        board = json.loads((Path(r.stdout.strip()) / "board.json").read_text())
        self.assertEqual((board["schema"], board["harness"]), (2, "claude"))
        self.ok(fh.run("orq", "doctor"))
        # house rules can be added and removed on update
        rules = h / "reglas.md"
        rules.write_text("- Regla de prueba.\n")
        self.ok(fh.run("sh", str(REPO / "install.sh"), "--no-interactivo", "--reglas-casa", str(rules)))
        self.assertIn("Regla de prueba", (h / ".orquesta/PROTOCOL.md").read_text())
        self.ok(fh.run("sh", str(REPO / "install.sh"), "--no-interactivo", "--reglas-casa", ""))
        self.assertNotIn("Regla de prueba", (h / ".orquesta/PROTOCOL.md").read_text())
        rules.unlink()
        # re-running updates in place and keeps the config
        r = self.ok(fh.run("sh", str(REPO / "install.sh"), "--no-interactivo"))
        self.assertIn("actualización", r.stdout)
        self.assertEqual(json.loads((h / ".orquesta/config.json").read_text())["user"], "Ana")
        r = self.ok(fh.undo())
        self.assertIn("nueva", r.stdout)  # runs created after install are named on undo
        after = snapshot(fh.home)
        for k in [k for k in after if k == "w" or k.startswith("w/")]:
            del after[k]
        self.assertEqual(after, before)

    def test_migrate_v1_and_undo(self):
        fh = self.fh = FakeHome(with_v1=True)
        h = fh.home
        before = snapshot(h)
        r = self.ok(fh.install("--max-vivos", "3"))
        self.assertIn("0 errores", r.stdout)
        self.assertIn("'perdida' no está", r.stdout)
        leg = h / ".claude/orquesta"
        self.assertIn("orquesta-shim", (leg / "bin/orq").read_text())
        self.assertIn("orquesta-shim", (leg / "hooks/orquesta-gate.py").read_text())
        self.assertEqual(os.readlink(leg / "runs.json"), str(h / ".orquesta/runs.json"))
        self.assertEqual((leg / "PROTOCOL.md").read_text(), (h / ".orquesta/PROTOCOL.md").read_text())
        reg = json.loads((h / ".orquesta/runs.json").read_text())
        self.assertEqual(set(reg), {"vieja", "perdida"})
        board = json.loads((fh.run_dir / "board.json").read_text())
        self.assertEqual((board["schema"], board["harness"], board["workspace"]), (2, "claude", str(h / "proyecto")))
        self.assertEqual((fh.run_dir / "agents/w1/settings.json").read_text(), '{"hooks": "v1"}\n')
        self.assertEqual((h / ".claude/skills/otra/SKILL.md").read_text(), "no es nuestra\n")

        r = self.ok(fh.run("orq", "runs"))
        self.assertIn("vieja\tabierta\tsin color\t1 workers", r.stdout)
        r = self.ok(fh.run("orq", "status", "vieja"))
        self.assertIn("- w1 [done, cerrado]", r.stdout)
        # old agents call the old paths: the shim orq and the shim gate, in both formats
        r = self.ok(fh.run(str(leg / "bin/orq"), "where", "vieja"))
        self.assertEqual(r.stdout.strip(), str(fh.run_dir))
        pay = json.dumps({"tool_input": {"to": "coord", "message": "hola"}})
        for args in (["--run", "vieja"], ["--run-dir", str(fh.run_dir)]):
            r = self.ok(fh.run(sys.executable, str(leg / "hooks/orquesta-gate.py"), *args, "--agent", "w1", stdin=pay))
            self.assertIn('"permissionDecision": "allow"', r.stdout)
        log = [json.loads(l) for l in (fh.run_dir / "messages.log").read_text().splitlines()]
        self.assertEqual([e["event"] for e in log], ["attempt", "attempt"])
        (fh.run_dir / "messages.log").write_text("")  # agents' activity is not part of the undo check
        r = self.ok(fh.run("orq", "doctor"))
        self.assertIn("puerta en seco --run w1 -> coord: allow", r.stdout)

        # orq render keeps the legacy copy of the protocol in step
        (leg / "PROTOCOL.md").write_text("viejo\n")
        r = self.ok(fh.run("orq", "render"))
        self.assertEqual((leg / "PROTOCOL.md").read_text(), (h / ".orquesta/PROTOCOL.md").read_text())

        r = self.ok(fh.undo())
        self.assertEqual(snapshot(h), before)

    def test_undo_without_install(self):
        fh = self.fh = FakeHome(with_v1=False)
        r = fh.undo()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no hay instalación que deshacer", r.stderr)

    def test_refuses_foreign_orq_home(self):
        fh = self.fh = FakeHome(with_v1=False)
        (fh.home / ".orquesta").mkdir()
        (fh.home / ".orquesta/algo").write_text("x")
        r = fh.install()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no es una instalación de orquesta", r.stderr)

    def test_orq_home_override(self):
        fh = self.fh = FakeHome(with_v1=False)
        alt = fh.home / "otro-sitio"
        r = self.ok(fh.run("sh", str(REPO / "install.sh"), "--no-interactivo", "--nombre", "Ana", ORQ_HOME=str(alt)))
        self.assertTrue((alt / "bin/orq").exists())
        self.assertFalse((fh.home / ".orquesta").exists())
        # the installed code finds its home by its own location, without the variable
        r = self.ok(fh.run(str(alt / "bin/orq"), "doctor"))
        self.assertIn(f"ORQ_HOME={alt}", r.stdout)



AGENTS_BEFORE = "# Mis instrucciones\n\n- Responde en español."  # no final newline, on purpose
HOOKS_BEFORE = '{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "mi-hook"}]}]}}'


class TestCodexInstall(unittest.TestCase):
    """The installer respects an existing ~/.codex (AGENTS.md, hooks.json) and --deshacer restores it."""

    def setUp(self):
        self.fh = FakeHome(with_v1=False)
        cx = self.fh.home / ".codex"
        cx.mkdir()
        (cx / "AGENTS.md").write_text(AGENTS_BEFORE)
        (cx / "hooks.json").write_text(HOOKS_BEFORE)
        (cx / "config.toml").write_text('model = "x"\n')

    def tearDown(self):
        self.fh.close()

    def ok(self, r):
        self.assertEqual(r.returncode, 0, f"\n--- stdout\n{r.stdout}\n--- stderr\n{r.stderr}")
        return r

    def install(self):
        return self.ok(self.fh.install("--arneses", "claude,codex", "--superficie-codex", "app"))

    def test_install_and_undo(self):
        h = self.fh.home
        before = snapshot(h)
        r = self.install()
        self.assertIn("0 errores", r.stdout)
        cx = h / ".codex"
        agents = (cx / "AGENTS.md").read_text()
        self.assertTrue(agents.startswith(AGENTS_BEFORE + "\n\n<!-- orquesta:start"), agents)
        self.assertIn("orq whoami", agents)
        hooks = json.loads((cx / "hooks.json").read_text())["hooks"]
        self.assertEqual(hooks["PreToolUse"][0]["hooks"][0]["command"], "mi-hook")  # theirs, untouched
        for ev in ("PreToolUse", "PermissionRequest", "PostToolUse"):
            ours = hooks[ev][-1]
            self.assertEqual(ours["matcher"], "send_message_to_thread$")
            self.assertTrue(ours["hooks"][0]["command"].endswith(".orquesta/lib/hooks/codex_gate.py"))
        rules = (cx / "rules/orquesta.rules").read_text()
        self.assertIn('prefix_rule(pattern=["orq"], decision="allow"', rules)
        self.assertIn('prefix_rule(pattern=["codex", "queue"], decision="forbidden"', rules)
        self.assertIn("send_message_to_thread", (h / ".orquesta/PROTOCOL.codex.md").read_text())
        self.assertIn("chat nuevo de la app de Codex", (h / ".agents/skills/orquesta-launch/SKILL.md").read_text())
        self.assertIn("ventana de Terminal", (h / ".claude/skills/orquesta-launch/SKILL.md").read_text())
        cfg = json.loads((h / ".orquesta/config.json").read_text())
        self.assertEqual((cfg["harnesses"], cfg["codex"]), (["claude", "codex"], {"surface": "app"}))
        # re-running keeps one block and one set of hooks
        self.install()
        self.assertEqual((cx / "AGENTS.md").read_text().count("orquesta:start"), 1)
        self.assertEqual(len(json.loads((cx / "hooks.json").read_text())["hooks"]["PermissionRequest"]), 1)
        self.ok(self.fh.undo())
        self.assertEqual(snapshot(h), before)

    def test_undo_after_the_user_edited_codex_files(self):
        h = self.fh.home
        self.install()
        cx = h / ".codex"
        (cx / "AGENTS.md").write_text((cx / "AGENTS.md").read_text() + "\n- Una línea nueva.\n")
        data = json.loads((cx / "hooks.json").read_text())
        data["hooks"]["Stop"] = [{"hooks": [{"type": "command", "command": "otro"}]}]
        (cx / "hooks.json").write_text(json.dumps(data))
        self.ok(self.fh.undo())
        agents = (cx / "AGENTS.md").read_text()
        self.assertNotIn("orquesta", agents)
        self.assertIn("Una línea nueva", agents)
        self.assertTrue(agents.startswith(AGENTS_BEFORE))
        hooks = json.loads((cx / "hooks.json").read_text())["hooks"]
        self.assertEqual(sorted(hooks), ["PreToolUse", "Stop"])
        self.assertNotIn("codex_gate", json.dumps(hooks))
        self.assertFalse((cx / "rules").exists())

    def test_dropping_codex_on_update_removes_its_pieces(self):
        h = self.fh.home
        before_agents = (h / ".codex/AGENTS.md").read_bytes()
        self.install()
        self.ok(self.fh.install())  # --arneses claude
        self.assertEqual((h / ".codex/AGENTS.md").read_bytes(), before_agents)
        self.assertFalse((h / ".agents").exists())
        self.assertFalse((h / ".codex/rules").exists())


if __name__ == "__main__":
    unittest.main()
