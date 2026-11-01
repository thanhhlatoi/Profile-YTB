import logging
import os
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from app.config import AppPaths
from app.models.database import create_session_factory
from app.services import control_server
from app.services.be_reporter import BeReporter
from app.services.chrome_process_service import ChromeProcessService
from app.services.controller import Controller
from app.services.download_service import DownloadService
from app.services.nas_sync import NasSync
from app.services.profile_service import ProfileService
from app.services.scheduler_service import SchedulerService
from app.services.telegram_notifier import TelegramNotifier
from app.services.task_service import TaskService
from app.ui.main_window import MainWindow


def main() -> int:
    # Qt's gtk3 theme aborts on newer GNOME (missing xsettings 'antialiasing' key).
    if sys.platform.startswith("linux") and not os.environ.get("QT_QPA_PLATFORMTHEME"):
        os.environ["QT_QPA_PLATFORMTHEME"] = "generic"
    app = QApplication(sys.argv)
    app.setApplicationName("Chrome Profile Manager")
    paths = AppPaths.create()
    # Same file and format as MainWindow.log, so scheduler errors show in "Nhật ký".
    logging.basicConfig(
        filename=paths.logs / "app.log",
        level=logging.INFO,
        format="%(asctime)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    socket_path = control_server.socket_path(paths)
    if control_server.available(socket_path):
        # Two copies would mean two schedulers publishing the same drafts.
        QMessageBox.information(
            None, "Chrome Profile Manager", "Ứng dụng đang chạy (xem biểu tượng dưới khay)."
        )
        return 0
    session_factory = create_session_factory(paths.db_url)
    process = ChromeProcessService(paths, session_factory)
    process.discover()
    profiles = ProfileService(paths, session_factory)
    reporter = BeReporter(paths, session_factory)
    tasks = TaskService(session_factory, process, reporter=reporter)
    # Older versions soft-deleted into a trash; finish those deletes.
    profiles.purge_trash()
    scheduler = SchedulerService(tasks)
    scheduler.start()
    scheduler.restore()
    reporter.start()
    downloads = DownloadService(paths)
    nas = NasSync(paths.config / "settings.json")
    notifier = TelegramNotifier(paths.config / "settings.json", extra=nas.sync_job)

    def on_download(job: dict) -> None:
        reporter.report_download(job)
        notifier.on_job(job)

    downloads.on_change = on_download
    control = control_server.ControlServer(
        socket_path,
        Controller(profiles, process, tasks, scheduler, paths.config / "settings.json", downloads),
    )
    control.start()
    window = MainWindow(paths, profiles, process, tasks, scheduler)
    # --minimized (autostart): stay in the tray, but only if a tray exists to reopen from.
    if "--minimized" not in sys.argv or not window.tray.isSystemTrayAvailable():
        window.show()
    app.setQuitOnLastWindowClosed(False)
    result = app.exec()
    control.stop()
    reporter.stop()
    scheduler.stop()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
