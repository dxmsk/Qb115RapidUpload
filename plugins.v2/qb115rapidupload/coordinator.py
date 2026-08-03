import threading
from pathlib import Path
from typing import Dict, Optional, Tuple

from app.log import logger

from .hashing import resolve_snapshot_path, sha1_file
from .models import FileChangedDuringHash, HashingCancelled, UnsafeSourcePath


LOG_PREFIX = "[qB 115 秒传]"


class TaskCoordinator:
    SOURCE_MISSING_RECHECK_SECONDS = 5

    def __init__(
        self,
        repository,
        client_getter,
        retry_minutes_getter,
        stop_requested=None,
        success_callback=None,
        failure_callback=None,
        path_mapper=None,
    ):
        self.repository = repository
        self.client_getter = client_getter
        self.retry_minutes_getter = retry_minutes_getter
        self.stop_requested = stop_requested or (lambda: False)
        self.success_callback = success_callback or (lambda _download_hash: None)
        self.failure_callback = failure_callback or (
            lambda _task_id, _code, _message: None
        )
        self.path_mapper = path_mapper or (lambda value: str(value or ""))
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

    def recover_source_paths(self, organized_checker=None) -> int:
        """Recover tasks falsely abandoned by an older path-join strategy."""
        recovered = 0
        for task in self.repository.source_missing_tasks():
            if organized_checker:
                try:
                    if organized_checker(task["download_hash"]):
                        continue
                except Exception:
                    pass
            resolved_paths = {}
            try:
                files = self.repository.files(task["id"])
                if not files:
                    continue
                for item in files:
                    path = resolve_snapshot_path(
                        save_path=self.path_mapper(task["save_path"]),
                        content_path=self.path_mapper(task.get("content_path") or ""),
                        relative_path=item["relative_path"],
                        absolute_path=self.path_mapper(item.get("absolute_path") or ""),
                    )
                    resolved_paths[int(item["id"])] = str(path)
            except (FileNotFoundError, UnsafeSourcePath, OSError):
                continue
            if self.repository.recover_source_missing(task["id"], resolved_paths):
                recovered += 1
        return recovered

    def _retry(self, task_id: int, code: str, message: str) -> None:
        if self.repository.schedule_retry(
            task_id,
            minutes=self.retry_minutes_getter(),
            code=code,
            message=message,
        ):
            log_message = f"{LOG_PREFIX} 秒传失败，将自动重试：{code} - {message}"
            if code == "NOT_REUSABLE":
                logger.info(log_message)
            else:
                logger.warning(log_message)
            try:
                self.failure_callback(task_id, code, message)
            except Exception as exc:
                logger.warning(f"{LOG_PREFIX} 秒传失败后触发自动整理失败：{exc}")

    def _handle_missing(self, task_id: int, relative_path: str, exc: Optional[Exception] = None) -> None:
        task = self.repository.task(task_id) or {}
        if str(task.get("last_error_code") or "") == "SOURCE_MISSING_RECHECK":
            self.repository.abandon_missing(task_id, relative_path)
            detail = f" - {exc}" if exc else ""
            logger.warning(
                f"{LOG_PREFIX} 连续两次未找到原文件，放弃秒传：{relative_path}{detail}"
            )
            return
        message = f"首次未找到原文件，{self.SOURCE_MISSING_RECHECK_SECONDS} 秒后复核：{relative_path}"
        if self.repository.schedule_retry_seconds(
            task_id,
            seconds=self.SOURCE_MISSING_RECHECK_SECONDS,
            code="SOURCE_MISSING_RECHECK",
            message=message,
        ):
            detail = f" - {exc}" if exc else ""
            logger.info(f"{LOG_PREFIX} {message}{detail}")

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
                path = resolve_snapshot_path(
                    save_path=self.path_mapper(task["save_path"]),
                    content_path=self.path_mapper(task.get("content_path") or ""),
                    relative_path=item["relative_path"],
                    absolute_path=self.path_mapper(item.get("absolute_path") or ""),
                )
            except FileNotFoundError as exc:
                self._handle_missing(task_id, item["relative_path"], exc)
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
                self._handle_missing(task_id, item["relative_path"])
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
            try:
                self.success_callback(task["download_hash"])
            except Exception as exc:
                logger.warning(f"{LOG_PREFIX} 通知自动整理插件取消队列失败：{exc}")
