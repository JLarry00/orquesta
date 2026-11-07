"""Test support: run an orquesta implementation (v1 or this package) inside a throwaway HOME.

Golden tests pin the behaviour of v1 (the single-file `orq` + `orquesta-gate.py` that lived in
~/.claude/orquesta before this package). Both implementations are run the same way and their output
is normalised (paths, session ids, timestamps) so it can be compared with the files in tests/golden.

- v1 runs only if a real v1 is available (ORQ_V1_DIR, or ~/.claude/orquesta with the v1 code). Its
  files are *copied* into the temporary HOME; the original is never touched or executed in place.
- The package runs with ORQ_HOME=<tmp HOME>/.claude/orquesta, so the paths it writes match v1's.

Set ORQ_GOLDEN_WRITE=1 to regenerate the golden files from v1.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GOLDEN = Path(__file__).resolve().parent / "golden"
V1_MARKER = 'HOME_ORQ = Path.home() / ".claude/orquesta"'
TS_RE = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d")
APPROVER = "Ana"  # the package reads it from config.json; v1 had the approver's name hard-coded
APPROVER_RE = re.compile(r"\b(OK|orden) de [A-ZÁÉÍÓÚÑ]\w*")  # v1 hard-coded a name; the package uses APPROVER
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


V1_MISSING = ("sin la v1 (ORQ_V1_DIR o la instalación antigua): no se vuelve a ejecutar la v1; "
              "el paquete sí se compara con los golden guardados")


def v1_source():
    """Folder with the v1 code, or None if this machine has no v1 (e.g. a clean install)."""
    d = Path(os.environ.get("ORQ_V1_DIR") or Path.home() / ".claude/orquesta").expanduser()
    f = d / "bin/orq"
    try:
        return d if V1_MARKER in f.read_text() else None
    except OSError:
        return None


class Impl:
    name = "?"

    def __init__(self, home):
        self.home = home
        self.orq_home = home / ".claude/orquesta"

    def env(self, sid=None, extra=None):
        env = {k: v for k, v in os.environ.items()
               if k not in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "ORQ_HOME", "PYTHONPATH")}
        env["HOME"] = str(self.home)
        env["PATH"] = f"{self.home / 'stubs'}:/usr/bin:/bin:/usr/sbin:/sbin"
        env["FAKE_AGENTS_FILE"] = str(self.home / "fake-agents.json")
        env["FAKE_OSASCRIPT_LOG"] = str(self.home / "osascript.log")
        env["FAKE_CLAUDE_LOG"] = str(self.home / "claude-p.log")
        if sid:
            env["CLAUDE_CODE_SESSION_ID"] = sid
        env.update(extra or {})
        return env

    def orq(self, *args, sid=None, cwd=None, stdin=None):
        return subprocess.run([sys.executable, *self.orq_argv(), *args], cwd=cwd or self.home, input=stdin,
                              env=self.env(sid, self.extra_env()), capture_output=True, text=True, timeout=60)

    def gate(self, *args, stdin="", sid=None):
        return subprocess.run([sys.executable, str(self.gate_file()), *args], input=stdin,
                              env=self.env(sid, self.extra_env()), capture_output=True, text=True, timeout=60)

    def extra_env(self):
        return {}


class V1(Impl):
    name = "v1"

    def install(self):
        src = v1_source()
        for rel in ("bin/orq", "hooks/orquesta-gate.py"):
            (self.orq_home / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / rel, self.orq_home / rel)

    def orq_argv(self):
        return [str(self.orq_home / "bin/orq")]

    def gate_file(self):
        return self.orq_home / "hooks/orquesta-gate.py"

    def gate_in_settings(self):
        return self.gate_file()


class Pkg(Impl):
    name = "pkg"

    def install(self):
        self.orq_home.mkdir(parents=True, exist_ok=True)

    def extra_env(self):
        return {"ORQ_HOME": str(self.orq_home), "PYTHONPATH": str(REPO)}

    def orq_argv(self):
        return ["-m", "orq"]

    def gate_file(self):
        return REPO / "hooks/claude_gate.py"

    def gate_in_settings(self):
        return REPO / "hooks/claude_gate.py"


def implementations():
    out = []
    if v1_source():
        out.append(V1)
    if (REPO / "orq/__main__.py").exists():
        out.append(Pkg)
    return out


# Stub `claude`: `agents --json` reports $FAKE_AGENTS_FILE; `-p … "/color <c>"` logs its argv and cwd to
# $FAKE_CLAUDE_LOG and answers like Claude Code 2.1.316, or fails if $FAKE_CLAUDE_FAIL is set.
CLAUDE_STUB = r"""#!/bin/sh
if [ "$1 $2" = "agents --json" ]; then cat "$FAKE_AGENTS_FILE" 2>/dev/null || echo "[]"; exit 0; fi
if [ "$1" = "-p" ]; then
  { printf 'cwd=%s\n' "$PWD"; for x in "$@"; do printf '[%s] ' "$x"; done; printf '\n'; } >> "$FAKE_CLAUDE_LOG"
  if [ -n "$FAKE_CLAUDE_FAIL" ]; then echo "Error: simulated failure" >&2; exit 1; fi
  for x in "$@"; do last=$x; done
  echo "Session color set to: ${last#/color }"; exit 0
fi
exit 2
"""


class Sandbox:
    """A temporary HOME with stub `claude` and `osascript` on PATH and one implementation installed."""

    def __init__(self, impl_cls, state_dir="workspace"):
        self.tmp = tempfile.TemporaryDirectory(prefix="orq-test-")
        self.home = Path(self.tmp.name).resolve()
        self.impl = impl_cls(self.home)
        stubs = self.home / "stubs"
        stubs.mkdir()
        write_exec(stubs / "claude", CLAUDE_STUB)
        write_exec(stubs / "osascript", '#!/bin/sh\nprintf "%s\\n---\\n" "$*" >> "$FAKE_OSASCRIPT_LOG"\n')
        self.impl.install()
        (self.impl.orq_home / "PROTOCOL.md").write_text("PROTOCOLO DE PRUEBA\n")
        (self.impl.orq_home / "config.json").write_text(json.dumps({"state_dir": state_dir, "approver": APPROVER}) + "\n")
        self.ws = self.home / "ws"
        self.ws.mkdir()
        self.sids = {}

    def close(self):
        self.tmp.cleanup()

    def live(self, *pairs):
        """Sessions the stub `claude agents --json` reports as alive: (session_id, name)."""
        (self.home / "fake-agents.json").write_text(json.dumps([{"sessionId": s, "name": n} for s, n in pairs]))

    def norm(self, text):
        text = text.replace(str(self.impl.gate_in_settings()), "<GATE>")
        text = text.replace(str(self.home), "<HOME>")
        for name, sid in self.sids.items():
            text = text.replace(sid, f"<SID:{name}>")
        text = UUID_RE.sub("<UUID>", text)
        text = APPROVER_RE.sub(r"\1 de <APROBADOR>", text)
        return TS_RE.sub("<TS>", text)


def write_exec(path, text):
    path.write_text(text)
    path.chmod(0o755)


def golden(name, actual, writer):
    """Expected text for golden file `name`.

    tests/golden/<name> holds v1's output. When the package differs on purpose (see CHANGELOG), its expected
    output is in tests/golden/pkg/<name>, used only for the package.
    ORQ_GOLDEN_WRITE=v1 (or 1) rewrites v1's files from the v1 run; ORQ_GOLDEN_WRITE=pkg writes the package's
    overrides (only where it differs from v1) from the package run. Review the diff before committing.
    """
    base, override = GOLDEN / name, GOLDEN / "pkg" / name
    mode = os.environ.get("ORQ_GOLDEN_WRITE")
    if writer == "v1" and mode in ("1", "v1"):
        base.parent.mkdir(parents=True, exist_ok=True)
        base.write_text(actual)
        return None
    if writer == "pkg" and mode == "pkg":
        if base.exists() and base.read_text() == actual:
            if override.exists():
                override.unlink()
        else:
            override.parent.mkdir(parents=True, exist_ok=True)
            override.write_text(actual)
        return None
    return (override if writer == "pkg" and override.exists() else base).read_text()
