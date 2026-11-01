"""Bao cao ve gmail-manager BE bang token cua may: heartbeat, dong bo profile/task, ket qua tac vu.

Cau hinh: file `be_link.json` trong thu muc config cua app (hoac bien moi truong BE_URL, BE_TOKEN):
    {"url": "http://192.168.1.50:8080", "token": "ytb_..."}
Token do BE cap (dashboard > Token may). Thieu cau hinh hoac BE tat thi reporter im lang, khong anh huong app.
Khong gui: ghi chu (notes), startup_urls, extra_arguments, payload tac vu (co the chua du lieu nhay cam).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import queue
import socket
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

from app.constants import ActionType
from app.models.database import Profile, Task

log = logging.getLogger(__name__)

HEARTBEAT_SECONDS = 15
FULL_SYNC_SECONDS = 300
HTTP_TIMEOUT = 10


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


class BeReporter:
    def __init__(self, paths, session_factory) -> None:
        self.config_file = paths.config / "be_link.json"
        self.session_factory = session_factory
        self._stop = threading.Event()
        self._events: queue.Queue = queue.Queue(maxsize=500)
        self._threads: list[threading.Thread] = []
        self._hashes: dict[str, str] = {}
        self._last_full = 0.0
        self._warned_auth = False
        self._downloads: queue.Queue = queue.Queue(maxsize=500)
        self._be_task_ids: dict[str, str] = {}  # job_id cua app -> id tien trinh ben BE
        self._linked: set[str] = set()  # job_id ma BE dang co tien trinh YTB_DOWNLOAD cho (do Hermes giao)
        self._unlinked: set[str] = set()  # job_id BE khong cho (job tao tu app): bao theo kieu tien trinh rieng

    # ---------- vong doi ----------

    def start(self) -> None:
        for target, name in (
            (self._loop, "be-reporter"),
            (self._drain, "be-reporter-events"),
            (self._drain_downloads, "be-reporter-downloads"),
        ):
            thread = threading.Thread(target=target, name=name, daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        self._stop.set()

    # ---------- cau hinh / HTTP ----------

    def _config(self) -> tuple[str, str] | None:
        url, token = os.environ.get("BE_URL", ""), os.environ.get("BE_TOKEN", "")
        if not (url and token):
            try:
                data = json.loads(self.config_file.read_text(encoding="utf-8"))
                url, token = data.get("url", ""), data.get("token", "")
            except (OSError, ValueError):
                return None
        url, token = url.strip().rstrip("/"), token.strip()
        return (url, token) if url and token else None

    def _send(self, method: str, path: str, body: dict) -> bool:
        config = self._config()
        if not config:
            return False
        url, token = config
        request = urllib.request.Request(
            url + path,
            data=json.dumps(body).encode("utf-8"),
            method=method,
            headers={"Content-Type": "application/json", "X-Machine-Token": token},
        )
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT):
                self._warned_auth = False
                return True
        except urllib.error.HTTPError as exc:
            if exc.code == 401 and not self._warned_auth:
                self._warned_auth = True
                log.warning("BE tu choi token (sai hoac da bi thu hoi)")
            else:
                log.debug("BE tra %s cho %s", exc.code, path)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            log.debug("Khong gui duoc toi BE: %s", exc)
        return False

    # ---------- heartbeat + dong bo ----------

    def _loop(self) -> None:
        while True:
            try:
                self._tick()
            except Exception:  # khong de loi bao cao lam sap app
                log.exception("be-reporter tick loi")
            if self._stop.wait(HEARTBEAT_SECONDS):
                return

    def _tick(self) -> None:
        if not self._config():
            return
        with self.session_factory() as session:
            profiles = session.query(Profile).filter_by(deleted=False).all()
            tasks = session.query(Task).all()
            running = [
                {"profile": p.name[:100], "email": None, "pid": p.pid, "status": "running", "task": None}
                for p in profiles
                if p.status == "RUNNING"
            ]
            profile_rows = [self._profile_row(p) for p in profiles]
            task_rows = [self._task_row(t) for t in tasks]
        self._send(
            "POST",
            "/api/bot/report/agent/heartbeat",
            {"os": platform.platform()[:60], "ip": self._local_ip(), "chromes": running,
             "machine": socket.gethostname()},
        )
        full = time.monotonic() - self._last_full > FULL_SYNC_SECONDS
        synced = self._sync("profiles", "/api/bot/report/sync/profiles", {"profiles": profile_rows}, full)
        synced = self._sync("tasks", "/api/bot/report/sync/tasks", {"tasks": task_rows}, full) or synced
        if full and synced:
            self._last_full = time.monotonic()

    def _sync(self, key: str, path: str, body: dict, force: bool) -> bool:
        digest = hashlib.sha1(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()
        if not force and self._hashes.get(key) == digest:
            return False
        if self._send("PUT", path, body):
            self._hashes[key] = digest
            return True
        return False

    @staticmethod
    def _profile_row(p: Profile) -> dict:
        proxy = bool(p.proxy_enabled and p.proxy_host)
        return {
            "localId": p.id, "name": p.name, "profileDirectory": p.profile_directory, "email": None,
            "tags": (p.tags or "")[:500] or None, "notes": None, "important": bool(p.important),
            "groupName": (p.group_name or None), "channelUrl": (p.channel_url or None),
            "proxyScheme": p.proxy_scheme if proxy else None, "proxyHost": p.proxy_host if proxy else None,
            "proxyPort": p.proxy_port if proxy else None, "status": p.status, "pid": p.pid,
            "lastOpenedAt": _iso(p.last_opened_at),
        }

    @staticmethod
    def _task_row(t: Task) -> dict:
        return {
            "localId": t.id, "name": t.name, "profileLocalId": t.profile_id, "targetGroup": t.target_group or None,
            "actionType": t.action_type, "scheduleType": t.schedule_type, "intervalMinutes": t.interval_minutes,
            "enabled": bool(t.enabled), "status": t.status, "lastRunAt": _iso(t.last_run_at),
            "nextRunAt": _iso(t.next_run_at), "lastError": (t.last_error or "")[:500] or None,
        }

    @staticmethod
    def _local_ip() -> str | None:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("10.255.255.255", 1))
                return s.getsockname()[0]
        except OSError:
            return None

    # ---------- ket qua tac vu ----------

    def report_run(self, task_name: str, action_type: str, profile_name: str, channel_url: str, error: str) -> None:
        """Goi sau moi lan chay mot profile. Dang YouTube = mot luot dang len kenh (BE tu ghi log loi neu that bai)."""
        if action_type == ActionType.PUBLISH_YOUTUBE:
            self._enqueue("/api/bot/report/posts", {
                "platform": "YOUTUBE", "channel": (channel_url or profile_name)[:200],
                "success": not error, "error": error[:500] or None})
        elif error:
            self._enqueue("/api/bot/report/errors", {
                "profile": profile_name[:100], "message": f"Tac vu '{task_name}' ({action_type}) loi: {error}"[:1000]})

    # ---------- tien do tai video ----------

    def report_download(self, job: dict) -> None:
        """Goi moi khi job tai doi trang thai (tu DownloadService.on_change); chay o luong rieng."""
        try:
            self._downloads.put_nowait(dict(job))
        except queue.Full:
            log.debug("Hang doi bao cao tai video day, bo qua")

    def _call_json(self, method: str, path: str, body: dict) -> dict | None:
        config = self._config()
        if not config:
            return None
        url, token = config
        request = urllib.request.Request(
            url + path, data=json.dumps(body).encode("utf-8"), method=method,
            headers={"Content-Type": "application/json", "X-Machine-Token": token},
        )
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8") or "{}")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            log.debug("BE loi %s: %s", path, exc)
            return None

    def _drain_downloads(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._downloads.get(timeout=1)
            except queue.Empty:
                continue
            try:
                self._push_download(job)
            except Exception:
                log.exception("Bao cao tai video loi")

    def _report_job(self, job: dict) -> bool | None:
        """Bao trang thai that theo job_id: BE ket thuc tien trinh YTB_DOWNLOAD (do Hermes giao) chi khi job xong.
        True = BE co tien trinh dang cho job nay; False = khong co; None = khong goi duoc BE."""
        tail = job.get("log_tail") or ""
        reply = self._call_json("POST", "/api/bot/report/downloads", {
            "jobId": job["job_id"], "url": (job.get("url") or "")[:500], "status": job.get("status") or "QUEUED",
            "finished": bool(job.get("finished")), "files": len(job.get("moved", [])),
            "item": job.get("item"), "items": job.get("items"),
            "saveTo": (job.get("save_to") or "")[:500] or None, "error": (job.get("error") or "")[:1000] or None,
            "note": (job.get("note") or "")[:1000] or None, "logTail": tail[-4000:] or None,
        })
        return None if reply is None else bool(reply.get("linked"))

    def _push_download(self, job: dict) -> None:
        job_id, status = job["job_id"], job.get("status")
        if job_id not in self._be_task_ids and job_id not in self._unlinked:
            # Hermes vua goi download_video: BE gan job_id ngay sau khi tool tra ve, nen cho mot chut roi thu lai
            tries = 1 if job_id in self._linked or not (job.get("finished") or status == "RUNNING") else 4
            for attempt in range(tries):
                linked = self._report_job(job)
                if linked:
                    self._linked.add(job_id)
                    if job.get("finished"):
                        self._linked.discard(job_id)
                    return
                if linked is None or attempt == tries - 1 or self._stop.wait(3):
                    break
            if linked is None and (job_id in self._linked or status == "QUEUED"):
                return  # BE tam khong goi duoc: lan bao sau se cap nhat
            if linked is False:
                if status == "QUEUED" and not job.get("finished"):
                    return  # chua biet co tien trinh BE nao cho job nay: doi lan bao RUNNING
                self._unlinked.add(job_id)  # job tu app (khong qua Hermes): dung tien trinh rieng nhu cu
        if job.get("finished"):
            self._unlinked.discard(job_id)
        be_id = self._be_task_ids.get(job_id)
        if be_id is None:
            created = self._call_json("POST", "/api/bot/report/tasks", {
                "type": "YTB_APP_DOWNLOAD",
                "title": f"Tai video: {job.get('url', '')}"[:200],
                "message": f"Luu vao {job.get('save_to', '')}"[:500],
            })
            if not created or not created.get("id"):
                return
            be_id = self._be_task_ids[job_id] = created["id"]
        if status == "RUNNING":
            self._call_json("POST", f"/api/bot/report/tasks/{be_id}/progress",
                            {"progress": 10, "message": "Dang tai", "level": "INFO"})
        elif job.get("finished"):
            ok = status == "SUCCESS"
            result = json.dumps({"save_to": job.get("save_to"), "folders": job.get("folders", []),
                                 "files": len(job.get("moved", [])), "note": job.get("note")},
                                ensure_ascii=False)
            self._call_json("POST", f"/api/bot/report/tasks/{be_id}/finish", {
                "status": "SUCCEEDED" if ok else "FAILED", "result": result[:20000],
                "message": (job.get("error") or job.get("note") or f"Tai xong ({status})")[:500]})
            self._be_task_ids.pop(job_id, None)

    def _enqueue(self, path: str, body: dict) -> None:
        try:
            self._events.put_nowait((path, body))
        except queue.Full:
            log.debug("Hang doi bao cao BE day, bo qua su kien")

    def _drain(self) -> None:
        while not self._stop.is_set():
            try:
                path, body = self._events.get(timeout=1)
            except queue.Empty:
                continue
            for _ in range(3):  # thu lai vai lan neu BE tam thoi khong len
                if self._send("POST", path, body) or self._stop.wait(5):
                    break
