"""MoviePilot transfer-queue integration for the unified qB/115 plugin."""

import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from app.log import logger


LOG_PREFIX = "[qB 115 秒传]"


class OrganizerCoordinator:
    """Submit only the rapid-upload failures to MoviePilot's transfer chain.

    The class deliberately owns no qB polling.  CompletionDetector is the
    single source of completed-torrent observations, which prevents the race
    where a separate organizer moves a file before SHA1 hashing starts.
    """

    def __init__(
        self,
        repository,
        enabled_getter: Callable[[], bool],
        force_getter: Callable[[], bool],
        stop_requested: Callable[[], bool],
    ):
        self.repository = repository
        self.enabled_getter = enabled_getter
        self.force_getter = force_getter
        self.stop_requested = stop_requested

    @staticmethod
    def _resolve_downloader_source(download_hash: str, fallback: str) -> str:
        try:
            from app.db.downloadhistory_oper import DownloadHistoryOper

            history = DownloadHistoryOper().get_by_hash(download_hash)
            downloader = getattr(history, "downloader", None) if history else None
            if downloader:
                return str(downloader)
        except Exception:
            pass
        return str(fallback or "qbittorrent")

    @staticmethod
    def _source_path(task: Dict[str, Any]) -> str:
        content = str(task.get("content_path") or "").strip()
        if content and Path(content).exists():
            return content

        files = []
        try:
            files = list(task.get("files") or [])
        except Exception:
            files = []
        if len(files) == 1:
            candidate = str(files[0].get("absolute_path") or "").strip()
            if candidate:
                return candidate

        candidates = [
            str(item.get("absolute_path") or "")
            for item in files
            if str(item.get("absolute_path") or "")
        ]
        if candidates:
            try:
                common = Path(os.path.commonpath(candidates))
                return str(common if common.is_dir() else common.parent)
            except Exception:
                pass
        return str(task.get("save_path") or "").strip()

    @staticmethod
    def _fileitem(path_text: str, size: int = 0):
        from app.schemas import FileItem

        path = Path(path_text)
        is_file = path.is_file()
        normalized = path.as_posix()
        if not is_file and not normalized.endswith("/"):
            normalized += "/"
        try:
            actual_size = path.stat().st_size if is_file else int(size or 0)
        except OSError:
            actual_size = int(size or 0)
        return FileItem(
            storage="local",
            path=normalized,
            type="file" if is_file else "dir",
            name=path.name,
            basename=path.stem,
            extension=path.suffix.lstrip(".") if is_file else "",
            size=actual_size,
        )

    @classmethod
    def remove_from_queue(cls, source_path: str) -> bool:
        if not source_path:
            return False
        try:
            from app.chain.transfer import TransferChain

            item = cls._fileitem(source_path)
            TransferChain().remove_from_queue(item)
            return True
        except Exception as exc:
            logger.debug(f"{LOG_PREFIX} 移除整理队列失败：{exc}")
            return False

    def enqueue_task(self, task_id: int) -> bool:
        if not self.enabled_getter() or self.stop_requested():
            return False
        task = self.repository.task(task_id)
        if not task or task.get("status") != "RETRY_WAIT":
            return False
        source_path = self._source_path({**task, "files": self.repository.files(task_id)})
        if not source_path or not Path(source_path).exists():
            self.repository.mark_organize_queued(task_id, source_path)
            self.repository.mark_organize_submit_failed(
                task_id, "整理源路径不存在，等待下一次秒传/整理重试", retry_minutes=5
            )
            return False
        # Mark before submitting so an event emitted synchronously by
        # do_transfer cannot race an unmarked task.
        if not self.repository.mark_organize_queued(task_id, source_path):
            return False
        try:
            from app.chain.transfer import TransferChain

            total_size = int(task.get("total_size") or 0)
            item = self._fileitem(source_path, total_size)
            downloader = self._resolve_downloader_source(
                str(task.get("download_hash") or ""), str(task.get("downloader") or "qbittorrent")
            )
            state, message = TransferChain().do_transfer(
                fileitem=item,
                downloader=downloader,
                download_hash=str(task.get("download_hash") or ""),
                manual=self.force_getter(),
                force=self.force_getter(),
                background=True,
            )
            if not state:
                raise RuntimeError(str(message or "MoviePilot 拒绝整理任务"))
            logger.info(
                f"{LOG_PREFIX} 秒传失败后已加入 MoviePilot 整理队列："
                f"{str(task.get('download_hash') or '')[:12]}"
            )
            return True
        except Exception as exc:
            self.repository.mark_organize_submit_failed(task_id, str(exc), retry_minutes=5)
            logger.warning(f"{LOG_PREFIX} 加入整理队列失败：{exc}")
            return False

    def process_due(self, limit: int = 4) -> int:
        if not self.enabled_getter() or self.stop_requested():
            return 0
        count = 0
        for task in self.repository.organize_candidates(limit=limit):
            if self.stop_requested():
                break
            if self.enqueue_task(int(task["id"])):
                count += 1
        return count
