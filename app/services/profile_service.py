import json
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import psutil

from app.constants import ProfileStatus
from app.models.database import Profile
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
                raise ValueError("Tên profile đã tồn tại (kể cả trong thùng rác)")
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
                raise ValueError("Tên profile đã tồn tại (kể cả trong thùng rác)")
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
                raise ValueError("Tên profile đã tồn tại (kể cả trong thùng rác)")
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
                raise ValueError("Tên profile đã tồn tại (kể cả trong thùng rác)")
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

    def delete(self, profile_id: str) -> None:
        with self.session_factory() as session:
            profile = session.get(Profile, profile_id)
            if not profile or profile.deleted:
                raise ValueError("Không tìm thấy profile")
            if profile.status == ProfileStatus.RUNNING:
                raise ValueError("Không thể xóa profile đang chạy")
            if profile.imported:
                if not profile.user_data_dir:
                    raise ValueError("Profile Chrome không có thư mục dữ liệu")
                user_data_dir = Path(profile.user_data_dir)
                source = ensure_inside(
                    user_data_dir / profile.profile_directory, user_data_dir
                )
            else:
                source = ensure_inside(
                    profile_path(self.paths.profiles, profile.id), self.paths.profiles
                )
            # Soft delete: data goes to trash so "Khôi phục" can bring it back.
            target = ensure_inside(self.paths.trash / profile.id, self.paths.trash)
            if source.exists():
                shutil.move(str(source), str(target))
            profile.deleted = True
            profile.updated_at = datetime.now()
            session.commit()

    def restore(self, profile_id: str) -> None:
        with self.session_factory() as session:
            profile = session.get(Profile, profile_id)
            if not profile or not profile.deleted:
                raise ValueError("Không tìm thấy profile trong thùng rác")
            source = ensure_inside(self.paths.trash / profile.id, self.paths.trash)
            if profile.imported:
                if not profile.user_data_dir:
                    raise ValueError("Profile Chrome không có thư mục dữ liệu")
                user_data_dir = Path(profile.user_data_dir)
                target = ensure_inside(
                    user_data_dir / profile.profile_directory, user_data_dir
                )
            else:
                target = ensure_inside(self.paths.profiles / profile.id, self.paths.profiles)
            if source.exists():
                if target.exists():
                    raise ValueError(f"Thư mục đích đã tồn tại: {target}")
                shutil.move(str(source), str(target))
            target.mkdir(parents=True, exist_ok=True, mode=0o700)
            target.chmod(0o700)
            profile.deleted = False
            profile.updated_at = datetime.now()
            session.commit()

    def permanent_delete(self, profile_id: str) -> None:
        with self.session_factory() as session:
            profile = session.get(Profile, profile_id)
            if not profile or not profile.deleted:
                raise ValueError("Không tìm thấy profile trong thùng rác")
            target = ensure_inside(self.paths.trash / profile.id, self.paths.trash)
            if target.exists():
                shutil.rmtree(target)
            session.delete(profile)
            session.commit()
