from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TaskStatus(str, Enum):
    WATCHING = "WATCHING"
    WAITING = "WAITING"
    PROCESSING = "PROCESSING"
    RETRY_WAIT = "RETRY_WAIT"
    SUCCESS = "SUCCESS"
    ABANDONED_ORGANIZED = "ABANDONED_ORGANIZED"
    ABANDONED_SOURCE_MISSING = "ABANDONED_SOURCE_MISSING"
    CANCELLED = "CANCELLED"


class FileStatus(str, Enum):
    WAITING = "WAITING"
    SUCCESS = "SUCCESS"


TERMINAL_TASK_STATUSES = {
    TaskStatus.SUCCESS.value,
    TaskStatus.ABANDONED_ORGANIZED.value,
    TaskStatus.ABANDONED_SOURCE_MISSING.value,
    TaskStatus.CANCELLED.value,
}


@dataclass(frozen=True)
class FileSnapshot:
    relative_path: str
    absolute_path: str
    remote_relative_dir: str
    expected_size: int


@dataclass(frozen=True)
class RapidUploadResult:
    success: bool
    code: str
    message: str
    remote_file_id: Optional[str] = None


class HashingCancelled(RuntimeError):
    pass


class FileChangedDuringHash(RuntimeError):
    pass


class UnsafeSourcePath(RuntimeError):
    pass
