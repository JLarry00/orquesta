#!/bin/sh
# Instalador de la orquesta: comprueba python3 >= 3.9 y ejecuta installer.py. Ver ./install.sh -h
set -e
here=$(cd "$(dirname "$0")" && pwd)
if ! command -v python3 >/dev/null 2>&1; then
  echo "install.sh: hace falta python3 3.9 o posterior (en macOS: xcode-select --install)" >&2
  exit 1
fi
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))'; then
  echo "install.sh: hace falta python3 3.9 o posterior; tienes $(python3 --version 2>&1)" >&2
  exit 1
fi
exec python3 -I "$here/installer.py" "$@"
