#!/usr/bin/env bash
set -euo pipefail
probe_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python_bin=${OPENARM_PYTHON:-/home/tangyuan/miniconda3/envs/autodata/bin/python}
cuda_package_dir=$("$python_bin" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"] + "/nvidia/cu13")')
export LD_LIBRARY_PATH="$cuda_package_dir/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export OMNI_KIT_ACCEPT_EULA=YES
export PYTHONDONTWRITEBYTECODE=1
exec "$python_bin" -u "$probe_dir/run.py" "$@"
