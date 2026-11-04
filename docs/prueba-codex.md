# Prueba de orquesta con la app de Codex

Guía para probar la versión 0.9 (0.9.0 o posterior) en un ordenador con la app de Codex. Primero la app; la CLI de Codex vendrá en
otra ronda.

Todo lo de Codex está construido a partir de su código fuente (rust-v0.166.0) y su documentación, **sin haberlo
ejecutado nunca**. Esta prueba es la primera vez que corre de verdad, así que lo importante es apuntar lo que pasa,
también cuando falla.

Cada paso dice: qué hacer → qué observar → qué hacer si falla. Apunta ✓ o ✗ en cada uno.

## 0. Antes de empezar

- Apunta:
  - la versión de macOS;
  - la versión de la app de Codex (Acerca de);
  - `python3 --version`;
  - `codex --version`, si tienes la CLI (no hace falta).
- **Coste:** nada de esta lista cuesta más que el uso normal de tu suscripción.
- **Carpeta de prueba:** crea una carpeta vacía, por ejemplo `~/prueba-orquesta`, y añádela como proyecto en la app.
- **Copia lo que tengas de Codex**, para comparar al deshacer:

  ```sh
  mkdir -p ~/codex-antes
  cp -p ~/.codex/AGENTS.md ~/.codex/hooks.json ~/.codex/config.toml ~/codex-antes/ 2>/dev/null
  ls ~/.codex/rules 2>/dev/null
  ```

## A. Instalar

1. Descomprime el zip y ejecuta `./install.sh`. Responde:
   - **arneses:** `codex` (o `claude,codex` si también usas Claude Code);
   - **superficie:** `app`;
   - **estado:** `workspace`.
   - **Observa:**
     - las preguntas, en español;
     - que al final `orq doctor` dice «0 errores»;
     - que existen:
       - `~/.orquesta/`;
       - `~/.orquesta/PROTOCOL.codex.md`;
       - `~/.agents/skills/orquesta-launch/SKILL.md`;
       - el bloque `<!-- orquesta:start -->` al final de `~/.codex/AGENTS.md`;
       - tres entradas con `codex_gate.py` en `~/.codex/hooks.json`;
       - `~/.codex/rules/orquesta.rules`.
     - Abre una terminal **nueva** y comprueba que `orq --version` responde.
   - **Si falla:** copia la salida entera del instalador.
     - Si falta `python3`, apunta qué ofrece macOS (las Command Line Tools).
     - Si `orq` no está en el PATH, apunta tu shell y si `~/.local/bin` está en el PATH; mientras tanto, añádelo como dice el instalador.
2. **Confirmar los hooks.** Abre la app de Codex.
   - **Observa:** si la app te avisa de hooks nuevos y cómo te pide confirmarlos. Confírmalos. Si no avisa, busca en los ajustes algo de hooks. Si tienes la CLI, `codex` → `/hooks` también sirve, porque la confirmación se guarda en `~/.codex/config.toml`, que comparten.
   - **Si falla:** apúntalo. Sin hooks confirmados no funcionan la puerta (pasos C y F) ni la sonda.

## B. La app sin orquesta

3. **Mensajes nativos.** Abre dos chats, **A** y **B**, en el proyecto de prueba. En A, pide:
   - «Llama a `list_threads` y dime el id de B.»
   - «Envía a B con `send_message_to_thread`: "hola desde A".»
   - **Observa:**
     - el texto exacto del aviso de aprobación (haz captura);
     - si B empieza a responder sin que lo toques;
     - qué ve B: ¿el mensaje?, ¿`<codex_delegation>` con el id de A?;
     - qué recibe A de vuelta.
   - **Si falla:** copia el error. Fallos conocidos: «No handler registered» y «thread not found». Reinicia la app una vez y repite.
4. **Identidad y superficie.** En A, pide que ejecute `echo $CODEX_THREAD_ID; echo $__CFBundleIdentifier`.
   - **Observa:**
     - que lo primero es el id de A (el de `list_threads`, o el que sale en «copiar enlace», `codex://threads/<id>`);
     - qué sale en lo segundo (orquesta usa `com.openai.codex` o `com.openai.chat` para saber que es la app).
   - **Si falla:** si el id sale vacío, orquesta no puede reconocer a los agentes de la app. Para aquí y avisa.
5. **`orq` sin sandbox.** En A, pide que ejecute `orq --version`, y después `orq runs`.
   - **Observa:** si pide permiso. Con la regla de orquesta no debería, y debería responder con la versión del zip (`orq 0.9.…`).
   - **Si falla:** apunta el aviso o el error. Si dice que no encuentra `orq`, repite con la ruta completa, `~/.orquesta/bin/orq --version`.

## C. La puerta, con la sonda

La sonda hace que la puerta apunte en `~/.orquesta/sonda.log` todo lo que Codex le pasa, sin decidir nada.

6. En una terminal: `orq doctor --sonda on`. Repite el envío de A a B del paso 3, y pide a A que ejecute `ls`.
   - **Observa** en `~/.orquesta/sonda.log`:
     - líneas `PreToolUse` del envío, con el `tool_name` exacto (se espera `mcp__codex_app__send_message_to_thread`);
     - que `session_id` es el id de A;
     - si aparece una línea `PermissionRequest` cuando sale el aviso;
     - la línea `PostToolUse` cuando se ha enviado.

     El `ls` no debería aparecer, porque la puerta solo mira los envíos.
   - **Si falla:** si no hay ninguna línea, los hooks no corren en la app o no están confirmados (paso 2). Apunta qué eventos faltan.
7. `orq doctor --sonda permitir` y repite el envío.
   - **Observa:** ¿sigue saliendo el aviso de aprobación?
     - Si **no sale**, los mensajes *libres* funcionan sin clics.
     - Si **sale**, en la app todo mensaje pide aprobación. Apúntalo: hay que decidir si vale así o si hace falta otro camino.
   - Al acabar: `orq doctor --sonda off`.
8. **`codex queue`** (solo si tienes la CLI). Con B parado y a la vista, en una terminal: `codex queue --thread <id-de-B> --message "ping desde la terminal"`.
   - **Observa:** si B lo muestra, cuánto tarda y si empieza a responder solo. Repite con B ocupado.
   - **Si falla:** copia la salida. Sin esto, `orq send` (el camino de reserva) no sirve en la app.

## D. Instrucciones globales

9. En un chat nuevo, C, pregunta: «¿Qué dicen tus instrucciones sobre la orquesta?».
   - **Observa:** que cita el bloque (habla de `orq whoami`). Después usa `/compact` (o dale una tarea larga) y vuelve a preguntar.
   - **Si falla:** apúntalo. La alternativa sería poner el bloque en el `AGENTS.md` del proyecto.

## E. Una orquesta pequeña

10. **Crear.** En el chat A, pide: «Ejecuta `orq init prueba --coordinator a --goal "probar orquesta"`».
    - **Observa:**
      - que no pide permiso;
      - el color que anuncia;
      - que `orq status prueba` sale con «· Codex (app)» y con `a [director]`.
    - **Si falla:** copia la salida.
11. **Lanzar.** Escribe un encargo corto en `~/prueba-orquesta/.orquesta/prueba/agents/w1/brief.md`, por ejemplo «Escribe en `result.md` tres ideas para un nombre de producto y avisa a tu coordinador». Pide a A: «Lanza w1 con `orq launch prueba w1 --parent a --topic "ideas" --effort low`».
    - **Observa:**
      - que la app abre un chat nuevo **en el proyecto de prueba**, con el primer mensaje ya escrito (empieza por el emoji y «w1 · prueba»);
      - elige modelo y esfuerzo, y pulsa Enter;
      - que el worker ejecuta `orq join …` sin pedir permiso y recibe su identidad y el protocolo;
      - qué título le pone la app al chat: ¿lleva el emoji?;
      - que `orq status prueba` enseña w1 sin «sin unirse».
    - **Si falla:** apunta si el enlace abrió el proyecto correcto, si el mensaje estaba escrito y si `orq join` pidió aprobación o falló. Copia lo que diga.
12. **Mensajes.** Lanza w2 igual. Deja la matriz por defecto: coordinador↔worker libre y el resto manual.
    - Pide a w1 que avise a A (libre) y que escriba a w2 (manual), usando `orq to` y `send_message_to_thread`.
    - **Observa:**
      - si el libre pasa sin aviso (según el paso 7);
      - que el manual saca el aviso **en el chat de w1** (apruébalo);
      - que `~/prueba-orquesta/.orquesta/prueba/messages.log` tiene `attempt` y `sent` de los dos, y que un mensaje que rechaces deja `attempt` sin `sent`.
    - Pide también a w1 que escriba al chat B (fuera de la orquesta). Debería bloquearse con «ese chat no es de la orquesta».
13. **Lo que no se puede hacer.** Pide a w1 que ponga su estado en `done` (`orq state`) y después que edite `board.json` a mano.
    - **Observa:** `orq state` funciona. La edición a mano no está bloqueada técnicamente (se espera), pero el protocolo le dice que no lo haga: apunta si se niega.
14. **Ocupado.** Da a w2 una tarea larga («cuenta despacio hasta 200 explicando cada número») y, mientras, haz que w1 le escriba.
    - **Observa:** si el mensaje espera a que w2 termine, se rechaza o le interrumpe.
15. **Reabrir.** Cierra la app del todo, vuelve a abrirla y, desde una terminal, `orq resume prueba w1` (o `orq open prueba w1`).
    - **Observa:**
      - que se abre el chat de w1 con su historial;
      - que w1 sigue sabiendo quién es (pídele `orq whoami`);
      - que `orq status prueba` enseña su «última señal».
16. **Otro proyecto** (informativo). Crea un segundo proyecto con un chat D. Desde A, envía a D con `send_message_to_thread`.
    - **Observa:** si llega o se rechaza.

## F. Barra lateral

17. Mira si la app deja agrupar chats en secciones o carpetas de la barra lateral, y si esas secciones pueden tener color o icono.
    - **Observa:** si existe, crea una para «prueba» y apunta si se ve el color o el icono. Es informativo: orquesta todavía no la usa.

## G. Cerrar y desinstalar

18. `orq close prueba`, y después `./install.sh --deshacer` desde la carpeta del zip.
    - **Observa:**
      - que `~/.orquesta`, `~/.agents/skills/orquesta-*` y `~/.codex/rules/orquesta.rules` han desaparecido;
      - que `orq` ya no responde en una terminal nueva;
      - que `diff ~/codex-antes/AGENTS.md ~/.codex/AGENTS.md` y lo mismo con `hooks.json` no dan diferencias, si no los tocaste entre medias.
    - `~/.codex/config.toml` puede tener ahora entradas `hooks.state` con la confirmación de los hooks, que escribe Codex, no orquesta. Son inofensivas.
    - **Si falla:** copia la salida de `--deshacer`.

## Qué traer de vuelta

- La lista con ✓ o ✗ en cada paso.
- Las versiones del paso 0.
- `~/.orquesta/sonda.log`. Cópialo **antes** de desinstalar, porque `--deshacer` borra `~/.orquesta`.
- `~/prueba-orquesta/.orquesta/prueba/messages.log`.
- Las capturas de cada aviso de aprobación y de la barra lateral con los títulos de los chats.
