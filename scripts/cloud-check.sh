#!/usr/bin/env bash
set -euo pipefail
workspace_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$workspace_root"
python3 scripts/check-version-management.py "$@"
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts/tests -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s workspace-overlays/shared_config/tests -v
if [[ ! -d private-blog/node_modules/cheerio ]]; then
  echo 'Blog dependencies missing; run: npm --prefix private-blog ci' >&2
  exit 1
fi
npm --prefix private-blog run build
npm --prefix private-blog run check
