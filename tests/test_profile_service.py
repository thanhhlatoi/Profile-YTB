import json
import os

import pytest

from app.config import AppPaths
from app.models.database import create_session_factory
from app.services.profile_service import ProfileService
from app.utils.validation import ProfileInput


def setup(tmp_path):
    paths = AppPaths.create(tmp_path / "data")
    service = ProfileService(paths, create_session_factory(paths.db_url))
    binary = tmp_path / "chrome"
    binary.write_text("x")
    binary.chmod(os.stat(binary).st_mode | 0o111)
    return paths, service, str(binary)


def test_delete_moves_to_trash_then_restore_and_purge(tmp_path):
    paths, service, binary = setup(tmp_path)
    profile = service.create(ProfileInput(name="A", browser_binary=binary))
    with pytest.raises(ValueError):
        service.create(ProfileInput(name="A", browser_binary=binary))
    service.delete(profile.id)
    assert not (paths.profiles / profile.id).exists()
    assert (paths.trash / profile.id).is_dir()
    assert service.list() == []
    with pytest.raises(ValueError):
        service.create(ProfileInput(name="A", browser_binary=binary))
    service.restore(profile.id)
    assert (paths.profiles / profile.id).is_dir()
    service.delete(profile.id)
    service.permanent_delete(profile.id)
    assert not (paths.trash / profile.id).exists()
    assert service.list(include_deleted=True) == []


def test_delete_imported_profile_is_recoverable(tmp_path):
    paths, service, binary = setup(tmp_path)
    user_data_dir = tmp_path / "chrome-user-data"
    chrome_profile = user_data_dir / "Profile 1"
    chrome_profile.mkdir(parents=True)
    (chrome_profile / "Preferences").write_text("{}")

    with service.session_factory() as session:
        from app.models.database import Profile

        profile = Profile(
            name="Imported",
            profile_directory="Profile 1",
            user_data_dir=str(user_data_dir),
            imported=True,
            browser_binary=binary,
        )
        session.add(profile)
        session.commit()
        profile_id = profile.id

    service.delete(profile_id)
    assert not chrome_profile.exists()
    assert (paths.trash / profile_id / "Preferences").exists()
    assert service.list() == []
    service.restore(profile_id)
    assert (chrome_profile / "Preferences").exists()


def test_clone_copies_configuration_without_importing_browser_data(tmp_path):
    paths, service, binary = setup(tmp_path)
    source = service.create(
        ProfileInput(
            name="Source", browser_binary=binary, tags="youtube", purpose="Work",
            group_name="Team A", pinned=True, startup_urls=["https://example.com"],
        )
    )

    clone = service.clone(source.id, "Clone")

    assert clone.id != source.id
    assert clone.tags == "youtube"
    assert clone.group_name == "Team A"
    assert clone.user_data_dir is None
    assert (paths.profiles / clone.id).is_dir()


def test_json_export_import_round_trip(tmp_path):
    paths, service, binary = setup(tmp_path)
    service.create(ProfileInput(name="Exported", browser_binary=binary, group_name="A"))
    export_path = tmp_path / "profiles.json"

    assert service.export_json(export_path) == 1
    payload = json.loads(export_path.read_text())
    assert payload[0]["group_name"] == "A"

    other_paths = AppPaths.create(tmp_path / "other-data")
    other = ProfileService(other_paths, create_session_factory(other_paths.db_url))
    assert other.import_json(export_path) == 1
    assert other.list()[0].name == "Exported"


def test_convert_imported_profile_to_own_keeps_data(tmp_path, monkeypatch):
    paths, service, binary = setup(tmp_path)
    chrome = tmp_path / "google-chrome"
    source = chrome / "Profile 2"
    (source / "Cache").mkdir(parents=True)
    (source / "Cache" / "big").write_text("x")
    (source / "Network").mkdir()
    (source / "Network" / "Cookies").write_text("cookies")
    (source / "Network" / "Cache").mkdir()  # same name deeper down must be kept
    (chrome / "Local State").write_text(json.dumps({
        "os_crypt": {"k": 1},
        "profile": {"info_cache": {"Default": {"name": "Other"}, "Profile 2": {"name": "Me"}}},
    }))
    from app.models.database import Profile

    with service.session_factory() as session:
        session.add(Profile(name="Nguyen", profile_directory="Profile 2",
                            user_data_dir=str(chrome), imported=True, browser_binary=binary,
                            group_name="Team"))
        session.commit()
        imported_id = session.query(Profile).filter_by(name="Nguyen").one().id

    monkeypatch.setattr(ProfileService, "_chrome_running", staticmethod(lambda _: True))
    with pytest.raises(RuntimeError, match="đóng Google Chrome"):
        service.convert_to_own(imported_id, "Nguyen (riêng)")
    monkeypatch.setattr(ProfileService, "_chrome_running", staticmethod(lambda _: False))

    own = service.convert_to_own(imported_id, "Nguyen (riêng)")
    target = paths.profiles / own.id
    assert (target / "Default/Network/Cookies").read_text() == "cookies"
    assert (target / "Default/Network/Cache").is_dir()
    assert not (target / "Default/Cache").exists()
    state = json.loads((target / "Local State").read_text())
    assert state["os_crypt"] == {"k": 1}
    assert state["profile"]["info_cache"] == {"Default": {"name": "Me"}}
    assert not own.imported and own.remote_debugging and own.group_name == "Team"
    assert (source / "Cache/big").exists()  # original untouched
    with pytest.raises(ValueError, match="đã tồn tại"):
        service.convert_to_own(imported_id, "Nguyen (riêng)")
    with pytest.raises(ValueError, match="Chrome gốc"):
        service.convert_to_own(own.id, "x")
