import threading
from pathlib import Path
from typing import Dict, Tuple

from app.log import logger

from .hashing import resolve_source_path, sha1_file
from .models import FileChangedDuringHash, HashingCancelled, UnsafeSourcePath


LOG_PREFIX = "[qB 115 秒传]"


class TaskCoordinator:
    def __init__(self, repository, client_getter, retry_minutes_getter, stop_requested=None):
        self.repository = repository
        self.client_getter = client_getter
        self.retry_minutes_getter = retry_minutes_getter
        self.stop_requested = stop_requested or (lambda: False)
        self._run_lock = threading.Lock()

    def process_due(self) -> int:
        if not self._run_lock.acquire(blocking=False):
            return 0
        processed = 0
        try:
            for task in self.repository.due_tasks(limit=2):
                if not self.repository.claim(task["id"]):
                    continue
                processed += 1
                self._process_task(task["id"])
            return processed
        finally:
            self._run_lock.release()

    def _retry(self, task_id: int, code: str, message: str) -> None:
        if self.repository.schedule_retry(
            task_id,
            minutes=self.retry_minutes_getter(),
            code=code,
            message=message,
        ):
            logger.warning(f"{LOG_PREFIX} 秒传失败，将自动重试：{code} - {message}")

    def _process_task(self, task_id: int) -> None:
        task = self.repository.task(task_id)
        if not task:
            return
        files = self.repository.files(task_id)
        if not files:
            self._retry(task_id, "EMPTY_FILE_LIST", "qBittorrent 文件列表为空")
            return

        resolved: Dict[int, Tuple[dict, Path]] = {}
        for item in files:
            try:
                path = resolve_source_path(task["save_path"], item["relative_path"])
            except FileNotFoundError:
                self.repository.abandon_missing(task_id, item["relative_path"])
                logger.warning(f"{LOG_PREFIX} 原文件不存在，放弃秒传：{item['relative_path']}")
                return
            except UnsafeSourcePath as exc:
                self.repository.cancel(
                    task_id,
                    f"不安全的源路径：{exc}",
                    reason_code="UNSAFE_SOURCE_PATH",
                )
                logger.error(f"{LOG_PREFIX} 不安全的源路径，任务已取消：{exc}")
                return
            resolved[item["id"]] = (item, path)

        client = self.client_getter()
        if client is None:
            self._retry(task_id, "CONFIG_MISSING", "115 Cookie 未配置")
            return

        cancelled = lambda: self.stop_requested() or self.repository.is_cancel_requested(task_id)
        for item, path in resolved.values():
            if item["status"] == "SUCCESS":
                continue
            if cancelled():
                return
            try:
                stat = path.stat()
                cached = (
                    item.get("sha1")
                    and item.get("observed_size") == stat.st_size
                    and item.get("observed_mtime_ns") == stat.st_mtime_ns
                )
                if cached:
                    digest, size, mtime_ns = item["sha1"], stat.st_size, stat.st_mtime_ns
                else:
                    expected = item["expected_size"] if item["expected_size"] >= 0 else None
                    digest, size, mtime_ns = sha1_file(path, expected_size=expected, cancelled=cancelled)
                    self.repository.update_file_hash(item["id"], digest, size, mtime_ns)
                if cancelled():
                    return
                result = client.rapid_upload(
                    path=path,
                    file_name=path.name,
                    size=size,
                    sha1=digest,
                    target_cid=task["target_cid"],
                    remote_relative_dir=item.get("remote_relative_dir") or "",
                    cancelled=cancelled,
                )
                if not result.success:
                    if result.code != "CANCELLED":
                        self._retry(task_id, result.code, result.message)
                    return
                self.repository.mark_file_success(item["id"], result.remote_file_id)
                logger.info(f"{LOG_PREFIX} 文件秒传成功：{item['relative_path']}")
            except FileNotFoundError:
                self.repository.abandon_missing(task_id, item["relative_path"])
                return
            except HashingCancelled:
                return
            except FileChangedDuringHash as exc:
                self._retry(task_id, "FILE_CHANGED", str(exc))
                return
            except Exception as exc:
                self._retry(task_id, "INTERNAL_ERROR", str(exc) or exc.__class__.__name__)
                return

        if self.repository.mark_success(task_id):
            logger.info(f"{LOG_PREFIX} 下载任务全部文件秒传成功：{task['download_hash'][:12]}")
