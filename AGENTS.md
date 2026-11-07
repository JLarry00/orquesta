# Desarrollar orquesta

Instrucciones para cualquier agente (Claude Code, Codex u otro arnés) que trabaje en este repo. Qué es orquesta
y cómo se usa: [README.md](README.md). Ramas, comprobaciones de GitHub y publicación:
[docs/flujo-de-trabajo.md](docs/flujo-de-trabajo.md).

## Repos y ramas

- Orquesta se desarrolla en un repo **privado**, con ramas `develop` (por defecto), `pre` y `main`; se trabaja en
  `feat/<algo>` o `fix/<algo>` desde `develop`.
- El repo **público** solo tiene `main`: recibe cada versión publicada como un único commit, sin historial, por una
  PR que abre el workflow `publish`. Si estás en el público (no hay `develop`), un cambio se propone al dueño del
  repo, que lo lleva al de desarrollo: las reglas de abajo son las de ese repo.

## Reglas de git

- Commits pequeños, con mensaje en inglés.
- Identidad: `…@users.noreply.github.com`. Comprueba `git config user.email` antes del primer commit; nunca un
  correo personal o de empresa.
- Las PR van **siempre a `develop`**. Se mergean **siempre con merge commit**: nunca squash ni rebase.
- Las promociones `develop` → `pre` → `main`, y la PR de publicación del repo público, las hace el dueño del
  repo. Un agente nunca mergea.
- Nunca: push a `develop`, `pre` o `main`; force push; reescribir historia que ya está subida; `--no-verify`.
- Push y PR, solo cuando el dueño lo pida. Secretos, ajustes del repo y protecciones de rama, nunca.

## Código

- Python 3.9 o posterior, **solo la biblioteca estándar**.
- Textos para personas (salidas de `orq`, instalador, protocolo, skills, docs) en español; código,
  identificadores y commits en inglés.
- Lo propio de cada arnés va en `orq/harness/<arnés>.py` y `templates/snippets/<arnés>.md`. El resto se queda
  neutral.
- Si cambia el comportamiento: README, CHANGELOG y, para publicar, la versión de `orq/__init__.py`.

## Puerta antes de subir (push o PR)

Todo esto, en orden, y todo en verde:

1. Rama al día: `git fetch origin` y `git merge origin/develop`. Nunca rebase de una rama ya subida.
2. `python3 -m unittest`
3. `python3 scripts/check-private.py`: archivos y commits que aún no están en el remoto. Usa las palabras privadas
   del archivo `.forbidden-words` de la raíz (ignorado por git); si no lo tienes, pídeselo al dueño.
4. Las dos revisiones de IA sobre `git diff origin/develop..HEAD`, y las dos con **APPROVE**:
   - [`code-verifier`](.claude/agents/code-verifier.md): corrección, regresiones, instalación, compatibilidad,
     arneses, tests, documentación e idioma.
   - [`privacy-auditor`](.claude/agents/privacy-auditor.md): datos privados que el filtro no pilla.

   Con `REJECT`, arregla lo que digan y vuelve a pasar las dos. **Cómo lanzarlas:**
   - En **Claude Code** son subagentes del repo (`.claude/agents/`): lánzalos en paralelo.
   - En un arnés **sin subagentes** (Codex u otros): haz tú las dos revisiones, una detrás de otra, siguiendo esas
     definiciones al pie de la letra y con su formato de informe. Si el arnés deja abrir un chat nuevo, mejor ahí,
     sin el contexto de quien ha escrito el cambio. Revisa como un tercero: no des por bueno lo que acabas de
     escribir.
5. El cuerpo de la PR lleva: qué cambia y por qué, cómo se ha verificado (tests y filtro) y **los dos veredictos**
   (la línea final de cada informe y sus avisos).

GitHub Actions repite los tests y el filtro (sin IA). La revisión de IA solo se hace aquí, antes de subir.
