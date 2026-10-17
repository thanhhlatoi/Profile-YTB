"""Unix socket so CLI and MCP (Hermes over SSH) run commands inside the running app.

The app owns the desktop session, so Chrome opens on the user's screen, and it is the
single executor: no double publish, and progress/stop work for every job.
Access control is the filesystem: the socket is 0600 in the app's 0700 data folder.
"""

import hashlib
import json
import logging
import os
import socket
import socketserver
import threading
from pathlib import Path

logger = logging.getLogger(__name__)
SOCKET_NAME = "control.sock"


def socket_path(paths) -> Path:
    """Per-user runtime dir (short, private, also set for SSH logins), else the data dir.

    Unix socket paths are limited to ~108 bytes, so a deep data folder is a last resort.
    """
    runtime = Path(f"/run/user/{os.getuid()}")
    if not runtime.is_dir():
        return paths.root / SOCKET_NAME
    # Tied to the data folder: another data folder (tests, a second setup) gets its own app.
    tag = hashlib.sha1(str(Path(paths.root).resolve()).encode()).hexdigest()[:8]
    return runtime / f"profile-ytb-{tag}.sock"


class ControlError(RuntimeError):
    pass


class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            request = json.loads(self.rfile.readline().decode("utf-8"))
            result = self.server.controller.handle(
                request["command"], request.get("args"), bool(request.get("agent"))
            )
            reply = {"ok": True, "result": result}
        except Exception as error:
            logger.warning("Lệnh điều khiển lỗi: %s", error)
            reply = {"ok": False, "error": str(error)}
        self.wfile.write(json.dumps(reply, ensure_ascii=False, default=str).encode() + b"\n")


class ControlServer:
    def __init__(self, path: Path, controller):
        self.path = Path(path)
        self.path.unlink(missing_ok=True)  # Stale socket from a crash.
        self.server = socketserver.ThreadingUnixStreamServer(str(self.path), _Handler)
        self.server.daemon_threads = True
        self.server.controller = controller
        os.chmod(self.path, 0o600)

    def start(self) -> None:
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.path.unlink(missing_ok=True)


def available(path: Path) -> bool:
    try:
        with socket.socket(socket.AF_UNIX) as probe:
            probe.connect(str(path))
        return True
    except OSError:
        return False


def call(path: Path, command: str, args: dict | None = None, agent: bool = False,
         timeout: float = 600):
    try:
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(timeout)
            client.connect(str(path))
            message = {"command": command, "args": args or {}, "agent": agent}
            client.sendall(json.dumps(message).encode() + b"\n")
            reply = client.makefile("rb").readline()
    except OSError as error:
        raise ControlError(
            "Không kết nối được ứng dụng Profile YTB. Hãy mở ứng dụng trên máy Ubuntu."
        ) from error
    if not reply:
        raise ControlError("Ứng dụng Profile YTB không trả lời")
    reply = json.loads(reply)
    if not reply["ok"]:
        raise ControlError(reply["error"])
    return reply["result"]
