<!-- Fragmento de Claude Code: cada bloque empieza con su clave entre comentarios y llega hasta la siguiente. -->
<!-- enviar -->
`SendMessage`
<!-- listar -->
`ListAgents`
<!-- como_enviar -->
Usa `SendMessage` con el nombre de sesión del destinatario. Con `ListAgents` ves quién existe.
<!-- reglas_globales -->
Tus instrucciones globales (CLAUDE.md, memorias y lo que te haya pedido {{usuario}})
<!-- subagente_interno -->
Para tareas cortas y sin conversación, usa un subagente interno (herramienta Agent) en lugar de una ventana.
<!-- nombre_sesion -->
tu nombre de sesión, el que sale en `ListAgents` («This session is …»)
<!-- renombrar -->
`/rename <nombre>`
<!-- color_director -->
Para que tu ventana también lo lleve, pide a {{usuario}} que escriba en ella el comando que imprime `orq init` (`/color <color>`): los comandos con barra no los puedes ejecutar tú.
<!-- subagente_corto -->
Subagente interno (herramienta Agent)
<!-- tabla_modelos -->
| Dificultad | Ejemplo | `--model` / `--effort` |
|---|---|---|
| Trivial | buscar, listar, resumir un archivo | `haiku` / `low` |
| Sencilla | cambio acotado, script corto | `sonnet` / `medium` |
| **Estándar (por defecto)** | lo normal | `opus` / `medium` |
| Media-alta y alta | depurar, diseñar un módulo, arquitectura, fallo escurridizo, decisión cara de revertir | `opus` / `high` |

Explica la elección en `--why`. `xhigh` y `max` no se usan nunca; el tope es `high`.
<!-- donde_trabajas -->
Trabajas en tu propia ventana
<!-- protocolo_durable -->
Este protocolo va en tu system prompt: lo tienes siempre presente, también después de compactar la conversación.
<!-- donde_apruebas -->
tu ventana
<!-- su_sesion -->
su ventana de Terminal
<!-- nueva_sesion -->
una ventana de Terminal
<!-- worker_o_subagente -->
¿Worker en ventana o subagente interno?
<!-- al_lanzar -->
Se abre una ventana de Terminal con la sesión llamada `<nombre>`, del color de la orquesta, en el workspace. El protocolo le llega en el system prompt, así que no lo pierde al compactar.
<!-- donde_aprueba_remitente -->
la ventana de quien lo envía
<!-- cerrar_worker -->
Un worker terminado puede cerrarse para liberar memoria: {{usuario}} cierra la ventana, o tú usas `orq state <run> <n> stopped` después de que la cierre. No cierres ventanas por tu cuenta.
<!-- reabrir -->
abre una ventana nueva con la misma sesión
<!-- nombre_cambia -->
El nombre sí puede cambiar al reiniciar. `orq` lo detecta por el id y actualiza el board solo; la puerta también reconoce al director por su id. Si {{usuario}} quiere un nombre estable, que haga {{renombrar}}.
<!-- carpeta_extra -->
Si un worker necesita una carpeta de fuera (por ejemplo un worktree), dásela con `--dir` al lanzarlo.
