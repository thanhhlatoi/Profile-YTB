from enum import Enum


class StrEnum(str, Enum):
    """String-valued enum compatible with Python 3.10 and newer."""

    def __str__(self) -> str:
        return self.value


class ProfileStatus(StrEnum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    ERROR = "ERROR"


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    DISABLED = "DISABLED"


class ActionType(StrEnum):
    OPEN = "OPEN"
    CLOSE = "CLOSE"
    RESTART = "RESTART"
    OPEN_URL = "OPEN_URL"
    OPEN_URLS = "OPEN_URLS"
    STOP_AFTER = "STOP_AFTER"
    PUBLISH_YOUTUBE = "PUBLISH_YOUTUBE"
