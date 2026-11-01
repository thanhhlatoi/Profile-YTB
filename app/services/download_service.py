"""YouTube downloader (yt-dlp + bgutil PO token) that runs inside the app.

Hermes/CLI start a job through the Controller; jobs run one at a time in the background and
are polled by id. Tool paths and the output folder come from settings.json ("download"), never
from the caller, so an agent can only choose the link, subtitle language and range.
"""

import json
import logging
import os
import re
import shutil
import subprocess
import threading
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

URL_RE = re.compile(r"^https://((www|m|music)\.)?(youtube\.com|youtu\.be)/[\w\-./?=&%@+]+$")
LANG_RE = re.compile(r"^[A-Za-z0-9,\-*.]+$")
RANGE_RE = re.compile(r"^(\d{1,5})-(\d{1,5})$")
FOLDER_RE = re.compile(r"^\w[\w \-]{0,49}$")  # One sub-folder name: no dots or slashes.
MAX_BATCH = 20
KEEP_JOBS = 200
ARCHIVE_NAME = ".archive.txt"
SKIPPED_MARK = "has already been recorded in the archive"
ITEM_RE = re.compile(r"\[download\] Downloading (?:item|video) (\d+) of (\d+)")
SORT = {".mp4": "Nguon", ".jpg": "Thumnail", ".srt": "Sub"}
POT_PORT = 4416
MAX_PARALLEL, DEFAULT_PARALLEL = 4, 2
NAME_TEMPLATE = "%(playlist_index)03d %(title).100s.%(ext)s"
FORMAT = "(bestvideo[vcodec^=avc1][height<=720]/bestvideo[height<=720])+bestaudio[ext=m4a]/best"


class DownloadError(ValueError):
    pass


def parse_folder(value) -> str | None:
    value = str(value or "").strip()
    if not value:
        return None
    if not FOLDER_RE.match(value):
        raise DownloadError("folder không hợp lệ (chữ, số, khoảng trắng, gạch ngang; tối đa 50)")
    return value


def locations(cfg) -> dict[str, str]:
    """Allowed destinations: the default plus the drives listed in settings.json."""
    found = {"default": str(cfg["out_root"])}
    for name, path in (cfg.get("roots") or {}).items():
        found[str(name).strip().upper().rstrip(":\\")] = str(path)
    return found


def resolve_root(value, cfg) -> str:
    """Map "E" / "e:" / "ổ E" to the configured folder; unknown names are rejected."""
    options = locations(cfg)
    key = str(value or "").strip()
    if not key or key.lower() == "default":
        return options["default"]
    key = re.sub(r"^(ổ|o|drive)\s+", "", key, flags=re.IGNORECASE).upper().rstrip(":\\ ")
    if key not in options:
        allowed = ", ".join(k for k in options if k != "default") or "chỉ thư mục mặc định"
        raise DownloadError(f"Ổ/nơi lưu '{value}' không được phép. Có: {allowed}")
    return options[key]


def lang_folder(sub_lang) -> str:
    """Sub-folder named after the subtitle language: "en" -> "EN", "en,ja" -> "EN_JA", "zh-Hans" -> "ZH-HANS"."""
    codes = [re.sub(r"[^A-Za-z0-9-]", "", c) for c in re.split(r"[,\s]+", str(sub_lang or "en"))]
    return "_".join(c.upper() for c in codes if c)[:40] or "EN"


def target_dir(base, folder, sub_lang) -> Path:
    """<root>[/<folder>]/<LANG>: the same path + the same subtitle language always lands in the same
    place, and a new language gets its own folder."""
    path = Path(base) / folder if folder else Path(base)
    return path / lang_folder(sub_lang)


def parse_range(value) -> tuple[int, int] | None:
    if not value:
        return None
    match = RANGE_RE.match(str(value).strip())
    if not match or int(match[1]) < 1 or int(match[2]) < int(match[1]):
        raise DownloadError("range không hợp lệ (ví dụ 1-3)")
    return int(match[1]), int(match[2])


class DownloadService:
    def __init__(self, paths, settings_path=None):
        self.paths = paths
        self.settings_path = settings_path or paths.config / "settings.json"
        self.jobs: dict[str, dict] = {}
        self._procs: dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()
        self._pot_lock = threading.Lock()  # Two jobs must not both start the PO token server.
        # Jobs beyond the limit wait in QUEUED; settings.json "download.parallel" (1-4).
        self._slots = threading.BoundedSemaphore(self._parallel(self.config()))
        # Jobs survive an app restart; on_change(job) lets the app report progress to the BE.
        self.state_file = Path(paths.root) / "downloads.json"
        self.on_change = None
        self._load()

    # --- persistence -------------------------------------------------------------------

    def _load(self) -> None:
        try:
            saved = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for job in saved if isinstance(saved, list) else []:
            if not isinstance(job, dict) or "job_id" not in job:
                continue
            if not job.get("finished"):
                # The process died with the app: say so instead of a job stuck in RUNNING.
                job.update(
                    status="INTERRUPTED", finished=True,
                    error="Ứng dụng khởi động lại khi đang tải. Gửi lại link để tải tiếp "
                          "(video đã tải xong được bỏ qua nhờ archive).",
                )
            self.jobs[job["job_id"]] = job
        for leftover in Path(self.paths.root).glob("dl_*.txt"):
            leftover.unlink(missing_ok=True)  # Orphan lists from interrupted jobs.
        self._save()

    def _save(self) -> None:
        with self._lock:
            jobs = list(self.jobs.values())[-KEEP_JOBS:]
            self.jobs = {j["job_id"]: j for j in jobs}
            tmp = self.state_file.with_suffix(".tmp")
            try:
                tmp.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
                os.replace(tmp, self.state_file)
            except OSError:
                logger.warning("Không ghi được %s", self.state_file)

    def _notify(self, job) -> None:
        self._save()
        if self.on_change:
            try:
                self.on_change(dict(job))
            except Exception:  # reporting must never break a download
                logger.exception("Báo cáo tiến độ tải lỗi")

    @staticmethod
    def _parallel(cfg) -> int:
        try:
            return max(1, min(MAX_PARALLEL, int(cfg.get("parallel", DEFAULT_PARALLEL))))
        except (TypeError, ValueError):
            return DEFAULT_PARALLEL

    # --- configuration -----------------------------------------------------------------

    def config(self) -> dict:
        tools = self.paths.root / "tools"
        defaults = {
            "ytdlp": str(tools / "yt-dlp.exe"),
            "cookies": str(tools / "cookies.txt"),
            "ffmpeg_dir": r"C:\ffmpeg\bin" if os.name == "nt" else "",
            "pot_home": str(tools / "bgutil-ytdlp-pot-provider" / "server"),
            "out_root": str(Path.home() / "Downloads" / "YouTube"),
            "roots": {},  # Extra destinations by drive letter, from settings.json.
            "archive": str(tools / "archive_hermes.txt"),
        }
        try:
            saved = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
        return {**defaults, **saved.get("download", {})}

    # --- command building --------------------------------------------------------------

    @staticmethod
    def build_args(
        url, sub_lang, rng, cfg, pot_ok, list_file, folder=None, root=None
    ) -> list[str]:
        single = bool(re.search(r"watch\?|youtu\.be/", url))
        channel = bool(
            re.search(r"youtube\.com/(@|channel/|c/|user/)", url)
            and not re.search(r"/(videos|shorts|streams|playlist)", url)
        )
        target = url.rstrip("/") + "/videos" if channel else url
        args = [target]
        # STT (1 = newest) prefixes video, thumbnail and sub so they sort and match when editing.
        name_template = "%(title).100s.%(ext)s" if single else NAME_TEMPLATE
        if single:
            args.append("--no-playlist")
        elif rng:
            args += ["--playlist-start", str(rng[0]), "--playlist-end", str(rng[1])]
        pot_home = cfg["pot_home"]
        base = Path(root or cfg["out_root"])
        out_dir = target_dir(base, folder, sub_lang)
        args += [
            "--cookies", cfg["cookies"],
            "--js-runtimes", "node",
            "--extractor-args", f"youtubepot-bgutilhttp:base_url=http://127.0.0.1:{POT_PORT}",
            "--extractor-args", f"youtubepot-bgutilscript:server_home={pot_home}",
            "--force-ipv4",
        ]
        if cfg["ffmpeg_dir"]:
            args += ["--ffmpeg-location", cfg["ffmpeg_dir"]]
        args += [
            "--write-subs", "--write-auto-subs", "--sub-langs", sub_lang,
            "--sub-format", "vtt", "--convert-subs", "srt", "--no-embed-subs",
            "--no-mtime", "--format", FORMAT, "--merge-output-format", "mp4",
            "--write-thumbnail", "--convert-thumbnails", "jpg",
            "--http-chunk-size", "10M", "--concurrent-fragments", "4",
            "--sleep-requests", "0.5",
            "--sleep-interval", "1" if pot_ok else "2",
            "--max-sleep-interval", "4" if pot_ok else "6",
            "--sleep-subtitles", "1",
            "--retries", "20", "--fragment-retries", "50", "--retry-sleep", "exp=1:20",
            "--file-access-retries", "10", "--extractor-retries", "10",
            # One archive per destination folder: deleting or moving the folder also forgets what
            # was downloaded, so an old global list can never skip videos that are not on disk.
            "--download-archive", str(out_dir / ARCHIVE_NAME),
            "--no-write-playlist-metafiles",  # no "000 <channel> - Videos.jpg"
            "--windows-filenames",
            "--print-to-file", "after_move:%(filepath)s", str(list_file),
            "-o", str(out_dir / "%(channel)s" / name_template),
        ]
        return args

    @staticmethod
    def organize(folder: Path) -> list[str]:
        moved = []
        for item in folder.iterdir():
            sub = SORT.get(item.suffix.lower())
            if not item.is_file() or not sub:
                continue
            (folder / sub).mkdir(exist_ok=True)
            item.replace(folder / sub / item.name)
            moved.append(f"{item.name} > {sub}")
        return moved

    # --- PO token server ---------------------------------------------------------------

    @staticmethod
    def _pot_alive() -> bool:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{POT_PORT}/ping", timeout=3).close()
            return True
        except OSError:
            return False

    def _ensure_pot(self, cfg) -> bool:
        if self._pot_alive():
            return True
        main = Path(cfg["pot_home"]) / "build" / "main.js"
        if not main.exists():
            return False
        flags = 0x08000000 | 0x00000008 if os.name == "nt" else 0  # no window, detached
        subprocess.Popen(
            ["node", str(main)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=flags, close_fds=True,
        )
        for _ in range(10):
            threading.Event().wait(1)
            if self._pot_alive():
                return True
        return False

    # --- jobs --------------------------------------------------------------------------

    def _prepare(
        self, url, sub_lang, range_, folder, cfg, drive=None
    ) -> tuple[dict, tuple | None]:
        url, sub_lang = str(url or "").strip(), str(sub_lang or "en").strip() or "en"
        if not URL_RE.match(url):
            raise DownloadError(f"Link không phải YouTube hợp lệ: {url[:80]}")
        if not LANG_RE.match(sub_lang):
            raise DownloadError("sub_lang không hợp lệ")
        rng, folder = parse_range(range_), parse_folder(folder)
        root = resolve_root(drive, cfg)
        # "F:\\YouTube" typed as a path must not become F:\\YouTube\\YouTube (or ...\\EN\\EN).
        if folder and folder.lower() in (Path(root).name.lower(), lang_folder(sub_lang).lower()):
            folder = None
        for key in ("ytdlp", "cookies"):
            if not Path(cfg[key]).is_file():
                raise DownloadError(f"Chưa có {key}: {cfg[key]} (chạy scripts/setup_downloader)")
        job = {
            "job_id": uuid.uuid4().hex[:8], "url": url, "sub_lang": sub_lang,
            "range": list(rng) if rng else None, "folder": folder, "root": root, "status": "QUEUED",
            "finished": False, "started_at": datetime.now().isoformat(timespec="seconds"),
            "folders": [], "moved": [], "log_tail": "", "error": None,
            "save_to": str(target_dir(root, folder, sub_lang)),
        }
        return job, rng

    def _launch(self, job, cfg, rng) -> None:
        with self._lock:
            self.jobs[job["job_id"]] = job
        self._notify(job)
        threading.Thread(target=self._run, args=(job, cfg, rng), daemon=True).start()

    def start(self, url, sub_lang="en", range_=None, folder=None, drive=None) -> dict:
        cfg = self.config()
        job, rng = self._prepare(url, sub_lang, range_, folder, cfg, drive)
        self._launch(job, cfg, rng)
        return {"job_id": job["job_id"], "status": "QUEUED",
                "hint": "Dùng download_status để theo dõi tiến độ"}

    def start_batch(self, urls, sub_lang="en", range_=None, folder=None, drive=None) -> dict:
        """Queue several links at once; they run one after another. All-or-nothing validation."""
        if isinstance(urls, str):
            urls = re.split(r"[\s,]+", urls)
        unique = list(dict.fromkeys(u.strip() for u in (urls or []) if str(u).strip()))
        if not unique:
            raise DownloadError("Chưa có link nào")
        if len(unique) > MAX_BATCH:
            raise DownloadError(f"Tối đa {MAX_BATCH} link mỗi lần")
        cfg = self.config()
        prepared = [self._prepare(u, sub_lang, range_, folder, cfg, drive) for u in unique]
        for job, rng in prepared:
            self._launch(job, cfg, rng)
        return {"jobs": [{"job_id": j["job_id"], "url": j["url"]} for j, _ in prepared],
                "status": "QUEUED", "hint": "Dùng download_status() để xem tất cả job"}

    def _run(self, job, cfg, rng) -> None:
        with self._slots:
            if job["status"] == "CANCELLED":
                job["finished"] = True
                self._notify(job)
                return
            job["status"] = "RUNNING"
            self._notify(job)
            list_file = self.paths.root / f"dl_{job['job_id']}.txt"
            try:
                with self._pot_lock:
                    pot_ok = self._ensure_pot(cfg)
                root = job.get("root") or cfg["out_root"]
                out_dir = target_dir(root, job.get("folder"), job["sub_lang"])
                out_dir.mkdir(parents=True, exist_ok=True)
                args = self.build_args(
                    job["url"], job["sub_lang"], rng, cfg, pot_ok, list_file,
                    job.get("folder"), root,
                )
                proc = subprocess.Popen(
                    [cfg["ytdlp"], *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    cwd=str(Path(cfg["ytdlp"]).parent),
                    creationflags=0x08000000 if os.name == "nt" else 0,
                )
                self._procs[job["job_id"]] = proc
                tail: list[str] = []
                skipped = 0
                for line in proc.stdout:
                    skipped += SKIPPED_MARK in line
                    tail = (tail + [line.rstrip()])[-15:]
                    job["log_tail"] = "\n".join(tail)
                    item = ITEM_RE.search(line)
                    if item:
                        # Bao tien do moi video (khong phai moi dong) de BE thay dang tai video thu may
                        job["item"], job["items"] = int(item.group(1)), int(item.group(2))
                        self._notify(job)
                code = proc.wait()
                folders = set()
                if list_file.exists():
                    for line in list_file.read_text(encoding="utf-8").splitlines():
                        if line.strip():
                            folders.add(Path(line).parent)
                for folder in folders:
                    if folder.is_dir():
                        job["moved"] += self.organize(folder)
                job["folders"] = sorted(str(f) for f in folders)
                if job["status"] != "CANCELLED":
                    job["status"] = "SUCCESS" if code == 0 else "FAILED"
                    if code != 0:
                        job["error"] = f"yt-dlp thoát với mã {code}"
                    elif not folders:
                        job["status"] = "NO_NEW_VIDEO"
                        job["note"] = (
                            f"Không tải video nào: {skipped} video đã có trong archive của thư mục "
                            f"{job['save_to']} (xóa file {ARCHIVE_NAME} trong thư mục đó để tải lại)"
                            if skipped else "Không có video nào khớp (kiểm tra link/range)"
                        )
            except Exception as error:
                logger.exception("Tải video lỗi")
                job["status"], job["error"] = "FAILED", str(error)
            finally:
                self._procs.pop(job["job_id"], None)
                list_file.unlink(missing_ok=True)
                job["finished"] = True
                self._notify(job)

    def where(self) -> list[dict]:
        """Destinations Hermes may choose from, with free space, so it can pick or ask."""
        result = []
        for name, path in locations(self.config()).items():
            try:
                anchor = Path(path).anchor or path
                free = round(shutil.disk_usage(anchor).free / 1024**3)
            except OSError:
                free = None
            result.append({"drive": name, "path": path, "free_gb": free})
        return result

    def status(self, job_id=None) -> dict | list:
        if job_id is None:
            return [self._view(j) for j in self.jobs.values()]
        job = self.jobs.get(job_id)
        if not job:
            raise DownloadError("Không tìm thấy job tải")
        return self._view(job)

    @staticmethod
    def _view(job) -> dict:
        return {**job, "finished": job["finished"]}

    def stop(self, job_id) -> dict:
        job = self.jobs.get(job_id)
        if not job:
            raise DownloadError("Không tìm thấy job tải")
        if job["finished"]:
            return {"job_id": job_id, "stop_requested": False, "note": "Job đã kết thúc"}
        job["status"] = "CANCELLED"
        self._notify(job)
        proc = self._procs.get(job_id)
        if proc:
            proc.terminate()
        return {"job_id": job_id, "stop_requested": True}
