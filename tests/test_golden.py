"""Golden tests: the behaviour of v1 that the package must keep.

Each scenario runs once per available implementation (v1 copy and/or this package) and compares
normalised output with tests/golden/*. See tests/support.py.
"""
import json
import sys
import unittest
from pathlib import Path

from orq.colors import PALETTE
from tests.support import APPROVER, Sandbox, golden, implementations

COORD_SID = "c0000000-0000-4000-8000-000000000001"
STRANGER_SID = "e0000000-0000-4000-8000-00000000000e"
NAMES = ["coord", "coord-nuevo", "a", "b", "c", "d", "desconocido"]


def proc(r):
    return f"exit={r.returncode}\n--- stdout\n{r.stdout}--- stderr\n{r.stderr}"


def strip_schema2(case, text):
    """The package adds `schema` and `harness` to new boards; v1 boards have neither."""
    b = json.loads(text)
    case.assertEqual((b.pop("schema"), b.pop("harness")), (2, "claude"))
    case.assertIn(b.pop("color"), PALETTE)
    return json.dumps(b, indent=2, ensure_ascii=False) + "\n"


class GoldenCase(unittest.TestCase):
    def check(self, sb, name, text):
        if name.endswith("board.json") and sb.impl.name == "pkg":
            text = strip_schema2(self, text)
        expected = golden(name, sb.norm(text), sb.impl.name)
        if expected is not None:
            self.assertEqual(sb.norm(text), expected, f"{sb.impl.name}: {name}")

    def each_impl(self):
        impls = implementations()
        if not impls:
            self.skipTest("no implementation available")
        for cls in impls:
            with self.subTest(impl=cls.name):
                yield cls


class TestLaunch(GoldenCase):
    """init → launch (coordinator and sub-coordinator) → errors → status → resume → rename → close."""

    def test_workspace_state(self):
        for cls in self.each_impl():
            sb = Sandbox(cls)
            try:
                self.run_workspace(sb)
            finally:
                sb.close()

    def run_workspace(self, sb):
        sb.sids["coord"] = COORD_SID
        sb.live((COORD_SID, "coord"))
        o = sb.impl.orq
        r = o("init", "r1", "--coordinator", "coord", "--goal", "objetivo de prueba", sid=COORD_SID, cwd=sb.ws)
        self.check(sb, "launch/init.txt", proc(r))
        d = Path(r.stdout.strip())
        self.check(sb, "launch/gitignore.txt", (d.parent / ".gitignore").read_text())

        r = o("launch", "r1", "a1", "--parent", "coord", "--topic", "tema uno", sid=COORD_SID)
        self.check(sb, "launch/no-brief.txt", proc(r))

        extra = sb.home / "extra"
        extra.mkdir()
        (d / "agents/a1").mkdir(parents=True)
        (d / "agents/a1/brief.md").write_text("# Brief: a1\n")
        r = o("launch", "r1", "a1", "--parent", "coord", "--topic", "tema uno", "--model", "opus",
              "--effort", "high", "--why", "porque sí", "--dir", str(extra), "--no-window", sid=COORD_SID)
        board = json.loads((d / "board.json").read_text())
        sb.sids["a1"] = board["agents"]["a1"]["session_id"]
        self.check(sb, "launch/launch-a1.txt", proc(r))

        (d / "agents/a2").mkdir()
        (d / "agents/a2/brief.md").write_text("# Brief: a2\n")
        r = o("launch", "r1", "a2", "--parent", "coord", "--topic", "x", "--no-window", sid=sb.sids["a1"])
        self.check(sb, "launch/subcoord-wrong-parent.txt", proc(r))
        r = o("launch", "r1", "a2", "--parent", "a1", "--topic", "tema dos", "--model", "sonnet",
              "--effort", "medium", "--no-window", sid=sb.sids["a1"])
        board = json.loads((d / "board.json").read_text())
        sb.sids["a2"] = board["agents"]["a2"]["session_id"]
        self.check(sb, "launch/launch-a2.txt", proc(r))

        for n in ("a1", "a2"):
            ad = d / "agents" / n
            for f in ("start.sh", "resume.sh", "settings.json", "system.md", "checkpoint.md"):
                self.check(sb, f"launch/{n}-{f}", (ad / f).read_text())

        r = o("launch", "r1", "a3", "--parent", "coord", "--topic", "x", "--model", "gpt", sid=COORD_SID)
        self.check(sb, "launch/bad-model.txt", proc(r))
        if sb.impl.name == "pkg":  # v1 still accepted xhigh; the package caps effort at high
            r = o("launch", "r1", "a3", "--parent", "coord", "--topic", "x", "--effort", "xhigh", sid=COORD_SID)
            self.assertEqual((r.returncode, r.stderr), (1, "orq: esfuerzo desconocido: xhigh\n"))
        r = o("state", "r1", "a1", "done", sid=sb.sids["a2"])
        self.check(sb, "launch/state-not-allowed.txt", proc(r))
        r = o("log", "r1", "a1", "hola", sid=STRANGER_SID)
        self.check(sb, "launch/log-stranger.txt", proc(r))
        r = o("state", "r1", "a2", "waiting", sid=sb.sids["a1"])
        self.check(sb, "launch/state-child.txt", proc(r))
        r = o("state", "r1", "a2", "dormido", sid=COORD_SID)
        self.check(sb, "launch/state-unknown.txt", proc(r))
        r = o("log", "r1", "a2", "una", "línea", sid=sb.sids["a2"])
        self.check(sb, "launch/log-self.txt", proc(r))
        r = o("comms", "r1", "--pair", "a1", "a2", "libre", sid=sb.sids["a1"])
        self.check(sb, "launch/comms-by-agent.txt", proc(r))
        r = o("comms", "r1", "--pair", "a2", "a1", "libre", sid=COORD_SID)
        self.check(sb, "launch/comms-pair.txt", proc(r))

        sb.live((COORD_SID, "coord"), (sb.sids["a1"], "a1"))
        r = o("status", "r1", "-v")
        self.check(sb, "launch/status.txt", proc(r))
        r = o("resume", "r1", "a1", sid=COORD_SID)
        self.check(sb, "launch/resume-alive.txt", proc(r))
        r = o("resume", "r1", "a2", sid=COORD_SID)
        self.check(sb, "launch/resume-a2.txt", proc(r))
        self.check(sb, "launch/osascript.txt", (sb.home / "osascript.log").read_text())
        if sb.impl.name == "pkg":  # v1 had no colours: sessions were created by start.sh itself
            self.check(sb, "launch/claude-p.txt", (sb.home / "claude-p.log").read_text())

        sb.live((COORD_SID, "coord-nuevo"))
        r = o("status", "r1")
        self.check(sb, "launch/status-renamed.txt", proc(r))
        r = o("init", "r9", "--coordinator", "coord-nuevo", sid=COORD_SID, cwd=sb.ws)
        self.check(sb, "launch/init-second-run.txt", proc(r))
        r = o("close", "r1", sid=sb.sids["a1"])
        self.check(sb, "launch/close-by-agent.txt", proc(r))
        r = o("close", "r1", sid=COORD_SID)
        self.check(sb, "launch/close.txt", proc(r))
        r = o("runs")
        self.check(sb, "launch/runs.txt", proc(r))
        r = o("where", "r1")
        self.check(sb, "launch/where.txt", proc(r))
        r = o("where", cwd=sb.ws)
        self.check(sb, "launch/where-ws.txt", proc(r))
        for f in ("board.json", "comms.json", "messages.log", "agents/a1/log.md", "agents/a2/log.md"):
            self.check(sb, "launch/final-" + f.replace("/", "-"), (d / f).read_text())
        self.check(sb, "launch/runs.json", (sb.impl.orq_home / "runs.json").read_text())

    def test_state_dir_outside_workspace(self):
        for cls in self.each_impl():
            sb = Sandbox(cls)
            try:
                state = sb.home / "estado"
                (sb.impl.orq_home / "config.json").write_text(json.dumps({"state_dir": str(state), "approver": APPROVER}))
                sb.sids["coord"] = COORD_SID
                sb.live((COORD_SID, "coord"))
                r = sb.impl.orq("init", "r2", "--coordinator", "coord", sid=COORD_SID, cwd=sb.ws)
                self.check(sb, "outside/init.txt", proc(r))
                d = Path(r.stdout.strip())
                self.assertFalse((d.parent / ".gitignore").exists())
                (d / "agents/b1").mkdir(parents=True)
                (d / "agents/b1/brief.md").write_text("b1\n")
                r = sb.impl.orq("launch", "r2", "b1", "--parent", "coord", "--topic", "t", "--no-window",
                                sid=COORD_SID)
                sb.sids["b1"] = json.loads((d / "board.json").read_text())["agents"]["b1"]["session_id"]
                self.check(sb, "outside/launch.txt", proc(r))
                for f in ("start.sh", "resume.sh", "settings.json"):
                    self.check(sb, f"outside/b1-{f}", (d / "agents/b1" / f).read_text())
                r = sb.impl.orq("where", cwd=sb.ws)
                self.check(sb, "outside/where-ws.txt", proc(r))
            finally:
                sb.close()


def gate_fixture(sb):
    """A run folder written by hand: coord → a → c → d, coord → b; pairs a<->b libre, b<->c manual."""
    d = sb.ws / ".orquesta/rt"
    (d / "agents").mkdir(parents=True)
    ag = lambda parent: {"parent": parent, "topic": "t", "model": "opus", "effort": "medium",
                         "session_id": f"s-{parent}", "state": "running"}
    board = {"run": "rt", "created": "2026-01-01T00:00:00+01:00", "goal": "", "workspace": str(sb.ws),
             "coordinator": "coord", "coordinator_session": COORD_SID,
             "agents": {"a": ag("coord"), "b": ag("coord"), "c": ag("a"), "d": ag("c")}}
    (d / "board.json").write_text(json.dumps(board))
    (d / "comms.json").write_text(json.dumps({"default": "manual", "pairs": {"a<->b": "libre", "b<->c": "manual"}}))
    (d / "messages.log").touch()
    (sb.impl.orq_home / "runs.json").write_text(json.dumps({"rt": str(d)}))
    sb.live((COORD_SID, "coord-nuevo"))
    return d


MODE_TABLE_SCRIPT = """
import importlib.util, json, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("gate", sys.argv[1])
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
names = json.loads(sys.argv[3])
for s in names:
    for r in names:
        if s != r:
            print(s, "->", r, "=", *g.mode_for(Path(sys.argv[2]), s, r))
"""


class TestGate(GoldenCase):
    def test_mode_for_table(self):
        for cls in self.each_impl():
            sb = Sandbox(cls)
            try:
                d = gate_fixture(sb)
                import subprocess
                r = subprocess.run([sys.executable, "-c", MODE_TABLE_SCRIPT, str(sb.impl.gate_file()), str(d),
                                    json.dumps(NAMES)], env=sb.impl.env(None, sb.impl.extra_env()),
                                   capture_output=True, text=True)
                self.check(sb, "gate/mode_for.txt", proc(r))
            finally:
                sb.close()

    def test_gate_output(self):
        def pay(**ti):
            return json.dumps({"tool_name": "SendMessage", "tool_input": ti})

        for cls in self.each_impl():
            sb = Sandbox(cls)
            try:
                d = gate_fixture(sb)
                rd = ["--run-dir", str(d)]
                cases = [
                    ("a-coord", rd + ["--agent", "a"], pay(to="coord", summary="s", message="hola")),
                    ("a-coord-renamed", rd + ["--agent", "a"], pay(to="coord-nuevo", message="m")),
                    ("a-b-pair-libre", rd + ["--agent", "a"], pay(to="b", message="m")),
                    ("b-c-pair-manual", rd + ["--agent", "b"], pay(to="c", message="m")),
                    ("c-d-child", rd + ["--agent", "c"], pay(to="d", message="m")),
                    ("a-d-default", rd + ["--agent", "a"], pay(to="d", message="m")),
                    ("ref-suffix", rd + ["--agent", "a"], pay(to="b [3fa9c1]", message="m")),
                    ("recipient-content", rd + ["--agent", "d"], pay(recipient=" c ", content="x")),
                    ("unknown-recipient", rd + ["--agent", "a"], pay(to="nadie", message="m")),
                    ("bad-stdin", rd + ["--agent", "a"], "esto no es json"),
                    ("old-format", ["--run", "rt", "--agent", "a"], pay(to="coord", message="m")),
                    ("old-format-unknown-run", ["--run", "nope", "--agent", "a"], pay(to="coord")),
                    ("missing-run-dir", ["--run-dir", str(sb.home / "nada"), "--agent", "a"], pay(to="b")),
                    ("post-str", rd + ["--agent", "a", "--post"],
                     json.dumps({"tool_input": {"to": "coord"}, "tool_response": "ok"})),
                    ("post-dict", ["--run", "rt", "--agent", "a", "--post"],
                     json.dumps({"tool_input": {"to": "b"}, "tool_response": {"success": True}})),
                    ("post-list", rd + ["--agent", "a", "--post"],
                     json.dumps({"tool_input": {"to": "b"}, "tool_response": [1, 2]})),
                    ("post-unknown-run", ["--run", "nope", "--agent", "a", "--post"], pay(to="b")),
                    ("post-bad-stdin", rd + ["--agent", "a", "--post"], "{"),
                ]
                out = []
                for label, args, stdin in cases:
                    r = sb.impl.gate(*args, stdin=stdin)
                    out.append(f"## {label}\n{proc(r)}")
                self.check(sb, "gate/output.txt", "\n".join(out))
                self.check(sb, "gate/messages.log", (d / "messages.log").read_text())
            finally:
                sb.close()


if __name__ == "__main__":
    unittest.main()
