"""Shared state of an orchestra: paths, config, registry, board/comms files and who is calling.

Layout of one orchestra (the run folder, `<workspace>/.orquesta/<run>/` or `<state_dir>/<run>/`):
  board.json      agent tree (parent, topic, model, effort, session, state), plus `schema` and `harness`
  comms.json      communication matrix: default + pairs (libre | manual)
  messages.log    one JSON line per message between agents (written by the gate)
  agents/<n>/     brief.md, checkpoint.md, log.md, result.md, settings.json, start.sh, resume.sh, system.md

The install home (ORQ_HOME, by default ~/.orquesta) holds config.json, runs.json (name -> run folder),
PROTOCOL.md and lib/ (this package).
"""
import datetime as dt
import json
import os
import sys
from pathlib import Path

SCHEMA = 2
DEFAULT_HARNESS = "claude"
STATES = {"running", "waiting", "blocked", "done", "stopped"}
DEFAULT_MAX_ALIVE = 4
DEFAULT_APPROVER = "tu usuario"

PKG_DIR = Path(__file__).resolve().parent
LIB_DIR = PKG_DIR.parent  # <ORQ_HOME>/lib when installed, the repo root when run from a checkout


def home():
    """Install home: $ORQ_HOME; else the home this code is installed in (<home>/lib/orq); else ~/.orquesta."""
    env = os.environ.get("ORQ_HOME")
    if env:
        return Path(env).expanduser()
    if LIB_DIR.name == "lib":
        return LIB_DIR.parent
    return Path.home() / ".orquesta"


def config_path():
    return home() / "config.json"


def registry_path():
    return home() / "runs.json"


def protocol_path(harness="claude"):
    """The rendered protocol. Claude keeps v1's name (old agents' launchers point at it); others get a suffix."""
    return home() / ("PROTOCOL.md" if harness in (None, "claude") else f"PROTOCOL.{harness}.md")


def gate_path():
    return LIB_DIR / "hooks/claude_gate.py"


def tilde(p):
    """`~/...` form of a path under $HOME (permission rules accept both forms)."""
    p, h = str(p), str(Path.home())
    return "~" + p[len(h):] if p == h or p.startswith(h + "/") else p


def now():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def die(msg):
    print(f"orq: {msg}", file=sys.stderr)
    sys.exit(1)


def load(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def save(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def write_atomic(path, text, mode=None):
    """Write via a temp file + rename, so a reader (a hook firing mid-install) never sees half a file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.orq-tmp")
    tmp.write_text(text)
    if mode is not None:
        tmp.chmod(mode)
    tmp.replace(path)


def config():
    return load(config_path(), {}) or {}


def approver():
    return config().get("approver") or DEFAULT_APPROVER


def max_alive():
    return int(config().get("max_alive") or DEFAULT_MAX_ALIVE)


def state_root(workspace):
    """Where a workspace's orchestras live: <workspace>/.orquesta, or config.json's state_dir."""
    sd = config().get("state_dir", "workspace")
    return workspace / ".orquesta" if sd in (None, "", "workspace") else Path(sd).expanduser().resolve()


def registry():
    return load(registry_path(), {})


def find_run(run):
    """Run folder: the registered one; if not registered, ./.orquesta/<run>."""
    p = registry().get(run)
    if p and (Path(p) / "board.json").exists():
        return Path(p)
    local = Path.cwd() / ".orquesta" / run
    return local if (local / "board.json").exists() else None


def run_dir(run):
    d = find_run(run)
    if not d:
        die(f"no existe la orquesta '{run}' (crea una con `orq init {run} --coordinator <tu-nombre>`)")
    return d


def workspace_of(d, board):
    return Path(board.get("workspace") or d.parent.parent)


def harness_of(board):
    """Boards written before schema 2 have no `harness`: they are Claude Code orchestras."""
    return (board or {}).get("harness") or DEFAULT_HARNESS


SESSION_ENVS = {"claude": "CLAUDE_CODE_SESSION_ID", "codex": "CODEX_THREAD_ID"}
HARNESS_NAMES = {"claude": "Claude Code", "codex": "Codex"}


def harness_label(name):
    return HARNESS_NAMES.get(name, name)


def calling_harness():
    """(harness, session id) of the agent session that runs orq, read from its environment; (None, "") in a
    plain shell. An orchestra uses the harness its director runs in: nobody chooses it.

    Both variables set means one harness was started from inside the other, so the caller is ambiguous.
    """
    found = [(h, os.environ[v]) for h, v in SESSION_ENVS.items() if os.environ.get(v)]
    if len(found) > 1:
        die("veo las variables de sesión de dos arneses (" + " y ".join(SESSION_ENVS.values()) + "): no sé si "
            "esta sesión es de Claude Code o de Codex. Ejecútalo desde una sesión abierta fuera del otro arnés")
    return found[0] if found else (None, "")


def session_id(harness=None):
    """Id of the calling agent session: CLAUDE_CODE_SESSION_ID (Claude Code) or CODEX_THREAD_ID (Codex).

    With a harness, its own variable is tried first. Empty string outside any agent (a plain shell).
    """
    names = ["CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID"]
    if harness == "codex":
        names.reverse()
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return ""


def descendants(board, name):
    out, todo = set(), [name]
    while todo:
        cur = todo.pop()
        for n, ag in board["agents"].items():
            if ag["parent"] == cur and n not in out:
                out.add(n)
                todo.append(n)
    return out


def caller(board):
    """Who runs orq: 'coordinator', an agent's name, or None for some other, unrelated agent session.

    Outside any agent (the user's own shell) there is no session id, and that counts as the coordinator.
    """
    sid = session_id(harness_of(board))
    if not sid or sid == board.get("coordinator_session"):
        return "coordinator"
    for n, ag in board["agents"].items():
        if ag["session_id"] == sid:
            return n
    return None


def allow_on(board, target, what):
    """Agents act only on themselves and their descendants; the coordinator, on everyone."""
    who = caller(board)
    if who == "coordinator":
        return
    if who is None:
        die(f"esta sesión no es ni el director ni un worker de la orquesta: no puede {what}")
    if target != who and target not in descendants(board, who):
        die(f"'{who}' no puede {what} de '{target}': solo de sí mismo o de sus workers")


def identity_head(d, run, name, parent):
    return (f"# Tu identidad en la orquesta\n\nEres el worker «{name}» de la orquesta «{run}». "
            f"Tu coordinador es «{parent}». Carpeta de la orquesta: {d}. Tu encargo: {d / 'agents' / name / 'brief.md'}.\n\n")


def find_session(sid):
    """(run, run folder, board, who) of the registered run where session `sid` is the director ('coordinator')
    or a worker (its name); None if it is in none. Closed runs count too (a worker may still be finishing)."""
    if not sid:
        return None
    for run, p in registry().items():
        d = Path(p)
        try:
            board = json.loads((d / "board.json").read_text())
        except (OSError, ValueError):
            continue
        if board.get("coordinator_session") == sid:
            return run, d, board, "coordinator"
        for n, ag in board.get("agents", {}).items():
            if ag.get("session_id") == sid:
                return run, d, board, n
    return None


def touch_signal(d, name):
    """Last sign of life of an agent whose harness can't list live sessions: the time of its last orq call."""
    p = d / "agents" / name / "signal"
    try:
        p.write_text(now() + "\n")
    except OSError:
        pass


def append_log(ad, text):
    with open(ad / "log.md", "a") as f:
        f.write(f"- {now()} | {text}\n")
