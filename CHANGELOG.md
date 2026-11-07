# Cambios

## 0.9.2 (2026-11-07)

Sin cambios en `orq` ni en el instalador: solo cómo se desarrolla y se publica el repo
([`docs/flujo-de-trabajo.md`](docs/flujo-de-trabajo.md)). Es la primera versión que se publica con este flujo, con
tag y notas.

- **Dos repos, una rama larga en cada uno:** el de desarrollo, privado, con `dev` (sustituye a `develop`, `pre` y
  `main`); el público, con `main`, que solo recibe versiones publicadas, un commit por versión y sin el historial
  de desarrollo.
- **Versiones con tag:** una PR de versión sube `__version__` y pone la fecha en su sección del CHANGELOG; el tag
  anotado `vX.Y.Z` en ese commit de `dev` lanza `publish` (antes lo lanzaba cada push a `main`), que comprueba el
  tag, las notas y los checks y abre en el público la PR `release/X.Y.Z`.
- **Notas de cada versión:** la sección del CHANGELOG va en el commit público y en el cuerpo de la PR (antes solo
  decían de qué commit venían). Al mergear la PR, `release` crea en el público el tag `vX.Y.Z` y la GitHub
  Release con esas notas.
- **Scripts:** `release_notes.py` (nuevo: la versión y su sección del CHANGELOG, para los dos workflows) y
  `publish.py` (publica desde un tag, se niega si el tag, la versión o las notas no cuadran, y crea o actualiza
  la PR pública).

## 0.9.1 (2026-11-07)

Sin cambios en `orq` ni en el instalador: solo cómo se desarrolla y se publica el repo
([`docs/flujo-de-trabajo.md`](docs/flujo-de-trabajo.md)).

- **GitHub Actions, sin IA:** `checks` (tests con Python 3.9 y filtro de datos privados) en cada push y PR;
  `publish` (de la `main` de desarrollo a una PR `release/<versión>` en el repo público, solo si las
  comprobaciones pasan).
- **Revisión de IA en local, antes de subir:** dos revisores, `code-verifier` y `privacy-auditor`
  (`.claude/agents/`), que tienen que dar APPROVE. `AGENTS.md` (y `CLAUDE.md`, que lo importa) explica a
  cualquier arnés las reglas del repo y esa puerta.
- **`scripts/check-private.py`:** palabras privadas, correos que no son noreply de GitHub, rutas personales y
  patrones de secretos, en los archivos y en los commits nuevos. Enmascara lo que encuentra.
- **`scripts/publish.py`:** el contenido de la `main` de desarrollo como un commit nuevo sobre la `main` pública,
  sin historial; se niega si la versión ya está publicada con otro contenido.
- **Tests:** sin la versión antigua instalada (en CI), los golden de esa versión salen como *skipped* con su motivo.

## 0.9.0 (sin publicar; para la prueba con la app de Codex)

Codex, superficie **app** (🧪: construido a partir del código de Codex rust-v0.166.0, sin haberlo ejecutado; la
prueba está en `docs/prueba-codex.md`). La superficie CLI de Codex sigue sin construir: `orq launch` se niega.

- **Lanzar:** `orq launch` en una orquesta de Codex abre `codex://new?path=<workspace>&prompt=…`, un chat nuevo en
  el proyecto con el primer mensaje escrito. Quien lo lanza elige modelo y esfuerzo en la app y lo envía (no hay
  parámetro para ellos). El worker ejecuta `orq join <run> <nombre> <clave>`, que une su nombre con
  `CODEX_THREAD_ID` y le da su identidad y el protocolo.
- **Comandos nuevos:** `orq whoami` (identidad + protocolo, lo que en Claude Code va en el system prompt),
  `orq join`, `orq to <nombre>` (id del chat y modo de la pareja), `orq send` (reserva con `codex queue`, solo
  parejas libres) y `orq open <run> <nombre>`; `orq doctor --sonda on|permitir|off` para la prueba.
- **Puerta de Codex** (`hooks/codex_gate.py`), global en `~/.codex/hooks.json`, sobre `send_message_to_thread`:
  PreToolUse apunta el intento o bloquea si el destinatario no es de la orquesta; PermissionRequest aprueba los
  libres y deja que Codex pregunte por los manuales; PostToolUse apunta el envío.
- **Quién está vivo:** en la app no se puede ver desde fuera. Cada llamada a `orq` de un agente es su «última
  señal» (`agents/<n>/signal`), y el tope cuenta los agentes en `running`, `waiting` o `blocked`.
- **Superficie:** se hereda de la sesión del director si se puede saber (`ORQUESTA_SURFACE`, o el
  `__CFBundleIdentifier` de la app, sin verificar); si no, `codex.surface` de `config.json`. Va en el board y en
  cada agente.
- **Instalador:** pregunta los arneses (por defecto, los que encuentra) y, con Codex, la superficie. Con Codex
  escribe el bloque de `~/.codex/AGENTS.md` (o `AGENTS.override.md` si existe), tres grupos de hooks en
  `~/.codex/hooks.json`, `~/.codex/rules/orquesta.rules` (`orq` fuera del sandbox sin preguntar; `codex queue`
  prohibido), `~/.orquesta/PROTOCOL.codex.md` y las skills en `~/.agents/skills`. Respeta lo que ya hubiera.
  `--deshacer` deja esos archivos byte a byte como estaban si nadie los tocó; si los tocaste, quita solo lo suyo.
  `orq doctor` lo comprueba y prueba la puerta de Codex en seco.
- **Adaptadores:** abrir ventanas o chats, lanzar y reabrir es cosa del adaptador de cada arnés (`harness/claude.py`,
  `harness/codex.py`), no de `cli.py`. Para Claude Code el comportamiento no cambia (golden intactos) y lo que se
  genera para él es idéntico, salvo lo ya dicho en 0.4.0.
- Las orquestas de Codex guardan el estado siempre en el workspace; `--dir` es solo de Claude Code.

## 0.4.0 (sin publicar)

Primera versión empaquetada, solo para Claude Code. Sustituye a la versión de un solo archivo que vivía en
`~/.claude/orquesta`.

- Paquete `orq/` (solo biblioteca estándar, Python 3.9+) con el mismo comportamiento que la versión anterior,
  fijado con tests «golden».
- Se instala en `~/.orquesta/` (`ORQ_HOME` para cambiarlo) con `./install.sh`; `--deshacer` lo revierte.
- Migra la versión anterior y deja `~/.claude/orquesta/` como capa de calzos para los agentes ya lanzados.
- Protocolo y skills generados desde plantillas en español, sin datos personales; archivo opcional de reglas
  de la casa.
- El esfuerzo máximo es `high`: `orq launch` rechaza `xhigh` (la versión anterior lo admitía).
- Vocabulario nuevo en todos los textos para personas (README, protocolo, skills y mensajes de `orq`, de la
  puerta y del instalador): **director** (el coordinador de primer nivel), **coordinador**, **worker**,
  **encargo** (`brief.md`) y **entrega** (`result.md`). Por eso cambian, respecto a la versión anterior,
  textos como «[director]» en `orq status`, «libre (coordinador<->worker)» en la puerta o «falta el encargo»
  en `orq launch`; los tests «golden» del paquete los guardan aparte, en `tests/golden/pkg/`. No cambian los
  nombres de archivo, las claves JSON, los comandos ni las opciones (`brief.md`, `--parent`, `coordinator`…).
- **Un color por orquesta** (`board.json` → `color`): `orq init` elige el primero de la paleta de `/color` (red,
  blue, green, yellow, purple, orange; pink y cyan no, porque sus emojis son corazones) que no use otra
  orquesta abierta (o `--color`), y lo dice. `orq launch` crea antes la sesión del worker con
  `claude -p --session-id … "/color <c>"` (no llama al modelo), y `start.sh` la reanuda con `--resume`; si
  crearla falla, `orq launch` se detiene sin tocar el tablero. `orq status` y `orq runs` muestran el color. Las
  orquestas sin color (las de la versión anterior) se lanzan como antes.
- Textos que no dan por hecho Claude Code: el README presenta orquesta como coordinador de agentes para varios arneses
  (Claude Code ✅; Codex CLI y app 🚧, sin construir ni probar), con una tabla «Arneses». Las frases propias de
  Claude Code del protocolo y de la skill `orquesta-launch` (ventana de Terminal, system prompt…) pasan al
  fragmento `templates/snippets/claude.md`; lo que se genera para Claude Code no cambia ni una letra.
- Vocabulario: «orquestador» es sinónimo de **director**, no de coordinador.
- README: sección «Tus reglas y las reglas de la casa». Un worker carga lo mismo que cualquier sesión del
  arnés en ese proyecto; el archivo de reglas de la casa es solo para lo propio de la orquesta.
- **El arnés se hereda del director.** `orq init` lo detecta por la sesión que lo ejecuta
  (`CLAUDE_CODE_SESSION_ID` → Claude Code, `CODEX_THREAD_ID` → Codex) y lo guarda en el board; ya no hay opción
  `--harness`. Desde una terminal normal (sin arnés), o con las variables de los dos arneses a la vez, se niega
  (la versión anterior sí dejaba crear orquestas desde una terminal). `orq coordinator` se niega si la sesión
  nueva es de otro arnés. Una orquesta de Codex se puede crear, pero `orq launch` y `orq resume` se niegan con
  «todavía no disponible»; `orq status` funciona, sin saber quién está vivo.
- Mensajes de `orq` sin «ventana» fijo: lo que depende del arnés sale de su adaptador (para Claude Code siguen
  diciendo «en una ventana nueva»). Cambia «preparado sin ventana» por «preparado sin abrir» (`--no-window`) y la
  ayuda de `launch` y `resume`.
- El `settings.json` de cada worker ya no lleva la regla `Write(/<orquesta>/agents/**)`, que la versión anterior sí
  ponía: Claude Code la ignora (avisa de que solo cuentan las reglas `Edit(...)`) y la regla `Edit` ya deja
  escribir al worker en su carpeta. Comprobado con un worker de prueba: escribe en su carpeta y fuera se le niega.
- Comandos nuevos: `orq doctor`, `orq migrate`, `orq render`, `orq --version`.
- `board.json` lleva `schema: 2` y `harness`; el llamador se reconoce por `CLAUDE_CODE_SESSION_ID` o
  `CODEX_THREAD_ID`, para dejar sitio a Codex.
