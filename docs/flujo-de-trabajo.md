# Flujo de trabajo: ramas, comprobaciones y publicación

Orquesta vive en dos repos:

| Repo | Visibilidad | Ramas | Para qué |
|---|---|---|---|
| `JLarry00/orquesta-dev` | privado | `develop` (por defecto), `pre`, `main`, y `feat/*` / `fix/*` | todo el desarrollo, con su historial |
| `JLarry00/orquesta` | público | `main` y, de paso, `release/<versión>` | solo versiones publicadas, un commit por versión, sin el historial de desarrollo |

En los dos, las PR se mergean **solo con merge commit** (squash y rebase están desactivados). Los commits van a
nombre de `JLarry00 <202979278+JLarry00@users.noreply.github.com>`: nunca un correo personal o de empresa. Las
reglas para los agentes que trabajan en el repo están en [`AGENTS.md`](../AGENTS.md).

## Dónde se revisa cada cosa

| Dónde | Qué | Con IA |
|---|---|---|
| **En local, antes de subir** (lo hace el agente que trabaja en el repo) | tests, filtro de datos privados y dos revisiones de IA: [`code-verifier`](../.claude/agents/code-verifier.md) y [`privacy-auditor`](../.claude/agents/privacy-auditor.md), las dos con APPROVE | sí |
| **En GitHub Actions**, en cada push y PR | tests y filtro de datos privados; y, en la `main` de desarrollo, la publicación | no |

La IA solo se usa en local: GitHub Actions no tiene ningún token de Claude ni de otro modelo.

## El camino de un cambio

1. **Rama** `feat/<algo>` o `fix/<algo>` desde `develop`, con commits pequeños en inglés.
2. **Puerta antes de subirla** (detalle en [`AGENTS.md`](../AGENTS.md)):
   ```sh
   git fetch origin && git merge origin/develop
   python3 -m unittest                 # tests
   python3 scripts/check-private.py    # archivos + commits que aún no están en el remoto
   ```
   y las dos revisiones de IA sobre `git diff origin/develop..HEAD`, hasta que las dos digan APPROVE. El filtro
   usa las palabras privadas de `.forbidden-words` (en la raíz, ignorado por git, una por línea).
3. **PR a `develop`**, con los dos veredictos en el cuerpo. Se ejecuta `checks` (tests y filtro). JLarry00
   la revisa y la mergea.
4. **Promoción:** PR `develop` → `pre` y PR `pre` → `main`, las dos de JLarry00.
5. **Publicación:** al llegar a la `main` de desarrollo se ejecuta `publish`:
   1. repite `checks` sobre ese commit; si fallan, no publica nada;
   2. crea un commit nuevo con el **contenido** de esa `main` encima de la `main` pública (sin historial), a nombre
      del correo noreply, y lo sube a la rama `release/<versión>` del repo público;
   3. abre la PR `release/<versión>` → `main` en el repo público (o, si ya estaba abierta, la actualiza).
6. En el repo público, la PR pasa `tests` y `private-data`. **JLarry00 la mergea** (merge commit) y la rama se
   borra sola.

**La versión manda:** si la `main` pública ya tiene la versión de `orq/__init__.py` con otro contenido, `publish`
se niega. Antes de promocionar a `main`, sube la versión y añade su sección al `CHANGELOG.md`. Si el contenido no
ha cambiado, no hace nada.

Para publicar a mano (por ejemplo, después de arreglar un secreto que faltaba): pestaña **Actions** del repo de
desarrollo → `publish` → **Run workflow** sobre `main`. Desde otra rama no hace nada.

## Quién hace qué

| Quién | Qué |
|---|---|
| Agentes (Claude Code, Codex…) | ramas `feat/*`/`fix/*`, commits y la puerta antes de subir (tests, filtro y las dos revisiones de IA). Sin push ni PR salvo que se lo pidan. |
| JLarry00 (dueño de los repos) | sube ramas, abre y mergea PR, promociona `develop` → `pre` → `main`, mergea las PR de publicación, y gestiona secretos, tokens y protecciones. |
| GitHub Actions | ejecuta los tests, el filtro y la publicación. Nunca mergea y no usa IA. |

## Qué se ejecuta en GitHub y cuándo

| Workflow (job) | Repo | Cuándo | Qué hace |
|---|---|---|---|
| `checks` (`tests`) | los dos | cada push a cualquier rama y cada PR | `python -m unittest` con Python 3.9 en Ubuntu 24.04. Los golden que comparan con la versión antigua salen como *skipped*, con el motivo, porque en CI no está; el paquete sí se compara con los golden guardados. |
| `checks` (`private-data`) | los dos | igual | `scripts/check-private.py` sobre los archivos y los commits nuevos (en una PR, los de la PR; en un push, los del push; en una rama nueva, los que no tiene ninguna otra rama). Falla si no hay palabras privadas cargadas, salvo en PR desde un fork. |
| `publish` | solo el de desarrollo | push a `main`, o a mano | `checks` + `scripts/publish.py` + PR en el público. En el repo público el archivo también está, pero sus jobs se saltan. |

Seguridad:
- Ningún workflow usa `pull_request_target`. Las PR desde forks no reciben secretos: en ellas el filtro no
  tiene palabras privadas.
- Las acciones de terceros van fijadas por SHA y cada workflow declara sus permisos (`contents: read`). El
  checkout no guarda credenciales.
- `publish` usa el token `PUBLIC_REPO_TOKEN` solo para subir la rama `release/*` y abrir la PR del público.
- Lo que encuentra el filtro sale enmascarado, porque los logs de un repo público son públicos.

> **Ojo:** una PR desde un fork pasa `private-data` sin palabras privadas y sin la revisión de IA local. Además, el
> filtro solo revisa el contenido final de la PR y los metadatos de sus commits, no el contenido de cada commit
> intermedio, que con un merge commit queda en el historial público. Antes de mergearla, pasa el filtro y las dos
> revisiones en local sobre su rama, y mira sus commits uno a uno (`git log -p`).

## Puesta en marcha (comandos del dueño de los repos, en orden)

Los ejecuta el dueño de los repos; ningún agente toca secretos, tokens ni protecciones. Hacen falta dos
secretos: `FORBIDDEN_WORDS` en los dos repos y `PUBLIC_REPO_TOKEN` solo en el de desarrollo.

**1. Palabras privadas** (para `tests` y `private-data`), desde la raíz de la copia de trabajo:

```sh
grep -v '^#' .forbidden-words | paste -sd, - | gh secret set FORBIDDEN_WORDS -R JLarry00/orquesta-dev
grep -v '^#' .forbidden-words | paste -sd, - | gh secret set FORBIDDEN_WORDS -R JLarry00/orquesta
```

Cuando cambies `.forbidden-words`, repite estos dos comandos.

**2. Token para publicar** (*fine-grained personal access token*), en github.com:
1. Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → **Generate new token**.
2. Nombre: `orquesta-publish`. Caducidad: la que quieras (90 días, por ejemplo); al caducar, `publish` fallará al
   subir la rama y habrá que repetir este paso.
3. Resource owner: `JLarry00`. Repository access: **Only select repositories** → `JLarry00/orquesta` (solo el
   público).
4. Repository permissions:
   - **Contents: Read and write** (subir la rama `release/*`);
   - **Pull requests: Read and write** (abrir la PR);
   - **Workflows: Read and write**: hace falta porque la publicación lleva los archivos de `.github/workflows`, y
     GitHub no deja subir cambios en ellos sin este permiso;
   - Metadata: Read (se añade sola).
5. **Generate token**, cópialo y guárdalo **solo en el repo de desarrollo** (`gh secret set` pide el valor sin
   mostrarlo):

```sh
gh secret set PUBLIC_REPO_TOKEN -R JLarry00/orquesta-dev
```

**3. Comprobar los secretos** (solo se ven los nombres):

```sh
gh secret list -R JLarry00/orquesta-dev   # FORBIDDEN_WORDS, PUBLIC_REPO_TOKEN
gh secret list -R JLarry00/orquesta       # FORBIDDEN_WORDS
```

**4. Comprobaciones obligatorias en la `main` pública.** Hazlo cuando `tests` y `private-data` hayan pasado ya en
alguna PR del público (la primera de publicación). El comando repite la protección actual (solo por PR, 0
aprobaciones, también para administradores, sin force push ni borrado) y añade las dos comprobaciones, atadas a
GitHub Actions (`app_id` 15368) para que nadie las pueda imitar con un estado puesto a mano:

```sh
gh api -X PUT repos/JLarry00/orquesta/branches/main/protection --input - <<'EOF'
{
  "required_status_checks": {
    "strict": false,
    "checks": [
      {"context": "tests", "app_id": 15368},
      {"context": "private-data", "app_id": 15368}
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": false,
    "require_code_owner_reviews": false,
    "require_last_push_approval": false,
    "required_approving_review_count": 0
  },
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": false,
  "lock_branch": false,
  "allow_fork_syncing": false
}
EOF
gh api repos/JLarry00/orquesta/branches/main/protection --jq '.required_status_checks.checks[].context'
```

`strict` va a `false` porque la rama `release/*` siempre se crea encima de la `main` pública del momento: ya
está al día.

En el repo de desarrollo no hay comprobaciones obligatorias: un repo privado de una cuenta gratuita no admite
protección de ramas. Allí lo que se exige son los checks en verde y los dos veredictos APPROVE en la PR antes de
mergear (lo mira quien mergea) y, para publicar, `publish` repite los checks.

## La primera vez (qué mirar)

1. **Al subir esta rama** (`feat/ci-checks-and-publish`) y abrir su PR a `develop`:
   - `checks` aparece dos veces (push y PR): las dos en verde; en `tests`, los golden de la versión antigua como
     *skipped* con su motivo.
   - En `private-data`, la línea «Commits revisados» con el rango esperado y «N palabras privadas» > 0.
2. **Al promocionar a `main`** (con la versión ya subida): `publish` ejecuta `checks / tests` y
   `checks / private-data`, sube `release/<versión>` al público y abre la PR. En esa PR: los dos checks en verde,
   un solo commit «Release <versión>» a nombre del correo noreply y sin el historial de desarrollo.
3. **Después de mergearla**, aplica el paso 4 de la puesta en marcha.
