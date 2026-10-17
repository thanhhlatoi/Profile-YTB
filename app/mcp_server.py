"""MCP server (stdio) for Hermes Agent. Hermes starts it over SSH from another machine.

Every tool forwards to the running Profile YTB app through its control socket with
agent=True, so the agent limits in settings.json apply and Chrome opens on the desktop.
No delete operations are exposed on purpose.
"""

from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from app.config import AppPaths
from app.services import control_server

SOCKET = control_server.socket_path(AppPaths.create())

server = MCPServer(
    name="profile-ytb",
    instructions=(
        "Điều khiển Chrome Profile Manager (Profile YTB) trên máy Ubuntu để public video nháp "
        "YouTube. Quy trình chuẩn: list_profiles -> check_channel -> publish -> task_status "
        "(lặp lại mỗi 30-60 giây tới khi finished=true) -> báo kết quả. Publish chạy nền và "
        "trả về task_id ngay. Không đoán tên profile: lấy từ list_profiles."
    ),
)


def _call(command: str, **args):
    try:
        return control_server.call(SOCKET, command, args, agent=True)
    except control_server.ControlError as error:
        # ToolError keeps the message visible to the agent (other errors are masked).
        raise ToolError(str(error)) from error


@server.tool()
def list_profiles(group: str | None = None) -> list[dict]:
    """Liệt kê profile Chrome (tên, nhóm, trạng thái đang chạy). Lọc theo nhóm nếu có."""
    return _call("list_profiles", group=group)


@server.tool()
def check_channel(profile: str) -> dict:
    """Kiểm tra kênh trước khi đăng, KHÔNG public: số video nháp, số thứ tự, nháp trùng số,
    nháp thiếu thumbnail, chế độ hiển thị mặc định. Mất khoảng 10-60 giây."""
    return _call("check", profile=profile)


@server.tool()
def publish(
    profile: str | None = None,
    group: str | None = None,
    max_videos: int | None = None,
    visibility: Literal["public", "unlisted", "private"] | None = None,
) -> dict:
    """Public video nháp trên YouTube Studio cho một profile hoặc cả nhóm (chạy lần lượt).
    Chạy nền, trả về task_id; theo dõi bằng task_status. Bỏ trống visibility/max_videos để
    dùng cấu hình của profile (vẫn bị giới hạn bởi chính sách agent)."""
    return _call(
        "publish", profile=profile, group=group, max_videos=max_videos, visibility=visibility
    )


@server.tool()
def task_status(task: str) -> dict:
    """Tiến độ tác vụ theo ID hoặc tên: status, finished, progress từng profile
    (currentIndex/totalVideos/success/failed) và kết quả từng profile."""
    return _call("status", task=task)


@server.tool()
def stop_task(task: str) -> dict:
    """Dừng tác vụ: video đang xử lý làm xong rồi mới dừng."""
    return _call("stop", task=task)


@server.tool()
def list_tasks() -> list[dict]:
    """Liệt kê tác vụ đã tạo (lịch, trạng thái, lần chạy cuối/kế tiếp)."""
    return _call("list_tasks")


@server.tool()
def run_task(task: str) -> dict:
    """Chạy ngay một tác vụ có sẵn (theo ID hoặc tên). Chạy nền; theo dõi bằng task_status."""
    return _call("run_task", task=task)


@server.tool()
def task_history(task: str, limit: int = 20) -> list[dict]:
    """Lịch sử các lần chạy của tác vụ: profile, thành công/lỗi, kết quả, lỗi."""
    return _call("history", task=task, limit=limit)


@server.tool()
def open_profiles(
    names: list[str] | None = None, group: str | None = None
) -> dict:
    """Mở cửa sổ Chrome của các profile (theo tên/ID hoặc cả nhóm)."""
    return _call("open", names=names, group=group)


@server.tool()
def close_profiles(
    names: list[str] | None = None, group: str | None = None
) -> dict:
    """Đóng cửa sổ Chrome của các profile (theo tên/ID hoặc cả nhóm)."""
    return _call("close", names=names, group=group)


if __name__ == "__main__":
    server.run("stdio")
