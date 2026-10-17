import os

import pytest

from app.utils.validation import ProfileInput


def valid_binary(tmp_path):
    binary = tmp_path / "chrome"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(os.stat(binary).st_mode | 0o111)
    return str(binary)


def test_validate_urls_and_proxy(tmp_path):
    data = ProfileInput(
        name="A", browser_binary=valid_binary(tmp_path), startup_urls=["https://example.com"]
    )
    assert data.startup_urls == ["https://example.com"]
    with pytest.raises(ValueError):
        ProfileInput(name="A", browser_binary=valid_binary(tmp_path), startup_urls=["bad"])
    with pytest.raises(ValueError):
        ProfileInput(name="A", browser_binary=valid_binary(tmp_path), proxy_enabled=True)


def test_reject_unsafe_arguments(tmp_path):
    with pytest.raises(ValueError):
        ProfileInput(
            name="A",
            browser_binary=valid_binary(tmp_path),
            extra_arguments="--user-data-dir=/tmp/x",
        )
