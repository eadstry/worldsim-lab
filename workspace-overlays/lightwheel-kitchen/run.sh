#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
mode=${1:-smoke}
case "$mode" in smoke|pi05) ;; *) echo 'Usage: run.sh [smoke|pi05] [runner options / overrides]' >&2; exit 2;; esac
if (($#)); then shift; fi
: "${ARENA_ROOT:?Set ARENA_ROOT to the existing IsaacLab-Arena checkout}"
ARENA_ROOT=$(cd -- "$ARENA_ROOT" && pwd)
runtime_python=${ARENA_PYTHON:-$ARENA_ROOT/.venv/bin/python}
[[ -x "$runtime_python" ]] || { echo "Runtime missing: $runtime_python" >&2; exit 1; }
[[ "$runtime_python" = /* ]] || { echo 'ARENA_PYTHON must be absolute' >&2; exit 1; }
expected=98866596fd024d96c874fe6fb95ae916d1133629
[[ $(git -C "$ARENA_ROOT" rev-parse HEAD) = "$expected" ]] || { echo 'Arena revision differs from reviewed source.json' >&2; exit 1; }
cd -- "$ARENA_ROOT"
exec "$runtime_python" isaaclab_arena/evaluation/experiment_runner.py \
  --experiment_config "$here/$mode.yaml" --viz none \
  --output_base_dir "$here/../../runs/lightwheel-kitchen/$mode" \
  "$@" "shared.environment.type=$here/scene.yaml"
