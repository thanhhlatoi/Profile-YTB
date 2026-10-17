import json

from app.services.chrome_profile_discovery import discover_chrome_profiles


def test_discovers_local_state_and_directories(tmp_path):
    data_dir = tmp_path / ".config/google-chrome"
    (data_dir / "Default").mkdir(parents=True)
    (data_dir / "Profile 1").mkdir()
    (data_dir / "Local State").write_text(
        json.dumps(
            {
                "profile": {
                    "info_cache": {
                        "Default": {"name": "Main"},
                        "Profile 1": {"name": "Work"},
                    }
                }
            }
        )
    )

    profiles = discover_chrome_profiles(tmp_path)

    assert [(item["name"], item["profile_directory"]) for item in profiles] == [
        ("Main", "Default"),
        ("Work", "Profile 1"),
    ]
