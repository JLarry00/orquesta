"""Render the protocol and the skills from templates/ with the values in config.json.

Placeholders are `{{clave}}`. Values come from config.json (user, approver, max_alive, house_rules) and from
the harness snippet (templates/snippets/<harness>.md), whose blocks start with a `<!-- clave -->` line.
The house-rules file, if configured, is appended to the protocol and to the orquesta-launch skill.
"""
import re
from pathlib import Path

from orq import core

TEMPLATES = core.LIB_DIR / "templates"
SKILLS = ("orquesta-launch", "orquesta-resume")
KEY_RE = re.compile(r"^<!-- ([a-z_]+) -->$", re.M)
PLACEHOLDER_RE = re.compile(r"\{\{([a-z_]+)\}\}")
DEFAULT_USER = "tu usuario"


class RenderError(Exception):
    pass


def snippets(harness):
    text = (TEMPLATES / "snippets" / f"{harness}.md").read_text()
    parts = KEY_RE.split(text)  # [preamble, key1, body1, key2, body2, ...]
    return {parts[i]: parts[i + 1].strip("\n") for i in range(1, len(parts), 2)}


def house_rules(cfg):
    """Text of the house-rules file, or "" if none is configured. A configured but missing file is an error."""
    p = cfg.get("house_rules")
    if not p:
        return ""
    path = Path(p).expanduser()
    if not path.is_file():
        raise RenderError(f"no encuentro el archivo de reglas de la casa: {path}")
    return path.read_text().strip()


def context(cfg, harness="claude"):
    h = core.home()
    user = cfg.get("user") or DEFAULT_USER
    ctx = {
        "usuario": user,
        "aprobador": cfg.get("approver") or user,
        "orq_bin": f"{core.tilde(h)}/bin/orq",
        "protocolo": core.tilde(core.protocol_path(harness)),
        "config": f"{core.tilde(h)}/config.json",
        "max_vivos": str(cfg.get("max_alive") or core.DEFAULT_MAX_ALIVE),
    }
    ctx.update(snippets(harness))
    return ctx


def fill(text, ctx):
    for _ in range(3):  # snippets may hold placeholders themselves
        text = PLACEHOLDER_RE.sub(lambda m: ctx.get(m.group(1), m.group(0)), text)
    left = sorted(set(PLACEHOLDER_RE.findall(text)))
    if left:
        raise RenderError(f"faltan valores para: {', '.join(left)}")
    return text


def harnesses(cfg):
    return [x for x in (cfg.get("harnesses") or ["claude"]) if (TEMPLATES / "snippets" / f"{x}.md").exists()]


def protocol(cfg, harness="claude"):
    rules = house_rules(cfg)
    ctx = context(cfg, harness)
    ctx["reglas_de_la_casa"] = f"\n## Reglas de la casa\n\n{rules}\n" if rules else ""
    return fill((TEMPLATES / "PROTOCOL.md.tmpl").read_text(), ctx)


def skill(name, cfg, harness="claude"):
    rules = house_rules(cfg) if name == "orquesta-launch" else ""
    ctx = context(cfg, harness)
    ctx["reglas_de_la_casa"] = (f"\n## 8. Reglas de la casa\n\nAplícalas al coordinar y al escribir los briefs.\n\n"
                                f"{rules}\n") if rules else ""
    return fill((TEMPLATES / "skills" / name / "SKILL.md.tmpl").read_text(), ctx)


def skills_dir(harness="claude"):
    """Claude Code: ~/.claude/skills. Codex: $HOME/.agents/skills (core/src/skills, rust-v0.166.0)."""
    return Path.home() / (".claude/skills" if harness == "claude" else ".agents/skills")


def outputs(cfg):
    """[(path, text)] that an install writes: per harness, the protocol, plus the skills if enabled."""
    out = []
    for hn in harnesses(cfg):
        out.append((core.protocol_path(hn), protocol(cfg, hn)))
        if cfg.get("skills", True):
            for name in SKILLS:
                out.append((skills_dir(hn) / name / "SKILL.md", skill(name, cfg, hn)))
    return out
