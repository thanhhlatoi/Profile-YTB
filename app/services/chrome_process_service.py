import shlex
import signal
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import RLock

import psutil

from app.constants import ProfileStatus
from app.models.database import Profile


class ChromeProcessService:
    def __init__(self, paths, session_factory, process_factory=subprocess.Popen):
        self.paths = paths
        self.session_factory = session_factory
        self.process_factory = process_factory
        self._lock = RLock()
        self._processes: dict[str, subprocess.Popen] = {}

    def build_command(self, profile: Profile, urls: list[str] | None = None) -> list[str]:
        command = [
            profile.browser_binary,
            f"--user-data-dir={profile.user_data_dir or self.paths.profiles / profile.id}",
            f"--profile-directory={profile.profile_directory}",
            "--no-remote",
        ]
        if getattr(profile, "debug_port", None):
            # Localhost only: any local program can drive this profile while it is open.
            command += [
                f"--remote-debugging-port={profile.debug_port}",
                "--remote-debugging-address=127.0.0.1",
                # Automation runs in a tab that may not be focused; keep its timers at full speed.
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows",
            ]
        if profile.proxy_enabled:
            command.append(
                f"--proxy-server={profile.proxy_scheme}://{profile.proxy_host}:{profile.proxy_port}"
            )
        if profile.extra_arguments:
            command.extend(shlex.split(profile.extra_arguments))
        command.extend(urls or [line for line in profile.startup_urls.splitlines() if line.strip()])
        return command

    def _markers(self, profile: Profile) -> tuple[str, str]:
        data_dir = profile.user_data_dir or str(self.paths.profiles / profile.id)
        return f"--user-data-dir={data_dir}", f"--profile-directory={profile.profile_directory}"

    def _belongs_to(self, process: psutil.Process, profile: Profile) -> bool:
        try:
            # Exact argument match: "Profile 1" must not match "Profile 10".
            return set(self._markers(profile)) <= set(process.cmdline())
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            return False

    def discover(self) -> None:
        # Read every cmdline once, not once per profile.
        snapshot = []
        for process in psutil.process_iter(["pid", "ppid", "cmdline"]):
            args = set(process.info["cmdline"] or ())
            if any(arg.startswith("--user-data-dir=") for arg in args):
                snapshot.append((process.info["pid"], process.info["ppid"], args))
        with self.session_factory() as session:
            profiles = session.query(Profile).filter_by(deleted=False).all()
            for profile in profiles:
                markers = set(self._markers(profile))
                matches = {pid: ppid for pid, ppid, args in snapshot if markers <= args}
                # The browser root is the matching process whose parent is not also a match.
                roots = [pid for pid, ppid in matches.items() if ppid not in matches]
                profile.pid = min(roots) if roots else None
                profile.status = ProfileStatus.RUNNING if roots else ProfileStatus.STOPPED
            session.commit()

    def is_running(self, profile: Profile) -> bool:
        process = self._processes.get(profile.id)
        if process and process.poll() is None:
            return True
        if profile.pid:
            try:
                return self._belongs_to(psutil.Process(profile.pid), profile)
            except psutil.NoSuchProcess:
                return False
        return False

    def open(self, profile_id: str, urls: list[str] | None = None) -> int:
        with self._lock, self.session_factory() as session:
            profile = session.get(Profile, profile_id)
            if not profile or profile.deleted:
                raise ValueError("Không tìm thấy profile")
            if self.is_running(profile):
                return profile.pid or self._processes[profile.id].pid
            if not profile.imported:
                data_dir = Path(self.paths.profiles / profile.id)
                data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                data_dir.chmod(0o700)
            if profile.remote_debugging and not profile.imported and not profile.debug_port:
                profile.debug_port = self._free_debug_port(session)
            elif not profile.remote_debugging or profile.imported:
                # Chrome 136+ ignores remote debugging on the default (imported) data dir.
                profile.debug_port = None
            profile.status = ProfileStatus.STARTING
            session.commit()
            try:
                process = self.process_factory(
                    self.build_command(profile, urls), shell=False, start_new_session=True
                )
                self._processes[profile.id] = process
                profile.pid = process.pid
                profile.status = ProfileStatus.RUNNING
                profile.last_opened_at = datetime.now()
                session.commit()
                return process.pid
            except Exception:
                profile.status = ProfileStatus.ERROR
                session.commit()
                raise

    @staticmethod
    def _free_debug_port(session, start: int = 9222) -> int:
        used = {port for (port,) in session.query(Profile.debug_port) if port}
        for port in range(start, start + 1000):
            if port in used:
                continue
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", port)) != 0:
                    return port
        raise RuntimeError("Không còn cổng CDP trống trong khoảng 9222-10221")

    def close(self, profile_id: str, timeout: float = 5.0) -> None:
        with self._lock, self.session_factory() as session:
            profile = session.get(Profile, profile_id)
            if not profile:
                raise ValueError("Không tìm thấy profile")
            try:
                process = self._processes.get(profile_id) or (
                    psutil.Process(profile.pid) if profile.pid else None
                )
                if not process:
                    profile.status, profile.pid = ProfileStatus.STOPPED, None
                    session.commit()
                    return
                profile.status = ProfileStatus.STOPPING
                session.commit()
                target = (
                    psutil.Process(process.pid)
                    if isinstance(process, subprocess.Popen)
                    else process
                )
                children = target.children(recursive=True)
                target.terminate()
                gone, alive = psutil.wait_procs([target, *children], timeout=timeout)
                for child in alive:
                    child.kill()
                if isinstance(process, subprocess.Popen) and process.poll() is None:
                    process.send_signal(signal.SIGTERM)
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        process.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            finally:
                self._processes.pop(profile_id, None)
                profile.status, profile.pid = ProfileStatus.STOPPED, None
                session.commit()

    def restart(self, profile_id: str) -> int:
        self.close(profile_id)
        time.sleep(0.1)
        return self.open(profile_id)

    def open_url(self, profile_id: str, url: str) -> int:
        return self.open(profile_id, [url])

    def stop_all(self) -> None:
        with self.session_factory() as session:
            profile_ids = [
                profile.id for profile in session.query(Profile).filter_by(deleted=False).all()
            ]
        self.bulk_close(profile_ids)

    def bulk_open(self, profile_ids: list[str], max_workers: int = 2) -> dict[str, object]:
        return self._bulk(self.open, profile_ids, max_workers)

    def bulk_close(self, profile_ids: list[str], max_workers: int = 2) -> dict[str, object]:
        return self._bulk(self.close, profile_ids, max_workers)

    @staticmethod
    def _bulk(action, profile_ids: list[str], max_workers: int) -> dict[str, object]:
        results: dict[str, object] = {}
        workers = max(1, min(max_workers, len(profile_ids) or 1))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(action, profile_id): profile_id for profile_id in profile_ids}
            for future in as_completed(futures):
                profile_id = futures[future]
                try:
                    results[profile_id] = future.result()
                except Exception as exc:
                    results[profile_id] = exc
        return results
