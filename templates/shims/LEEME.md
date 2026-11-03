# Capa de compatibilidad (calzos)

Esta carpeta era la instalación de la versión anterior de la orquesta. Ahora la orquesta está instalada en
`{{orq_home}}`, y esta carpeta solo existe para que los agentes lanzados antes de migrar sigan funcionando,
porque sus `settings.json` y sus lanzadores llevan estas rutas escritas:

- `bin/orq` reenvía a `{{orq_bin}}`.
- `hooks/orquesta-gate.py` reenvía a la puerta instalada (admite `--run` y `--run-dir`).
- `runs.json` y `config.json` son enlaces a los de `{{orq_home}}`.
- `PROTOCOL.md` es una copia del protocolo actual (`orq render` la mantiene al día).

No edites nada aquí. Para volver a la versión anterior: `./install.sh --deshacer` desde el repo de la orquesta.
Cuando ya no quede ningún agente de antes de la migración, se puede borrar esta carpeta.
