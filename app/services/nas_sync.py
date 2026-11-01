"""Copy thumbnails of a finished download job to the NAS, mirroring the folder layout of the local drive.

    F:\YouTube\EN\<channel>\Thumnail\001 x.jpg  ->  <dest>\EN\<channel>\Thumnail\001 x.jpg

Copy only: nothing is moved or deleted on either side, an existing file is never overwritten (same size =
already synced, different size = left as is and counted as a conflict).

Config in settings.json: {"nas_sync": {"enabled": true, "dest": ["Z:\\YouTube", "\\\\192.168.1.153\\Data\\YouTube"]}}
The first destination whose drive/share is reachable is used.
"""

import json
import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

THUMB_DIR = "Thumnail"
THUMB_EXT = ".jpg"


class NasSync:
    def __init__(self, settings_path) -> None:
        self.settings_path = settings_path

    def _config(self) -> dict | None:
        try:
            saved = json.loads(Path(self.settings_path).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return None
        section = saved.get("nas_sync") or {}
        dest = section.get("dest")
        dest = [dest] if isinstance(dest, str) else list(dest or [])
        if not section.get("enabled") or not dest:
            return None
        return {"dest": [str(d) for d in dest]}

    @staticmethod
    def _reachable(base: Path) -> bool:
        try:
            return Path(base.anchor).exists()
        except OSError:
            return False

    def sync_job(self, job: dict) -> list[str]:
        """Message lines for the Telegram notice; [] when sync is off or the job produced nothing."""
        config = self._config()
        folders = job.get("folders") or []
        if not config or not folders:
            return []
        base = next((Path(d) for d in config["dest"] if self._reachable(Path(d))), None)
        if base is None:
            return ["NAS: không vào được NAS (" + ", ".join(config["dest"]) + "), chưa chép thumbnail"]
        root = Path(job.get("root") or "")
        copied = skipped = conflicts = failed = 0
        last_dest = base
        for folder in map(Path, folders):
            try:
                relative = folder.relative_to(root)
            except ValueError:
                failed += 1
                continue
            source_dir = folder / THUMB_DIR
            if not source_dir.is_dir():
                continue
            target_dir = base / relative / THUMB_DIR
            for source in sorted(source_dir.iterdir()):
                if source.suffix.lower() != THUMB_EXT or not source.is_file():
                    continue
                result = self._copy(source, target_dir / source.name)
                copied += result == "copied"
                skipped += result == "same"
                conflicts += result == "conflict"
                failed += result == "error"
                last_dest = target_dir
        line = f"NAS: chép {copied} thumbnail"
        if skipped:
            line += f", bỏ qua {skipped} (đã có)"
        if conflicts:
            line += f", {conflicts} trùng tên khác dung lượng (giữ bản trên NAS)"
        if failed:
            line += f", {failed} lỗi"
        return [line, f"Đích NAS: {last_dest}"]

    @staticmethod
    def _copy(source: Path, target: Path) -> str:
        try:
            if target.exists():
                return "same" if target.stat().st_size == source.stat().st_size else "conflict"
            target.parent.mkdir(parents=True, exist_ok=True)
            part = target.with_name(target.name + ".part")  # a half-copied file never carries the final name
            shutil.copy2(source, part)
            os.replace(part, target)
            return "copied"
        except OSError as error:
            logger.warning("Chép lên NAS lỗi (%s): %s", source.name, type(error).__name__)
            return "error"
