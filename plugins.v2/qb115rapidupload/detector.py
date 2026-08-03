import json
import os
import re
import threading
import time
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional

from app.helper.downloader import DownloaderHelper
from app.log import logger
from app.schemas.types import TorrentQueryStatus

from .hashing import resolve_snapshot_path
from .models import FileSnapshot, UnsafeSourcePath


LOG_PREFIX = "[qB 115 秒传]"
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def _value(item: Any, key: str, default=None):
    if isinstance(item, dict):
        return item.get(key, default)
    value = getattr(item, key, default)
    return value


def sanitize_component(value: str) -> str:
    value = CONTROL_CHARS.sub("_", str(value or "")).strip().strip(".")
    if value in {"", ".", ".."}:
        return "_"
    return value[:255]


def safe_relative_name(value: str) -> Optional[PurePosixPath]:
    raw = str(value or "").replace("\\", "/").lstrip("/")
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path


class CompletionDetector:
    def __init__(
        self,
        repository,
        target_cid_getter,
        source_paths_getter=None,
        ignore_tags_getter=None,
    ):
        self.repository = repository
        self.target_cid_getter = target_cid_getter
        self.source_paths_getter = source_paths_getter or (lambda: [])
        self.ignore_tags_getter = ignore_tags_getter or (lambda: set())
        self._scan_lock = threading.Lock()
        self._baseline_path = repository.db_path.parent / "qb_completed_baseline.json"
        self._completed_seen: Dict[str, set[str]] = {}
        self._service_retry_after: Dict[str, float] = {}
        self._load_baseline()

    def _load_baseline(self) -> None:
        try:
            payload = json.loads(self._baseline_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                self._completed_seen = {
                    str(name): {
                        str(item).strip().lower()
                        for item in values
                        if str(item).strip()
                    }
                    for name, values in payload.items()
                    if isinstance(values, list)
                }
        except (OSError, ValueError, TypeError):
            self._completed_seen = {}

    def _save_baseline(self) -> None:
        try:
            self._baseline_path.parent.mkdir(parents=True, exist_ok=True)
            self._baseline_path.write_text(
                json.dumps(
                    {name: sorted(values) for name, values in self._completed_seen.items()},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning(f"{LOG_PREFIX} 保存 qB 完成基线失败：{exc}")

    @staticmethod
    def qb_services() -> Dict[str, Any]:
        return DownloaderHelper().get_services(type_filter="qbittorrent") or {}

    def register_download(self, downloader: str, download_hash: str, torrent_name: str = "") -> bool:
        if not downloader or not download_hash:
            return False
        service = self.qb_services().get(downloader)
        if not service:
            return False
        self.repository.register_watching(downloader, download_hash, torrent_name)
        return True

    def _source_paths(self) -> List[str]:
        value = self.source_paths_getter()
        if isinstance(value, (str, Path)):
            value = [value]
        paths = []
        for item in value or []:
            text = str(item or "").strip()
            if text:
                paths.append(text)
        return paths

    def _source_allowed(self, save_path: str) -> bool:
        roots = self._source_paths()
        if not roots:
            return True
        try:
            candidate = os.path.normcase(os.path.realpath(save_path))
        except Exception:
            return False
        for root in roots:
            try:
                root_path = os.path.normcase(os.path.realpath(root))
                if os.path.commonpath((candidate, root_path)) == root_path:
                    return True
            except (OSError, ValueError):
                continue
        return False

    @staticmethod
    def _tags(value: Any) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, (list, tuple, set)):
            parts = value
        else:
            parts = re.split(r"[,，\s]+", str(value))
        return {str(part).strip().casefold() for part in parts if str(part).strip()}

    def _ignored_tags(self) -> set[str]:
        try:
            return self._tags(self.ignore_tags_getter())
        except Exception:
            return set()

    @staticmethod
    def _is_completed(torrent: Any) -> bool:
        state = _value(torrent, "state", "")
        state = getattr(state, "value", state)
        state_text = str(state or "").strip().lower()
        if state_text in {"completed", "complete", "已完成"}:
            return True
        try:
            progress = float(_value(torrent, "progress", 0) or 0)
            amount_left = int(_value(torrent, "amount_left", 0) or 0)
        except (TypeError, ValueError):
            return False
        return progress >= 1 and amount_left <= 0 and state_text not in {
            "allocating",
            "checkingdl",
            "checkingup",
            "downloading",
            "error",
            "forceddl",
            "missingfiles",
            "metadl",
            "moving",
            "queueddl",
            "stalleddl",
            "unknown",
        }

    @classmethod
    def _completed_torrents(cls, service_name: str, service) -> Optional[List[Any]]:
        inactive = getattr(service.instance, "is_inactive", None)
        if callable(inactive) and inactive():
            return None
        getter = getattr(service.instance, "get_completed_torrents", None)
        if callable(getter):
            return getter()
        return service.module.list_torrents(
            status=TorrentQueryStatus.COMPLETED,
            downloader=service_name,
            include_all_tags=True,
        ) or []

    @classmethod
    def _normalize_torrent(cls, service, torrent: Any) -> Any:
        if not isinstance(torrent, dict):
            return torrent
        normalized = dict(torrent)
        for key in ("save_path", "content_path"):
            if normalized.get(key):
                normalized[key] = cls._normalized_path(service, normalized[key])
        return normalized

    @staticmethod
    def _normalized_path(service, path_value: Any) -> str:
        if not path_value:
            return ""
        try:
            return str(service.module.normalize_return_path(Path(str(path_value)), service.name))
        except Exception:
            return str(path_value)

    @staticmethod
    def _files(
        service,
        download_hash: str,
        save_path: str,
        content_path: str = "",
    ) -> List[FileSnapshot]:
        torrent_files = service.instance.get_files(tid=download_hash, retry=2, interval=1) or []
        selected = []
        for item in torrent_files:
            priority = _value(item, "priority", 1)
            try:
                if int(priority) == 0:
                    continue
            except (TypeError, ValueError):
                pass
            relative = safe_relative_name(_value(item, "name", ""))
            if not relative:
                logger.warning(f"{LOG_PREFIX} 跳过不安全的 qB 文件路径")
                continue
            try:
                expected_size = int(_value(item, "size", -1))
            except (TypeError, ValueError):
                expected_size = -1
            remote_parent = "/".join(sanitize_component(part) for part in relative.parent.parts)
            try:
                absolute = str(
                    resolve_snapshot_path(
                        save_path=save_path,
                        content_path=content_path,
                        relative_path=relative.as_posix(),
                    )
                )
            except (FileNotFoundError, UnsafeSourcePath):
                # Keep a deterministic fallback for files that are still
                # being materialized; the coordinator retries the same task
                # after checking all path variants again.
                absolute = str(Path(save_path).joinpath(*relative.parts))
            selected.append(
                FileSnapshot(
                    relative_path=relative.as_posix(),
                    absolute_path=absolute,
                    remote_relative_dir=remote_parent,
                    expected_size=expected_size,
                )
            )
        return selected

    def scan(self) -> int:
        if not self._scan_lock.acquire(blocking=False):
            logger.debug(f"{LOG_PREFIX} 上一轮 qB 秒级检测仍在运行，本轮跳过")
            return 0
        found = 0
        try:
            watching = self.repository.watching_tasks()
            watching_by_service: Dict[str, Dict[str, Dict[str, Any]]] = {}
            for task in watching:
                watching_by_service.setdefault(task["downloader"], {})[task["download_hash"].lower()] = task

            for service_name, service in self.qb_services().items():
                if time.monotonic() < self._service_retry_after.get(service_name, 0):
                    continue
                try:
                    torrents = self._completed_torrents(service_name, service)
                    if torrents is None:
                        self._service_retry_after[service_name] = time.monotonic() + 30
                        logger.warning(f"{LOG_PREFIX} qB 服务未连接，暂不更新完成基线：{service_name}")
                        continue
                except Exception as exc:
                    self._service_retry_after[service_name] = time.monotonic() + 30
                    logger.error(f"{LOG_PREFIX} 查询 qB 下载完成任务失败（{service_name}）：{exc}")
                    continue
                self._service_retry_after.pop(service_name, None)

                current: Dict[str, Any] = {}
                for item in torrents:
                    torrent = self._normalize_torrent(service, item)
                    download_hash = str(_value(torrent, "hash", "") or "").lower()
                    if not download_hash or not self._is_completed(torrent):
                        continue
                    current[download_hash] = torrent

                previous = self._completed_seen.get(service_name)
                first_scan = previous is None
                previous = previous or set()
                current_hashes = set(current)
                if first_scan or current_hashes != previous:
                    self._completed_seen[service_name] = current_hashes
                    self._save_baseline()
                service_watching = watching_by_service.setdefault(service_name, {})
                candidate_hashes = set(service_watching).intersection(current)
                if not first_scan:
                    candidate_hashes.update(set(current).difference(previous))

                for download_hash in sorted(candidate_hashes):
                    torrent = current[download_hash]
                    if self._process_completed_torrent(
                        service_name,
                        service,
                        service_watching,
                        download_hash,
                        torrent,
                    ):
                        found += 1
        finally:
            self._scan_lock.release()
        return found

    def _process_completed_torrent(
        self,
        service_name: str,
        service: Any,
        service_watching: Dict[str, Dict[str, Any]],
        download_hash: str,
        torrent: Any,
    ) -> bool:
        tags = str(_value(torrent, "tags", "") or "")
        matched_ignored_tags = self._tags(tags).intersection(self._ignored_tags())
        if matched_ignored_tags:
            task = service_watching.get(download_hash)
            if task:
                self.repository.cancel(
                    int(task["id"]),
                    f"命中排除标签：{', '.join(sorted(matched_ignored_tags))}",
                    reason_code="IGNORED_TAG",
                )
            logger.info(
                f"{LOG_PREFIX} 跳过排除标签任务：{download_hash[:12]} "
                f"({', '.join(sorted(matched_ignored_tags))})"
            )
            return False
        save_path = str(_value(torrent, "save_path", "") or "")
        if not save_path:
            logger.warning(f"{LOG_PREFIX} qB 任务缺少保存目录，跳过：{download_hash[:12]}")
            return False
        task = service_watching.get(download_hash)
        task_id = int(task["id"]) if task else self.repository.register_watching(
            service_name,
            download_hash,
            str(_value(torrent, "title", "") or _value(torrent, "name", "") or ""),
        )
        try:
            if not Path(save_path).exists():
                self.repository.cancel(
                    task_id,
                    "qB 保存目录不存在，可能已被整理或移走",
                    reason_code="SOURCE_PATH_MISSING",
                )
                logger.info(f"{LOG_PREFIX} 放弃已不存在的 qB 来源目录：{download_hash[:12]}")
                return False
        except OSError:
            return False
        if not self._source_allowed(save_path):
            self.repository.cancel(
                task_id,
                "qB 保存目录不在插件配置的秒传目录内",
                reason_code="OUTSIDE_RAPID_UPLOAD_PATH",
            )
            logger.info(f"{LOG_PREFIX} 跳过秒传目录外的 qB 任务：{download_hash[:12]}")
            return False
        try:
            files = self._files(
                service,
                download_hash,
                save_path,
                str(_value(torrent, "content_path", "") or ""),
            )
        except Exception as exc:
            self.repository.schedule_watch_retry(task_id, minutes=5, message=str(exc))
            logger.warning(f"{LOG_PREFIX} 获取 qB 文件列表失败，将在 5 分钟后重试 {download_hash[:12]}：{exc}")
            return False
        if not files:
            self.repository.schedule_watch_retry(task_id, minutes=5, message="qB 文件列表为空")
            return False
        organized = "已整理" in self._tags(tags)
        snapshot_id = self.repository.snapshot_completed(
            downloader=service_name,
            download_hash=download_hash,
            torrent_name=str(_value(torrent, "title", "") or _value(torrent, "name", "") or ""),
            save_path=save_path,
            content_path=str(_value(torrent, "content_path", "") or ""),
            target_cid=str(self.target_cid_getter() or "0"),
            files=files,
            torrent_tags=tags,
            organized=organized,
        )
        if snapshot_id:
            logger.info(f"{LOG_PREFIX} 已登记 qB 完成任务：{download_hash[:12]}")
        return bool(snapshot_id)
