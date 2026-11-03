# Color por orquesta en Codex (diseño, paso 5)

En Claude Code cada orquesta abierta tiene un color de `/color` (ver `orq/colors.py`): `orq launch` crea la
sesión con `claude -p … "/color <c>"` y la ventana la reanuda con la barra de ese color.

Codex no tiene color por hilo (investigado en `openai/codex` rust-v0.166.0). El adaptador de Codex hará esto:

- **Emoji al principio del nombre del hilo**, con el mapa `colors.EMOJI`: «🟣 builder · orquesta-export».
  Se pone con `thread/name/set` (lanzamiento por el daemon) o con `set_thread_title` / `/rename` (el worker
  lo hace al registrarse con `orq join`). Se ve en la CLI y en la barra lateral de la app.
- **Extra en la app, por probar:** una sección de la barra lateral por orquesta, con `color`/`icon`
  (API `thread/section/*`, PR #37898). No se sabe si la app la pinta: va a la lista de pruebas.

Mapa: 🔴 red, 🔵 blue, 🟢 green, 🟡 yellow, 🟣 purple, 🟠 orange.

La paleta no usa pink ni cyan, aunque `/color` los tiene: sus únicos emojis son corazones (🩷 🩵), y se
decidió (2026-11-02) quedarse con los seis colores que tienen círculo.
