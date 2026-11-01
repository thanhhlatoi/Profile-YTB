import pytest

from app.config import AppPaths
from app.services.controller import Controller
from app.services.download_service import (
    DownloadError,
    DownloadService,
    parse_folder,
    parse_range,
    resolve_root,
)

CFG = {
    "ytdlp": "yt-dlp", "cookies": "c.txt", "ffmpeg_dir": "ff", "pot_home": "pot",
    "out_root": "out", "archive": "arc.txt",
}


@pytest.fixture
def service(tmp_path):
    return DownloadService(AppPaths.create(tmp_path / "data"))


def test_rejects_bad_input(service):
    for url in ("http://youtube.com/watch?v=1", "https://evil.com/watch?v=1", "x; rm -rf /"):
        with pytest.raises(DownloadError):
            service.start(url)
    with pytest.raises(DownloadError):
        service.start("https://youtu.be/abc", sub_lang="en;calc")
    with pytest.raises(DownloadError):
        parse_range("5-2")
    assert parse_range("1-3") == (1, 3)
    assert parse_range(None) is None


def test_missing_tools_reported(service):
    with pytest.raises(DownloadError, match="Chưa có"):
        service.start("https://youtu.be/abc")


def test_build_args_channel_and_single(service):
    args = service.build_args("https://www.youtube.com/@abc", "vi", (1, 3), CFG, True, "l.txt")
    assert args[0] == "https://www.youtube.com/@abc/videos"
    assert args[args.index("--playlist-end") + 1] == "3"
    assert "--no-playlist" not in args
    single = service.build_args("https://youtu.be/abc", "en", (1, 3), CFG, False, "l.txt")
    assert "--no-playlist" in single and "--playlist-start" not in single
    assert single[single.index("--sleep-interval") + 1] == "2"


def test_organize_sorts_by_extension(service, tmp_path):
    folder = tmp_path / "chan"
    folder.mkdir()
    for name in ("a.mp4", "a.jpg", "a.en.srt", "notes.txt"):
        (folder / name).write_text("x")
    service.organize(folder)
    assert (folder / "Nguon" / "a.mp4").exists()
    assert (folder / "Thumnail" / "a.jpg").exists()
    assert (folder / "Sub" / "a.en.srt").exists()
    assert (folder / "notes.txt").exists()


def test_controller_download_disabled_without_service():
    controller = Controller(None, None, None)
    with pytest.raises(ValueError, match="chưa được bật"):
        controller.handle("download", {"url": "https://youtu.be/abc"}, agent=True)


def test_folder_must_be_a_single_safe_name():
    assert parse_folder(None) is None
    assert parse_folder("Drama 2026") == "Drama 2026"
    assert parse_folder("Tiếng Việt-1") == "Tiếng Việt-1"
    for bad in ("..", "../x", "a/b", "a\\b", "C:\\Windows", ".hidden", "x" * 51):
        with pytest.raises(DownloadError):
            parse_folder(bad)


def test_build_args_uses_folder(service):
    args = service.build_args("https://youtu.be/abc", "en", None, CFG, True, "l.txt", "Drama")
    output = args[args.index("-o") + 1].replace("\\", "/")
    assert output.startswith("out/Drama/%(channel)s/")
    plain = service.build_args("https://youtu.be/abc", "en", None, CFG, True, "l.txt")
    assert plain[plain.index("-o") + 1].replace("\\", "/").startswith("out/%(channel)s/")


def test_batch_validates_all_before_starting(service, tmp_path, monkeypatch):
    tools = tmp_path / "t"
    tools.mkdir()
    (tools / "y.exe").write_text("x")
    (tools / "c.txt").write_text("x")
    cfg = {**CFG, "ytdlp": str(tools / "y.exe"), "cookies": str(tools / "c.txt")}
    monkeypatch.setattr(service, "config", lambda: cfg)
    monkeypatch.setattr(
        service, "_launch", lambda job, cfg, rng: service.jobs.update({job["job_id"]: job})
    )
    with pytest.raises(DownloadError):
        service.start_batch(["https://youtu.be/a", "https://evil.com/x"])
    assert not service.jobs
    with pytest.raises(DownloadError):
        service.start_batch([])
    with pytest.raises(DownloadError):
        service.start_batch([f"https://youtu.be/{i}" for i in range(21)])
    result = service.start_batch(
        "https://youtu.be/a, https://youtu.be/b https://youtu.be/a", folder="Drama"
    )
    assert len(result["jobs"]) == 2
    assert all(j["folder"] == "Drama" for j in service.jobs.values())


def test_cancelled_queued_job_finishes(service):
    job = {"job_id": "x", "status": "CANCELLED", "finished": False}
    service._run(job, CFG, None)
    assert job["finished"] is True


def test_drive_only_from_allowed_list():
    cfg = {**CFG, "roots": {"E": "E:\\YouTube", "f:": "F:\\YouTube"}}
    assert resolve_root(None, cfg) == "out"
    assert resolve_root("default", cfg) == "out"
    assert resolve_root("E", cfg) == "E:\\YouTube"
    assert resolve_root("e:", cfg) == "E:\\YouTube"
    assert resolve_root("ổ F", cfg) == "F:\\YouTube"
    for bad in ("Z", "C:\\Windows", "E:\\..", "../x"):
        with pytest.raises(DownloadError):
            resolve_root(bad, cfg)


def test_build_args_uses_root_and_folder(service):
    args = service.build_args(
        "https://youtu.be/abc", "en", None, CFG, True, "l.txt", "Drama", "E:/YouTube"
    )
    output = args[args.index("-o") + 1].replace("\\", "/")
    assert output.startswith("E:/YouTube/Drama/%(channel)s/")


def test_filenames_start_with_stt(service):
    chan = service.build_args("https://www.youtube.com/@abc", "en", (3, 7), CFG, True, "l.txt")
    assert chan[chan.index("-o") + 1].endswith("%(playlist_index)03d %(title).100s.%(ext)s")
    one = service.build_args("https://youtu.be/abc", "en", None, CFG, True, "l.txt")
    assert "playlist_index" not in one[one.index("-o") + 1]


def test_parallel_limit_clamped(service):
    assert service._parallel({}) == 2
    assert service._parallel({"parallel": 99}) == 4
    assert service._parallel({"parallel": 0}) == 1
    assert service._parallel({"parallel": "x"}) == 2
