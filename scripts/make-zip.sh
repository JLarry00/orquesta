#!/bin/sh
# Crea dist/orquesta-<versión>.zip con lo que hay commiteado en <ref> (por defecto HEAD).
#   scripts/make-zip.sh [ref]
set -e
cd "$(dirname "$0")/.."
ref=${1:-HEAD}
ver=$(git show "$ref:orq/__init__.py" | sed -n 's/^__version__ = "\(.*\)"/\1/p')
[ -n "$ver" ] || { echo "make-zip: no encuentro __version__ en $ref" >&2; exit 1; }
if [ "$ref" = HEAD ] && [ -n "$(git status --porcelain)" ]; then
  echo "make-zip: aviso: hay cambios sin commitear; el zip solo lleva lo commiteado" >&2
fi
mkdir -p dist
out="dist/orquesta-$ver.zip"
git archive --format=zip --prefix="orquesta-$ver/" -o "$out" "$ref"
echo "$out ($(git rev-parse --short "$ref"))"
