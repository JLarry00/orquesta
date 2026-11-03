"""Install, update, migrate from v1, shims, undo and doctor.

Used by installer.py (from a checkout or the zip) and by `orq migrate` / `orq doctor` (installed copy).

v1 lived in ~/.claude/orquesta (bin/orq, hooks/orquesta-gate.py, PROTOCOL.md, config.json, runs.json) with
its skills in ~/.claude/skills/orquesta-*. Agents launched by v1 carry absolute paths to those files in their
settings.json and launchers, so after migrating, ~/.claude/orquesta stays as a layer of shims that forward
to ORQ_HOME. Everything the install replaces is first saved in one tarball, which --deshacer restores.
"""
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from orq import __version__, codex_setup, core, render

SHIM_MARK = "orquesta-shim"
MANIFEST = "install.json"
NEW_BOARD_KEYS = ("schema", "harness", "workspace")
LIB_PARTS = ("orq", "hooks", "templates")


def legacy_dir():
    return Path.home() / ".claude/orquesta"


def local_bin():
    return Path.home() / ".local/bin/orq"


def skill_dirs():
    """Every harness's orquesta skills (Claude Code: ~/.claude/skills; Codex: ~/.agents/skills)."""
    return [render.skills_dir(hn) / n for hn in ("claude", "codex") for n in render.SKILLS]


def replaced_targets():
    """Paths outside ORQ_HOME that an install may overwrite; all of them go into the backup first."""
    return [legacy_dir(), *skill_dirs(), local_bin()]


def manifest_path():
    return core.home() / MANIFEST


def load_manifest():
    return core.load(manifest_path())


def save_manifest(m):
    core.save(manifest_path(), m)


def exists(p):
    return p.exists() or p.is_symlink()


def legacy_state():
    """'v1' (real v1 code), 'shims' (already migrated) or None (no v1 here)."""
    f = legacy_dir() / "bin/orq"
    if not exists(f):
        return None
    try:
        return "shims" if SHIM_MARK in f.read_text() else "v1"
    except OSError:
        return "v1"


def rel_home(p):
    return os.path.relpath(p, Path.home())


def note_missing_dirs(manifest, path):
    """Record the ancestors of `path` (below $HOME) that don't exist yet, so undo can remove them if empty."""
    home = Path.home()
    missing = []
    for d in [path.parent, *path.parent.parents]:
        if d == home or home not in d.parents:
            break
        if not d.exists():
            missing.append(str(d))
    for d in reversed(missing):
        if d not in manifest["created_dirs"]:
            manifest["created_dirs"].append(d)


def say(msg):
    print(msg)


# ---------------------------------------------------------------- backup


def make_backup(stamp):
    """Tarball of every replaced target that exists now (symlinks kept as symlinks)."""
    dest = core.home() / "backup" / f"antes-de-instalar-{stamp}.tar.gz"
    dest.parent.mkdir(parents=True, exist_ok=True)
    existed = {}
    with tarfile.open(dest, "w:gz") as tar:
        for p in replaced_targets():
            existed[str(p)] = exists(p)
            if existed[str(p)]:
                tar.add(p, arcname=rel_home(p), recursive=True)
    return dest, existed


def restore_backup(tar_path):
    with tarfile.open(tar_path, "r:gz") as tar:
        for m in tar.getmembers():
            if m.name.startswith("/") or ".." in Path(m.name).parts:
                raise RuntimeError(f"ruta sospechosa en la copia: {m.name}")
        tar.extractall(Path.home())


def remove(p):
    if p.is_symlink() or p.is_file():
        p.unlink()
    elif p.is_dir():
        shutil.rmtree(p)


# ---------------------------------------------------------------- lib, bin, config


def copy_lib(src_root):
    """Copy orq/, hooks/ and templates/ into ORQ_HOME/lib, file by file with atomic renames."""
    lib = core.home() / "lib"
    wanted = set()
    for part in LIB_PARTS:
        for f in sorted((src_root / part).rglob("*")):
            if f.is_dir() or "__pycache__" in f.parts or f.suffix == ".pyc":
                continue
            rel = f.relative_to(src_root)
            wanted.add(rel)
            core.write_atomic(lib / rel, f.read_text(), mode=f.stat().st_mode & 0o777)
    for f in sorted(lib.rglob("*")) if lib.exists() else []:
        if f.is_file() and "__pycache__" not in f.parts and f.relative_to(lib) not in wanted:
            f.unlink()


BIN_SCRIPT = """#!/usr/bin/env python3
# orquesta: comando `orq` (lo genera el instalador). El código está en ../lib.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from orq.cli import main  # noqa: E402

main()
"""


def write_bin():
    core.write_atomic(core.home() / "bin/orq", BIN_SCRIPT, mode=0o755)


def link(path, target):
    """Point symlink `path` at `target`, replacing whatever is there atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.orq-tmp")
    if exists(tmp):
        tmp.unlink()
    tmp.symlink_to(target)
    os.replace(tmp, path)


def default_max_alive():
    try:
        mem = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout)
        return max(2, min(8, mem // 2 ** 30 // 2))
    except Exception:
        return core.DEFAULT_MAX_ALIVE


def v1_config():
    return core.load(legacy_dir() / "config.json", {}) or {}


# ---------------------------------------------------------------- runs


def import_v1_runs():
    """Copy v1's runs.json into ORQ_HOME/runs.json, entry by entry. Missing run folders are reported, not dropped."""
    src = core.load(legacy_dir() / "runs.json", {}) or {}
    reg = core.registry()
    for name, p in src.items():
        if not (Path(p) / "board.json").exists():
            say(f"  aviso: la orquesta '{name}' no está en {p} (la dejo en el registro)")
        reg.setdefault(name, p)
    core.save(core.registry_path(), reg)
    return src


def migrate_runs(manifest=None, dry_run=False):
    """Add schema/harness/workspace to every registered board that lacks them. Returns {run_dir: [keys]}."""
    done = {}
    backups = core.home() / "backup/boards"
    for name, p in sorted(core.registry().items()):
        d = Path(p)
        f = d / "board.json"
        try:
            board = json.loads(f.read_text())
        except (OSError, ValueError) as e:
            say(f"  aviso: no puedo leer {f} ({e}); la dejo como está")
            continue
        add = {}
        if "schema" not in board:
            add["schema"] = core.SCHEMA
        if "harness" not in board:
            add["harness"] = core.DEFAULT_HARNESS
        if "workspace" not in board:
            add["workspace"] = str(core.workspace_of(d, board))
        if not add:
            continue
        done[str(d)] = list(add)
        say(f"  {name}: añado {', '.join(f'{k}={v}' for k, v in add.items())}")
        if dry_run:
            continue
        backups.mkdir(parents=True, exist_ok=True)
        bk = backups / f"{name}.board.json"
        if not bk.exists():
            shutil.copy2(f, bk)
        board.update(add)
        core.save(f, board)
        if manifest is not None:
            prev = manifest.setdefault("migrated", {}).get(str(d), [])
            manifest["migrated"][str(d)] = prev + [k for k in add if k not in prev]
    return done


def unmigrate_runs(manifest):
    for d, keys in (manifest.get("migrated") or {}).items():
        f = Path(d) / "board.json"
        board = core.load(f)
        if board is None:
            say(f"  aviso: ya no existe {f}")
            continue
        for k in keys:
            board.pop(k, None)
        core.save(f, board)
        say(f"  {f}: quito {', '.join(keys)}")


# ---------------------------------------------------------------- shims


def shim_text(name):
    text = (render.TEMPLATES / "shims" / name).read_text()
    h = core.home()
    return (text.replace("{{orq_home}}", str(h)).replace("{{orq_bin}}", str(h / "bin/orq"))
            .replace("{{gate}}", str(h / "lib/hooks/claude_gate.py")))


def write_shims():
    """Turn ~/.claude/orquesta into a compatibility layer that forwards to ORQ_HOME."""
    leg = legacy_dir()
    h = core.home()
    core.write_atomic(leg / "bin/orq", shim_text("orq.sh"), mode=0o755)
    core.write_atomic(leg / "hooks/orquesta-gate.py", shim_text("orquesta-gate.py"), mode=0o755)
    core.write_atomic(leg / "PROTOCOL.md", core.protocol_path().read_text())
    core.write_atomic(leg / "LEEME.md", shim_text("LEEME.md"))
    link(leg / "runs.json", h / "runs.json")
    link(leg / "config.json", h / "config.json")


# ---------------------------------------------------------------- install / undo


def install(src_root, answers, stamp):
    """First install or update. `answers`: user, approver, state_dir, max_alive, house_rules, skills."""
    h = core.home()
    if h.resolve() == Path.home().resolve():
        raise RuntimeError("ORQ_HOME no puede ser tu carpeta personal")
    manifest = load_manifest()
    first = manifest is None
    if first and h.exists() and any(h.iterdir()):
        raise RuntimeError(f"{h} ya existe y no es una instalación de orquesta (falta {MANIFEST}); "
                           "muévela o elige otra con ORQ_HOME")
    legacy = legacy_state()
    say(f"Instalando orquesta {__version__} en {h}" + (" (actualización)" if not first else ""))
    if legacy == "v1":
        say(f"Encontrada la versión anterior en {legacy_dir()}: la migro.")

    if first:
        h.mkdir(parents=True, exist_ok=True)
        tar, existed = make_backup(stamp)
        say(f"Copia de seguridad: {tar}")
        manifest = {"installed": core.now(), "backup": str(tar.relative_to(h)), "existed": existed,
                    "created_dirs": [], "migrated": {}, "runs_before": {}}
        save_manifest(manifest)

    copy_lib(src_root)
    write_bin()

    cfg = core.config() or {}
    if first and legacy == "v1":
        cfg.update({k: v for k, v in v1_config().items() if k == "state_dir"})
    cfg.update({k: v for k, v in answers.items() if v is not None})
    if not cfg.get("house_rules"):
        cfg.pop("house_rules", None)
    cfg.setdefault("state_dir", "workspace")
    cfg.setdefault("harnesses", ["claude"])
    cfg.update({"schema": core.SCHEMA, "version": __version__})
    core.save(core.config_path(), cfg)

    if not core.registry_path().exists():
        core.save(core.registry_path(), {})
    if legacy == "v1":
        manifest["runs_before"] = import_v1_runs()

    for path, text in render.outputs(cfg):
        note_missing_dirs(manifest, path)
        core.write_atomic(path, text)
        say(f"Escrito {path}")
    wanted = {str(p.parent) for p, _ in render.outputs(cfg)}
    for d in skill_dirs():  # skills of harnesses no longer chosen, or all of them with skills off
        if str(d) not in wanted and exists(d):
            remove(d)
    if "codex" in cfg["harnesses"]:
        codex_setup.install(manifest, note_missing_dirs, say)
    elif manifest.get("codex"):
        codex_setup.undo(manifest, say)
        manifest.pop("codex")

    say("Migrando las orquestas registradas:")
    if not migrate_runs(manifest):
        say("  nada que migrar")

    if legacy in ("v1", "shims"):
        write_shims()
        say(f"Calzos escritos en {legacy_dir()} (ver LEEME.md allí)")

    prune_created_dirs(manifest)
    lb = local_bin()
    note_missing_dirs(manifest, lb)
    link(lb, h / "bin/orq")
    say(f"Enlace {lb} -> {h / 'bin/orq'}")
    manifest["version"] = __version__
    manifest["updated"] = core.now()
    save_manifest(manifest)
    return manifest


def prune_created_dirs(manifest):
    """Remove folders this install created that are empty now (e.g. ~/.agents after dropping Codex)."""
    for d in reversed(list(manifest.get("created_dirs") or [])):
        p = Path(d)
        try:
            if p.is_dir() and not any(p.iterdir()):
                p.rmdir()
        except OSError:
            pass


def undo():
    """Put everything back as it was before the first install."""
    h = core.home()
    manifest = load_manifest()
    if manifest is None:
        raise RuntimeError(f"no hay instalación que deshacer en {h} (falta {MANIFEST})")
    tar = h / manifest["backup"]
    if not tar.exists():
        raise RuntimeError(f"falta la copia de seguridad {tar}; no deshago nada")
    with tarfile.open(tar, "r:gz") as t:  # read it before touching anything
        t.getmembers()
    new_runs = {k: v for k, v in core.registry().items() if k not in (manifest.get("runs_before") or {})}

    say("Quitando los campos añadidos a los board.json:")
    unmigrate_runs(manifest)
    for p in replaced_targets():
        if exists(p):
            remove(p)
    restore_backup(tar)
    say(f"Restaurado desde {tar}")
    for p in replaced_targets():
        if not manifest["existed"].get(str(p)) and exists(p):
            remove(p)

    if new_runs:
        reg_v1 = legacy_dir() / "runs.json"
        if manifest["existed"].get(str(legacy_dir())) and reg_v1.exists():
            reg = core.load(reg_v1, {})
            reg.update(new_runs)
            core.save(reg_v1, reg)
            say(f"Orquestas creadas después de instalar, añadidas a {reg_v1}: {', '.join(sorted(new_runs))}")
        else:
            say("Aviso: estas orquestas se crearon con esta instalación y dejan de estar registradas "
                f"(sus carpetas siguen ahí): {', '.join(f'{k} ({v})' for k, v in sorted(new_runs.items()))}")

    codex_setup.undo(manifest, say)
    for d in reversed(manifest.get("created_dirs") or []):
        try:
            Path(d).rmdir()
        except OSError:
            pass
    shutil.rmtree(h)
    say(f"Borrado {h}")


# ---------------------------------------------------------------- doctor


class Report:
    def __init__(self):
        self.lines = []

    def ok(self, msg):
        self.lines.append(("ok", msg))

    def warn(self, msg):
        self.lines.append(("aviso", msg))

    def err(self, msg):
        self.lines.append(("ERROR", msg))

    @property
    def errors(self):
        return sum(1 for lvl, _ in self.lines if lvl == "ERROR")

    def print(self):
        for lvl, msg in self.lines:
            print(f"  {lvl:<5} {msg}")
        w = sum(1 for lvl, _ in self.lines if lvl == "aviso")
        print(f"{self.errors} errores, {w} avisos")


def gate_dry_run(gate, args, recipient):
    payload = json.dumps({"tool_name": "SendMessage", "tool_input": {"to": recipient, "message": "(doctor)"}})
    r = subprocess.run([sys.executable, str(gate), *args, "--dry-run"], input=payload, capture_output=True,
                       text=True, timeout=30)
    try:
        return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], r
    except Exception:
        return None, r


def synthetic_gate_check(rep, gate):
    with tempfile.TemporaryDirectory(prefix="orq-doctor-") as t:
        d = Path(t)
        (d / "board.json").write_text(json.dumps({
            "run": "doctor", "coordinator": "coord", "coordinator_session": "", "agents": {
                "a": {"parent": "coord", "session_id": "x"}, "b": {"parent": "coord", "session_id": "y"}}}))
        (d / "comms.json").write_text(json.dumps({"default": "manual", "pairs": {}}))
        (d / "messages.log").touch()
        got = (gate_dry_run(gate, ["--run-dir", str(d), "--agent", "a"], "coord")[0],
               gate_dry_run(gate, ["--run-dir", str(d), "--agent", "a"], "b")[0])
        logged = (d / "messages.log").read_text()
    if got == ("allow", "ask") and not logged:
        rep.ok("puerta en seco (orquesta de prueba): coordinador<->worker pasa, el resto pregunta")
    else:
        rep.err(f"puerta en seco (orquesta de prueba): esperaba (allow, ask) sin log y obtengo {got}")


def synthetic_codex_gate_check(rep, gate):
    """The Codex gate in dry run, on a throwaway ORQ_HOME with one orchestra: free -> allow, manual -> no decision."""
    with tempfile.TemporaryDirectory(prefix="orq-doctor-") as t:
        home, d = Path(t), Path(t) / "run"
        (d / "agents").mkdir(parents=True)
        (d / "board.json").write_text(json.dumps({
            "run": "doctor", "harness": "codex", "coordinator": "coord", "coordinator_session": "t-coord",
            "agents": {"a": {"parent": "coord", "session_id": "t-a"}, "b": {"parent": "coord", "session_id": "t-b"}}}))
        (d / "comms.json").write_text(json.dumps({"default": "manual", "pairs": {}}))
        (d / "messages.log").touch()
        (home / "runs.json").write_text(json.dumps({"doctor": str(d)}))
        out = []
        for to in ("t-coord", "t-b"):
            payload = json.dumps({"hook_event_name": "PermissionRequest", "session_id": "t-a",
                                  "tool_name": "mcp__codex_app__send_message_to_thread",
                                  "tool_input": {"threadId": to, "prompt": "(doctor)"}})
            r = subprocess.run([sys.executable, str(gate), "--dry-run"], input=payload, capture_output=True,
                               text=True, timeout=30, env={**os.environ, "ORQ_HOME": str(home)})
            out.append(r.stdout.strip())
        logged = (d / "messages.log").read_text()
    if out == ["a -> coord: allow", "a -> b: sin decisión (aviso)"] and not logged:
        rep.ok("puerta de Codex en seco (orquesta de prueba): coordinador<->worker pasa, el resto pregunta")
    else:
        rep.err(f"puerta de Codex en seco: esperaba allow / sin decisión, y obtengo {out}")


def codex_run_check(rep, name, board, gate):
    """Codex gate in dry run on a real run: the first joined worker writing to its coordinator must pass."""
    sid_of = {n: ag.get("session_id") for n, ag in board.get("agents", {}).items()}
    sid_of[board["coordinator"]] = board.get("coordinator_session")
    pairs = [(n, ag["parent"]) for n, ag in board.get("agents", {}).items() if sid_of.get(n) and sid_of.get(ag["parent"])]
    if not pairs or not gate.exists():
        rep.ok(f"{name}: board legible ({len(board.get('agents', {}))} workers, Codex)")
        return
    agent, parent = pairs[0]
    payload = json.dumps({"hook_event_name": "PermissionRequest", "session_id": sid_of[agent],
                          "tool_name": "mcp__codex_app__send_message_to_thread",
                          "tool_input": {"threadId": sid_of[parent], "prompt": "(doctor)"}})
    r = subprocess.run([sys.executable, str(gate), "--dry-run"], input=payload, capture_output=True, text=True,
                       timeout=30)
    if r.stdout.strip().endswith(": allow"):
        rep.ok(f"{name}: puerta de Codex en seco {agent} -> {parent}: allow")
    else:
        rep.err(f"{name}: puerta de Codex en seco {agent} -> {parent}: {r.stdout.strip()} {r.stderr.strip()}")


def doctor():
    rep = Report()
    h = core.home()
    v = sys.version_info
    (rep.ok if v >= (3, 9) else rep.err)(f"python {v.major}.{v.minor}.{v.micro}")
    cfg = core.load(core.config_path())
    if cfg is None:
        rep.err(f"no hay {core.config_path()}: ejecuta ./install.sh")
        rep.print()
        return rep
    rep.ok(f"configuración {core.config_path()} (versión {cfg.get('version', '?')}, usuario {cfg.get('user', '?')})")
    gate = h / "lib/hooks/claude_gate.py"
    for p in (h / "lib/orq/cli.py", gate, h / "lib/templates/PROTOCOL.md.tmpl"):
        if not p.exists():
            rep.err(f"falta {p}")
    b = h / "bin/orq"
    (rep.ok if os.access(b, os.X_OK) else rep.err)(f"comando {b}")
    found = shutil.which("orq")
    if not found:
        rep.warn(f"`orq` no está en el PATH: añade {local_bin().parent} al PATH")
    elif Path(found).resolve() != b.resolve():
        rep.warn(f"`orq` del PATH es {found}, no {b}")
    else:
        rep.ok(f"`orq` en el PATH ({found})")
    (rep.ok if shutil.which("claude") else rep.warn)("`claude` en el PATH")

    try:
        expected = dict(render.outputs(cfg))
    except render.RenderError as e:
        rep.err(str(e))
        expected = {}
    for path, text in expected.items():
        if not path.exists():
            rep.err(f"falta {path}: ejecuta `orq render`")
        elif path.read_text() != text:
            rep.warn(f"{path} no coincide con la configuración: ejecuta `orq render`")
        else:
            rep.ok(f"{path}")

    if gate.exists():
        synthetic_gate_check(rep, gate)
    leg = legacy_dir()
    state = legacy_state()
    if state == "v1":
        rep.err(f"{leg} tiene la versión anterior sin migrar: ejecuta ./install.sh")
    elif state == "shims":
        bad = []
        if SHIM_MARK not in (leg / "hooks/orquesta-gate.py").read_text():
            bad.append("hooks/orquesta-gate.py")
        for n in ("runs.json", "config.json"):
            if not ((leg / n).is_symlink() and (leg / n).resolve() == (h / n).resolve()):
                bad.append(n)
        if (leg / "PROTOCOL.md").read_text() != core.protocol_path().read_text():
            bad.append("PROTOCOL.md (desfasado: ejecuta `orq render`)")
        (rep.err if bad else rep.ok)(f"calzos en {leg}" + (f": revisa {', '.join(bad)}" if bad else ""))

    if "codex" in (cfg.get("harnesses") or []):
        codex_setup.check(rep)
        cg = h / "lib/hooks/codex_gate.py"
        if cg.exists():
            synthetic_codex_gate_check(rep, cg)
        (rep.ok if shutil.which("codex") else rep.warn)(
            "`codex` en el PATH" + ("" if shutil.which("codex") else " (solo hace falta para `orq send`)"))
        mode = (h / "sonda").read_text().strip() if (h / "sonda").exists() else ""
        if mode:
            rep.warn(f"la sonda de la puerta de Codex está activa ({mode}): apaga con `orq doctor --sonda off`")

    reg = core.registry()
    rep.ok(f"{len(reg)} orquestas registradas en {core.registry_path()}")
    for name, p in sorted(reg.items()):
        d = Path(p)
        try:
            board = json.loads((d / "board.json").read_text())
        except Exception as e:
            rep.warn(f"{name}: no puedo leer {d / 'board.json'} ({e.__class__.__name__})")
            continue
        missing = [k for k in ("schema", "harness") if k not in board]
        if missing:
            rep.warn(f"{name}: board sin {', '.join(missing)}: ejecuta `orq migrate`")
        agents = [(n, ag["parent"]) for n, ag in board.get("agents", {}).items()]
        if core.harness_of(board) == "codex":
            codex_run_check(rep, name, board, h / "lib/hooks/codex_gate.py")
            continue
        if not agents or not gate.exists():
            rep.ok(f"{name}: board legible ({len(agents)} workers)")
            continue
        agent, parent = agents[0]
        checks = [("--run-dir", gate, ["--run-dir", str(d), "--agent", agent])]
        if state == "shims":
            checks.append(("--run", leg / "hooks/orquesta-gate.py", ["--run", name, "--agent", agent]))
        for label, g, args in checks:
            dec, r = gate_dry_run(g, args, parent)
            if dec == "allow":
                rep.ok(f"{name}: puerta en seco {label} {agent} -> {parent}: allow")
            else:
                rep.err(f"{name}: puerta en seco {label} {agent} -> {parent}: {dec} {r.stdout.strip()} "
                        f"{r.stderr.strip()}")
    rep.print()
    return rep
