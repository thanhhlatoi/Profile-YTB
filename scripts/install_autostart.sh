#!/usr/bin/env bash
# Tự chạy app (ẩn xuống khay) khi đăng nhập Ubuntu. Gỡ: ./scripts/install_autostart.sh --remove
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="$HOME/.config/autostart/chrome-profile-manager.desktop"

if [[ "${1:-}" == "--remove" ]]; then
  rm -f "$TARGET"
  printf 'Đã tắt tự khởi động.\n'
  exit 0
fi

BUILD="$HOME/.local/share/chrome-profile-manager/dist/chrome-profile-manager"
if [[ -x "$BUILD" ]]; then
  EXEC="\"$BUILD\" --minimized"
else
  EXEC="\"$ROOT_DIR/scripts/run.sh\" --minimized"
fi

mkdir -p "$(dirname "$TARGET")"
cat > "$TARGET" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Chrome Profile Manager
Comment=Chạy lịch tác vụ Chrome profile
Exec=$EXEC
Icon=google-chrome
Terminal=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=15
DESKTOP
printf 'Đã bật tự khởi động: %s\n' "$TARGET"
