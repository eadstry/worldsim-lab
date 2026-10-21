#!/usr/bin/env bash
set -euo pipefail
task_script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
task_python=${OPENARM_PYTHON:-/home/tangyuan/miniconda3/envs/autodata/bin/python}
task_cuda=$("$task_python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"] + "/nvidia/cu13")')
if [[ -d "$task_cuda/lib" ]]; then
    export LD_LIBRARY_PATH="$task_cuda/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
export PATH="$(dirname -- "$task_python"):$PATH"
export OMNI_KIT_ACCEPT_EULA=YES
export PYTHONDONTWRITEBYTECODE=1
"$task_python" -u "$task_script_dir/diagnostic.py" "$@"
"$task_python" - "$@" <<'PY'
import argparse, json
from pathlib import Path
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument('--output', type=Path, required=True)
args, _ = parser.parse_known_args()
assert not (args.output/'error.txt').exists(), (args.output/'error.txt').read_text()
assert (args.output/'complete.json').is_file(), 'Missing experiment completion receipt'
assert json.loads((args.output/'complete.json').read_text())['trials'] > 0
assert (args.output/'diagnostic-integration.json').is_file()
PY
