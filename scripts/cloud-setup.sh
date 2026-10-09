#!/usr/bin/env bash
set -euo pipefail
workspace_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$workspace_root"
# Fetch source only; large simulation assets remain on the GPU server.
GIT_LFS_SKIP_SMUDGE=1 git submodule update --init --jobs 3 AutoData IsaacLab-Arena RLinf
mkdir -p AutoData/agentic_design
cp workspace-overlays/AutoData/agentic_design/*.md AutoData/agentic_design/
npm --prefix private-blog ci
npm --prefix private-blog run check
