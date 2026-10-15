#!/usr/bin/env bash
set -euo pipefail
workspace_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$workspace_root"
# Fetch source only; large simulation assets remain on the GPU server.
python3 scripts/check-version-management.py --allow-uninitialized --require-clean-upstream
GIT_LFS_SKIP_SMUDGE=1 git submodule update --init --jobs 3 AutoData IsaacLab-Arena RLinf
npm --prefix private-blog ci
python3 scripts/review-workspace.py install
bash scripts/cloud-check.sh
