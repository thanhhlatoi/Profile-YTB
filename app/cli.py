"""Command line control (cron, scripts, Hermes). Prints JSON; exit code 1 on failure.

When the app is running, commands go through its control socket so Chrome opens in the
desktop session and jobs run in the app's background scheduler. Otherwise they run here.
"""

import argparse
import json
import sys
import time

from app.config import AppPaths
from app.models.database import create_session_factory
from app.services import control_server
from app.services.chrome_process_service import ChromeProcessService
from app.services.controller import Controller
from app.services.profile_service import ProfileService
from app.services.task_service import TaskService


def local_controller(paths):
    factory = create_session_factory(paths.db_url)
    process = ChromeProcessService(paths, factory)
    process.discover()
    tasks = TaskService(factory, process)
    return Controller(
        ProfileService(paths, factory), process, tasks, settings_path=paths.config / "settings.json"
    )


def parser():
    root = argparse.ArgumentParser(prog="cpm", description="Điều khiển Chrome Profile Manager")
    sub = root.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list", help="Liệt kê profile")
    listing.add_argument("--group")
    listing.add_argument("--json", action="store_true", help="(mặc định đã là JSON)")
    for name, help_text in (("open", "Mở profile"), ("close", "Đóng profile")):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("names", nargs="*", help="Tên hoặc ID profile")
        command.add_argument("--group")
        command.add_argument("--all", action="store_true")
        command.add_argument("--workers", type=int, default=2)
    sub.add_parser("tasks", help="Liệt kê tác vụ")
    run = sub.add_parser("run-task", help="Chạy tác vụ theo tên hoặc ID")
    run.add_argument("task")
    run.add_argument("--wait", action="store_true", help="Chờ tới khi xong")
    publish = sub.add_parser("publish", help="Public video nháp ngay, không cần tạo tác vụ")
    publish.add_argument("profile", nargs="?")
    publish.add_argument("--group")
    publish.add_argument("--max", type=int, dest="max_videos")
    publish.add_argument("--visibility", choices=["public", "unlisted", "private"])
    publish.add_argument("--wait", action="store_true", help="Chờ tới khi xong")
    check = sub.add_parser("check", help="Kiểm tra kênh: số nháp, thiếu thumbnail (không đăng)")
    check.add_argument("profile")
    for name, help_text in (("status", "Tiến độ tác vụ"), ("stop", "Dừng tác vụ"),
                            ("history", "Lịch sử chạy")):
        sub.add_parser(name, help=help_text).add_argument("task")
    cdp = sub.add_parser("cdp", help="Địa chỉ CDP của profile cho Playwright/Selenium")
    cdp.add_argument("profile")
    return root


COMMANDS = {
    "list": ("list_profiles", lambda a: {"group": a.group}),
    "open": ("open", lambda a: {"names": a.names, "group": a.group, "all": a.all,
                                "workers": a.workers}),
    "close": ("close", lambda a: {"names": a.names, "group": a.group, "all": a.all,
                                  "workers": a.workers}),
    "tasks": ("list_tasks", lambda a: {}),
    "run-task": ("run_task", lambda a: {"task": a.task}),
    "publish": ("publish", lambda a: {"profile": a.profile, "group": a.group,
                                      "max_videos": a.max_videos, "visibility": a.visibility}),
    "check": ("check", lambda a: {"profile": a.profile}),
    "status": ("status", lambda a: {"task": a.task}),
    "stop": ("stop", lambda a: {"task": a.task}),
    "history": ("history", lambda a: {"task": a.task}),
    "cdp": ("cdp", lambda a: {"profile": a.profile}),
}


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    paths = AppPaths.create()
    socket_path = control_server.socket_path(paths)
    command, build_args = COMMANDS[args.command]
    command_args = build_args(args)
    try:
        if control_server.available(socket_path):
            def send(name, extra):
                return control_server.call(socket_path, name, extra)
        else:
            controller = local_controller(paths)

            def send(name, extra):
                return controller.handle(name, {**extra, "wait": True}
                                         if name in {"run_task", "publish"} else extra)
        result = send(command, command_args)
        if getattr(args, "wait", False) and isinstance(result, dict) and result.get("started"):
            while True:
                time.sleep(5)
                result = send("status", {"task": result.get("task_id")})
                if result["finished"]:
                    break
                print(json.dumps(result["progress"], ensure_ascii=False), file=sys.stderr)
    except Exception as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    failed = isinstance(result, dict) and (
        result.get("errors") or result.get("status") == "FAILED"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
