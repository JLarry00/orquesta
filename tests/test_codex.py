"""Codex orchestras (app surface): launch by deep link, join, whoami, to, send, open/resume, last-signal liveness,
and the Codex gate with payloads shaped like Codex's hook schemas (codex-rs/hooks/schema/generated, rust-v0.166.0).
"""
import json
import subprocess
import sys
import unittest
import urllib.parse
from pathlib import Path

from tests.support import REPO, Pkg, Sandbox, write_exec

DIR = "019a0000-0000-7000-8000-00000000d1d1"
W1 = "019a0000-0000-7000-8000-0000000000a1"
W2 = "019a0000-0000-7000-8000-0000000000a2"
OUT = "019a0000-0000-7000-8000-0000000000ff"


class CodexCase(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(Pkg)
        h = self.sb.home
        write_exec(h / "stubs/open", '#!/bin/sh\nprintf "%s\\n" "$*" >> "$HOME/open.log"\n')
        write_exec(h / "stubs/codex", '#!/bin/sh\nfor x in "$@"; do printf "[%s] " "$x"; done >> "$HOME/codex.log"\n'
                                      'echo >> "$HOME/codex.log"\necho queued\n')
        (self.sb.impl.orq_home / "PROTOCOL.codex.md").write_text("PROTOCOLO CODEX DE PRUEBA\n")

    def tearDown(self):
        self.sb.close()

    def orq(self, *args, tid=None, env=None):
        extra = dict(self.sb.impl.extra_env())
        if tid:
            extra["CODEX_THREAD_ID"] = tid
        extra.update(env or {})
        return subprocess.run([sys.executable, "-m", "orq", *args], cwd=self.sb.ws, capture_output=True, text=True,
                              env=self.sb.impl.env(None, extra), timeout=60)

    def ok(self, r):
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def run_dir(self):
        return Path(self.ok(self.orq("where", "r")).stdout.strip())

    def board(self):
        return json.loads((self.run_dir() / "board.json").read_text())

    def init(self, **kw):
        self.ok(self.orq("init", "r", "--coordinator", "dir", "--color", "purple", tid=DIR, **kw))
        return self.run_dir()

    def launch(self, name, *extra):
        d = self.run_dir()
        (d / "agents" / name).mkdir(parents=True, exist_ok=True)
        (d / "agents" / name / "brief.md").write_text("encargo\n")
        return self.orq("launch", "r", name, "--parent", "dir", "--topic", "t", "--effort", "high", *extra, tid=DIR)

    def join(self, name, tid):
        token = json.loads((self.run_dir() / "agents" / name / "pending.json").read_text())["token"]
        return self.orq("join", "r", name, token, tid=tid)

    def opened(self):
        p = self.sb.home / "open.log"
        return p.read_text().splitlines() if p.exists() else []


class TestAppFlow(CodexCase):
    def test_init_records_codex_app(self):
        d = self.init()
        b = self.board()
        self.assertEqual((b["harness"], b["surface"], b["coordinator_session"]), ("codex", "app", DIR))

    def test_launch_opens_a_prefilled_chat_and_join_binds_it(self):
        self.init()
        r = self.ok(self.launch("w1"))
        self.assertIn("elige esfuerzo high y pulsa Enter", r.stdout)
        [link] = self.opened()
        self.assertTrue(link.startswith("codex://new?path="), link)
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(link).query)
        self.assertEqual(q["path"], [str(self.sb.ws)])
        prompt = q["prompt"][0]
        self.assertTrue(prompt.startswith("🟣 w1 · r\n"), prompt)
        token = json.loads((self.run_dir() / "agents/w1/pending.json").read_text())["token"]
        self.assertIn(f"orq join r w1 {token}", prompt)
        ag = self.board()["agents"]["w1"]
        self.assertEqual((ag["session_id"], ag["surface"], ag["model"], ag["effort"]), ("", "app", "", "high"))
        self.assertIn("w1 [running, sin unirse] modelo por defecto/high", self.ok(self.orq("status", "r")).stdout)

        bad = self.orq("join", "r", "w1", "0000", tid=W1)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("la clave no coincide", bad.stderr)
        r = self.ok(self.join("w1", W1))
        self.assertIn("Eres el worker «w1» de la orquesta «r». Tu coordinador es «dir».", r.stdout)
        self.assertIn("PROTOCOLO CODEX DE PRUEBA", r.stdout)
        self.assertEqual(self.board()["agents"]["w1"]["session_id"], W1)
        self.assertFalse((self.run_dir() / "agents/w1/pending.json").exists())
        # whoami: the same text, any time later (after compacting, or in a reopened chat)
        self.assertEqual(self.ok(self.orq("whoami", tid=W1)).stdout, r.stdout)
        self.assertIn("Eres el director de la orquesta «r»", self.ok(self.orq("whoami", tid=DIR)).stdout)
        self.assertEqual(self.orq("whoami", tid=OUT).returncode, 1)
        # one chat, one agent
        self.ok(self.launch("w2", "--no-window"))
        self.assertIn("ya es 'w1'", self.join("w2", W1).stderr)

    def test_no_window_prints_the_link(self):
        self.init()
        r = self.ok(self.launch("w1", "--no-window"))
        self.assertIn("preparado sin abrir: codex://new?path=", r.stdout)
        self.assertEqual(self.opened(), [])

    def test_last_signal_and_cap_by_state(self):
        self.init()
        self.ok(self.launch("w1"))
        self.ok(self.join("w1", W1))
        self.ok(self.orq("log", "r", "w1", "hola", tid=W1))
        self.assertIn("w1 [running, última señal ", self.ok(self.orq("status", "r")).stdout)
        cfg = self.sb.impl.orq_home / "config.json"
        cfg.write_text(json.dumps({**json.loads(cfg.read_text()), "max_alive": 1}))
        r = self.launch("w2")
        self.assertEqual(r.returncode, 1)
        self.assertIn("tope 1", r.stderr)
        self.ok(self.orq("state", "r", "w1", "done", tid=W1))
        self.ok(self.launch("w2"))

    def test_to_send_open_resume(self):
        self.init()
        self.ok(self.launch("w1"))
        self.ok(self.launch("w2"))
        self.ok(self.join("w1", W1))
        self.assertIn("todavía no se ha unido", self.orq("to", "w2", tid=W1).stderr)
        self.ok(self.join("w2", W2))
        self.assertEqual(self.ok(self.orq("to", "dir", tid=W1)).stdout, f"{DIR}\tlibre (coordinador<->worker)\n")
        self.assertEqual(self.ok(self.orq("to", "w2", tid=W1)).stdout, f"{W2}\tmanual (por defecto)\n")
        # orq send: only free pairs (orq runs unsandboxed without asking, so nobody would approve a manual one)
        r = self.orq("send", "w2", "hola", tid=W1)
        self.assertEqual(r.returncode, 1)
        self.assertIn("es manual", r.stderr)
        self.ok(self.orq("send", "dir", "terminado", tid=W1))
        self.assertEqual((self.sb.home / "codex.log").read_text(),
                         f"[queue] [--thread] [{DIR}] [--message] [[de w1] terminado] \n")
        log = [json.loads(l) for l in (self.run_dir() / "messages.log").read_text().splitlines()]
        self.assertEqual([(e["event"], e["from"], e["to"]) for e in log], [("attempt", "w1", "dir"), ("sent", "w1", "dir")])
        # open and resume use the thread's deep link
        self.ok(self.orq("open", "r", "w2", tid=DIR))
        self.ok(self.orq("state", "r", "w1", "stopped", tid=DIR))
        self.ok(self.orq("resume", "r", "w1", tid=DIR))
        self.assertEqual(self.opened()[-2:], [f"codex://threads/{W2}", f"codex://threads/{W1}"])
        self.assertEqual(self.board()["agents"]["w1"]["state"], "running")


class TestLimits(CodexCase):
    def test_cli_surface_is_not_built_yet(self):
        self.ok(self.orq("init", "r", "--coordinator", "dir", tid=DIR, env={"ORQUESTA_SURFACE": "cli"}))
        self.assertEqual(self.board()["surface"], "cli")
        r = self.launch("w1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("la superficie «cli» de Codex todavía no está disponible", r.stderr)
        self.assertEqual(self.board()["agents"], {})

    def test_surface_from_config(self):
        cfg = self.sb.impl.orq_home / "config.json"
        cfg.write_text(json.dumps({**json.loads(cfg.read_text()), "codex": {"surface": "cli"}}))
        self.init()
        self.assertEqual(self.board()["surface"], "cli")

    def test_state_outside_workspace_is_refused(self):
        cfg = self.sb.impl.orq_home / "config.json"
        cfg.write_text(json.dumps({**json.loads(cfg.read_text()), "state_dir": str(self.sb.home / "estado")}))
        r = self.orq("init", "r", "--coordinator", "dir", tid=DIR)
        self.assertEqual(r.returncode, 1)
        self.assertIn("guardan su estado en el workspace", r.stderr)

    def test_dir_is_claude_only(self):
        self.init()
        r = self.launch("w1", "--dir", str(self.sb.home))
        self.assertEqual(r.returncode, 1)
        self.assertIn("--dir no está disponible en Codex", r.stderr)


class TestGate(CodexCase):
    """Payload fields as in pre-tool-use / permission-request / post-tool-use .command.input.schema.json."""

    def setUp(self):
        super().setUp()
        self.init()
        for n, t in (("w1", W1), ("w2", W2)):
            self.ok(self.launch(n, "--no-window"))
            self.ok(self.join(n, t))

    def gate(self, event, sender, to, tool="mcp__codex_app__send_message_to_thread", extra=None, sonda=None):
        payload = {"session_id": sender, "turn_id": "turn-1", "transcript_path": None, "cwd": str(self.sb.ws),
                   "hook_event_name": event, "model": "gpt-x", "permission_mode": "default",
                   "tool_name": tool, "tool_input": {"threadId": to, "prompt": "[de w1] hola"}}
        if event != "PermissionRequest":
            payload["tool_use_id"] = "call-1"
        if event == "PostToolUse":
            payload["tool_response"] = {"threadId": to}
        payload.update(extra or {})
        if sonda:
            (self.sb.impl.orq_home / "sonda").write_text(sonda + "\n")
        return subprocess.run([sys.executable, str(REPO / "hooks/codex_gate.py")], input=json.dumps(payload),
                              capture_output=True, text=True, env=self.sb.impl.env(None, self.sb.impl.extra_env()),
                              timeout=60)

    def log(self):
        return [json.loads(l) for l in (self.run_dir() / "messages.log").read_text().splitlines()]

    def test_free_message(self):
        r = self.gate("PreToolUse", W1, DIR)
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        r = self.gate("PermissionRequest", W1, DIR)
        self.assertEqual(json.loads(r.stdout), {"hookSpecificOutput": {"hookEventName": "PermissionRequest",
                                                                       "decision": {"behavior": "allow"}}})
        self.assertEqual(self.gate("PostToolUse", W1, DIR).stdout, "")
        self.assertEqual([(e["event"], e["from"], e["to"]) for e in self.log()],
                         [("attempt", "w1", "dir"), ("sent", "w1", "dir")])
        self.assertEqual(self.log()[0]["mode"], "libre")

    def test_manual_message_leaves_the_decision_to_codex(self):
        self.gate("PreToolUse", W1, W2, tool="mcp__codex_tui__send_message_to_thread")
        r = self.gate("PermissionRequest", W1, W2, tool="mcp__codex_tui__send_message_to_thread")
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertEqual([(e["event"], e["mode"]) for e in self.log()], [("attempt", "manual")])

    def test_outside_the_orchestra(self):
        r = self.gate("PreToolUse", W1, OUT)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("no es de la orquesta «r»", out["permissionDecisionReason"])
        for ev in ("PreToolUse", "PermissionRequest", "PostToolUse"):  # a chat in no orchestra: no-op
            self.assertEqual(self.gate(ev, OUT, W1).stdout, "")
        self.assertEqual(self.gate("PreToolUse", W1, DIR, tool="Bash", extra={"tool_input": {"command": "ls"}}).stdout, "")
        self.assertEqual(self.log(), [])

    def test_bad_input_never_decides(self):
        r = subprocess.run([sys.executable, str(REPO / "hooks/codex_gate.py")], input="no es json",
                           capture_output=True, text=True, env=self.sb.impl.env(None, self.sb.impl.extra_env()))
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_probe(self):
        r = self.gate("PermissionRequest", OUT, W1, sonda="on")
        self.assertEqual(r.stdout, "")
        r = self.gate("PermissionRequest", OUT, W1, sonda="permitir")
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["decision"], {"behavior": "allow"})
        lines = [json.loads(l) for l in (self.sb.impl.orq_home / "sonda.log").read_text().splitlines()]
        self.assertEqual([(l["sonda"], l["session_id"]) for l in lines], [("on", OUT), ("permitir", OUT)])
        self.ok(self.orq("doctor", "--sonda", "off"))
        self.assertFalse((self.sb.impl.orq_home / "sonda").exists())


if __name__ == "__main__":
    unittest.main()
