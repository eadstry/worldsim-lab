#!/usr/bin/env bash
set -euo pipefail
overlay_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
container_name=${OPENARM_CONTAINER:-autodata-sim-6.0.1-curobo}
if [[ ! -d "$overlay_dir/runtime" ]]; then
    echo 'Run prepare.py with the OpenArm ZIP first.' >&2
    exit 1
fi
if [[ $(docker inspect -f '{{.State.Running}}' "$container_name") != true ]]; then
    echo 'Start AutoData/docker/run_docker.sh -c first.' >&2
    exit 1
fi
# Use a fresh directory so a second invocation cannot change a running production process.
container_dir=$(docker exec "$container_name" mktemp -d /tmp/openarm-production.XXXXXXXX)
docker cp "$overlay_dir/." "$container_name:$container_dir/"
docker exec "$container_name" /isaac-sim/python.sh "$container_dir/run_local.py" "$@"
