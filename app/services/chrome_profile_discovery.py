import json
import shutil
from pathlib import Path


def chrome_user_data_dirs(home: Path | None = None) -> list[Path]:
    home = (home or Path.home()).expanduser()
    candidates = [
        home / ".config/google-chrome",
        home / ".config/google-chrome-unstable",
        home / ".config/chromium",
        home / ".config/chromium-browser",
        home / ".var/app/com.google.Chrome/config/google-chrome",
        home / ".var/app/org.chromium.Chromium/config/chromium",
    ]
    return list(dict.fromkeys(path for path in candidates if path.is_dir()))


def discover_chrome_profiles(home: Path | None = None) -> list[dict[str, str]]:
    profiles = []
    for user_data_dir in chrome_user_data_dirs(home):
        info_cache = {}
        try:
            local_state = json.loads((user_data_dir / "Local State").read_text(encoding="utf-8"))
            info_cache = local_state.get("profile", {}).get("info_cache", {})
        except (OSError, ValueError, AttributeError):
            pass

        directories = {
            directory
            for directory in info_cache
            if directory == "Default" or directory.startswith("Profile ")
        }
        directories.update(
            path.name
            for path in user_data_dir.iterdir()
            if path.is_dir() and (path.name == "Default" or path.name.startswith("Profile "))
        )
        binary = shutil.which("google-chrome") or shutil.which("google-chrome-stable")
        if "chromium" in user_data_dir.name:
            binary = binary or shutil.which("chromium") or shutil.which("chromium-browser")
        binary = binary or "/usr/bin/google-chrome"
        for directory in sorted(directories, key=lambda value: (value != "Default", value)):
            if not (user_data_dir / directory).is_dir():
                continue
            info = info_cache.get(directory, {})
            profiles.append(
                {
                    "name": str(info.get("name") or info.get("user_name") or directory),
                    "profile_directory": directory,
                    "user_data_dir": str(user_data_dir),
                    "browser_binary": binary,
                }
            )
    return profiles
