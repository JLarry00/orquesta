<!-- Fragmento de Codex (superficie app): cada bloque empieza con su clave entre comentarios y llega hasta la siguiente. -->
<!-- enviar -->
`send_message_to_thread`
<!-- listar -->
`orq status <run>`
<!-- como_enviar -->
Para escribir a otro agente: `orq to <nombre>` te da el id de su chat y si la pareja es libre o manual. Después llama a la herramienta `send_message_to_thread` con ese `threadId` y tu mensaje, que empiece por «[de <tu-nombre>]» y no pase de unas pocas líneas (la herramienta corta en 1000 bytes). Si la herramienta no existe en tu chat, usa `orq send <nombre> "<texto>"`, que solo sirve para parejas libres. No uses nunca `codex queue` directamente. Ejecuta los comandos `orq` solos, sin `cd` ni `&&` delante: así no te piden permiso.
<!-- reglas_globales -->
Tus instrucciones globales (AGENTS.md y lo que te haya pedido {{usuario}})
<!-- subagente_interno -->
Para tareas cortas y sin conversación, usa un subagente de Codex en lugar de un chat nuevo.
<!-- nombre_sesion -->
el nombre que elijas para ti como director (corto, en kebab-case); `orq` te reconoce por el id de este chat, no por el título
<!-- renombrar -->
renombrar el chat en la app
<!-- nombre_cambia -->
En Codex, `orq` te reconoce por el id de este chat (`CODEX_THREAD_ID`): puedes cambiar el título del chat sin que pase nada.
<!-- color_director -->
En Codex no hay color de barra: los títulos de los chats de tus workers empiezan por el emoji del color. Si quieres, pon ese emoji al principio del título de tu chat.
<!-- subagente_corto -->
Subagente de Codex
<!-- tabla_modelos -->
El modelo y el esfuerzo se eligen en la app al enviar el primer mensaje del worker; `orq launch` los apunta en el board y se los recuerda a {{usuario}}. Pasa en `--effort` el que recomiendas, y en `--model` un modelo solo si importa (sin él, el de por defecto de la app).

| Dificultad | Ejemplo | `--effort` |
|---|---|---|
| Trivial | buscar, listar, resumir un archivo | `low` |
| Sencilla y estándar (por defecto) | cambio acotado, lo normal | `medium` |
| Media-alta y alta | depurar, diseñar un módulo, arquitectura, fallo escurridizo, decisión cara de revertir | `high` |

Explica la elección en `--why`. Por encima de `high` no se usa nada; el tope es `high`.
<!-- donde_trabajas -->
Trabajas en tu propio chat de la app de Codex
<!-- protocolo_durable -->
Este protocolo te lo da `orq whoami` (y `orq join` la primera vez). Si al compactar la conversación lo pierdes de vista, vuelve a ejecutar `orq whoami`: tus instrucciones globales (AGENTS.md) te lo recuerdan.
<!-- donde_apruebas -->
tu chat
<!-- su_sesion -->
su propio chat de Codex
<!-- nueva_sesion -->
un chat nuevo de la app de Codex
<!-- worker_o_subagente -->
¿Worker en su propio chat o subagente de Codex?
<!-- al_lanzar -->
Se abre un chat nuevo en la app de Codex, en el proyecto del workspace, con el primer mensaje ya escrito. {{usuario}} elige el modelo y el esfuerzo en la app y lo envía. El worker se registra solo con `orq join` y recibe su identidad y el protocolo; si compacta, los recupera con `orq whoami`. Comprueba con `orq status <run>` que ya no sale «sin unirse».
<!-- donde_aprueba_remitente -->
el chat de quien lo envía
<!-- cerrar_worker -->
Un worker terminado puede archivarse para despejar la barra lateral: {{usuario}} archiva su chat en la app, y tú usas `orq state <run> <n> stopped`. No archives chats por tu cuenta.
<!-- reabrir -->
abre su chat en la app de Codex
<!-- carpeta_extra -->
En Codex cada chat trabaja en la carpeta de su proyecto: `--dir` no está disponible.
