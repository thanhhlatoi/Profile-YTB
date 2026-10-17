import json
import os
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app import cli
from app.config import AppPaths
from app.models.database import Profile, create_session_factory
from app.services.chrome_process_service import ChromeProcessService
from app.services.profile_service import ProfileService
from app.services.scheduler_service import SchedulerService
from app.services.studio_publisher import StudioPublisher, find_thumbnails
from app.services.task_service import TaskService
from app.utils.validation import ProfileInput


class FakeProcess:
    pid = 4321

    def poll(self):
        return None


def setup(tmp_path):
    paths = AppPaths.create(tmp_path / "data")
    factory = create_session_factory(paths.db_url)
    binary = tmp_path / "chrome"
    binary.write_text("x")
    binary.chmod(os.stat(binary).st_mode | 0o111)
    return paths, factory, ProfileService(paths, factory), str(binary)


def test_group_task_retries_and_records_history(tmp_path):
    paths, factory, profiles, binary = setup(tmp_path)
    for name in ("A", "B"):
        profiles.create(ProfileInput(name=name, browser_binary=binary, group_name="Team"))
    calls = []

    class Process:
        def open(self, profile_id, *_):
            calls.append(profile_id)
            if calls.count(profile_id) == 1 and len(calls) == 2:
                raise OSError("flaky")

    tasks = TaskService(factory, Process(), retry_delay=0)
    task = tasks.create(
        name="Open team", profile_id=None, target_group="Team", action_type="OPEN",
        payload="{}", max_retries=1,
    )
    tasks.run(task.id)
    assert tasks.get(task.id).status == "SUCCESS"
    runs = {run.profile_name: run for run in tasks.history(task.id)}
    assert runs["A"].attempts == 1 and runs["B"].attempts == 2
    assert all(run.status == "SUCCESS" for run in runs.values())


def test_failed_task_reports_profile_name(tmp_path):
    _, factory, profiles, binary = setup(tmp_path)
    profile = profiles.create(ProfileInput(name="Solo", browser_binary=binary))

    class Process:
        def open(self, *_):
            raise OSError("no chrome")

    tasks = TaskService(factory, Process(), retry_delay=0)
    task = tasks.create(name="Open", profile_id=profile.id, action_type="OPEN", payload="{}")
    with pytest.raises(RuntimeError):
        tasks.run(task.id)
    assert "Solo: no chrome" in tasks.get(task.id).last_error
    assert tasks.history(task.id)[0].status == "FAILED"


def test_scheduler_respects_enabled_and_unschedule(tmp_path):
    scheduler = SchedulerService(task_service=None)
    scheduler.start()
    try:
        daily = SimpleNamespace(
            id="d", enabled=True, schedule_type="daily",
            scheduled_at=datetime.now() - timedelta(days=3), interval_minutes=None,
        )
        scheduler.schedule(daily)
        assert scheduler.next_run("d") is not None  # past start time still repeats daily
        scheduler.unschedule("d")
        assert scheduler.next_run("d") is None
        daily.enabled = False
        scheduler.schedule(daily)
        assert scheduler.next_run("d") is None
        past = SimpleNamespace(
            id="o", enabled=True, schedule_type="once",
            scheduled_at=datetime.now() - timedelta(minutes=1), interval_minutes=None,
        )
        scheduler.schedule(past)
        assert scheduler.next_run("o") is None
    finally:
        scheduler.stop()


def test_cdp_port_only_for_own_profiles(tmp_path):
    paths, factory, profiles, binary = setup(tmp_path)
    commands = []
    process = ChromeProcessService(
        paths, factory, process_factory=lambda cmd, **_: commands.append(cmd) or FakeProcess()
    )
    own = profiles.create(ProfileInput(name="Own", browser_binary=binary, remote_debugging=True))
    process.open(own.id)
    port = profiles.list()[0].debug_port
    assert port and f"--remote-debugging-port={port}" in commands[0]


def test_find_thumbnails_matches_popup_rule(tmp_path):
    (tmp_path / "sub").mkdir()
    for name in ("12_title.jpg", "3 - ok.PNG", "sub/7-x.jpeg", "90-Millionen.txt", "5.jpg",
                 "8_a.jpg", "8_b.png", "100abc.jpg"):
        (tmp_path / name).write_bytes(b"x")
    thumbs, duplicates = find_thumbnails(tmp_path)
    assert sorted(thumbs) == ["12", "3", "7"]
    assert duplicates == ["#8 bị trùng: 8_a.jpg | 8_b.png"]


def test_publisher_refuses_imported_and_enables_cdp(tmp_path):
    paths, factory, profiles, binary = setup(tmp_path)
    own = profiles.create(ProfileInput(name="Own", browser_binary=binary))
    with factory() as session:
        session.add(Profile(name="Gốc", profile_directory="Default", user_data_dir="/u",
                            imported=True, browser_binary=binary))
        session.commit()
        imported = session.query(Profile).filter_by(name="Gốc").one().id
    publisher = StudioPublisher(ChromeProcessService(paths, factory))
    with pytest.raises(RuntimeError, match="Chrome gốc"):
        publisher._load_profile(imported)
    assert publisher._load_profile(own.id).remote_debugging is True


def test_summary_fails_when_any_video_failed():
    publisher = StudioPublisher(process_service=None)
    status = {"state": "DONE", "success": 2, "totalVideos": 3, "logs": [
        {"status": "SUCCESS", "index": 1}, {"status": "ERROR", "index": 2, "reason": "x"},
        {"status": "SUCCESS", "index": 3},
    ]}
    with pytest.raises(RuntimeError, match="lỗi 1"):
        publisher._summarize(status, [], port=1, target_id="t")
    ok = {"state": "DONE", "success": 1, "totalVideos": 2,
          "logs": [{"status": "SKIPPED", "index": 4, "reason": "Thiếu thumbnail"}]}
    publisher._http = lambda *a, **k: None
    assert publisher._summarize(ok, ["Thiếu thumbnail cho #4"], 1, "t").startswith(
        "Xong 1/2 video, bỏ qua 1"
    )


def test_automation_config_must_be_json_object(tmp_path):
    with pytest.raises(ValueError):
        ProfileInput(name="x", browser_binary="/bin/sh", automation_config="[1]")
    assert ProfileInput(name="x", browser_binary="/bin/sh", automation_config='{"a": 1}')


def test_cli_list_and_open_group(tmp_path, monkeypatch, capsys):
    paths, factory, profiles, binary = setup(tmp_path)
    profiles.create(ProfileInput(name="A", browser_binary=binary, group_name="Team"))
    monkeypatch.setattr(cli.AppPaths, "create", lambda: paths)
    opened = []
    monkeypatch.setattr(
        ChromeProcessService, "open", lambda self, profile_id, urls=None: opened.append(profile_id)
    )
    assert cli.main(["list"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["name"] == "A"
    assert cli.main(["open", "--group", "Team"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] == ["A"]
    assert len(opened) == 1
    assert cli.main(["open", "Missing"]) == 1
    assert "Không tìm thấy profile" in json.loads(capsys.readouterr().out)["error"]
