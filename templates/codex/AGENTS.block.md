<!-- orquesta:start (lo pone ./install.sh de orquesta; ./install.sh --deshacer lo quita) -->
## Orquesta

Si esta conversación es de un agente de una orquesta (lo dice tu primer mensaje, o el resumen de la conversación habla de una orquesta, de `orq join` o de `orq whoami`), ejecuta `orq whoami` antes de usar `orq` o de escribir a otro agente, y sigue lo que diga: te da tu identidad, el protocolo y tu encargo. Si `orq` no está en el PATH, usa `{{orq_bin}}`. Ejecuta los comandos `orq` solos, sin `cd` ni `&&` delante.

Para coordinar workers (lanzar, repartir trabajo, hacer de director), usa la skill `orquesta-launch`.
<!-- orquesta:end -->
