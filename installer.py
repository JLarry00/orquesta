"""Instalador de la orquesta. Se ejecuta con ./install.sh (que comprueba python3 >= 3.9).

  ./install.sh                                  preguntas, con un valor por defecto en cada una
  ./install.sh --no-interactivo --nombre Ana    sin preguntas
  ./install.sh --deshacer                       deja todo como estaba antes de la primera instalación

Instala en $ORQ_HOME (por defecto ~/.orquesta). Si encuentra la versión anterior en ~/.claude/orquesta, la
migra y deja allí una capa de calzos para los workers ya lanzados.
"""
import argparse
import datetime as dt
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from orq import __version__, core, setup  # noqa: E402


def ask(question, default, interactive):
    if not interactive:
        return default
    shown = f" [{default}]" if default not in (None, "") else ""
    try:
        got = input(f"{question}{shown}: ").strip()
    except EOFError:
        got = ""
    return got or default


def yes(question, default, interactive):
    got = ask(question + " (s/n)", "s" if default else "n", interactive)
    return str(got).lower().startswith(("s", "y"))


def parse(argv):
    p = argparse.ArgumentParser(prog="install.sh", description="Instala, actualiza o deshace la orquesta.")
    p.add_argument("--no-interactivo", action="store_true", help="no preguntar: usar opciones y valores por defecto")
    p.add_argument("--nombre", help="tu nombre (aparece en el protocolo y en las skills)")
    p.add_argument("--aprobador", help="quién aprueba los mensajes manuales (por defecto, tú)")
    p.add_argument("--arneses", help="arneses con los que la usarás, separados por comas: claude, codex "
                   "(por defecto, los que encuentre en este ordenador)")
    p.add_argument("--superficie-codex", choices=["app", "cli"],
                   help="en Codex, si usas la app o la CLI (por defecto, app; la CLI aún no está disponible)")
    p.add_argument("--estado", help="dónde guardar el estado: «workspace» (recomendado) o una ruta")
    p.add_argument("--max-vivos", type=int, help="tope de agentes vivos a la vez")
    p.add_argument("--reglas-casa", help="archivo Markdown de reglas de la casa ('' para quitarlo)")
    p.add_argument("--sin-skills", action="store_true", help="no instalar las skills (orquesta-launch y orquesta-resume)")
    p.add_argument("--deshacer", action="store_true", help="deshacer la instalación y restaurar la copia")
    return p.parse_args(argv)


KNOWN = ("claude", "codex")


def detected_harnesses():
    found = []
    if shutil.which("claude"):
        found.append("claude")
    if shutil.which("codex") or any(Path(p).exists() for p in ("/Applications/Codex.app", "/Applications/ChatGPT.app")):
        found.append("codex")
    return found or ["claude"]


def harness_answers(a, prev, interactive):
    default = ",".join(prev.get("harnesses") or detected_harnesses())
    got = a.arneses or ask("Arneses con los que usarás la orquesta (claude, codex; separados por comas)", default,
                           interactive)
    hs = [h.strip() for h in str(got).split(",") if h.strip()]
    bad = [h for h in hs if h not in KNOWN]
    if bad or not hs:
        sys.exit(f"install.sh: arnés desconocido: {', '.join(bad) or '(ninguno)'} (usa claude y/o codex)")
    surface = None
    if "codex" in hs:
        surface = a.superficie_codex or ask("En Codex, ¿usas la app o la CLI? (app, cli)",
                                            (prev.get("codex") or {}).get("surface") or "app", interactive)
        if surface not in ("app", "cli"):
            sys.exit("install.sh: la superficie de Codex es app o cli")
        if surface == "cli":
            print("Aviso: la CLI de Codex todavía no está disponible en orquesta; podrás crear orquestas, "
                  "pero no lanzar workers.")
    return hs, surface


def answers(a, interactive):
    prev = core.config() or {}
    v1 = setup.v1_config() if setup.legacy_state() == "v1" else {}
    user = a.nombre or ask("Tu nombre", prev.get("user") or os.environ.get("USER", ""), interactive)
    if not user:
        sys.exit("install.sh: falta tu nombre (--nombre)")
    approver = a.aprobador or ask("Quién aprueba los mensajes manuales", prev.get("approver") or user, interactive)
    hs, surface = harness_answers(a, prev, interactive)
    state = a.estado or ask("Dónde se guarda el estado de las orquestas («workspace» o una ruta)",
                            prev.get("state_dir") or v1.get("state_dir") or "workspace", interactive)
    if state != "workspace" and "codex" in hs:
        print("Aviso: con Codex el estado va siempre en el workspace (sus agentes trabajan con sandbox); "
              "las orquestas de Claude Code usarán la ruta que has dado.")
    if state != "workspace":
        state = str(Path(state).expanduser().resolve())
    max_alive = a.max_vivos or int(ask("Tope de agentes vivos a la vez",
                                       prev.get("max_alive") or setup.default_max_alive(), interactive))
    if a.reglas_casa is not None:
        rules = a.reglas_casa
    else:
        rules = ask("Archivo de reglas de la casa (vacío si no hay)", prev.get("house_rules") or "", interactive)
    if rules:
        rules = str(Path(rules).expanduser().resolve())
        if not Path(rules).is_file():
            sys.exit(f"install.sh: no existe el archivo de reglas de la casa {rules}")
    skills = False if a.sin_skills else yes("¿Instalo las skills (orquesta-launch y orquesta-resume)?",
                                            prev.get("skills", True), interactive)
    out = {"user": user, "approver": approver, "state_dir": state, "max_alive": max_alive,
           "house_rules": rules, "skills": skills, "harnesses": hs}
    if surface:
        out["codex"] = {**(prev.get("codex") or {}), "surface": surface}
    return out


def main(argv=None):
    a = parse(argv)
    if sys.version_info < (3, 9):
        sys.exit("install.sh: hace falta python3 3.9 o posterior")
    if a.deshacer:
        try:
            setup.undo()
        except RuntimeError as e:
            sys.exit(f"install.sh: {e}")
        print("Hecho: todo está como antes de instalar.")
        return
    interactive = not a.no_interactivo and sys.stdin.isatty()
    ans = answers(a, interactive)
    if "claude" in ans["harnesses"] and not shutil.which("claude"):
        print("Aviso: no encuentro `claude` en el PATH. La orquesta lo necesita para lanzar workers de Claude Code.")
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        setup.install(REPO, ans, stamp)
    except RuntimeError as e:
        sys.exit(f"install.sh: {e}")
    print()
    print(f"Comprobación (orq doctor):")
    rep = setup.doctor()
    path_dirs = [Path(p).expanduser() for p in os.environ.get("PATH", "").split(":") if p]
    if setup.local_bin().parent not in path_dirs:
        print(f"\nAñade {setup.local_bin().parent} al PATH (por ejemplo en ~/.zshrc):\n"
              '  export PATH="$HOME/.local/bin:$PATH"')
    if "codex" in ans["harnesses"]:
        print("\nCodex: la próxima vez que abras Codex te pedirá confirmar los hooks nuevos de orquesta (en la CLI, "
              "`/hooks`). Sin confirmarlos, la puerta de los mensajes no funciona.")
    print(f"\nOrquesta {__version__} instalada en {core.home()}. Deshacer: ./install.sh --deshacer")
    sys.exit(1 if rep.errors else 0)


if __name__ == "__main__":
    main()
