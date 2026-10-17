from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_dir


@dataclass(frozen=True)
class AppPaths:
    root: Path
    profiles: Path
    trash: Path
    logs: Path
    database: Path
    config: Path

    @classmethod
    def create(cls, root: Path | None = None) -> "AppPaths":
        base = (
            root or Path(user_data_dir("chrome-profile-manager", "ChromeProfileManager"))
        ).expanduser()
        paths = cls(
            base,
            base / "profiles",
            base / "trash",
            base / "logs",
            base / "database",
            base / "config",
        )
        for directory in (
            paths.root,
            paths.profiles,
            paths.trash,
            paths.logs,
            paths.database,
            paths.config,
        ):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            directory.chmod(0o700)
        return paths

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.database / 'profiles.db'}"
