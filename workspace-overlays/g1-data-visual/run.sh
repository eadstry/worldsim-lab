#!/usr/bin/env bash
set -euo pipefail
: "${ARENA_ROOT:?Set ARENA_ROOT}"
[[ $(git -C "$ARENA_ROOT" rev-parse HEAD) = 98866596fd024d96c874fe6fb95ae916d1133629 ]] || { echo "Arena revision mismatch" >&2; exit 1; }
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export PYTHONPATH="$here:$ARENA_ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec "$ARENA_ROOT/.venv/bin/python" -u "$here/launch.py" \
 --viz none --device cpu --enable_cameras --mimic --num_envs 1 --generation_num_trials 1 \
 --external_callback g1_capture.register --task galileo_g1_locomanip_pick_and_place \
 --object brown_box --embodiment g1_wbc_pink "$@"
