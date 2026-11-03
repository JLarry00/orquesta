#!/bin/sh
# Desinstala la orquesta: deja todo como estaba antes de la primera instalación.
here=$(cd "$(dirname "$0")" && pwd)
exec sh "$here/install.sh" --deshacer "$@"
