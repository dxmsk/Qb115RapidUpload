import os
import re
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional

from app.helper.downloader import DownloaderHelper
from app.log import logger
from app.schemas.types import TorrentQueryStatus

from .models import FileSnapshot


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
    def __init__(self, repository, target_cid_getter, source_paths_getter=None):
        self.repository = repository
        self.target_cid_getter = target_cid_getter
        self.source_paths_getter = source_paths_getter or (lambda: [])
        self._completed_seen: Dict[str, set[str]] = {}
        self._baseline_ready: set[str] = set()

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
    def _is_completed(torrent: Any) -> bool:
        state = _value(torrent, "state", "")
        state = getattr(state, "value", state)
        return str(state or "").strip().lower() in {"completed", "complete", "已完成"}

    @staticmethod
    def _normalized_path(service, path_value: Any) -> str:
        if not path_value:
            return ""
        try:
            return str(service.module.normalize_return_path(Path(str(path_value)), service.name))
        except Exception:
            return str(path_value)

    @staticmethod
    def _files(service, download_hash: str, save_path: str) -> List[FileSnapshot]:
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
        found = 0
        watching = self.repository.watching_tasks()
        watching_by_service: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for task in watching:
            watching_by_service.setdefault(task["downloader"], {})[task["download_hash"].lower()] = task

        for service_name, service in self.qb_services().items():
            try:
                torrents = service.module.list_torrents(
                    status=TorrentQueryStatus.COMPLETED,
                    downloader=service_name,
                    # The detector is scoped by the configured local directory;
                    # qB tasks added outside MoviePilot must also be observable.
                    include_all_tags=True,
                ) or []
            except Exception as exc:
                logger.error(f"{LOG_PREFIX} 查询 qB 下载完成任务失败（{service_name}）：{exc}")
                continue

            current: Dict[str, Any] = {}
            for torrent in torrents:
                download_hash = str(_value(torrent, "hash", "") or "").lower()
                if not download_hash or not self._is_completed(torrent):
                    continue
                current[download_hash] = torrent

            previous = self._completed_seen.get(service_name, set())
            first_scan = service_name not in self._baseline_ready
            self._completed_seen[service_name] = set(current)
            self._baseline_ready.add(service_name)
            service_watching = watching_by_service.setdefault(service_name, {})
            candidate_hashes = set(service_watching).intersection(current)
            if not first_scan:
                candidate_hashes.update(set(current).difference(previous))

            for download_hash in sorted(candidate_hashes):
                torrent = current[download_hash]
                save_path = str(_value(torrent, "save_path", "") or "")
                if not save_path:
                    logger.warning(f"{LOG_PREFIX} qB 任务缺少保存目录，跳过：{download_hash[:12]}")
                    continue
                task = service_watching.get(download_hash)
                task_id = int(task["id"]) if task else self.repository.register_watching(
                    service_name,
                    download_hash,
                    str(_value(torrent, "title", "") or _value(torrent, "name", "") or ""),
                )
                if not self._source_allowed(save_path):
                    self.repository.cancel(
                        task_id,
                        "qB 保存目录不在插件配置的秒传目录内",
                        reason_code="OUTSIDE_RAPID_UPLOAD_PATH",
                    )
                    logger.info(f"{LOG_PREFIX} 跳过秒传目录外的 qB 任务：{download_hash[:12]}")
                    continue
                try:
                    files = self._files(service, download_hash, save_path)
                except Exception as exc:
                    self.repository.schedule_watch_retry(task_id, minutes=5, message=str(exc))
                    logger.warning(f"{LOG_PREFIX} 获取 qB 文件列表失败，将在 5 分钟后重试 {download_hash[:12]}：{exc}")
                    continue
                if not files:
                    self.repository.schedule_watch_retry(task_id, minutes=5, message="qB 文件列表为空")
                    continue
                tags = str(_value(torrent, "tags", "") or "")
                organized = "已整理" in {item.strip() for item in tags.split(",") if item.strip()}
                snapshot_id = self.repository.snapshot_completed(
                    downloader=service_name,
                    download_hash=download_hash,
                    torrent_name=str(_value(torrent, "title", "") or _value(torrent, "name", "") or ""),
                    save_path=save_path,
                    content_path=str(_value(torrent, "content_path", "") or ""),
                    target_cid=str(self.target_cid_getter() or "0"),
                    files=files,
                    organized=organized,
                )
                if snapshot_id:
                    found += 1
        return found
