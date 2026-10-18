import json
import os
import shutil
import stat
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import psutil

from app.models.database import Profile, Task, TaskRun
from app.services.chrome_profile_discovery import discover_chrome_profiles
from app.utils.paths import ensure_inside, profile_path
from app.utils.validation import ProfileInput, validate_binary


class ProfileService:
    def __init__(self, paths, session_factory):
        self.paths, self.session_factory = paths, session_factory

    def create(self, data: ProfileInput) -> Profile:
        binary = validate_binary(data.browser_binary)
        with self.session_factory() as session:
            if session.query(Profile).filter_by(name=data.name).first():
                raise ValueError("Tên profile đã tồn tại")
            profile = Profile(
                id=str(uuid4()),
                name=data.name,
                profile_directory="Default",
                browser_type=data.browser_type,
                browser_binary=str(binary),
                color=data.color,
                notes=data.notes,
                tags=data.tags,
                purpose=data.purpose,
                group_name=data.group_name,
                pinned=data.pinned,
                proxy_enabled=data.proxy_enabled,
                proxy_scheme=data.proxy_scheme,
                proxy_host=data.proxy_host,
                proxy_port=data.proxy_port,
                startup_urls="\n".join(data.startup_urls),
                extra_arguments=data.extra_arguments,
                remote_debugging=data.remote_debugging,
                channel_url=data.channel_url,
                automation_config=data.automation_config,
            )
            session.add(profile)
            session.commit()
            profile_path(self.paths.profiles, profile.id).mkdir(mode=0o700)
            return profile

    def import_chrome_profiles(self) -> int:
        imported_count = 0
        discovered = discover_chrome_profiles()
        with self.session_factory() as session:
            current = session.query(Profile).all()
            existing = {(p.user_data_dir, p.profile_directory) for p in current}
            names = {p.name for p in current}
            for item in discovered:
                key = (item["user_data_dir"], item["profile_directory"])
                if key in existing:
                    continue
                name = item["name"]
                if name in names:
                    name = f"{name} ({item['profile_directory']})"
                if name in names:
                    name = f"{name} ({Path(item['user_data_dir']).name})"
                session.add(
                    Profile(
                        id=str(uuid4()),
                        name=name,
                        profile_directory=item["profile_directory"],
                        user_data_dir=item["user_data_dir"],
                        imported=True,
                        browser_type=(
                            "Chromium" if "chromium" in item["browser_binary"] else "Google Chrome"
                        ),
                        browser_binary=item["browser_binary"],
                    )
                )
                existing.add(key)
                names.add(name)
                imported_count += 1
            session.commit()
        return imported_count

    def update(self, profile_id: str, data: ProfileInput) -> Profile:
        validate_binary(data.browser_binary)
        with self.session_factory() as session:
            profile = session.get(Profile, profile_id)
            if not profile or profile.deleted:
                raise ValueError("Không tìm thấy profile")
            duplicate = (
                session.query(Profile)
                .filter(
                    Profile.name == data.name, Profile.id != profile_id
                )
                .first()
            )
            if duplicate:
                raise ValueError("Tên profile đã tồn tại")
            for key, value in data.model_dump().items():
                setattr(profile, key, "\n".join(value) if key == "startup_urls" else value)
            session.commit()
            return profile

    def set_important(self, profile_id: str, important: bool) -> None:
        with self.session_factory() as session:
            profile = session.get(Profile, profile_id)
            if not profile or profile.deleted:
                raise ValueError("Không tìm thấy profile")
            profile.important = important
            profile.updated_at = datetime.now()
            session.commit()

    # Rebuildable caches: skipping them keeps the copy small and fast.
    CACHE_DIRS = {
        "Cache", "Code Cache", "GPUCache", "DawnCache", "DawnGraphiteCache",
        "DawnWebGPUCache", "GrShaderCache", "ShaderCache",
    }

    @staticmethod
    def _chrome_running(user_data_dir: str) -> bool:
        target = Path(user_data_dir).resolve()
        for process in psutil.process_iter(["name", "cmdline"]):
            if "chrom" not in (process.info["name"] or ""):
                continue
            args = process.info["cmdline"] or []
            dirs = [a.split("=", 1)[1] for a in args if a.startswith("--user-data-dir=")]
            # No flag means Chrome's default dir, which is where imported profiles live.
            if not dirs or Path(dirs[0]).resolve() == target:
                return True
        return False

    def convert_to_own(self, profile_id: str, name: str) -> Profile:
        """Copy a Chrome gốc profile (with its logins) into a new Profile riêng.

        The original stays untouched. Chrome must be closed so the copy is consistent.
        """
        name = name.strip()
        with self.session_factory() as session:
            source = session.get(Profile, profile_id)
            if not source or source.deleted or not source.imported:
                raise ValueError("Chỉ chuyển được profile Chrome gốc")
            if session.query(Profile).filter_by(name=name).first():
                raise ValueError("Tên profile đã tồn tại")
            user_data_dir = Path(source.user_data_dir)
            source_dir = ensure_inside(user_data_dir / source.profile_directory, user_data_dir)
            if not source_dir.is_dir():
                raise ValueError(f"Không thấy thư mục dữ liệu: {source_dir}")
            if self._chrome_running(source.user_data_dir):
                raise RuntimeError(
                    "Hãy đóng Google Chrome hoàn toàn trước khi chuyển (kể cả Chrome chạy nền)."
                )
            new_id = str(uuid4())
            target = profile_path(self.paths.profiles, new_id)
            try:
                target.mkdir(mode=0o700)
                shutil.copytree(
                    source_dir,
                    target / "Default",
                    symlinks=True,
                    ignore=lambda folder, names: (
                        self.CACHE_DIRS & set(names) if Path(folder) == source_dir else set()
                    ),
                )
                self._copy_local_state(user_data_dir, source.profile_directory, target)
            except Exception:
                shutil.rmtree(target, ignore_errors=True)
                raise
            profile = Profile(
                id=new_id, name=name, profile_directory="Default",
                browser_type=source.browser_type, browser_binary=source.browser_binary,
                color=source.color, notes=source.notes, tags=source.tags,
                purpose=source.purpose, group_name=source.group_name, pinned=source.pinned,
                important=source.important, proxy_enabled=source.proxy_enabled,
                proxy_scheme=source.proxy_scheme, proxy_host=source.proxy_host,
                proxy_port=source.proxy_port, startup_urls=source.startup_urls,
                extra_arguments=source.extra_arguments, remote_debugging=True,
                channel_url=source.channel_url, automation_config=source.automation_config,
            )
            session.add(profile)
            session.commit()
            return profile

    @staticmethod
    def _copy_local_state(user_data_dir: Path, directory: str, target: Path) -> None:
        """Keep Chrome-wide settings, but list only the copied profile (as Default)."""
        try:
            state = json.loads((user_data_dir / "Local State").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        profile = state.setdefault("profile", {})
        info = profile.get("info_cache", {}).get(directory)
        profile["info_cache"] = {"Default": info} if info else {}
        profile["last_used"] = "Default"
        profile["last_active_profiles"] = ["Default"]
        profile["profiles_order"] = ["Default"]
        (target / "Local State").write_text(json.dumps(state), encoding="utf-8")

    def clone(self, profile_id: str, name: str) -> Profile:
        """Clone configuration only; never copy imported or browser data implicitly."""
        with self.session_factory() as session:
            source = session.get(Profile, profile_id)
            if not source or source.deleted:
                raise ValueError("Không tìm thấy profile")
            if session.query(Profile).filter_by(name=name).first():
                raise ValueError("Tên profile đã tồn tại")
            clone = Profile(
                id=str(uuid4()), name=name, profile_directory="Default",
                browser_type=source.browser_type, browser_binary=source.browser_binary,
                color=source.color, notes=source.notes, tags=source.tags,
                purpose=source.purpose, group_name=source.group_name, pinned=source.pinned,
                proxy_enabled=source.proxy_enabled, proxy_scheme=source.proxy_scheme,
                proxy_host=source.proxy_host, proxy_port=source.proxy_port,
                startup_urls=source.startup_urls, extra_arguments=source.extra_arguments,
                remote_debugging=source.remote_debugging,
                automation_config=source.automation_config,
            )
            session.add(clone)
            session.commit()
            profile_path(self.paths.profiles, clone.id).mkdir(mode=0o700)
            return clone

    def export_json(self, target: str | Path, profile_ids: list[str] | None = None) -> int:
        profiles = self.list()
        if profile_ids is not None:
            profiles = [profile for profile in profiles if profile.id in profile_ids]
        fields = (
            "name", "profile_directory", "browser_type", "browser_binary", "color", "notes",
            "tags", "purpose", "group_name", "pinned", "important", "proxy_enabled",
            "proxy_scheme", "proxy_host", "proxy_port", "startup_urls", "extra_arguments",
            "remote_debugging", "channel_url", "automation_config",
        )
        payload = [{field: getattr(profile, field) for field in fields} for profile in profiles]
        Path(target).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return len(payload)

    def import_json(self, source: str | Path) -> int:
        payload = json.loads(Path(source).read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("File import phải chứa một danh sách profile")
        count = 0
        with self.session_factory() as session:
            names = {
                profile.name for profile in session.query(Profile)
            }
            for item in payload:
                if not isinstance(item, dict) or not item.get("name"):
                    raise ValueError("Cấu hình profile không hợp lệ")
                urls = item.get("startup_urls") or ""
                data = ProfileInput(
                    **{**item, "startup_urls": urls.splitlines() if isinstance(urls, str) else urls}
                )
                if data.name in names:
                    continue
                name = data.name
                profile = Profile(
                    id=str(uuid4()), profile_directory="Default",
                    important=bool(item.get("important", False)),
                    **{**data.model_dump(), "startup_urls": "\n".join(data.startup_urls)},
                )
                session.add(profile)
                session.flush()
                profile_path(self.paths.profiles, profile.id).mkdir(mode=0o700)
                names.add(name)
                count += 1
            session.commit()
        return count

    def list(self, include_deleted: bool = False) -> list[Profile]:
        with self.session_factory() as session:
            query = session.query(Profile)
            if not include_deleted:
                query = query.filter_by(deleted=False)
            return query.order_by(Profile.name).all()

    @staticmethod
    def _dir_in_use(data_dir: Path, default_dir: bool) -> bool:
        """True if a Chrome process uses data_dir (or Chrome's default dir, when it is one)."""
        target = data_dir.resolve()
        for process in psutil.process_iter(["name", "cmdline"]):
            if "chrom" not in (process.info["name"] or "").lower():
                continue
            args = process.info["cmdline"] or []
            dirs = [a.split("=", 1)[1] for a in args if a.startswith("--user-data-dir=")]
            if (not dirs and default_dir) or (dirs and Path(dirs[0]).resolve() == target):
                return True
        return False

    @staticmethod
    def _remove_tree(path: Path) -> None:
        def make_writable(func, failed_path, _error):
            # Windows refuses to delete read-only files (Chrome marks some cache files so).
            os.chmod(failed_path, stat.S_IWRITE)
            func(failed_path)

        if not path.exists():
            return
        if sys.version_info >= (3, 12):
            shutil.rmtree(path, onexc=make_writable)
        else:
            shutil.rmtree(path, onerror=make_writable)

    @staticmethod
    def _forget_in_local_state(user_data_dir: Path, directory: str) -> None:
        """Drop the profile from Chrome's profile picker, as Chrome's own delete does."""
        local_state = user_data_dir / "Local State"
        try:
            state = json.loads(local_state.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        chrome = state.get("profile")
        if not isinstance(chrome, dict):
            return
        info_cache = chrome.get("info_cache", {})
        info_cache.pop(directory, None)
        for key in ("last_active_profiles", "profiles_order"):
            if isinstance(chrome.get(key), list):
                chrome[key] = [item for item in chrome[key] if item != directory]
        if chrome.get("last_used") == directory:
            chrome["last_used"] = next(iter(info_cache), "Default")
        temporary = local_state.with_name("Local State.cpm-tmp")
        temporary.write_text(json.dumps(state), encoding="utf-8")
        os.replace(temporary, local_state)

    def delete(self, profile_id: str) -> list[str]:
        """Permanently wipe a profile: its browser data, Chrome entry, tasks and history.

        Returns the ids of removed tasks so the caller can unschedule them.
        """
        with self.session_factory() as session:
            profile = session.get(Profile, profile_id)
            if not profile:
                raise ValueError("Không tìm thấy profile")
            if profile.imported:
                if not profile.user_data_dir or not profile.profile_directory:
                    raise ValueError("Profile Chrome không có thư mục dữ liệu")
                user_data_dir = Path(profile.user_data_dir)
                source = ensure_inside(user_data_dir / profile.profile_directory, user_data_dir)
                if source == user_data_dir.resolve():
                    raise ValueError("Từ chối xóa toàn bộ thư mục Chrome")
                if self._dir_in_use(user_data_dir, default_dir=True):
                    raise ValueError("Hãy đóng hết Google Chrome rồi xóa lại")
            else:
                source = ensure_inside(
                    profile_path(self.paths.profiles, profile.id), self.paths.profiles
                )
                if self._dir_in_use(source, default_dir=False):
                    raise ValueError("Profile đang mở, hãy đóng trước khi xóa")
            # Data left in the trash by older versions (soft delete).
            for path in (source, ensure_inside(self.paths.trash / profile.id, self.paths.trash)):
                self._remove_tree(path)
            if profile.imported:
                self._forget_in_local_state(user_data_dir, profile.profile_directory)

            removed_tasks = []
            for task in session.query(Task).filter_by(profile_id=profile.id).all():
                if task.target_group:
                    # Group tasks only use the profile as an anchor; move it to another member.
                    other = (
                        session.query(Profile)
                        .filter(
                            Profile.group_name == task.target_group,
                            Profile.deleted.is_(False),
                            Profile.id != profile.id,
                        )
                        .order_by(Profile.name)
                        .first()
                    )
                    if other:
                        task.profile_id = other.id
                        continue
                session.query(TaskRun).filter_by(task_id=task.id).delete()
                session.delete(task)
                removed_tasks.append(task.id)
            session.query(TaskRun).filter_by(profile_id=profile.id).delete()
            session.delete(profile)
            session.commit()
            return removed_tasks

    def purge_trash(self) -> list[str]:
        """Wipe profiles soft-deleted by older versions; returns the ids of removed tasks."""
        removed_tasks = []
        with self.session_factory() as session:
            ids = [p.id for p in session.query(Profile).filter_by(deleted=True)]
        for profile_id in ids:
            try:
                removed_tasks += self.delete(profile_id)
            except (OSError, ValueError):
                # E.g. Chrome is open; retried on the next start.
                pass
        return removed_tasks
