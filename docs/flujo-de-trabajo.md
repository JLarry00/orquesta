# Flujo de trabajo: ramas, versiones y publicación

Orquesta vive en dos repos, cada uno con una sola rama larga:

| Repo | Visibilidad | Ramas y tags | Para qué |
|---|---|---|---|
| `JLarry00/orquesta-dev` | privado | `dev` (por defecto) y ramas cortas `feat/*` / `fix/*`; tags `vX.Y.Z` | todo el desarrollo, con su historial y el trabajo a medias |
| `JLarry00/orquesta` | público | `main` y, mientras dura su PR, `release/X.Y.Z`; tags `vX.Y.Z` y sus Releases | solo versiones publicadas, un commit por versión, sin el historial de desarrollo |

En los dos, las PR se mergean **solo con merge commit** (squash y rebase están desactivados). Los commits van a
nombre de `JLarry00 <202979278+JLarry00@users.noreply.github.com>`: nunca un correo personal o de empresa. Las
reglas para los agentes que trabajan en el repo están en [`AGENTS.md`](../AGENTS.md).

## Dónde se revisa cada cosa

| Dónde | Qué | Con IA |
|---|---|---|
| **En local, antes de subir** (lo hace el agente que trabaja en el repo) | tests, filtro de datos privados y dos revisiones de IA: [`code-verifier`](../.claude/agents/code-verifier.md) y [`privacy-auditor`](../.claude/agents/privacy-auditor.md), las dos con APPROVE | sí |
| **En GitHub Actions** | tests y filtro de datos privados en cada push y PR; la publicación al subir un tag de versión; el tag y la Release del público al mergear | no |

La IA solo se usa en local: GitHub Actions no tiene ningún token de Claude ni de otro modelo.

## El camino de un cambio

1. **Rama** `feat/<algo>` o `fix/<algo>` desde `dev`, con commits pequeños en inglés. Si cambia el
   comportamiento, el CHANGELOG se apunta en la sección de la próxima versión, `## X.Y.Z (sin publicar)`.
2. **Puerta antes de subirla** (detalle en [`AGENTS.md`](../AGENTS.md)):
   ```sh
   git fetch origin && git merge origin/dev
   python3 -m unittest                 # tests
   python3 scripts/check-private.py    # archivos + commits que aún no están en el remoto
   ```
   y las dos revisiones de IA sobre `git diff origin/dev..HEAD`, hasta que las dos digan APPROVE. El filtro usa
   las palabras privadas de `.forbidden-words` (en la raíz, ignorado por git, una por línea).
3. **PR a `dev`**, con los dos veredictos en el cuerpo. Se ejecuta `checks` (tests y filtro). JLarry00 la revisa
   y la mergea. Lo que llega a `dev` no se publica solo: se publica al sacar una versión.

## Sacar una versión

1. **PR de versión** a `dev` (como cualquier cambio, con su puerta): sube `__version__` en `orq/__init__.py` y
   cambia la cabecera de su sección del CHANGELOG de `## X.Y.Z (sin publicar)` a `## X.Y.Z (AAAA-MM-DD)`. Esa
   sección son las notas de la versión: lo que verá quien lea la Release.
2. **Tag**, cuando JLarry00 la haya mergeado, en ese merge commit:
   ```sh
   git fetch origin && git switch dev && git merge --ff-only origin/dev
   python3 scripts/release_notes.py notes "$(python3 scripts/release_notes.py version)"   # las notas: ¿bien?
   git tag -a vX.Y.Z -m "orquesta X.Y.Z"
   git push origin vX.Y.Z
   ```
   El tag tiene que ser **anotado** (`-a`) y llamarse `v` + la versión de `orq/__init__.py`.
3. **`publish`** (en el repo de desarrollo, al llegar el tag):
   1. repite `checks` sobre el commit del tag;
   2. comprueba el tag: anotado, igual a `v` + `__version__` de su commit, y ese commit dentro de `dev`;
   3. comprueba que el CHANGELOG tiene la sección `## X.Y.Z (AAAA-MM-DD)`, ya sin «sin publicar». Si algo de
      esto falla, no publica nada y dice por qué;
   4. crea un commit nuevo con el **contenido** de ese commit encima de la `main` pública (sin historial), a
      nombre del correo noreply, con el mensaje `Release X.Y.Z` + las notas, y lo sube a `release/X.Y.Z` del
      repo público;
   5. abre la PR `release/X.Y.Z` → `main` (título `Release X.Y.Z`; cuerpo: las notas, la versión pública
      anterior y cómo mergear) o, si ya estaba abierta, le pone el título y el cuerpo de ahora.
4. En el repo público, la PR pasa `tests` y `private-data`. **JLarry00 la mergea** (merge commit) y la rama se
   borra sola.
5. **`release`** (en el repo público, al mergear): crea el tag anotado `vX.Y.Z` en el merge commit y la GitHub
   Release «orquesta X.Y.Z», marcada como *Latest*, con las notas y un enlace a todos los cambios desde la versión
   anterior. Si la Release ya existe, no hace nada.

**La versión manda:** `publish` se niega si la `main` pública ya tiene esa versión con otro contenido, o una
posterior. Un número publicado no se reutiliza nunca. Si el contenido ya está publicado, no hace nada.

## Qué cambió entre versiones

Desde la 0.9.2 (la 0.9.1 se publicó con el flujo anterior: sin tag, sin Release y sin notas en el commit):

- **Releases** del repo público (pestaña *Releases*): una por versión, con sus notas y el enlace a la comparación
  con la anterior.
- **`CHANGELOG.md`**: todas las versiones, de la más nueva a la más vieja.
- **Commits de la `main` pública**: cada `Release X.Y.Z` lleva las mismas notas en su mensaje.
- **Comparar dos versiones**: `https://github.com/JLarry00/orquesta/compare/vA.B.C...vX.Y.Z`.
- **En el repo de desarrollo**, el tag `vX.Y.Z` marca el commit de `dev` que se publicó: `git log vA.B.C..vX.Y.Z`
  da los commits de desarrollo entre dos versiones. Ese sha no viaja al público (allí no se podría abrir).

## Quién hace qué

| Quién | Qué |
|---|---|
| Agentes (Claude Code, Codex…) | ramas `feat/*`/`fix/*`, commits y la puerta antes de subir. Con OK de JLarry00: subir la rama, abrir la PR a `dev`, la PR de versión y subir el tag. Nunca mergean. |
| JLarry00 (dueño de los repos) | mergea las PR a `dev` y las de publicación del público, y gestiona secretos, tokens, protecciones y reglas. |
| GitHub Actions | ejecuta los tests, el filtro, la publicación y el tag y la Release del público. Nunca mergea y no usa IA. |

## Qué se ejecuta en GitHub y cuándo

| Workflow (job) | Repo | Cuándo | Qué hace |
|---|---|---|---|
| `checks` (`tests`) | los dos | cada push a una rama y cada PR | `python -m unittest` con Python 3.9 en Ubuntu 24.04. Los golden que comparan con la versión antigua salen como *skipped*, con el motivo, porque en CI no está; el paquete sí se compara con los golden guardados. |
| `checks` (`private-data`) | los dos | igual | `scripts/check-private.py` sobre los archivos y los commits nuevos (en una PR, los de la PR; en un push, los del push; en una rama nueva, los que no tiene ninguna otra rama). Falla si no hay palabras privadas cargadas, salvo en PR desde un fork. |
| `publish` | solo el de desarrollo | push de un tag `v*`, o a mano con un tag que ya existe | comprueba el tag y el CHANGELOG, `checks` sobre el commit del tag, `scripts/publish.py` y la PR en el público. |
| `release` | solo el público | push a `main` (el merge de la PR de publicación) | tag anotado y Release de la versión de `orq/__init__.py`, si no existen. |

Los dos repos tienen los mismos archivos: en el que no le toca, cada workflow se salta sus jobs (miran el nombre
del repo).

Seguridad:
- Ningún workflow usa `pull_request_target`. Las PR desde forks no reciben secretos: en ellas el filtro no
  tiene palabras privadas.
- Las acciones de terceros van fijadas por SHA y cada workflow declara sus permisos: `contents: read`, salvo
  `release`, que tiene `contents: write` para crear el tag y la Release. El checkout no guarda credenciales.
- `publish` usa el token `PUBLIC_REPO_TOKEN` solo para subir la rama `release/*` y abrir o actualizar la PR del
  público. `release` usa el token del propio workflow, que solo vale en el repo público.
- Lo que encuentra el filtro sale enmascarado, porque los logs de un repo público son públicos.

> **Ojo:** una PR desde un fork pasa `private-data` sin palabras privadas y sin la revisión de IA local. Además, el
> filtro solo revisa el contenido final de la PR y los metadatos de sus commits, no el contenido de cada commit
> intermedio, que con un merge commit queda en el historial público. Antes de mergearla, pasa el filtro y las dos
> revisiones en local sobre su rama, y mira sus commits uno a uno (`git log -p`).

## Si algo falla

- **`publish` se niega o falla, y la PR pública todavía no está mergeada** (un check en rojo, notas sin fecha,
  un tag mal puesto): se arregla en `dev` con una PR, se borra el tag en el repo de desarrollo y se vuelve a
  poner en el commit bueno.
  ```sh
  git push origin :refs/tags/vX.Y.Z && git tag -d vX.Y.Z    # borra el tag (remoto y local)
  git fetch origin && git switch dev && git merge --ff-only origin/dev
  git tag -a vX.Y.Z -m "orquesta X.Y.Z" && git push origin vX.Y.Z
  ```
  `publish` vuelve a subir `release/X.Y.Z` (la reemplaza) y actualiza la PR abierta.
- **Solo faltaba un secreto o el token caducó:** arréglalo y, en la pestaña **Actions** del repo de desarrollo,
  `publish` → **Run workflow** desde `dev` (los scripts que se ejecutan son los de esa rama) con el tag. No hace
  falta tocar el tag.
- **Ya publicado** (la PR pública está mergeada): nunca se reutiliza el número ni se mueve el tag. El arreglo
  sale en la versión siguiente, `X.Y.(Z+1)`, por el camino normal.
- **Una versión cada vez:** no etiquetes la siguiente mientras la PR pública de la anterior siga abierta. Las
  dos ramas `release/*` saldrían de la misma `main` pública y la segunda chocaría al mergear.
- **`release` falló** (no hay tag o Release en el público): **Re-run jobs** en la pestaña **Actions** del repo
  público. Es idempotente: crea lo que falte.

## Puesta en marcha (comandos del dueño de los repos, en orden)

Los ejecuta el dueño de los repos; ningún agente toca ramas largas, secretos, tokens, protecciones ni reglas.

**1. Una sola rama en el repo de desarrollo.** `main` pasa a llamarse `dev` y a ser la rama por defecto;
`develop` y `pre` se borran. Antes, comprueba que no se pierde nada (las dos tienen que estar dentro de `main`) y
que no hay PR abiertas contra ellas:

```sh
git fetch origin
git merge-base --is-ancestor origin/develop origin/main && git merge-base --is-ancestor origin/pre origin/main && echo "nada que perder"
gh pr list -R JLarry00/orquesta-dev --state open --json number,baseRefName,title
gh api -X POST repos/JLarry00/orquesta-dev/branches/main/rename -f new_name=dev
gh repo edit JLarry00/orquesta-dev --default-branch dev
gh api -X DELETE repos/JLarry00/orquesta-dev/git/refs/heads/develop
gh api -X DELETE repos/JLarry00/orquesta-dev/git/refs/heads/pre
```

Y en cada copia local: `git fetch --prune origin`, `git remote set-head origin -a`, `git switch -c dev
origin/dev` y borra las ramas locales viejas (`git branch -d develop main`).

**2. La PR antigua del público** (la `release/0.9.1` del flujo anterior, sin notas). No hizo falta cerrarla: se
mergeó el 2026-11-07, así que la 0.9.1 quedó publicada con el flujo anterior, sin tag ni Release, y la primera
versión con el flujo nuevo es la 0.9.2. No hay nada que ejecutar en este paso.

**3. Secretos** (si ya están, sáltalo; solo se ven los nombres):

```sh
gh secret list -R JLarry00/orquesta-dev   # FORBIDDEN_WORDS, PUBLIC_REPO_TOKEN
gh secret list -R JLarry00/orquesta       # FORBIDDEN_WORDS
```

- `FORBIDDEN_WORDS`, en los dos repos (para `tests` y `private-data`), desde la raíz de la copia de trabajo.
  Cuando cambies `.forbidden-words`, repite estos dos comandos:
  ```sh
  grep -v '^#' .forbidden-words | paste -sd, - | gh secret set FORBIDDEN_WORDS -R JLarry00/orquesta-dev
  grep -v '^#' .forbidden-words | paste -sd, - | gh secret set FORBIDDEN_WORDS -R JLarry00/orquesta
  ```
- `PUBLIC_REPO_TOKEN`, solo en el de desarrollo: un *fine-grained personal access token* (github.com →
  Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → **Generate new token**):
  1. Nombre: `orquesta-publish`. Caducidad: la que quieras (90 días, por ejemplo); al caducar, `publish` fallará
     al subir la rama y habrá que repetir este paso.
  2. Resource owner: `JLarry00`. Repository access: **Only select repositories** → `JLarry00/orquesta` (solo el
     público).
  3. Repository permissions: **Contents: Read and write** (subir la rama `release/*`); **Pull requests: Read and
     write** (abrir y actualizar la PR); **Workflows: Read and write** (la publicación lleva los archivos de
     `.github/workflows`, y GitHub no deja subir cambios en ellos sin este permiso); Metadata: Read (se añade
     sola).
  4. **Generate token**, cópialo y guárdalo (`gh secret set` pide el valor sin mostrarlo):
     ```sh
     gh secret set PUBLIC_REPO_TOKEN -R JLarry00/orquesta-dev
     ```

**4. Los tags de versión del público no se borran ni se mueven.** Un ruleset sobre los tags `v*`: prohibido
borrarlos, moverlos y forzarlos, sin excepciones (tampoco para el dueño). Crear tags sigue libre, para que
`release` pueda hacerlo:

```sh
gh api -X POST repos/JLarry00/orquesta/rulesets --input - <<'EOF'
{
  "name": "version-tags",
  "target": "tag",
  "enforcement": "active",
  "bypass_actors": [],
  "conditions": {"ref_name": {"include": ["refs/tags/v*"], "exclude": []}},
  "rules": [{"type": "deletion"}, {"type": "update"}, {"type": "non_fast_forward"}]
}
EOF
gh api repos/JLarry00/orquesta/rulesets --jq '.[] | [.id, .name, .target, .enforcement] | @tsv'
```

Sin verificar: que el patrón se escribe `refs/tags/v*` (es el formato de la API para ramas, `refs/heads/…`).
Compruébalo en el repo público → Settings → Rules → Rulesets → `version-tags`: tiene que aplicar a los tags
`v*`. En el repo de desarrollo no se puede: un repo privado de una cuenta gratuita no admite reglas.

**5. Comprobaciones obligatorias en la `main` pública.** El comando repite la protección actual (solo por PR, 0
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

En el repo de desarrollo no hay comprobaciones obligatorias (tampoco protección de ramas, por lo mismo). Allí lo
que se exige son los checks en verde y los dos veredictos APPROVE en la PR antes de mergear (lo mira quien
mergea) y, para publicar, `publish` repite los checks.

## La primera vez (qué mirar)

1. **Al subir la rama de este cambio y abrir su PR a `dev`:** `checks` en verde (push y PR).
2. **PR de versión 0.9.2** (fecha en la cabecera del CHANGELOG) y, mergeada, **tag `v0.9.2`**:
   - en la pestaña Actions del repo de desarrollo, `publish` con `checks / tests`, `checks / private-data` y
     `publish` en verde; en `private-data`, «Commits revisados: none» (en un tag solo se miran los archivos);
   - en el público, la PR `Release 0.9.2`: un solo commit a nombre del correo noreply, con las notas en el
     mensaje; en el cuerpo, las notas con enlaces que abren los archivos, «Previous public version: 0.9.1» y los
     dos checks en verde.
3. **Al mergearla:** en el público, `release` en verde, el tag `v0.9.2` anotado (`gh api
   repos/JLarry00/orquesta/git/ref/tags/v0.9.2 --jq .object.type` dice `tag`) y la Release «orquesta 0.9.2» como
   *Latest*, con las notas. Sin enlace de comparación: la 0.9.1 no tiene tag.
