#!/usr/bin/env bash
set -euo pipefail
: "${ARENA_ROOT:?Set existing ARENA_ROOT}"
[[ $(git -C "$ARENA_ROOT" rev-parse HEAD) = 98866596fd024d96c874fe6fb95ae916d1133629 ]] || { echo 'Arena revision mismatch' >&2; exit 1; }
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export OMNI_KIT_ACCEPT_EULA=YES ACCEPT_EULA=Y PYTHONDONTWRITEBYTECODE=1
exec "$ARENA_ROOT/.venv/bin/python" -u "$here/capture.py" --viz none --device cpu "$@"
