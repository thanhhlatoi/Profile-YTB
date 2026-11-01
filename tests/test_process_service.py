import os
from types import SimpleNamespace

from app.config import AppPaths
from app.constants import ProfileStatus
from app.models.database import Profile, create_session_factory
from app.services.chrome_process_service import ChromeProcessService
from app.services.profile_service import ProfileService
from app.utils.validation import ProfileInput


class FakeProcess:
    pid = 1234

    def poll(self):
        return None


def test_build_command_and_no_shell(tmp_path):
    paths = AppPaths.create(tmp_path / "data")
    factory = create_session_factory(paths.db_url)
    service = ChromeProcessService(
        paths, factory, process_factory=lambda command, shell, start_new_session: FakeProcess()
    )
    profile = SimpleNamespace(
        id="abc",
        profile_directory="Default",
        user_data_dir=None,
        browser_binary="/usr/bin/chromium",
        proxy_enabled=False,
        extra_arguments="--incognito",
        startup_urls="https://example.com",
    )
    command = service.build_command(profile)
    assert command[0] == "/usr/bin/chromium"
    assert "--user-data-dir=" in command[1]
    assert "--profile-directory=Default" in command
    assert "https://example.com" in command


def test_app_started_browser_stays_running_when_command_line_differs(tmp_path):
    paths = AppPaths.create(tmp_path / "data")
    factory = create_session_factory(paths.db_url)
    binary = tmp_path / ("chrome.exe" if os.name == "nt" else "chrome")
    binary.write_text("x")
    binary.chmod(binary.stat().st_mode | 0o111)
    profile = ProfileService(paths, factory).create(
        ProfileInput(name="A", browser_binary=str(binary))
    )
    service = ChromeProcessService(
        paths, factory, process_factory=lambda command, shell, start_new_session: FakeProcess()
    )
    service.open(profile.id)
    service.discover()  # No process on this machine carries the profile's arguments.
    with factory() as session:
        stored = session.get(Profile, profile.id)
        assert stored.status == ProfileStatus.RUNNING and stored.pid == 1234


def test_profile_1_does_not_match_profile_10(tmp_path):
    paths = AppPaths.create(tmp_path / "data")
    service = ChromeProcessService(paths, create_session_factory(paths.db_url))
    profile = SimpleNamespace(id="x", user_data_dir="/u", profile_directory="Profile 1")
    other = SimpleNamespace(
        cmdline=lambda: ["chrome", "--user-data-dir=/u", "--profile-directory=Profile 10"]
    )
    own = SimpleNamespace(
        cmdline=lambda: ["chrome", "--user-data-dir=/u", "--profile-directory=Profile 1"]
    )
    assert not service._belongs_to(other, profile)
    assert service._belongs_to(own, profile)
