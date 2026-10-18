import os

from app.config import AppPaths
from app.models.database import create_session_factory
from app.services.profile_service import ProfileService
from app.services.task_service import TaskService
from app.utils.validation import ProfileInput


def test_task_run(tmp_path):
    paths = AppPaths.create(tmp_path / "data")
    factory = create_session_factory(paths.db_url)
    binary = tmp_path / ("chrome.exe" if os.name == "nt" else "chrome")
    binary.write_text("x")
    binary.chmod(os.stat(binary).st_mode | 0o111)
    profiles = ProfileService(paths, factory)
    profile = profiles.create(ProfileInput(name="A", browser_binary=str(binary)))

    class Process:
        def open(self, *_):
            return 1

    tasks = TaskService(factory, Process())
    task = tasks.create(name="Open", profile_id=profile.id, action_type="OPEN", payload="{}")
    tasks.run(task.id)
    assert tasks.list()[0].status == "SUCCESS"
