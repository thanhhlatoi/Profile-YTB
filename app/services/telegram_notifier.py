"""Telegram message when a download job ends (Bot API called straight from the app, no LLM involved).

Config in settings.json: {"telegram": {"bot_token": "123:abc", "chat_id": "6222450119"}}.
Missing or invalid config means silence; a failed send never affects the download.
"""

import json
import logging
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

logger = logging.getLogger(__name__)

TIMEOUT = 15
TITLE = {
    "SUCCESS": "✅ Tải xong",
    "NO_NEW_VIDEO": "⚠️ Không tải được video nào",
    "FAILED": "❌ Tải thất bại",
    "CANCELLED": "⏹ Đã dừng tải",
    "INTERRUPTED": "⚠️ Tải bị gián đoạn",
}


class TelegramNotifier:
    def __init__(self, settings_path, extra=None) -> None:
        self.settings_path = settings_path
        self.extra = extra  # extra(job) -> list[str]: runs in the worker thread, lines are added to the message
        self._notified: set[str] = set()
        self._lock = threading.Lock()

    def _config(self) -> tuple[str, str] | None:
        try:
            saved = json.loads(self.settings_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, AttributeError):
            return None
        section = saved.get("telegram") or {}
        token, chat = str(section.get("bot_token", "")).strip(), str(section.get("chat_id", "")).strip()
        return (token, chat) if token and chat else None

    @staticmethod
    def format_job(job: dict) -> str:
        status = job.get("status", "")
        videos = sum(1 for m in job.get("moved", []) if str(m).endswith("> Nguon"))
        lines = [TITLE.get(status, f"ℹ️ Tải: {status}"), f"Link: {job.get('url', '')}"]
        if status == "SUCCESS":
            lines.append(f"Video: {videos} · Lưu: {job.get('save_to', '')}")
        else:
            reason = job.get("error") or job.get("note") or ""
            lines.append(f"Lưu vào: {job.get('save_to', '')}")
            if reason:
                lines.append(f"Lý do: {reason[:300]}")
        try:
            minutes = max(1, round((datetime.now() - datetime.fromisoformat(job["started_at"])).total_seconds() / 60))
            lines.append(f"Thời gian: {minutes} phút")
        except (KeyError, ValueError):
            pass
        return "\n".join(lines)

    def on_job(self, job: dict) -> None:
        """DownloadService.on_change hook: sends once per job, when it has finished."""
        if not job.get("finished"):
            return
        with self._lock:
            if job["job_id"] in self._notified:
                return
            self._notified.add(job["job_id"])
        threading.Thread(target=self._announce, args=(job,), daemon=True).start()

    def _announce(self, job: dict) -> None:
        lines = []
        if self.extra:
            try:
                lines = self.extra(job)
            except Exception:  # an extra step (NAS copy) must not block the message
                logger.exception("Bước phụ sau khi tải lỗi")
                lines = ["NAS: lỗi không mong muốn khi chép thumbnail (xem nhật ký)"]
        self.send("\n".join([self.format_job(job), *lines]))

    def send(self, text: str) -> bool:
        config = self._config()
        if not config:
            return False
        token, chat = config
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=urllib.parse.urlencode({"chat_id": chat, "text": text, "disable_web_page_preview": "true"}).encode(),
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT):
                return True
        except (urllib.error.URLError, OSError, ValueError) as error:
            # Never log the URL: it contains the bot token.
            logger.warning("Không gửi được thông báo Telegram: %s", type(error).__name__)
            return False
