import asyncio
import json
import os

import pytest

from app import mcp_server
from app.config import AppPaths
from app.models.database import create_session_factory
from app.services import control_server
from app.services.chrome_process_service import ChromeProcessService
from app.services.controller import Controller
from app.services.profile_service import ProfileService
from app.services.task_service import TaskService
from app.utils.validation import ProfileInput


class FakePublisher:
    def __init__(self):
        self.progress, self.calls, self.stopped = {}, [], []

    def publish(self, profile_id, config):
        self.calls.append((profile_id, config))
        return "Xong 2/2 video"

    def request_stop(self, profile_id):
        self.stopped.append(profile_id)

    def preview(self, profile_id):
        return {"draft_count": 2}


@pytest.fixture
def controller(tmp_path):
    paths = AppPaths.create(tmp_path / "data")
    factory = create_session_factory(paths.db_url)
    binary = tmp_path / ("chrome.exe" if os.name == "nt" else "chrome")
    binary.write_text("x")
    binary.chmod(os.stat(binary).st_mode | 0o111)
    profiles = ProfileService(paths, factory)
    for name, config in (("A", '{"visibility": "private"}'), ("B", "")):
        profiles.create(ProfileInput(name=name, browser_binary=str(binary), group_name="Team",
                                     automation_config=config))
    process = ChromeProcessService(paths, factory)
    tasks = TaskService(factory, process, publisher=FakePublisher(), retry_delay=0)
    settings = paths.config / "settings.json"
    return Controller(profiles, process, tasks, settings_path=settings), settings


def test_publish_creates_task_runs_and_reports_status(controller):
    ctl, _ = controller
    result = ctl.handle("publish", {"group": "Team", "max_videos": 3})
    assert result["status"] == "SUCCESS" and result["finished"]
    assert [r["result"] for r in result["runs"]] == ["Xong 2/2 video"] * 2
    assert ctl.tasks.publisher.calls[0][1] == {"maxVideos": 3}
    assert ctl.handle("list_tasks")[0]["target"] == "group:Team"
    task_id = result["task_id"]
    ctl.handle("stop", {"task": task_id})
    assert len(ctl.tasks.publisher.stopped) == 2


def test_agent_policy_caps_videos_and_blocks_visibility(controller):
    ctl, settings = controller
    settings.write_text(json.dumps({"agent": {"allowed_visibility": ["private", "unlisted"],
                                              "max_videos": 5}}))
    ctl.handle("publish", {"profile": "A", "max_videos": 50}, agent=True)
    assert ctl.tasks.publisher.calls[-1][1] == {"maxVideos": 5}
    with pytest.raises(PermissionError, match="public"):
        ctl.handle("publish", {"profile": "B"}, agent=True)  # B defaults to public
    with pytest.raises(PermissionError):
        ctl.handle("publish", {"profile": "A", "visibility": "public"}, agent=True)
    # The user (not the agent) is not limited.
    ctl.handle("publish", {"profile": "B", "visibility": "public"})


def test_socket_round_trip_and_mcp_tool(controller, tmp_path, monkeypatch):
    ctl, _ = controller
    path = tmp_path / "c.sock"
    server = control_server.ControlServer(path, ctl)
    server.start()
    try:
        if os.name != "nt":  # Windows has no Unix permission bits.
            assert oct(path.stat().st_mode & 0o777) == "0o600"
        names = [p["name"] for p in control_server.call(path, "list_profiles")]
        assert names == ["A", "B"]
        with pytest.raises(control_server.ControlError, match="Không tìm thấy profile"):
            control_server.call(path, "check", {"profile": "Nope"})
        monkeypatch.setattr(mcp_server, "SOCKET", path)
        result = asyncio.run(mcp_server.server.call_tool("check_channel", {"profile": "A"}))
        assert "draft_count" in json.dumps(result, default=str)
    finally:
        server.stop()
    assert not control_server.available(path)
    with pytest.raises(control_server.ControlError, match="mở ứng dụng"):
        control_server.call(path, "list_profiles")


def test_unknown_command_rejected(controller):
    ctl, _ = controller
    with pytest.raises(ValueError, match="không hỗ trợ"):
        ctl.handle("delete_everything")
