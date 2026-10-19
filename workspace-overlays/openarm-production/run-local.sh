#!/usr/bin/env bash
set -euo pipefail
overlay_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python_bin=${OPENARM_PYTHON:-/home/tangyuan/miniconda3/envs/autodata/bin/python}
cuda_package_dir=$("$python_bin" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"] + "/nvidia/cu13")')
if [[ -d "$cuda_package_dir/lib" ]]; then
    export LD_LIBRARY_PATH="$cuda_package_dir/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
if [[ -z ${CUDA_HOME:-} && -x "$cuda_package_dir/bin/nvcc" ]]; then
    export CUDA_HOME="$cuda_package_dir"
fi
export PATH="$(dirname -- "$python_bin")${CUDA_HOME:+:$CUDA_HOME/bin}:$PATH"
# Prior local EULA acceptance is documented in the preserved OpenArm workflow.
export OMNI_KIT_ACCEPT_EULA=YES
if [[ ${1:-} == --check-runtime ]]; then
    shift
    exec "$python_bin" -u "$overlay_dir/check_runtime.py" "$@"
fi
exec "$python_bin" "$overlay_dir/run_local.py" "$@"
