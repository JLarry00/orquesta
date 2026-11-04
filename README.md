# Orquesta

Coordina varios agentes de IA de programación, cada uno en su propia sesión: un director reparte encargos y los workers devuelven entregas.

Orquesta funciona con el arnés (el programa de agente) en el que la uses: abre un chat de Claude Code o de Codex, pídele que dirija, y sus workers serán del mismo arnés. Los modelos y esfuerzos son los de ese arnés. Se instala una vez en el ordenador y la pueden usar todos los arneses que tengas. Hoy funciona con Claude Code; el soporte de la app de Codex está construido y pendiente de prueba, y el de la CLI de Codex, en desarrollo.

## Vocabulario

| Término | Qué es | También se le llama |
|---|---|---|
| **Orquesta** | el producto, y cada ejecución: un objetivo con su árbol de agentes | |
| **Director** | el coordinador de primer nivel: la sesión que monta la orquesta | CEO, jefe de proyecto, coordinador general, orquestador |
| **Coordinador** («cordi») | quien lanza workers, respecto a ellos; el director lo es de los suyos | jefe |
| **Worker** | cualquier agente lanzado por un coordinador (todos menos el director) | trabajador, empleado, delegado |
| **Encargo** | lo que el coordinador le pide a un worker (`brief.md`) | orden, brief |
| **Entrega** | lo que el worker devuelve al terminar (`result.md`) | resultado |
| **Arnés** | el programa de agente en el que corre cada sesión (Claude Code, Codex…); el de una orquesta es el de su director | harness |

«Agente» a secas es cualquier sesión. «Subagente» es solo el interno del arnés (por ejemplo, la herramienta Agent de Claude Code). Un worker que lanza sus propios workers es su coordinador.

## Cómo funciona

El **director** divide el trabajo, escribe un **encargo** por worker y lo lanza con `orq launch`. Cada **worker**:

- es una sesión normal del mismo arnés que el director, en el workspace de la orquesta, con su encargo, un `checkpoint.md`, un `log.md` y, al terminar, su **entrega**;
- recibe el protocolo de forma que no lo pierde al compactar la conversación;
- habla con los demás con la herramienta de mensajes de su arnés, a través de una **puerta**: entre un coordinador y sus workers los mensajes pasan solos (*libre*); el resto depende de una matriz que fija el director, y los mensajes *manuales* los aprueba una persona en la sesión de quien envía;
- puede coordinar a sus propios workers: la orquesta es un árbol.

Cómo se hace cada cosa en cada arnés está en [Arneses](#arneses).

`orq` lleva el tablero (`orq status`), los estados, el log con hora, el tope de agentes vivos y la reapertura de workers cerrados con todo su historial (`orq resume`).

**Un color por orquesta.** `orq init` le da a cada orquesta un color (red, blue, green, yellow, purple, orange): el primero que no use otra orquesta abierta, o el que elijas con `--color`. Si están todos ocupados, repite el menos usado y avisa. Al cerrar una orquesta, su color queda libre. Sus workers lo llevan desde que se abren, y `orq init` te dice qué hacer para que la sesión del director también lo lleve. `orq status` y `orq runs` lo muestran. Cómo se ve depende del arnés (ver la tabla). Las orquestas de la versión anterior no tienen color.

## Arneses

Nadie elige el arnés de una orquesta: es el de la sesión que ejecuta `orq init`, que pasa a ser su director. `orq` lo detecta por esa sesión y lo guarda, y lanza todos los workers en él. Por eso el relevo del director (`orq coordinator`) tiene que hacerlo una sesión del mismo arnés. Desde una terminal normal, `orq init` se niega, porque no hay arnés del que heredar.

| Arnés | Dónde vive cada worker | Cómo se mandan los mensajes | Cómo le llega el protocolo | Cómo se ve el color | Cómo se aprueban los mensajes manuales |
|---|---|---|---|---|---|
| **Claude Code** ✅ | Una ventana de Terminal por worker, que `orq launch` abre sola | `SendMessage`; la puerta son hooks `PreToolUse`/`PostToolUse` | En el system prompt (`--append-system-prompt-file`), que se mantiene al compactar | Barra de la sesión del color de `/color` | Aviso de permiso en la ventana de quien envía |
| **App de Codex** 🧪 | Un chat de la app por worker. `orq launch` lo abre en el proyecto del workspace con el primer mensaje ya escrito; tú eliges modelo y esfuerzo y lo envías, y el worker se registra con `orq join` | Herramienta nativa `send_message_to_thread`; `orq to <nombre>` da el id del destinatario. La puerta son hooks globales en `~/.codex/hooks.json` | Bloque de orquesta en `~/.codex/AGENTS.md`, que le dice que ejecute `orq whoami` (identidad + protocolo), también después de compactar | Emoji al principio del título del chat: «🟣 w1 · informe» | Aviso de aprobación de la app en el chat de quien envía |
| **Codex CLI** 🚧 | Una sesión de terminal por worker (`codex resume` en una ventana de Terminal) | Igual que en la app (`codex_tui`) | Igual que en la app | Igual que en la app | Aviso en la sesión de quien envía |

✅ funciona y está probado. 🧪 construido, pendiente de probar en un ordenador con Codex ([guía de la prueba](docs/prueba-codex.md)). 🚧 en desarrollo: desde la CLI de Codex, `orq init` registra la orquesta, pero `orq launch` y `orq resume` se niegan.

Lo de Codex sale del código de Codex (rust-v0.166.0) y de su documentación, sin haberlo ejecutado; la prueba lo confirmará o lo cambiará. Lo más incierto:

- si los hooks se ejecutan en la app y cómo se confirman allí (en la CLI, con `/hooks`);
- si un mensaje *libre* puede pasar sin aviso en la app, o la app lo pregunta siempre (entonces libre = manual, o `orq send`);
- si la app lee `~/.codex/AGENTS.md` igual que la CLI;
- si el título del chat sale del primer mensaje (y por tanto lleva el emoji).

Lo propio de Codex:

- **Superficie:** cada orquesta de Codex es de la app o de la CLI, nunca mezcladas. Codex no dice desde qué superficie se ejecuta un comando, así que sale de tu configuración (`codex.surface`, que pregunta el instalador), salvo que la sesión del director lo indique con la variable `ORQUESTA_SURFACE`.
- **Sandbox:** los agentes de Codex trabajan con sandbox. Para que `orq` pueda escribir en `~/.orquesta` y abrir chats, el instalador añade la regla `~/.codex/rules/orquesta.rules`: los comandos `orq …` (solos, sin `cd` ni `&&` delante) se ejecutan fuera del sandbox y sin preguntar. `codex queue` directo queda prohibido.
- **Estado:** siempre en el workspace (`<workspace>/.orquesta/<run>/`).
- **Quién está vivo:** la app no deja verlo desde fuera. `orq status` enseña la última señal de cada worker (su última llamada a `orq`), y el tope de agentes vivos cuenta los que están en `running`, `waiting` o `blocked`.
- **`orq send <nombre> "<texto>"`** es el camino de reserva si la herramienta de mensajes no está: usa `codex queue` y solo vale para parejas libres.
- **Sin `--dir`:** en la app, cada chat trabaja en la carpeta de su proyecto.

El diseño del color en Codex está en [`docs/codex-color.md`](docs/codex-color.md).

## Requisitos

Para todo:

- macOS.
- `python3` 3.9 o posterior (el de macOS sirve). Solo usa la biblioteca estándar.

Por arnés:

- **Claude Code:** [Claude Code](https://claude.com/claude-code) (`claude`) en el PATH, y Terminal.app.
- **Codex** 🧪: la app de Codex. La CLI (`codex`) es opcional: solo la usa `orq send`.

## Instalar

Desde el zip o desde un clon del repo:

```sh
./install.sh
```

El instalador te pregunta, con un valor por defecto en cada caso:

- tu nombre (aparece en el protocolo y en las skills);
- quién aprueba los mensajes manuales (por defecto, tú);
- con qué arneses la usarás: `claude`, `codex` o los dos (por defecto, los que encuentre instalados), y en Codex si usas la app o la CLI;
- dónde se guarda el estado de las orquestas (por defecto, en el workspace de cada una: `<workspace>/.orquesta/<run>/`);
- el tope de agentes vivos a la vez (por defecto, según la RAM);
- un archivo opcional de **reglas de la casa** (ver abajo);
- si instala las skills.

Sin preguntas:

```sh
./install.sh --no-interactivo --nombre Ana [--aprobador Ana] [--arneses claude,codex] \
             [--superficie-codex app] [--estado workspace|<ruta>] [--max-vivos 4] \
             [--reglas-casa ~/reglas.md] [--sin-skills]
```

Instala en `~/.orquesta/` (cámbialo con la variable `ORQ_HOME`):

| Ruta | Qué es |
|---|---|
| `~/.orquesta/lib/` | el código (`orq`, la puerta, las plantillas) |
| `~/.orquesta/bin/orq` | el comando; `~/.local/bin/orq` apunta aquí |
| `~/.orquesta/config.json` | tu configuración |
| `~/.orquesta/runs.json` | el registro de orquestas (nombre → carpeta) |
| `~/.orquesta/PROTOCOL.md`, `PROTOCOL.codex.md` | el protocolo de los workers de Claude Code y de Codex, ya rellenado |
| `~/.orquesta/backup/` | lo que el instalador ha sustituido, para poder deshacer |
| `~/.claude/skills/orquesta-launch/`, `orquesta-resume/` | las skills de Claude Code |
| `~/.agents/skills/orquesta-launch/`, `orquesta-resume/` | las skills de Codex |
| `~/.codex/AGENTS.md` (un bloque marcado), `~/.codex/hooks.json` (tres entradas), `~/.codex/rules/orquesta.rules` | lo de Codex: el aviso de `orq whoami`, la puerta de los mensajes y la regla del sandbox. Lo que ya tuvieras en esos archivos se respeta |

Con Codex, la primera vez que lo abras después de instalar te pedirá confirmar los hooks nuevos (en la CLI, `/hooks`). Hasta que los confirmes, no se ejecutan, y la puerta de los mensajes no funciona.

Si `~/.local/bin` no está en tu PATH, el instalador te lo dice. Añádelo en `~/.zshrc`:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

Comprueba la instalación con:

```sh
orq doctor
```

Volver a ejecutar `./install.sh` actualiza la instalación y conserva tu configuración.

### Si ya tenías la versión anterior (`~/.claude/orquesta`)

El instalador la detecta y la migra:

1. Guarda una copia de `~/.claude/orquesta/`, de las skills y del enlace `~/.local/bin/orq` en `~/.orquesta/backup/`.
2. Copia `config.json` y `runs.json` (avisa de las orquestas cuya carpeta ya no existe, pero no las borra).
3. Ejecuta `orq migrate`: añade `schema`, `harness` y `workspace` a cada `board.json`, sin quitar nada. No toca los archivos de los workers (`settings.json`, `start.sh`, `resume.sh`, `system.md`).
4. Deja `~/.claude/orquesta/` como **capa de calzos**, para que los workers que ya estaban lanzados sigan funcionando: `bin/orq` y la puerta reenvían a la instalación nueva, `runs.json` y `config.json` son enlaces a `~/.orquesta/`, y `PROTOCOL.md` es la copia nueva. Dentro hay un `LEEME.md` que lo explica.

Hazlo cuando ningún agente esté a mitad de un comando `orq`.

### Deshacer y desinstalar

```sh
./install.sh --deshacer     # deja todo como estaba antes de la primera instalación
./uninstall.sh              # lo mismo
```

`--deshacer` restaura la copia de seguridad (la versión anterior, si la había), quita los campos que `orq migrate` añadió a los `board.json`, quita las skills, el enlace de `~/.local/bin/orq` y lo que puso en `~/.codex` (si no has tocado esos archivos, los deja byte a byte como estaban; si los has tocado, quita solo lo suyo), y borra `~/.orquesta/`. Las orquestas creadas después de instalar se conservan en el registro.

## Consejo (Claude Code): título de las ventanas de Terminal

Terminal enseña en el título de cada ventana el comando que la abrió, que aquí es largo. Para ver solo el nombre del worker: **Terminal › Ajustes › Perfiles › (tu perfil) › Ventana**, y en «Título» desmarca **«Argumentos»**.

## Uso

Desde una sesión de agente abierta en tu proyecto, pide algo como «lanza un worker que revise los tests» o «haz de director de esto». La skill `orquesta-launch` le explica cómo hacerlo. Los comandos que usa, por si quieres verlos (se ejecutan desde la sesión del director):

```sh
orq init informe --coordinator <nombre-de-tu-sesión> --goal "Informe de ventas"
# escribe el encargo en $(orq where informe)/agents/datos/brief.md
orq launch informe datos --parent <nombre-de-tu-sesión> --topic "Sacar los datos" --model opus --effort medium
orq status informe -v
```

Los modelos y esfuerzos que acepta `--model`/`--effort` son los del arnés de la orquesta (`orq launch -h`).

Para ponerte al día después de estar en otra cosa: «ponme al día de la orquesta» (skill `orquesta-resume`).

Comandos propios de Codex, que usan los agentes: `orq join` (el worker se registra), `orq whoami` (identidad y protocolo), `orq to <nombre>` (id del chat de otro agente), `orq send` (reserva para parejas libres) y `orq open <run> <nombre>` (abre el chat de un agente).

Todos los comandos: `orq -h` y `orq <comando> -h`.

## Tus reglas y las reglas de la casa

Cada worker es una sesión normal de su arnés, abierta en el workspace de la orquesta. Por eso carga las mismas reglas que cualquier otra sesión tuya en ese proyecto, y orquesta no tiene que copiarlas ni resumirlas.

- **Claude Code** (comprobado): tu `CLAUDE.md` global (`~/.claude/CLAUDE.md`) y el del proyecto, las skills de `~/.claude/skills`, las memorias de Claude Code del proyecto (van por carpeta: el worker ve las del workspace) y tus hooks de usuario. El `--settings` que pone `orq launch` solo añade lo de la orquesta: permisos para su carpeta y para `orq`, las carpetas extra de `--dir` y la puerta de los mensajes.
- **Codex** 🧪 (sin probar): tu `AGENTS.md` global (`~/.codex/AGENTS.md`) y el del proyecto, y tus skills de `~/.agents/skills`, como cualquier sesión de Codex.

Así, si ya tienes un sistema de reglas grande (muchas instrucciones, skills, hooks…), los workers lo usan sin hacer nada.

El archivo de **reglas de la casa** es solo para lo propio de la orquesta: cómo quieres que trabajen los workers y qué deben tener en cuenta los coordinadores al escribir encargos (qué no se toca, qué necesita permiso, cómo se trabaja con git…). Puede ser corto y enlazar a otros archivos («las reglas de git están en `~/reglas/git.md`»), que los workers pueden abrir cuando les haga falta. Indícalo al instalar (`--reglas-casa`): se añade al final del protocolo de los workers y de la skill `orquesta-launch`. Tienes un ejemplo en [`examples/reglas-de-la-casa.ejemplo.md`](examples/reglas-de-la-casa.ejemplo.md). El producto no trae reglas de ninguna empresa.

Si cambias el archivo después, ejecuta `orq render`. Los workers ya lanzados lo reciben al reabrirse.

## Desarrollo

```sh
python3 -m unittest            # tests; los «golden» comparan con el comportamiento de la versión anterior
scripts/check-private.py       # filtro de datos privados (archivos y commits sin subir); pásalo antes de un push
scripts/make-zip.sh            # dist/orquesta-<versión>.zip
```

Antes de subir un cambio hay una puerta (tests, filtro y dos revisiones de IA en local): [`AGENTS.md`](AGENTS.md). Ramas, comprobaciones de GitHub Actions y cómo se publica una versión: [`docs/flujo-de-trabajo.md`](docs/flujo-de-trabajo.md).

Estructura:

```
install.sh  uninstall.sh  installer.py
orq/                 # el paquete: cli, core, comms (la matriz), msglog, render, setup (migrate, calzos, doctor)
  harness/claude.py  # lo propio de Claude Code (lanzar, ventanas, settings)
  harness/codex.py   # lo propio de Codex (enlace de la app, join, señal)
  codex_setup.py     # lo que el instalador pone en ~/.codex y cómo lo quita
hooks/claude_gate.py # la puerta de Claude Code (PreToolUse y PostToolUse sobre SendMessage)
hooks/codex_gate.py  # la puerta de Codex (PreToolUse, PermissionRequest y PostToolUse)
templates/           # PROTOCOL.md.tmpl, skills, fragmentos por arnés, calzos, codex/ (bloque, reglas)
examples/  scripts/  tests/
```
