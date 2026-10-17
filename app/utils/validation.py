import json
import shlex
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator


class ProfileInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    browser_type: str = "Google Chrome"
    browser_binary: str
    color: str = "#4285F4"
    notes: str = ""
    tags: str = ""
    purpose: str = ""
    group_name: str = ""
    pinned: bool = False
    proxy_enabled: bool = False
    proxy_scheme: str = "http"
    proxy_host: str = ""
    proxy_port: int | None = Field(default=None, ge=1, le=65535)
    startup_urls: list[str] = Field(default_factory=list)
    extra_arguments: str = ""
    remote_debugging: bool = False
    channel_url: str = ""
    automation_config: str = ""

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Tên profile không được để trống")
        return value

    @field_validator("startup_urls")
    @classmethod
    def valid_urls(cls, values: list[str]) -> list[str]:
        for value in values:
            parsed = urlparse(value.strip())
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"URL không hợp lệ: {value}")
        return [value.strip() for value in values if value.strip()]

    @field_validator("extra_arguments")
    @classmethod
    def safe_arguments(cls, value: str) -> str:
        args = shlex.split(value)
        if any(arg == "--user-data-dir" or arg.startswith("--user-data-dir=") for arg in args):
            raise ValueError("Không được ghi đè --user-data-dir")
        if any(
            arg == "--profile-directory" or arg.startswith("--profile-directory=") for arg in args
        ):
            raise ValueError("Không được ghi đè --profile-directory")
        return value

    @field_validator("channel_url")
    @classmethod
    def valid_channel_url(cls, value: str) -> str:
        value = value.strip()
        if value and urlparse(value).scheme != "https":
            raise ValueError("Link kênh/Studio phải bắt đầu bằng https://")
        return value

    @field_validator("automation_config")
    @classmethod
    def valid_automation_config(cls, value: str) -> str:
        value = value.strip()
        if value and not isinstance(json.loads(value), dict):
            raise ValueError("Cấu hình tự động phải là JSON object, ví dụ {\"maxVideos\": 5}")
        return value

    @model_validator(mode="after")
    def proxy_consistency(self):
        if self.proxy_enabled and (not self.proxy_host or self.proxy_port is None):
            raise ValueError("Proxy cần host và port")
        return self


def validate_binary(path: str) -> Path:
    binary = Path(path).expanduser().resolve()
    if not binary.is_file() or not binary.stat().st_mode & 0o111:
        raise ValueError("Đường dẫn trình duyệt không tồn tại hoặc không có quyền thực thi")
    return binary
