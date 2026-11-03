#!/bin/sh
# orquesta-shim: capa de compatibilidad con la versión anterior. El comando de verdad es este:
exec "{{orq_bin}}" "$@"
