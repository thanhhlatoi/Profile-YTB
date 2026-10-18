import os
import shutil
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32":
    KNOWN_BINARIES = tuple(
        str(Path(base) / "Google/Chrome/Application/chrome.exe")
        for base in (
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", ""),
        )
        if base
    )
else:
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
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        resolved = shutil.which(name)
        if resolved and resolved not in paths:
            paths.append(resolved)
    for raw_path in paths:
        path = Path(raw_path)
        if not path.is_file() or not path.stat().st_mode & 0o111:
            continue
        if sys.platform == "win32":
            # chrome.exe --version opens a window instead; the install dir is named by version.
            versions = [p.name for p in path.parent.iterdir() if p.is_dir() and p.name[0].isdigit()]
            version = max(versions, key=lambda v: [int(x) for x in v.split(".") if x.isdigit()],
                          default="Không xác định")
            versions_label = f"Google Chrome {version}"
            results.append({"type": "Google Chrome", "path": str(path), "version": versions_label})
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
