import shutil
import subprocess
from pathlib import Path

KNOWN_BINARIES = (
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
)


def detect_browsers() -> list[dict[str, str]]:
    results = []
    paths = list(KNOWN_BINARIES)
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        resolved = shutil.which(name)
        if resolved and resolved not in paths:
            paths.append(resolved)
    for raw_path in paths:
        path = Path(raw_path)
        if not path.is_file() or not path.stat().st_mode & 0o111:
            continue
        try:
            version = subprocess.run(
                [str(path), "--version"], capture_output=True, text=True, timeout=5, check=False
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            version = "Không xác định"
        browser_type = (
            "Chromium" if "chrom" in path.name and "chrome" not in path.name else "Google Chrome"
        )
        results.append({"type": browser_type, "path": str(path), "version": version})
    return results
