#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Linux: .venv/bin/python. Windows (Git Bash): .venv/Scripts/python.exe
for venv_python in "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/.venv/Scripts/python.exe"; do
  if [[ -x "$venv_python" ]]; then
    exec "$venv_python" -m app.main "$@"
  fi
done

exec python3 -m app.main "$@"
