"""One colour per open orchestra: assignment, display and the `/color` launch (package only)."""
import json
import subprocess
import sys
import unittest
import uuid
from collections import Counter
from pathlib import Path

from orq import colors
from tests.support import Pkg, Sandbox

COORD = "c0000000-0000-4000-8000-000000000001"


class TestPick(unittest.TestCase):
    def test_first_free(self):
        self.assertEqual(colors.pick(Counter()), ("red", None))
        self.assertEqual(colors.pick(Counter(red=1, green=1)), ("blue", None))

    def test_all_taken_repeats_least_used(self):
        used = Counter({c: 2 for c in colors.PALETTE})
        used["purple"] = 1
        c, warning = colors.pick(used)
        self.assertEqual(c, "purple")
        self.assertIn("repito purple", warning)

    def test_emoji_for_every_colour(self):
        self.assertEqual(set(colors.EMOJI), set(colors.PALETTE))
        self.assertEqual(colors.label("purple"), "🟣 purple")
        self.assertEqual(colors.label(None), "sin color")


class CliCase(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(Pkg)
        self.sb.live((COORD, "dir"))

    def tearDown(self):
        self.sb.close()

    def orq(self, *args, **kw):
        return self.sb.impl.orq(*args, **kw)

    def init(self, run, *extra):
        # each run gets its own director session (one open run per director)
        r = self.orq("init", run, "--coordinator", f"dir-{run}", *extra, sid=str(uuid.uuid4()), cwd=self.sb.ws)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = Path(r.stdout.strip())
        return json.loads((d / "board.json").read_text())["color"], r, d


class TestAssign(CliCase):
    def test_free_taken_closed_and_manual(self):
        c1, r, _ = self.init("uno")
        self.assertEqual(c1, "red")
        self.assertIn("escribe en ella: /color red", r.stderr)
        self.assertEqual(r.stdout.count("\n"), 1)  # stdout stays the run folder only
        c2, _, _ = self.init("dos")
        self.assertEqual(c2, "blue")
        self.assertEqual(self.orq("close", "uno").returncode, 0)
        c3, _, _ = self.init("tres")
        self.assertEqual(c3, "red")  # closing «uno» freed red
        c4, _, _ = self.init("cuatro", "--color", "orange")
        self.assertEqual(c4, "orange")
        c5, _, _ = self.init("cinco")
        self.assertEqual(c5, "green")
        for bad in ("marron", "pink", "cyan"):  # pink and cyan are out: their emoji are hearts
            r = self.orq("init", "seis", "--coordinator", "x", "--color", bad, sid=str(uuid.uuid4()), cwd=self.sb.ws)
            self.assertNotEqual(r.returncode, 0, bad)
        # reopening «uno» while «tres» has red: allowed, with a warning
        r = self.orq("close", "uno", "--reopen")
        self.assertIn("ya usa el color red", r.stderr)

    def test_all_taken(self):
        for i in range(len(colors.PALETTE)):
            self.init(f"r{i}")
        c, r, _ = self.init("extra")
        self.assertEqual(c, "red")
        self.assertIn("los 6 colores están en uso", r.stderr)

    def test_boards_without_colour_take_none(self):
        _, _, d = self.init("vieja")
        b = json.loads((d / "board.json").read_text())
        del b["color"]
        (d / "board.json").write_text(json.dumps(b))
        c, _, _ = self.init("nueva")
        self.assertEqual(c, "red")

    def test_status_and_runs_show_it(self):
        self.init("uno", "--color", "purple")
        self.assertIn("Orquesta uno · 🟣 purple", self.orq("status", "uno").stdout)
        self.assertIn("uno\tabierta\t🟣 purple\t0 workers", self.orq("runs").stdout)


class TestLaunch(CliCase):
    def brief(self, d, name):
        (d / "agents" / name).mkdir(parents=True)
        (d / "agents" / name / "brief.md").write_text("encargo\n")

    def test_session_created_in_workspace_then_resumed(self):
        _, _, d = self.init("uno", "--color", "yellow")
        self.brief(d, "w1")
        elsewhere = self.sb.home / "otra"
        elsewhere.mkdir()
        r = self.orq("launch", "uno", "w1", "--parent", "dir-uno", "--topic", "t", "--model", "haiku",
                     "--no-window", cwd=elsewhere)
        self.assertEqual(r.returncode, 0, r.stderr)
        sid = json.loads((d / "board.json").read_text())["agents"]["w1"]["session_id"]
        log = (self.sb.home / "claude-p.log").read_text()
        self.assertEqual(log, f"cwd={self.sb.ws}\n[-p] [--session-id] [{sid}] [-n] [w1] [--model] [haiku] "
                              "[/color yellow] \n")
        start = (d / "agents/w1/start.sh").read_text()
        self.assertIn(f"exec claude --resume {sid} -n w1 --model haiku", start)
        self.assertTrue(start.rstrip().endswith("Empieza."))
        self.assertIn(f"exec claude --resume {sid} -n w1", (d / "agents/w1/resume.sh").read_text())

    def test_failure_aborts_cleanly(self):
        _, _, d = self.init("uno")
        self.brief(d, "w1")
        r = subprocess.run([sys.executable, "-m", "orq", "launch", "uno", "w1", "--parent", "dir-uno", "--topic", "t",
                            "--no-window"], cwd=self.sb.home, capture_output=True, text=True,
                           env=self.sb.impl.env(None, {**self.sb.impl.extra_env(), "FAKE_CLAUDE_FAIL": "1"}))
        self.assertEqual(r.returncode, 1)
        self.assertIn("no he podido crear la sesión de 'w1' con el color red", r.stderr)
        self.assertIn("simulated failure", r.stderr)
        self.assertNotIn("w1", json.loads((d / "board.json").read_text())["agents"])
        self.assertFalse((d / "agents/w1/start.sh").exists())

    def test_board_without_colour_launches_like_v1(self):
        _, _, d = self.init("vieja")
        b = json.loads((d / "board.json").read_text())
        del b["color"]
        (d / "board.json").write_text(json.dumps(b))
        self.brief(d, "w1")
        r = self.orq("launch", "vieja", "w1", "--parent", "dir-vieja", "--topic", "t", "--no-window")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.sb.home / "claude-p.log").exists())
        self.assertIn("exec claude --session-id ", (d / "agents/w1/start.sh").read_text())


if __name__ == "__main__":
    unittest.main()
