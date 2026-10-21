#!/usr/bin/env bash
set -euo pipefail
experiment_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
experiment_python=${OPENARM_PYTHON:-/home/tangyuan/miniconda3/envs/autodata/bin/python}
experiment_cuda=$("$experiment_python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"] + "/nvidia/cu13")')
if [[ -d "$experiment_cuda/lib" ]]; then
    export LD_LIBRARY_PATH="$experiment_cuda/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
export PATH="$(dirname -- "$experiment_python"):$PATH"
export OMNI_KIT_ACCEPT_EULA=YES
export PYTHONDONTWRITEBYTECODE=1
exec "$experiment_python" -u "$experiment_dir/experiment.py" "$@"
