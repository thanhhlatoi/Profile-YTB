from pathlib import Path


def ensure_inside(path: Path, parent: Path) -> Path:
    candidate = path.expanduser().resolve()
    base = parent.expanduser().resolve()
    if candidate != base and base not in candidate.parents:
        raise ValueError("Đường dẫn nằm ngoài vùng dữ liệu ứng dụng")
    return candidate


def profile_path(root: Path, profile_id: str) -> Path:
    return ensure_inside(root / profile_id, root)
