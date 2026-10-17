#!/usr/bin/env bash
# Gọi CLI từ cron/script: ./scripts/cpm.sh open --group "Team A"
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
PYTHON="$ROOT_DIR/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON=python3
exec "$PYTHON" -m app.cli "$@"
