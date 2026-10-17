import pytest

from app.utils.paths import ensure_inside


def test_path_outside_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        ensure_inside(tmp_path.parent / "outside", tmp_path / "profiles")
