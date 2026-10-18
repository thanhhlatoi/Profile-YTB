#!/usr/bin/env bash
# Cho Hermes Agent (VPS hoặc máy khác trong mạng nhà) điều khiển Profile YTB qua SSH.
# Dùng: ./scripts/setup_hermes_access.sh /đường/dẫn/hermes_ubuntu.pub
# Khóa này CHỈ chạy được MCP server của Profile YTB: không mở được shell, không forward cổng.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEY_FILE="${1:-}"

if [[ -z "$KEY_FILE" || ! -f "$KEY_FILE" ]]; then
  printf 'Dùng: %s <file khóa công khai .pub của máy chạy Hermes>\n' "$0" >&2
  exit 2
fi
KEY="$(head -n1 "$KEY_FILE")"
if [[ ! "$KEY" =~ ^(ssh-ed25519|ssh-rsa|ecdsa-sha2-) ]]; then
  printf 'File %s không phải khóa công khai SSH.\n' "$KEY_FILE" >&2
  exit 2
fi
if [[ ! -x /usr/sbin/sshd ]]; then
  printf 'Chưa cài SSH server. Chạy:\n  sudo apt install openssh-server\nrồi chạy lại script này.\n' >&2
  exit 1
fi
if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then
  printf 'Chưa có .venv. Chạy ./scripts/install_ubuntu.sh trước.\n' >&2
  exit 1
fi

WRAPPER="$HOME/.local/bin/profile-ytb-mcp"
mkdir -p "$(dirname "$WRAPPER")"
cat > "$WRAPPER" <<WRAP
#!/usr/bin/env bash
cd "$ROOT_DIR" && exec "$ROOT_DIR/.venv/bin/python" -m app.mcp_server
WRAP
chmod 755 "$WRAPPER"

mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
touch "$HOME/.ssh/authorized_keys"
chmod 600 "$HOME/.ssh/authorized_keys"
KEY_BODY="$(awk '{print $2}' <<<"$KEY")"
if grep -qF "$KEY_BODY" "$HOME/.ssh/authorized_keys"; then
  printf 'Khóa này đã có trong authorized_keys, giữ nguyên.\n'
else
  printf 'command="%s",restrict %s\n' "$WRAPPER" "$KEY" >> "$HOME/.ssh/authorized_keys"
  printf 'Đã thêm khóa (chỉ được chạy MCP).\n'
fi

# Hermes trên VPS đi qua Tailscale hoặc NetBird; không có thì dùng IP mạng LAN.
NETWORK="Tailscale"
IP="$(tailscale ip -4 2>/dev/null | head -n1 || true)"
if [[ -z "$IP" ]]; then
  NETWORK="NetBird"
  # "NetBird IP: 100.92.1.2/16"
  IP="$(netbird status 2>/dev/null | sed -n 's/^ *NetBird IP: *\([0-9.]*\).*/\1/p' | head -n1 || true)"
fi
if [[ -z "$IP" ]]; then
  NETWORK="mạng LAN"
  IP="$(hostname -I | awk '{print $1}')"
fi
cat <<INFO

Xong. Dán đoạn sau vào ~/.hermes/config.yaml trên máy chạy Hermes
(đổi đường dẫn khóa riêng nếu bạn đặt tên khác):

mcp_servers:
  profile_ytb:
    command: "ssh"
    args: ["-T", "-i", "~/.ssh/hermes_ubuntu", "-o", "BatchMode=yes",
           "-o", "ServerAliveInterval=30", "$USER@$IP"]
    timeout: 300
    connect_timeout: 60

Lưu ý:
- IP trên lấy từ $NETWORK ($IP). Hermes chạy trên VPS thì cần Tailscale hoặc NetBird trên cả 2 máy;
  dùng mạng LAN thì đặt IP cố định cho máy này trong router (DHCP reservation).
- App Profile YTB phải đang chạy (dưới khay) thì Hermes mới thao tác được.
INFO
