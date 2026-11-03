"""Codex adapter. Two surfaces, never mixed in one orchestra: the desktop app ("app") and the CLI ("cli").

Only the app surface is built (plan step 6); the CLI surface (step 9) refuses to launch for now.

How an app worker starts (research §9.3, route L-app-1):
  1. `orq launch` writes agents/<n>/pending.json with a one-time token and opens the deep link
     `codex://new?path=<workspace>&prompt=<text>`: a new chat in the workspace's project with the prompt
     already typed. The user picks model and effort in the app and presses Enter (no deep-link parameter
     sets them).
  2. The prompt asks the agent to run `orq join <run> <n> <token>` first. `orq join` reads CODEX_THREAD_ID,
     binds the name to the thread id in board.json and prints the identity and the protocol.
  3. The global `~/.codex/AGENTS.md` block (installer) tells any Codex chat that belongs to an orchestra to
     run `orq whoami` before using orq: that survives compaction and reopening.
Liveness: the app's threads can't be listed from outside, so `orq status` shows each agent's last sign of
life (its last orq call, agents/<n>/signal) and the cap counts agents by state.
"""
import secrets
import subprocess
import urllib.parse

from orq import colors, core

NAME = "codex"
SESSION_ENV = "CODEX_THREAD_ID"
SURFACES = ("app", "cli")
BUILT_SURFACES = ("app",)
EFFORTS = ["low", "medium", "high"]  # orchestra policy: high is the cap
DEFAULT_MODEL = ""  # the app's own default: the user picks it in the composer
LIVENESS = "signal"

LIVE_SOURCE = "la app de Codex no deja ver desde fuera qué chats están abiertos"
OPENED = "en un chat nuevo de la app de Codex"
FIND_LIVE = "búscalo en la barra lateral de la app"


def color_hint(color):
    return (f"En Codex no hay color de barra: los nombres de los chats de sus workers empiezan por "
            f"{colors.EMOJI.get(color, '')}.")


def models():
    """None: any model name is accepted (the app's list changes, and the user picks it there anyway)."""
    return set(core.config().get("models", {}).get(NAME) or []) or None


def efforts():
    return set(core.config().get("efforts", {}).get(NAME) or EFFORTS)


def live_sessions(timeout=30):
    return None


APP_BUNDLES = ("com.openai.codex", "com.openai.chat")


def calling_surface():
    """"app" or "cli" from the calling session's environment, or None when it can't be told apart.

    Codex exports nothing that names the surface (rust-v0.166.0: exec env has CODEX_THREAD_ID, CODEX_CI, …
    for both). Two signals, in order: ORQUESTA_SURFACE, if the user sets it (e.g. for the CLI with
    `-c 'shell_environment_policy.set.ORQUESTA_SURFACE="cli"'`); and macOS's __CFBundleIdentifier, which a
    command started from the app may inherit from the app's process (unverified: a test item). Otherwise None,
    and `orq init` uses config.json's codex.surface.
    """
    import os
    s = os.environ.get("ORQUESTA_SURFACE", "").strip().lower()
    if s in ("app", "cli", "tui"):
        return "cli" if s == "tui" else s
    if os.environ.get("__CFBundleIdentifier", "") in APP_BUNDLES:
        return "app"
    return None


def surface_of(board):
    return (board or {}).get("surface") or "app"


def require_built(board, what):
    s = surface_of(board)
    if s not in BUILT_SURFACES:
        core.die(f"la superficie «{s}» de Codex todavía no está disponible: orq aún no sabe {what} en ella "
                 f"(de momento solo la app)")
    return s


def thread_link(tid):
    return f"codex://threads/{tid}"


def new_chat_link(workspace, prompt):
    return "codex://new?" + urllib.parse.urlencode({"path": str(workspace), "prompt": prompt},
                                                    quote_via=urllib.parse.quote)


def title(board, name):
    """What the chat should be called: «🟣 w1 · run» (the emoji is the orchestra's colour)."""
    e = colors.EMOJI.get(board.get("color") or "", "")
    return f"{e} {name} · {board['run']}".strip()


def first_prompt(board, j, token):
    rec = ""
    if j.model or j.effort:
        rec = (f"\n\n(Para quien lo lanza: modelo recomendado {j.model or 'el de por defecto'}, "
               f"esfuerzo {j.effort}.)")
    return (f"{title(board, j.name)}\n\n"
            f"Eres el worker «{j.name}» de la orquesta «{j.run}», y tu coordinador es «{j.parent}». "
            f"Antes de nada, ejecuta este comando y sigue lo que diga (te da tu identidad, el protocolo y tu "
            f"encargo):\n\n    orq join {j.run} {j.name} {token}{rec}")


def open_link(link):
    subprocess.run(["open", link], check=True, capture_output=True)


def prepare(j):
    """Writes pending.json and the first prompt. The thread id arrives later, with `orq join`."""
    require_built(j.board, "lanzar workers")
    if j.extra:
        core.die("--dir no está disponible en Codex: en la app, cada chat trabaja en la carpeta de su proyecto")
    token = secrets.token_hex(8)
    core.save(j.ad / "pending.json", {"token": token, "created": core.now()})
    prompt = first_prompt(j.board, j, token)
    (j.ad / "launch.md").write_text(prompt + "\n")
    j.link = new_chat_link(j.ws, prompt)
    return ""


def open_new(j, sid):
    if j.no_window:
        print(f"preparado sin abrir: {j.link}")
        return
    open_link(j.link)
    rec = f"modelo {j.model}, " if j.model else ""
    print(f"lanzado '{j.name}' {OPENED}, con el encargo ya escrito: elige {rec}esfuerzo {j.effort} y pulsa Enter. "
          f"El worker se registrará solo con `orq join`.")


def reopen(d, board, run, name):
    require_built(board, "reabrir workers")
    sid = board["agents"][name].get("session_id")
    if not sid:
        core.die(f"'{name}' todavía no se ha unido (no ha ejecutado `orq join`): no sé qué chat abrir")
    open_link(thread_link(sid))
    print(f"abierto el chat de '{name}' en la app de Codex")


def show(d, board, name):
    require_built(board, "abrir chats")
    sid = board.get("coordinator_session") if name == board["coordinator"] else board["agents"][name].get("session_id")
    if not sid:
        core.die(f"'{name}' todavía no se ha unido (no ha ejecutado `orq join`)")
    open_link(thread_link(sid))
    print(f"abierto el chat de '{name}' en la app de Codex")
