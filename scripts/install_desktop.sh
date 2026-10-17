#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${HOME}/.local/share/chrome-profile-manager"
DESKTOP_DIR="${HOME}/.local/share/applications"

if [[ ! -x "$ROOT_DIR/dist/chrome-profile-manager/chrome-profile-manager" ]]; then
    printf 'Chưa có bản build. Chạy ./scripts/build_ubuntu.sh trước.\n' >&2
    exit 1
fi

mkdir -p "$APP_DIR" "$DESKTOP_DIR"
rm -rf "$APP_DIR/dist"
cp -a "$ROOT_DIR/dist/chrome-profile-manager" "$APP_DIR/dist"
cat > "$DESKTOP_DIR/chrome-profile-manager.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Chrome Profile Manager
Comment=Quản lý Chrome profiles
Exec=$APP_DIR/dist/chrome-profile-manager/chrome-profile-manager
Icon=google-chrome
Terminal=false
Categories=Utility;WebBrowser;
StartupNotify=true
EOF
chmod +x "$DESKTOP_DIR/chrome-profile-manager.desktop"
printf 'Đã cài launcher: %s\n' "$DESKTOP_DIR/chrome-profile-manager.desktop"
