from types import SimpleNamespace

from app.config import AppPaths
from app.models.database import create_session_factory
from app.services.chrome_process_service import ChromeProcessService


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
