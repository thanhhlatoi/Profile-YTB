"""Publish YouTube Studio drafts by driving the profile's Chrome over CDP.

The Studio workflow is the proven JS from the "bom nguyen tu" extension (app/studio_js),
injected into an isolated world exactly like a content script. Python only opens the
page, feeds thumbnails from a folder and watches progress.
"""

import base64
import json
import re
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import websocket

from app.constants import ProfileStatus
from app.models.database import Profile

JS_DIR = Path(__file__).resolve().parent.parent / "studio_js"
# Same order as the extension's manifest content_scripts.
JS_MODULES = (
    "selector-engine.js", "wait-engine.js", "action-engine.js", "thumbnail-manager.js",
    "parser.js", "logger.js", "state-machine.js", "router.js", "error-recovery.js",
    "workflow-engine.js",
)
# The modules only use chrome.storage.local; keep it in memory inside the isolated world.
CHROME_SHIM = """
var __YTP_STORE__ = {};
var chrome = {storage: {local: {
  get: async keys => {
    const list = typeof keys === 'string' ? [keys] : (Array.isArray(keys) ? keys
      : Object.keys(__YTP_STORE__));
    return Object.fromEntries(list.filter(k => k in __YTP_STORE__)
      .map(k => [k, __YTP_STORE__[k]]));
  },
  set: async items => { Object.assign(__YTP_STORE__, items); },
}}};
"""
DEFAULT_STUDIO_URL = "https://studio.youtube.com/"
LIST_SELECTOR = json.dumps("ytcp-video-row, ytcp-content-list")
CONTENT_LINK = json.dumps('a[href*="/channel/"][href*="/videos"]')
# Same rule as popup.js getThumbnailIndex: leading number followed by _ space or -.
THUMB_RE = re.compile(r"^(\d+)(?=[_\s-]).*\.(png|jpe?g)$", re.IGNORECASE)
TERMINAL_STATES = {"DONE", "ERROR", "STOPPED"}


def find_thumbnails(folder: Path) -> tuple[dict[str, Path], list[str]]:
    """Map index label -> file. Indexes used by several files are dropped and reported."""
    found: dict[str, list[Path]] = {}
    for path in sorted(folder.rglob("*")):
        match = THUMB_RE.match(path.name)
        if match and path.is_file():
            found.setdefault(match.group(1), []).append(path)
    unique = {index: paths[0] for index, paths in found.items() if len(paths) == 1}
    duplicates = [
        f"#{index} bị trùng: {' | '.join(p.name for p in paths)}"
        for index, paths in found.items()
        if len(paths) > 1
    ]
    return unique, duplicates


class CDPError(RuntimeError):
    pass


class CDPSession:
    """Minimal Chrome DevTools Protocol client for one page target."""

    def __init__(self, ws_url: str):
        # suppress_origin: Chrome rejects DevTools websockets that send an Origin header.
        self.ws = websocket.create_connection(ws_url, timeout=60, suppress_origin=True)
        self._next_id = 0

    def call(self, method: str, **params):
        self._next_id += 1
        message_id = self._next_id
        self.ws.send(json.dumps({"id": message_id, "method": method, "params": params}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == message_id:
                if "error" in message:
                    raise CDPError(f"{method}: {message['error'].get('message')}")
                return message.get("result", {})

    def evaluate(self, expression: str, context_id: int | None = None):
        params = {"expression": expression, "awaitPromise": True, "returnByValue": True}
        if context_id is not None:
            params["contextId"] = context_id
        result = self.call("Runtime.evaluate", **params)
        if "exceptionDetails" in result:
            details = result["exceptionDetails"]
            text = details.get("exception", {}).get("description") or details.get("text")
            raise CDPError(f"Lỗi JavaScript: {text}")
        return result.get("result", {}).get("value")

    def close(self):
        self.ws.close()


class StudioPublisher:
    def __init__(self, process_service, poll_seconds: float = 2):
        self.process_service = process_service
        self.poll_seconds = poll_seconds
        self._stop_requests: set[str] = set()
        self._lock = threading.Lock()
        # Live snapshot per profile while a publish runs (read by status queries).
        self.progress: dict[str, dict] = {}

    def request_stop(self, profile_id: str) -> None:
        with self._lock:
            self._stop_requests.add(profile_id)

    def _stop_requested(self, profile_id: str) -> bool:
        with self._lock:
            return profile_id in self._stop_requests

    # --- profile / browser -------------------------------------------------------------

    def _load_profile(self, profile_id: str) -> Profile:
        with self.process_service.session_factory() as session:
            profile = session.get(Profile, profile_id)
            if not profile or profile.deleted:
                raise ValueError("Không tìm thấy profile")
            if profile.imported:
                raise RuntimeError(
                    "Profile Chrome gốc không hỗ trợ tự động (Chrome chặn CDP). Chuột phải "
                    "profile > 'Chuyển thành Profile riêng' (giữ đăng nhập), rồi dùng profile mới."
                )
            if not profile.remote_debugging:
                # Publishing needs CDP; turn it on instead of failing.
                profile.remote_debugging = True
                session.commit()
            return profile

    def _ensure_browser(self, profile_id: str) -> int:
        profile = self._load_profile(profile_id)
        if profile.status == ProfileStatus.RUNNING and not self._cdp_alive(profile.debug_port):
            # Running from before CDP was enabled: restart so the port flag applies.
            self.process_service.close(profile_id)
        self.process_service.open(profile_id, [])
        port = self._load_profile(profile_id).debug_port
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self._cdp_alive(port):
                return port
            time.sleep(0.5)
        raise RuntimeError(f"Chrome không mở cổng CDP {port} sau 30 giây")

    @staticmethod
    def _cdp_alive(port) -> bool:
        if not port:
            return False
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2):
                return True
        except OSError:
            return False

    @staticmethod
    def _http(port: int, path: str, method: str = "GET"):
        request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method)
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read().decode()
            return json.loads(body) if body.strip().startswith(("{", "[")) else body

    # --- page --------------------------------------------------------------------------

    def _open_studio(self, cdp: CDPSession, url: str) -> None:
        """Wait for the Content list; from the dashboard, follow the Content link."""
        deadline = time.monotonic() + 60
        clicked = False
        while time.monotonic() < deadline:
            state = cdp.evaluate(
                f"({{href: location.href, list: !!document.querySelector({LIST_SELECTOR}),"
                f" link: !!document.querySelector({CONTENT_LINK})}})"
            ) or {}
            href = state.get("href", "")
            if "accounts.google.com" in href:
                raise RuntimeError("Profile chưa đăng nhập YouTube. Mở profile và đăng nhập trước.")
            if state.get("list"):
                return
            if state.get("link") and not clicked:
                cdp.evaluate(f"document.querySelector({CONTENT_LINK}).click()")
                clicked = True
            time.sleep(1)
        raise RuntimeError(
            "Không thấy danh sách video trong YouTube Studio. "
            f"Kiểm tra Link Studio của profile (đang mở: {url})"
        )

    def _inject(self, cdp: CDPSession) -> int:
        """Load the workflow modules into an isolated world, like a content script."""
        frame_id = cdp.call("Page.getFrameTree")["frameTree"]["frame"]["id"]
        context_id = cdp.call(
            "Page.createIsolatedWorld", frameId=frame_id, worldName="profile-ytb"
        )["executionContextId"]
        source = CHROME_SHIM + "\n".join(
            (JS_DIR / name).read_text(encoding="utf-8") for name in JS_MODULES
        )
        cdp.evaluate(source + "\ntrue", context_id)
        return context_id

    def _load_thumbnails(self, cdp, context_id, folder: str, max_videos: int) -> list[str]:
        """Copy thumbnails for the drafts about to run into the extension's IndexedDB."""
        path = Path(folder).expanduser()
        if not path.is_dir():
            raise RuntimeError(f"Thư mục thumbnail không tồn tại: {path}")
        thumbs, notes = find_thumbnails(path)
        drafts = cdp.evaluate(
            "Parser.getDraftRows().map(d => d.indexLabel)", context_id
        ) or []
        wanted = drafts[: max_videos or None]
        cdp.evaluate("ThumbnailManager.clearAll().then(() => true)", context_id)
        for index in wanted:
            file = thumbs.get(index)
            if not file:
                continue
            mime = "image/png" if file.suffix.lower() == ".png" else "image/jpeg"
            data_url = f"data:{mime};base64,{base64.b64encode(file.read_bytes()).decode()}"
            cdp.evaluate(
                f"ThumbnailManager.saveFromBase64({json.dumps(index)}, {json.dumps(data_url)},"
                f" {json.dumps(file.name)}).then(() => true)",
                context_id,
            )
        missing = [index for index in wanted if index not in thumbs]
        if missing:
            notes.append(f"Thiếu thumbnail cho #{', #'.join(missing)}")
        return notes

    def _screenshot(self, cdp: CDPSession, profile: Profile) -> str:
        try:
            data = cdp.call("Page.captureScreenshot", format="png")["data"]
        except Exception:
            return ""
        folder = self.process_service.paths.logs / "screenshots"
        folder.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^\w-]+", "_", profile.name)
        path = folder / f"{datetime.now():%Y%m%d-%H%M%S}_{safe_name}.png"
        path.write_bytes(base64.b64decode(data))
        return str(path)

    # --- public API --------------------------------------------------------------------

    def _start(self, profile_id: str, task_config: dict):
        """Open Studio in a new tab with the workflow injected; caller must close cdp."""
        profile = self._load_profile(profile_id)
        config = {
            "scheduleMode": False,
            "skipMissing": True,
            **json.loads(profile.automation_config or "{}"),
            **task_config,
        }
        port = self._ensure_browser(profile_id)
        url = profile.channel_url or DEFAULT_STUDIO_URL
        target = self._http(port, f"/json/new?{url}", method="PUT")
        self._http(port, f"/json/activate/{target['id']}")
        cdp = CDPSession(target["webSocketDebuggerUrl"])
        try:
            cdp.call("Page.enable")
            cdp.call("Page.bringToFront")
            self._open_studio(cdp, url)
            context_id = self._inject(cdp)
        except Exception as error:
            raise self._fail(cdp, profile, error) from error
        return profile, config, port, target, cdp, context_id

    def _fail(self, cdp: CDPSession, profile: Profile, error: Exception) -> RuntimeError:
        shot = self._screenshot(cdp, profile)
        cdp.close()
        return RuntimeError(f"{error}" + (f" (ảnh chụp: {shot})" if shot else ""))

    def preview(self, profile_id: str) -> dict:
        """Check a channel without publishing: drafts, duplicates and thumbnail coverage."""
        profile, config, port, target, cdp, context_id = self._start(profile_id, {})
        try:
            drafts = cdp.evaluate(
                "(() => { const q = Parser.getDraftRows(); return {"
                " drafts: q.map(d => ({index: d.indexLabel, title: d.title})),"
                " duplicates: Parser.findDuplicates(q)}; })()",
                context_id,
            ) or {}
        except Exception as error:
            raise self._fail(cdp, profile, error) from error
        cdp.close()
        self._http(port, f"/json/close/{target['id']}")
        result = {
            "profile": profile.name,
            "draft_count": len(drafts.get("drafts", [])),
            "drafts": drafts.get("drafts", []),
            "duplicate_draft_indexes": drafts.get("duplicates", []),
            "visibility": config.get("visibility", "public"),
            "max_videos": int(config.get("maxVideos") or 0),
            "thumbnail_folder": config.get("thumbnailFolder", ""),
        }
        if config.get("thumbnailFolder"):
            folder = Path(config["thumbnailFolder"]).expanduser()
            thumbs, duplicates = find_thumbnails(folder) if folder.is_dir() else ({}, [])
            result["thumbnail_folder_exists"] = folder.is_dir()
            result["missing_thumbnails"] = [
                d["index"] for d in result["drafts"] if d["index"] not in thumbs
            ]
            result["duplicate_thumbnails"] = duplicates
        return result

    def publish(self, profile_id: str, task_config: dict) -> str:
        """Run the Studio workflow; return a short summary or raise with the reason."""
        with self._lock:
            self._stop_requests.discard(profile_id)
        profile, config, port, target, cdp, context_id = self._start(profile_id, task_config)
        try:
            notes = []
            if config.get("thumbnailFolder"):
                notes = self._load_thumbnails(
                    cdp, context_id, config["thumbnailFolder"], int(config.get("maxVideos") or 0)
                )
            status = self._run_workflow(cdp, context_id, profile_id, config)
        except Exception as error:
            raise self._fail(cdp, profile, error) from error
        finally:
            self.progress.pop(profile_id, None)
        cdp.close()
        return self._summarize(status, notes, port, target["id"])

    def _run_workflow(self, cdp, context_id, profile_id, config) -> dict:
        cdp.evaluate(
            "(async () => {"
            " await chrome.storage.local.set({running: true, state: 'SCAN', currentIndex: 0,"
            " success: 0, failed: 0, logs: [], lastError: '', statusText: '',"
            " startTime: Date.now(), totalVideos: 0});"
            f" WorkflowEngine.run({json.dumps(config)}).catch(async e => {{"
            "   await chrome.storage.local.set({running: false, state: 'ERROR',"
            "   statusText: 'Lỗi: ' + e.message}); });"
            " return true; })()",
            context_id,
        )
        deadline = time.monotonic() + float(config.get("timeout", 4 * 3600))
        stop_sent = False
        while time.monotonic() < deadline:
            time.sleep(self.poll_seconds)
            if self._stop_requested(profile_id) and not stop_sent:
                cdp.evaluate("WorkflowEngine.stop(), true", context_id)
                stop_sent = True
            try:
                status = cdp.evaluate("JSON.stringify(__YTP_STORE__)", context_id)
            except CDPError as error:
                raise RuntimeError(
                    "Trang YouTube Studio bị tải lại hoặc đóng giữa chừng"
                ) from error
            status = json.loads(status or "{}")
            self.progress[profile_id] = {
                key: status.get(key)
                for key in ("state", "statusText", "currentIndex", "totalVideos", "success",
                            "failed")
            }
            if not status.get("running") and status.get("state") in TERMINAL_STATES:
                return status
        cdp.evaluate("WorkflowEngine.stop(), true", context_id)
        raise TimeoutError("Quá thời gian chờ xuất bản (đã gửi lệnh dừng)")

    def _summarize(self, status: dict, notes: list[str], port: int, target_id: str) -> str:
        logs = status.get("logs") or []
        skipped = [log for log in logs if log.get("status") == "SKIPPED"]
        errors = [log for log in logs if log.get("status") == "ERROR"]
        if status.get("state") == "ERROR":
            raise RuntimeError(status.get("statusText") or "Workflow lỗi")
        summary = (
            f"Xong {status.get('success', 0)}/{status.get('totalVideos', 0)} video"
            + (f", bỏ qua {len(skipped)}" if skipped else "")
            + (f", lỗi {len(errors)}" if errors else "")
            + (" (đã dừng theo yêu cầu)" if status.get("state") == "STOPPED" else "")
        )
        details = [f"#{log.get('index')}: {log.get('reason')}" for log in errors + skipped]
        if errors:
            # Keep the tab open on failure so the user can inspect it.
            raise RuntimeError("; ".join([summary, *details, *notes]))
        try:
            self._http(port, f"/json/close/{target_id}")
        except OSError:
            pass
        return "; ".join([summary, *notes]) if notes else summary
