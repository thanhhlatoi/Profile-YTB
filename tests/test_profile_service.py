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
    binary = tmp_path / ("chrome.exe" if os.name == "nt" else "chrome")
    binary.write_text("x")
    binary.chmod(os.stat(binary).st_mode | 0o111)
    return paths, service, str(binary)


def test_delete_wipes_own_profile_and_its_tasks(tmp_path):
    from app.models.database import Task, TaskRun

    paths, service, binary = setup(tmp_path)
    profile = service.create(ProfileInput(name="A", browser_binary=binary))
    data_dir = paths.profiles / profile.id
    (data_dir / "Default").mkdir()
    readonly = data_dir / "Default" / "Cookies"
    readonly.write_text("x")
    readonly.chmod(0o444)
    with service.session_factory() as session:
        session.add(Task(id="t1", name="T", profile_id=profile.id, action_type="open"))
        session.add(TaskRun(task_id="t1", profile_id=profile.id))
        session.commit()

    assert service.delete(profile.id) == ["t1"]
    assert not data_dir.exists()
    assert service.list(include_deleted=True) == []
    with service.session_factory() as session:
        assert session.query(Task).count() == 0
        assert session.query(TaskRun).count() == 0
    service.create(ProfileInput(name="A", browser_binary=binary))  # Name is free again.


def test_delete_imported_profile_removes_folder_and_chrome_entry(tmp_path, monkeypatch):
    from app.models.database import Profile

    paths, service, binary = setup(tmp_path)
    monkeypatch.setattr(ProfileService, "_dir_in_use", staticmethod(lambda *_a, **_k: False))
    user_data_dir = tmp_path / "chrome-user-data"
    chrome_profile = user_data_dir / "Profile 1"
    chrome_profile.mkdir(parents=True)
    (chrome_profile / "Preferences").write_text("{}")
    (user_data_dir / "Local State").write_text(json.dumps({"profile": {
        "info_cache": {"Default": {}, "Profile 1": {}},
        "last_used": "Profile 1",
        "last_active_profiles": ["Profile 1", "Default"],
        "profiles_order": ["Default", "Profile 1"],
    }}))
    with service.session_factory() as session:
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
    assert (user_data_dir / "Default").exists() is False  # Untouched siblings stay as they were.
    state = json.loads((user_data_dir / "Local State").read_text())["profile"]
    assert list(state["info_cache"]) == ["Default"]
    assert state["last_used"] == "Default"
    assert state["last_active_profiles"] == ["Default"]
    assert state["profiles_order"] == ["Default"]
    assert service.list(include_deleted=True) == []


def test_delete_imported_refused_while_chrome_runs(tmp_path, monkeypatch):
    from app.models.database import Profile

    paths, service, binary = setup(tmp_path)
    monkeypatch.setattr(ProfileService, "_dir_in_use", staticmethod(lambda *_a, **_k: True))
    user_data_dir = tmp_path / "chrome-user-data"
    (user_data_dir / "Profile 1").mkdir(parents=True)
    with service.session_factory() as session:
        profile = Profile(name="I", profile_directory="Profile 1", user_data_dir=str(user_data_dir),
                          imported=True, browser_binary=binary)
        session.add(profile)
        session.commit()
        profile_id = profile.id
    with pytest.raises(ValueError):
        service.delete(profile_id)
    assert (user_data_dir / "Profile 1").exists()


def test_purge_trash_finishes_old_soft_deletes(tmp_path):
    paths, service, binary = setup(tmp_path)
    profile = service.create(ProfileInput(name="Old", browser_binary=binary))
    (paths.profiles / profile.id).rename(paths.trash / profile.id)
    with service.session_factory() as session:
        from app.models.database import Profile

        session.get(Profile, profile.id).deleted = True
        session.commit()
    service.purge_trash()
    assert not (paths.trash / profile.id).exists()
    assert service.list(include_deleted=True) == []


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
