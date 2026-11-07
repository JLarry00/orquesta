# Desarrollar orquesta

Instrucciones para cualquier agente (Claude Code, Codex u otro arnés) que trabaje en este repo. Qué es orquesta
y cómo se usa: [README.md](README.md). Ramas, comprobaciones de GitHub y publicación:
[docs/flujo-de-trabajo.md](docs/flujo-de-trabajo.md).

## Repos y ramas

- Orquesta se desarrolla en un repo **privado** con una sola rama larga, `dev`; se trabaja en `feat/<algo>` o
  `fix/<algo>` desde `dev`.
- El repo **público** solo tiene `main`: recibe cada versión publicada como un único commit, sin historial, por una
  PR `release/X.Y.Z` que abre el workflow `publish` al subir el tag `vX.Y.Z` en el de desarrollo. Si estás en el
  público (no hay `dev`), un cambio se propone al dueño del repo, que lo lleva al de desarrollo: las reglas de
  abajo son las de ese repo.

## Reglas de git

- Commits pequeños, con mensaje en inglés.
- Identidad: `…@users.noreply.github.com`. Comprueba `git config user.email` antes del primer commit; nunca un
  correo personal o de empresa.
- Las PR van **siempre a `dev`**. Se mergean **siempre con merge commit**: nunca squash ni rebase.
- Mergea siempre el dueño del repo: las PR a `dev` y la PR de publicación del repo público. Un agente nunca mergea.
- **Versión:** una PR propia que sube `__version__` (`orq/__init__.py`) y pone la fecha en la cabecera del
  CHANGELOG, `## X.Y.Z (AAAA-MM-DD)`. Mergeada, se etiqueta ese merge commit de `dev` con un tag **anotado**,
  `git tag -a vX.Y.Z -m "orquesta X.Y.Z"`, y se sube el tag: eso publica. Nunca se mueve ni se reutiliza un tag
  publicado; si algo sale mal, se saca la versión siguiente (detalle en la guía).
- Nunca: push a `dev` o `main`; force push; reescribir historia que ya está subida; `--no-verify`.
- Push, PR y tags, solo cuando el dueño lo pida. Secretos, ajustes del repo, protecciones y reglas de rama o de
  tags, nunca.

## Código

- Python 3.9 o posterior, **solo la biblioteca estándar**.
- Textos para personas (salidas de `orq`, instalador, protocolo, skills, docs) en español; código,
  identificadores y commits en inglés.
- Lo propio de cada arnés va en `orq/harness/<arnés>.py` y `templates/snippets/<arnés>.md`. El resto se queda
  neutral.
- Si cambia el comportamiento: README y CHANGELOG, en la sección de la próxima versión, `## X.Y.Z (sin publicar)`.
  La versión de `orq/__init__.py` y la fecha de esa cabecera van en la PR de versión.

## Puerta antes de subir (push o PR)

Todo esto, en orden, y todo en verde:

1. Rama al día: `git fetch origin` y `git merge origin/dev`. Nunca rebase de una rama ya subida.
2. `python3 -m unittest`
3. `python3 scripts/check-private.py`: archivos y commits que aún no están en el remoto. Usa las palabras privadas
   del archivo `.forbidden-words` de la raíz (ignorado por git); si no lo tienes, pídeselo al dueño.
4. Las dos revisiones de IA sobre `git diff origin/dev..HEAD`, y las dos con **APPROVE**:
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
