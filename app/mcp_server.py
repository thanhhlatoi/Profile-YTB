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
        "Điều khiển Chrome Profile Manager (Profile YTB) trên máy của người dùng để public video nháp "
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
def channel_status(profile: str) -> dict:
    """Trạng thái một kênh, KHÔNG mở YouTube: profile có đang mở không, link kênh, chế độ hiển
    thị mặc định, và lần đăng gần nhất (kết quả hoặc lỗi). Dùng check_channel để xem nháp."""
    return _call("channel_status", profile=profile)


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


@server.tool()
def download_locations() -> list[dict]:
    """Các ổ/nơi lưu được phép khi tải video (drive, path, free_gb). Gọi khi người dùng nói
    ổ đĩa hoặc hỏi có thể lưu ở đâu; chỉ dùng tên trong danh sách này cho tham số drive."""
    return _call("download_locations")


@server.tool()
def download_video(
    url: str,
    sub_lang: str = "en",
    range: str | None = None,
    folder: str | None = None,
    drive: str | None = None,
) -> dict:
    """Tải video YouTube (kèm sub .srt và thumbnail) về máy người dùng. url là link video,
    playlist hoặc kênh; sub_lang như en/ja; range như "3-7" (STT, chỉ cho kênh/playlist);
    drive là ổ đĩa như "E" hoặc "F" (xem download_locations; bỏ trống = nơi mặc định);
    folder là tên thư mục con trong ổ đó. Chạy nền, trả về job_id; theo dõi bằng download_status."""
    return _call(
        "download", url=url, sub_lang=sub_lang, range=range, folder=folder, drive=drive
    )


@server.tool()
def download_batch(
    urls: list[str],
    sub_lang: str = "en",
    range: str | None = None,
    folder: str | None = None,
    drive: str | None = None,
) -> dict:
    """Tải NHIỀU link YouTube một lần (tối đa 20). Các job xếp hàng và chạy lần lượt; cùng
    sub_lang, range, folder, drive cho cả lô. Trả về danh sách job_id; theo dõi bằng
    download_status()."""
    return _call(
        "download_batch", urls=urls, sub_lang=sub_lang, range=range, folder=folder, drive=drive
    )


@server.tool()
def download_status(job: str | None = None) -> dict | list:
    """Tiến độ tải video: status (QUEUED/RUNNING/SUCCESS/FAILED/CANCELLED), finished,
    thư mục đã lưu, log_tail. Bỏ trống job để xem tất cả."""
    return _call("download_status", job=job)


@server.tool()
def download_stop(job: str) -> dict:
    """Dừng một job tải video đang chạy hoặc đang chờ."""
    return _call("download_stop", job=job)


if __name__ == "__main__":
    server.run("stdio")
