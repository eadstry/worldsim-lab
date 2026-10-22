#!/usr/bin/env bash
set -euo pipefail
workspace_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$workspace_root"
python3 scripts/check-version-management.py "$@"
python3 scripts/build-outputs-index.py --check
python3 scripts/check-doc-links.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts/tests -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s workspace-overlays/shared_config/tests -v
