"""orq: CLI de la orquesta (un director y sus workers, cada uno en su propia sesión del mismo arnés).

Cada orquesta pertenece a un workspace (la carpeta desde la que se hace `orq init`, o --workspace). Los
workers se lanzan siempre en ese workspace. El estado va en <workspace>/.orquesta/<run>/, o en
<state_dir>/<run>/ si config.json fija "state_dir" a una ruta. Ver orq/core.py para el formato.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from orq import __version__, colors, comms, core, harness, msglog
from orq.comms import MODES, pair_key
from orq.core import die, load, now, save

ACTIVE = {"running", "waiting", "blocked"}  # states that count toward the cap when liveness is unknown


def check_one_run(sid, force, except_run=None):
    """Un director lleva una sola orquesta abierta: así no se le mezclan los contextos."""
    if not sid or force:
        return
    for name, p in core.registry().items():
        b = load(Path(p) / "board.json")
        if name != except_run and b and b.get("coordinator_session") == sid and not b.get("closed"):
            die(f"esta sesión ya dirige la orquesta '{name}', que sigue abierta. Una orquesta por director: "
                f"abre otro chat para esta, o ciérrala antes con `orq close {name}` "
                f"(--force solo con OK de {core.approver()})")


def adapter(board):
    return harness.get(core.harness_of(board))


def by_signal(board):
    h = adapter(board)
    return h is not None and h.LIVENESS == "signal"


def live_sessions(board):
    h = adapter(board)
    return h.live_sessions() if h else None


def live_unknown(board):
    """Why liveness is unknown, for the warnings."""
    h = adapter(board)
    if h is None:
        return f"{core.harness_label(core.harness_of(board))} aún no está disponible"
    return h.LIVE_SOURCE if by_signal(board) else f"falla {h.LIVE_SOURCE}"


def require_live(board, force):
    live = live_sessions(board)
    if live is None and not force and not by_signal(board):
        die(f"no puedo saber qué agentes están vivos ({live_unknown(board)}), así que no puedo "
            f"comprobar el tope. Usa --force solo con OK de {core.approver()}")
    return live


def rename_everywhere(d, board, old, new):
    """Cambia el nombre de un participante en board.json y comms.json."""
    if board["coordinator"] == old:
        board["coordinator"] = new
    for ag in board["agents"].values():
        if ag["parent"] == old:
            ag["parent"] = new
    save(d / "board.json", board)
    comms = load(d / "comms.json")
    pairs = {}
    for k, v in comms["pairs"].items():
        pairs[pair_key(*(new if x == old else x for x in k.split("<->")))] = v
    comms["pairs"] = pairs
    save(d / "comms.json", comms)


def sync_coordinator(d, board, live):
    """El nombre de una sesión cambia al reiniciarse, su id no: si el director se llama distinto, se actualiza."""
    sid = board.get("coordinator_session")
    if not live or not sid or sid not in live:
        return
    name = live[sid]
    if name and name != board["coordinator"]:
        print(f"orq: el director ahora se llama '{name}' (antes '{board['coordinator']}'); board actualizado",
              file=sys.stderr)
        rename_everywhere(d, board, board["coordinator"], name)


def cmd_init(a):
    if a.run in core.registry() or core.find_run(a.run):
        die(f"la orquesta '{a.run}' ya existe")
    ws = Path(a.workspace or os.getcwd()).expanduser().resolve()
    if not ws.is_dir():
        die(f"no existe el workspace {ws}")
    h_name, sid = core.calling_harness()
    if not h_name:
        die("`orq init` se ejecuta desde la sesión que va a ser el director (un chat de Claude Code o de Codex), "
            "no desde una terminal normal: la orquesta usa el arnés de esa sesión, y sus workers también")
    check_one_run(sid, a.force)
    extra = {}
    if h_name == "codex":
        if core.config().get("state_dir", "workspace") not in (None, "", "workspace"):
            die("las orquestas de Codex guardan su estado en el workspace (<workspace>/.orquesta): sus agentes "
                "trabajan con sandbox y no podrían escribir fuera. Quita state_dir de config.json")
        extra["surface"] = harness.codex.calling_surface() or core.config().get("codex", {}).get("surface") or "app"
    color, warning = (a.color, None) if a.color else colors.pick(colors.in_use(core.registry()))
    root = core.state_root(ws)
    d = root / a.run
    (d / "agents").mkdir(parents=True)
    if root == ws / ".orquesta" and not (root / ".gitignore").exists():
        (root / ".gitignore").write_text("# estado local de la orquesta: fuera de git\n*\n")
    save(d / "board.json", {"run": a.run, "schema": core.SCHEMA, "harness": h_name, **extra, "color": color,
                            "created": now(), "goal": a.goal or "", "workspace": str(ws), "coordinator": a.coordinator,
                            "coordinator_session": sid, "agents": {}})
    save(d / "comms.json", {"default": "manual", "pairs": {}})
    (d / "messages.log").touch()
    reg = core.registry()
    reg[a.run] = str(d)
    core.registry_path().parent.mkdir(parents=True, exist_ok=True)
    save(core.registry_path(), reg)
    if warning:
        print(f"orq: aviso: {warning}", file=sys.stderr)
    h = harness.get(h_name)
    print(f"orq: color de la orquesta: {colors.label(color)}. {h.color_hint(color)}", file=sys.stderr)
    if extra.get("surface") and extra["surface"] not in harness.codex.BUILT_SURFACES:
        print(f"orq: aviso: orquesta de Codex en la superficie «{extra['surface']}», que orq todavía no sabe "
              "lanzar (de momento solo la app)", file=sys.stderr)
    print(d)


def check_cap(board, live, force):
    if force:
        return
    if by_signal(board):  # can't see who is alive: count the agents that are not done or stopped
        alive = [n for n, ag in board["agents"].items() if ag.get("state") in ACTIVE]
    elif live is None:
        return
    else:
        alive = [n for n, ag in board["agents"].items() if ag.get("session_id") in live]
    cap = core.max_alive()
    if len(alive) >= cap:
        die(f"ya hay {len(alive)} agentes vivos ({', '.join(alive)}); tope {cap}. "
            f"Cierra alguno o usa --force con OK de {core.approver()}")


def cmd_launch(a):
    d = core.run_dir(a.run)
    board = load(d / "board.json")
    h = harness.require(core.harness_of(board), "lanzar workers")
    live = require_live(board, a.force)
    sync_coordinator(d, board, live)
    who = core.caller(board)
    if who is None:
        die("esta sesión no es ni el director ni un worker de la orquesta: no puede lanzar workers")
    if who != "coordinator" and a.parent != who:
        die(f"'{who}' solo puede lanzar workers suyos (--parent {who})")
    name = a.name
    if name in board["agents"] or name == board["coordinator"]:
        die(f"ya hay un agente '{name}' en esta orquesta")
    if a.parent != board["coordinator"] and a.parent not in board["agents"]:
        die(f"el coordinador '{a.parent}' no está en la orquesta")
    if a.model is None:
        a.model = h.DEFAULT_MODEL
    models = h.models()
    if models is not None and a.model not in models:
        die(f"modelo desconocido: {a.model}")
    if a.effort not in h.efforts():
        die(f"esfuerzo desconocido: {a.effort}")
    ad = d / "agents" / name
    brief = ad / "brief.md"
    if not brief.exists():
        die(f"falta el encargo: escribe {brief} antes de lanzar")
    ws = core.workspace_of(d, board)
    cwd = str(ws)
    if not ws.is_dir():
        die(f"no existe el workspace {cwd}")
    extra = []
    for x in a.dir or []:
        p = Path(x).expanduser().resolve()
        if not p.is_dir():
            die(f"no existe el directorio {p}")
        extra.append(str(p))

    check_cap(board, live, a.force)

    job = SimpleNamespace(d=d, board=board, run=a.run, name=name, parent=a.parent, model=a.model, effort=a.effort,
                          ws=ws, ad=ad, extra=extra, color=board.get("color"), no_window=a.no_window)
    sid = h.prepare(job)
    for f, head in (("checkpoint.md", f"# {name}: checkpoint\n\n(sin checkpoint aún)\n"),
                    ("log.md", f"# {name}: log\n\n")):
        if not (ad / f).exists():
            (ad / f).write_text(head)

    entry = {"parent": a.parent, "topic": a.topic, "model": a.model, "effort": a.effort,
             "why": a.why or "", "cwd": cwd, "dirs": extra, "session_id": sid, "state": "running",
             "launched_at": now()}
    if board.get("surface"):
        entry["surface"] = board["surface"]
    board["agents"][name] = entry
    save(d / "board.json", board)
    core.append_log(ad, f"lanzado por {a.parent} ({a.model or 'modelo por defecto'}/{a.effort}) en {cwd}")
    h.open_new(job, sid)


def cmd_resume(a):
    d = core.run_dir(a.run)
    board = load(d / "board.json")
    ag = board["agents"].get(a.name) or die(f"no hay agente '{a.name}'")
    h = harness.require(core.harness_of(board), "reabrir workers")
    core.allow_on(board, a.name, "reabrir agentes")
    live = require_live(board, a.force)
    sync_coordinator(d, board, live)
    if live is not None and ag["session_id"] in live:
        die(f"'{a.name}' ya está vivo; {h.FIND_LIVE}")
    if not (by_signal(board) and ag["state"] in ACTIVE):  # already counted when liveness is by signal
        check_cap(board, live, a.force)
    h.reopen(d, board, a.run, a.name)
    if ag["state"] == "stopped":
        ag["state"] = "running"
        save(d / "board.json", board)


def signal_text(d, name, ag):
    if not ag.get("session_id"):
        return "sin unirse"
    p = d / "agents" / name / "signal"
    if not p.exists():
        return "sin señales"
    return f"última señal {p.read_text().strip()}"


def first_lines(path, n):
    if not path.exists():
        return []
    lines = [l for l in path.read_text().splitlines() if l.strip() and not l.startswith("# ")]
    return lines[:n]


def cmd_status(a):
    d = core.run_dir(a.run)
    board = load(d / "board.json")
    live = live_sessions(board)
    sync_coordinator(d, board, live)
    comms = load(d / "comms.json")
    if live is None and not by_signal(board):
        print(f"orq: aviso: no puedo saber qué agentes están vivos ({live_unknown(board)})", file=sys.stderr)
    elif live is not None and board.get("coordinator_session") and board["coordinator_session"] not in live:
        print("orq: aviso: la sesión del director está cerrada; los avisos de sus workers no llegarán. "
              "Ábrela de nuevo o toma el relevo con `orq coordinator`", file=sys.stderr)
    closed = f", cerrada {board['closed']}" if board.get("closed") else ""
    col = f" · {colors.label(board['color'])}" if board.get("color") else ""
    if core.harness_of(board) != "claude":
        col += f" · {core.harness_label(core.harness_of(board))}"
        if board.get("surface"):
            col += f" ({board['surface']})"
    print(f"Orquesta {board['run']}{col}  (creada {board['created']}{closed})")
    print(f"Workspace: {core.workspace_of(d, board)}   Estado: {d}")
    if board.get("goal"):
        print(f"Objetivo: {board['goal']}")
    children = {}
    for n, ag in board["agents"].items():
        children.setdefault(ag["parent"], []).append(n)

    def show(node, depth):
        for n in children.get(node, []):
            ag = board["agents"][n]
            if by_signal(board):
                alive = signal_text(d, n, ag)
            else:
                alive = "?" if live is None else ("vivo" if ag["session_id"] in live else "cerrado")
            res = " · result.md" if (d / "agents" / n / "result.md").exists() else ""
            model = ag["model"] or "modelo por defecto"
            print(f"{'  ' * depth}- {n} [{ag['state']}, {alive}] {model}/{ag['effort']} · {ag['topic']}{res}")
            if a.verbose:
                for l in first_lines(d / "agents" / n / "checkpoint.md", 4):
                    print(f"{'  ' * depth}    | {l}")
            show(n, depth + 1)

    print(f"- {board['coordinator']} [director]")
    show(board["coordinator"], 1)
    if comms["pairs"]:
        print(f"Comunicación (por defecto {comms['default']}): " +
              ", ".join(f"{k}={v}" for k, v in comms["pairs"].items()))
    else:
        print(f"Comunicación: {comms['default']} para todo salvo coordinador<->worker (siempre libre)")


def cmd_comms(a):
    d = core.run_dir(a.run)
    comms = load(d / "comms.json")
    if (a.default or a.pair) and core.caller(load(d / "board.json")) != "coordinator":
        die(f"solo el director (por orden de {core.approver()}) puede cambiar la matriz de comunicación")
    if a.default:
        comms["default"] = a.default
    if a.pair:
        x, y, mode = a.pair
        if mode not in MODES:
            die("el modo es libre o manual")
        comms["pairs"][pair_key(x, y)] = mode
    save(d / "comms.json", comms)
    print(json.dumps(comms, indent=2, ensure_ascii=False))


def cmd_state(a):
    d = core.run_dir(a.run)
    board = load(d / "board.json")
    if a.name not in board["agents"]:
        die(f"no hay agente '{a.name}'")
    core.allow_on(board, a.name, "cambiar el estado")
    sync_coordinator(d, board, live_sessions(board))
    if a.state not in core.STATES:
        die(f"estado desconocido; usa uno de {', '.join(sorted(core.STATES))}")
    board["agents"][a.name]["state"] = a.state
    save(d / "board.json", board)
    core.append_log(d / "agents" / a.name, f"estado -> {a.state}")


def cmd_log(a):
    d = core.run_dir(a.run)
    ad = d / "agents" / a.name
    if not ad.is_dir():
        die(f"no hay agente '{a.name}'")
    core.allow_on(load(d / "board.json"), a.name, "escribir en el log")
    core.append_log(ad, " ".join(a.text))


def cmd_coordinator(a):
    """Relevo: esta sesión pasa a ser la del director (p. ej. si la anterior se cerró para siempre)."""
    d = core.run_dir(a.run)
    board = load(d / "board.json")
    h_name, sid = core.calling_harness()
    if not sid:
        die("ejecútalo desde la sesión que va a ser el director")
    if h_name != core.harness_of(board):
        die(f"esta orquesta es de {core.harness_label(core.harness_of(board))} y esta sesión es de "
            f"{core.harness_label(h_name)}: el director tiene que ser del mismo arnés que sus workers")
    if any(ag["session_id"] == sid for ag in board["agents"].values()):
        die("un worker de la orquesta no puede hacerse director")
    check_one_run(sid, a.force, except_run=a.run)
    old = board["coordinator"]
    board["coordinator_session"] = sid
    rename_everywhere(d, board, old, a.name)
    print(f"director: '{old}' -> '{a.name}' (sesión {sid})")


def cmd_close(a):
    """Marca la orquesta como cerrada (o la reabre): libera al director para llevar otra."""
    d = core.run_dir(a.run)
    board = load(d / "board.json")
    if core.caller(board) != "coordinator":
        die("solo el director puede cerrar o reabrir la orquesta")
    if a.reopen:
        check_one_run(board.get("coordinator_session"), a.force, except_run=a.run)
        board.pop("closed", None)
        if board.get("color") and colors.in_use(core.registry(), except_run=a.run).get(board["color"]):
            print(f"orq: aviso: otra orquesta abierta ya usa el color {board['color']}", file=sys.stderr)
    else:
        board["closed"] = now()
    save(d / "board.json", board)
    print(f"orquesta '{a.run}' {'reabierta' if a.reopen else 'cerrada'}")


def cmd_runs(a):
    for name, p in sorted(core.registry().items()):
        b = load(Path(p) / "board.json")
        if not b:
            print(f"{name}\t(no encontrada en {p})")
            continue
        st = "cerrada" if b.get("closed") else "abierta"
        print(f"{name}\t{st}\t{colors.label(b.get('color'))}\t{len(b['agents'])} workers\t{b.get('goal', '')}\n\t{p}")


def cmd_where(a):
    """Ruta del estado de una orquesta, o dónde se crearían las de este workspace."""
    print(core.run_dir(a.run) if a.run else core.state_root(Path.cwd().resolve()))


def cmd_render(a):
    """Vuelve a generar el protocolo y las skills con config.json (p. ej. tras editar las reglas de la casa)."""
    from orq import render
    try:
        outs = render.outputs(core.config())
    except render.RenderError as e:
        die(str(e))
    from orq import setup
    if setup.legacy_state() == "shims":  # the copy old agents read
        outs.append((setup.legacy_dir() / "PROTOCOL.md", outs[0][1]))
    for path, text in outs:
        core.write_atomic(path, text)
        print(f"escrito {path}")


def cmd_migrate(a):
    """Añade schema, harness y workspace a los board.json registrados que no los tengan (sin quitar nada)."""
    from orq import setup
    manifest = setup.load_manifest()
    if not setup.migrate_runs(manifest, dry_run=a.dry_run):
        print("nada que migrar")
    elif manifest is not None and not a.dry_run:
        setup.save_manifest(manifest)


def whoami_text(run, d, board, who):
    h = core.harness_of(board)
    proto = core.protocol_path(h)
    body = proto.read_text() if proto.exists() else f"(falta el protocolo: {proto}; ejecuta `orq render`)\n"
    if who == "coordinator":
        return (f"# Tu identidad en la orquesta\n\nEres el director de la orquesta «{run}» "
                f"({core.harness_label(h)}). Carpeta de la orquesta: {d}. Para coordinar, sigue la skill "
                f"`orquesta-launch`; `orq status {run}` te da el árbol.\n")
    return core.identity_head(d, run, who, board["agents"][who]["parent"]) + body


def cmd_whoami(a):
    """Quién es esta sesión en la orquesta, con el protocolo: lo que en Claude Code va en el system prompt."""
    h_name, sid = core.calling_harness()
    found = core.find_session(sid)
    if not found:
        die("esta sesión no es de ninguna orquesta registrada" + ("" if sid else " (no veo ninguna sesión de agente)"))
    print(whoami_text(*found), end="")


def cmd_join(a):
    """Primer paso de un worker de Codex: une el nombre con el id de este chat (CODEX_THREAD_ID)."""
    d = core.run_dir(a.run)
    board = load(d / "board.json")
    h_name, sid = core.calling_harness()
    if not sid or h_name != core.harness_of(board):
        die(f"`orq join` se ejecuta desde el chat del worker ({core.harness_label(core.harness_of(board))})")
    ag = board["agents"].get(a.name) or die(f"no hay agente '{a.name}'")
    pend = load(d / "agents" / a.name / "pending.json")
    if ag.get("session_id") == sid:
        print(whoami_text(a.run, d, board, a.name), end="")
        return
    if ag.get("session_id") or not pend:
        die(f"'{a.name}' ya está unido a otro chat")
    if pend.get("token") != a.token:
        die("la clave no coincide: copia el comando exacto del primer mensaje")
    other = core.find_session(sid)
    if other:
        die(f"este chat ya es '{other[3]}' en la orquesta '{other[0]}'")
    ag["session_id"] = sid
    ag["joined_at"] = now()
    save(d / "board.json", board)
    (d / "agents" / a.name / "pending.json").unlink()
    core.append_log(d / "agents" / a.name, f"unido al chat {sid}")
    core.touch_signal(d, a.name)
    print(whoami_text(a.run, d, board, a.name), end="")


def caller_run(a):
    """(run, run folder, board, who) of the calling session; with --run, that run."""
    h_name, sid = core.calling_harness()
    if getattr(a, "run", None):
        d = core.run_dir(a.run)
        board = load(d / "board.json")
        who = core.caller(board) or die(f"esta sesión no es de la orquesta '{a.run}'")
        return a.run, d, board, who
    found = core.find_session(sid)
    return found or die("esta sesión no es de ninguna orquesta registrada (usa --run)")


def resolve_target(board, name):
    """(name as in the matrix, session id) of a participant."""
    if name == board["coordinator"]:
        return name, board.get("coordinator_session") or ""
    ag = board["agents"].get(name) or die(f"no hay agente '{name}' en la orquesta '{board['run']}'")
    return name, ag.get("session_id") or ""


def cmd_to(a):
    """El id del chat de otro agente, para send_message_to_thread, y el modo de esa pareja."""
    run, d, board, who = caller_run(a)
    me = board["coordinator"] if who == "coordinator" else who
    name, tid = resolve_target(board, a.name)
    if not tid:
        die(f"'{name}' todavía no se ha unido (no ha ejecutado `orq join`)")
    mode, why = comms.mode_for(board, load(d / "comms.json"), me, name)
    print(f"{tid}\t{mode} ({why})")


def cmd_send(a):
    """Camino de reserva de Codex, solo para parejas libres: entrega con `codex queue` y lo apunta en messages.log.

    `orq` corre fuera del sandbox sin preguntar (regla allow de orquesta.rules), así que aquí nadie aprobaría un
    mensaje manual: esos van por send_message_to_thread, que pide aprobación en el chat de quien envía.
    """
    run, d, board, who = caller_run(a)
    me = board["coordinator"] if who == "coordinator" else who
    name, tid = resolve_target(board, a.to)
    if not tid:
        die(f"'{name}' todavía no se ha unido (no ha ejecutado `orq join`)")
    if core.harness_of(board) != "codex":
        die("`orq send` es solo para Codex; en Claude Code usa SendMessage")
    mode, why = comms.mode_for(board, load(d / "comms.json"), me, name)
    if mode != "libre":
        die(f"{me} -> {name} es manual ({why}): mándalo con send_message_to_thread, que pide aprobación en tu chat")
    text = " ".join(a.text)
    msglog.attempt(d, me, name, mode, "", text)
    exe = shutil.which("codex") or die("no encuentro `codex` en el PATH")
    r = subprocess.run([exe, "queue", "--thread", tid, "--message", f"[de {me}] {text}"],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        die(f"`codex queue` ha fallado: {(r.stdout + r.stderr).strip() or r.returncode}")
    msglog.sent(d, me, name, (r.stdout or "").strip())
    print(f"enviado a '{name}' ({mode})")


def cmd_open(a):
    """Abre el chat de un agente (Codex app), sin cambiar su estado."""
    d = core.run_dir(a.run)
    board = load(d / "board.json")
    if a.name != board["coordinator"] and a.name not in board["agents"]:
        die(f"no hay agente '{a.name}'")
    adapter(board).show(d, board, a.name)


def cmd_doctor(a):
    from orq import setup
    if a.sonda:
        p = core.home() / "sonda"
        if a.sonda == "off":
            if p.exists():
                p.unlink()
            print(f"sonda apagada (el registro sigue en {core.home() / 'sonda.log'})")
        else:
            p.write_text(a.sonda + "\n")
            print(f"sonda «{a.sonda}»: la puerta de Codex apunta cada llamada en {core.home() / 'sonda.log'}"
                  + (" y aprueba todo send_message_to_thread" if a.sonda == "permitir" else " sin decidir nada"))
        return
    print(f"orq {__version__} · ORQ_HOME={core.home()}")
    sys.exit(1 if setup.doctor().errors else 0)


def build_parser():
    p = argparse.ArgumentParser(prog="orq", description="Orquesta: un director coordina workers, cada uno en su propia sesión "
                                "del arnés en el que corre el director.")
    p.add_argument("--version", action="version", version=f"orq {__version__}")
    s = p.add_subparsers(dest="cmd", required=True)

    x = s.add_parser("init", help="crear una orquesta")
    x.add_argument("run")
    x.add_argument("--coordinator", required=True, help="nombre de la sesión del director; ejecútalo desde esa "
                   "sesión: orq guarda su id y usa su arnés para la orquesta")
    x.add_argument("--goal")
    x.add_argument("--workspace", help="carpeta del proyecto donde se lanzan los workers (por defecto, la actual)")
    x.add_argument("--color", choices=colors.PALETTE,
                   help="color de la orquesta (por defecto, el primero que no use otra orquesta abierta)")
    x.add_argument("--force", action="store_true", help="aunque esta sesión ya dirija otra orquesta abierta")
    x.set_defaults(f=cmd_init)

    x = s.add_parser("launch", help="lanzar un worker en su propia sesión (requiere su encargo, brief.md)")
    x.add_argument("run")
    x.add_argument("name")
    x.add_argument("--parent", required=True, help="su coordinador (el director u otro worker)")
    x.add_argument("--topic", required=True)
    x.add_argument("--model", help="modelo (por defecto, opus en Claude Code y el de la app en Codex)")
    x.add_argument("--effort", default="medium")
    x.add_argument("--why", help="por qué ese modelo/esfuerzo")
    x.add_argument("--dir", action="append", metavar="DIR",
                   help="carpeta extra fuera del workspace a la que da acceso (p. ej. un worktree); repetible")
    x.add_argument("--force", action="store_true", help="saltarse el tope de agentes vivos")
    x.add_argument("--no-window", action="store_true", help="solo preparar, sin abrir la sesión")
    x.set_defaults(f=cmd_launch)

    x = s.add_parser("resume", help="reabrir un worker cerrado, con todo su historial")
    x.add_argument("run")
    x.add_argument("name")
    x.add_argument("--force", action="store_true", help="saltarse el tope de agentes vivos")
    x.set_defaults(f=cmd_resume)

    x = s.add_parser("status", help="árbol de la orquesta (director, coordinadores, workers) y su estado")
    x.add_argument("run")
    x.add_argument("-v", "--verbose", action="store_true", help="incluir el inicio de cada checkpoint")
    x.set_defaults(f=cmd_status)

    x = s.add_parser("comms", help="ver o cambiar la matriz de comunicación")
    x.add_argument("run")
    x.add_argument("--default", choices=list(MODES))
    x.add_argument("--pair", nargs=3, metavar=("A", "B", "MODO"))
    x.set_defaults(f=cmd_comms)

    x = s.add_parser("state", help="cambiar el estado de un worker")
    x.add_argument("run")
    x.add_argument("name")
    x.add_argument("state")
    x.set_defaults(f=cmd_state)

    x = s.add_parser("log", help="añadir una línea con hora al log de un worker")
    x.add_argument("run")
    x.add_argument("name")
    x.add_argument("text", nargs="+")
    x.set_defaults(f=cmd_log)

    x = s.add_parser("coordinator", help="hacer de esta sesión el director, con el nombre dado")
    x.add_argument("run")
    x.add_argument("name")
    x.add_argument("--force", action="store_true", help="aunque esta sesión ya coordine otra orquesta abierta")
    x.set_defaults(f=cmd_coordinator)

    x = s.add_parser("close", help="cerrar una orquesta terminada (o reabrirla con --reopen)")
    x.add_argument("run")
    x.add_argument("--reopen", action="store_true")
    x.add_argument("--force", action="store_true")
    x.set_defaults(f=cmd_close)

    x = s.add_parser("runs", help="listar orquestas")
    x.set_defaults(f=cmd_runs)

    x = s.add_parser("where", help="ruta del estado de una orquesta (sin run: dónde se crearían aquí)")
    x.add_argument("run", nargs="?")
    x.set_defaults(f=cmd_where)

    x = s.add_parser("render", help="regenerar el protocolo y las skills desde config.json")
    x.set_defaults(f=cmd_render)

    x = s.add_parser("migrate", help="poner al día los board.json de las orquestas registradas")
    x.add_argument("--dry-run", action="store_true", help="solo decir qué cambiaría")
    x.set_defaults(f=cmd_migrate)

    x = s.add_parser("whoami", help="quién es esta sesión en su orquesta, con el protocolo (Codex lo usa al empezar)")
    x.set_defaults(f=cmd_whoami)

    x = s.add_parser("join", help="(worker de Codex) unir tu nombre con este chat; viene en tu primer mensaje")
    x.add_argument("run")
    x.add_argument("name")
    x.add_argument("token")
    x.set_defaults(f=cmd_join)

    x = s.add_parser("to", help="id del chat de otro agente (para send_message_to_thread) y el modo de la pareja")
    x.add_argument("name")
    x.add_argument("--run", help="orquesta (por defecto, la de esta sesión)")
    x.set_defaults(f=cmd_to)

    x = s.add_parser("send", help="(Codex, reserva) mandar un mensaje con `codex queue` si no tienes la herramienta")
    x.add_argument("to")
    x.add_argument("text", nargs="+")
    x.add_argument("--run", help="orquesta (por defecto, la de esta sesión)")
    x.set_defaults(f=cmd_send)

    x = s.add_parser("open", help="abrir el chat de un agente (Codex app) sin cambiar su estado")
    x.add_argument("run")
    x.add_argument("name")
    x.set_defaults(f=cmd_open)

    x = s.add_parser("doctor", help="comprobar la instalación (incluye una prueba en seco de la puerta)")
    x.add_argument("--sonda", choices=["on", "permitir", "off"],
                   help="(prueba de Codex) que la puerta apunte todo lo que recibe en sonda.log; «permitir» "
                        "además aprueba todos los send_message_to_thread")
    x.set_defaults(f=cmd_doctor)
    return p


def signal_from_caller():
    """Codex agents can't be seen from outside: each orq call they make is their sign of life."""
    h_name, sid = (None, "")
    try:
        h_name, sid = core.calling_harness()
    except SystemExit:
        return
    if h_name and harness.get(h_name).LIVENESS == "signal":
        found = core.find_session(sid)
        if found and found[3] != "coordinator":
            core.touch_signal(found[1], found[3])


def main(argv=None):
    a = build_parser().parse_args(argv)
    signal_from_caller()
    a.f(a)
