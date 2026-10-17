#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -x ".venv/bin/python" ]]; then
    printf 'Chưa có virtualenv. Chạy trước: ./scripts/install_ubuntu.sh\n' >&2
    exit 1
fi

source .venv/bin/activate
python -m pip install -r requirements.txt
python -m PyInstaller \
    --noconfirm \
    --clean \
    --name chrome-profile-manager \
    --windowed \
    --collect-all PySide6 \
    --add-data app/studio_js:app/studio_js \
    app/main.py

printf '\nBuild xong: %s\n' "$ROOT_DIR/dist/chrome-profile-manager/chrome-profile-manager"
