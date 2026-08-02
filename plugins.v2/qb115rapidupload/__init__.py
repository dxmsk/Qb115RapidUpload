import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.event import Event, eventmanager
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import ChainEventType, EventType

from .client115 import RapidUpload115Client
from .coordinator import TaskCoordinator
from .detector import CompletionDetector
from .repository import TaskRepository


class Qb115RapidUpload(_PluginBase):
    plugin_name = "qB 115 秒传"
    plugin_desc = "qBittorrent 下载完成后只读计算 SHA1 并秒传至 115"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/upload.png"
    plugin_version = "0.1.0"
    plugin_author = "Codex"
    author_url = ""
    plugin_config_prefix = "qb115rapidupload_"
    plugin_order = 35
    auth_level = 1

    LOG_PREFIX = "[qB 115 秒传]"

    def __init__(self):
        super().__init__()
        self._enabled = True
        self._cookie_115 = ""
        self._target_cid = "0"
        self._retry_interval_minutes = 30
        self._stop_after_organized = True
        self._cancel_organize_after_success = True
        self._repository: Optional[TaskRepository] = None
        self._client: Optional[RapidUpload115Client] = None
        self._detector: Optional[CompletionDetector] = None
        self._coordinator: Optional[TaskCoordinator] = None
        self._stop_event = threading.Event()

    def init_plugin(self, config: dict = None):
        config = dict(config or {})
        self._enabled = bool(config.get("enabled", True))
        self._cookie_115 = str(config.get("cookie_115") or "").strip()
        self._target_cid = self._normalize_target_cid(config.get("target_cid", "0"))
        self._retry_interval_minutes = self._normalize_retry(config.get("retry_interval_minutes", 30))
        self._stop_after_organized = bool(config.get("stop_after_organized", True))
        self._cancel_organize_after_success = bool(config.get("cancel_organize_after_success", True))
        self._stop_event.clear()

        self._repository = TaskRepository(self.get_data_path() / "qb115rapidupload.db")
        self._client = RapidUpload115Client(self._cookie_115) if self._cookie_115 else None
        self._detector = CompletionDetector(self._repository, lambda: self._target_cid)
        self._coordinator = TaskCoordinator(
            self._repository,
            client_getter=lambda: self._client,
            retry_minutes_getter=lambda: self._retry_interval_minutes,
            stop_requested=self._stop_event.is_set,
        )
        if self._enabled and not self._cookie_115:
            logger.warning(f"{self.LOG_PREFIX} 插件已启用，但尚未配置 115 Cookie")

    @staticmethod
    def _normalize_target_cid(value: Any) -> str:
        value = str(value if value is not None else "0").strip()
        return value if re.fullmatch(r"\d+", value) else "0"

    @staticmethod
    def _normalize_retry(value: Any) -> int:
        try:
            return min(1440, max(1, int(value)))
        except (TypeError, ValueError):
            return 30

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/tasks",
                "endpoint": self.api_tasks,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "查询秒传任务",
            },
            {
                "path": "/retry",
                "endpoint": self.api_retry,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "立即重试任务",
            },
            {
                "path": "/cancel",
                "endpoint": self.api_cancel,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "取消秒传任务",
            },
            {
                "path": "/test_cookie",
                "endpoint": self.api_test_cookie,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "测试 115 Cookie",
            },
            {
                "path": "/test_target",
                "endpoint": self.api_test_target,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "测试 115 目标目录",
            },
            {
                "path": "/scan",
                "endpoint": self.api_scan,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "立即扫描 qB 完成任务",
            },
        ]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "text": "插件只读取 qB 完成文件计算 SHA1，不会移动、重命名、删除或修改任何本地文件。仅命中 115 秒传时成功，不会回退成普通上传。",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {"model": "enabled", "label": "启用插件"},
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "cookie_115",
                                            "label": "115 Cookie（必填）",
                                            "type": "password",
                                            "placeholder": "UID=...; CID=...; SEID=...; KID=...",
                                            "hint": "所有 115 请求均使用此 Cookie；请妥善保管",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "target_cid",
                                            "label": "目标目录 ID",
                                            "placeholder": "0",
                                            "hint": "0 表示 115 根目录",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "retry_interval_minutes",
                                            "label": "重试间隔（分钟）",
                                            "type": "number",
                                            "min": 1,
                                            "max": 1440,
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "stop_after_organized",
                                            "label": "整理后停止秒传",
                                            "hint": "MoviePilot整理完成后不再尝试秒传",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "cancel_organize_after_success",
                                            "label": "秒传成功后取消整理任务",
                                            "hint": "秒传成功后自动取消对应整理任务，避免重复转移",
                                        },
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ], {
            "enabled": True,
            "cookie_115": "",
            "target_cid": "0",
            "retry_interval_minutes": 30,
            "stop_after_organized": True,
            "cancel_organize_after_success": True,
        }

    @staticmethod
    def _status_text(status: str) -> str:
        return {
            "WATCHING": "监控下载中",
            "WAITING": "等待秒传",
            "PROCESSING": "秒传处理中",
            "RETRY_WAIT": "等待重试",
            "SUCCESS": "秒传成功",
            "ABANDONED_ORGANIZED": "已放弃（已整理）",
            "ABANDONED_SOURCE_MISSING": "已放弃（文件不存在）",
            "CANCELLED": "已取消",
        }.get(status, status)

    def get_page(self) -> List[dict]:
        tasks = self._repository.list_tasks(100) if self._repository else []
        items = []
        for task in tasks:
            items.append(
                {
                    "id": task["id"],
                    "name": task.get("torrent_name") or task.get("download_hash", "")[:12],
                    "hash": task.get("download_hash", "")[:12],
                    "status": self._status_text(task.get("status", "")),
                    "files": f"{task.get('success_count', 0)}/{task.get('file_count', 0)}",
                    "attempts": task.get("attempt_count", 0),
                    "next_retry": task.get("next_retry_at") or "-",
                    "error": task.get("last_error_message") or "-",
                }
            )
        if not items:
            return [
                {
                    "component": "VAlert",
                    "props": {"type": "info", "variant": "tonal", "text": "暂无秒传任务"},
                }
            ]
        return [
            {
                "component": "VDataTable",
                "props": {
                    "headers": [
                        {"title": "任务", "key": "name"},
                        {"title": "Hash", "key": "hash"},
                        {"title": "状态", "key": "status"},
                        {"title": "文件", "key": "files"},
                        {"title": "尝试", "key": "attempts"},
                        {"title": "下次重试", "key": "next_retry"},
                        {"title": "最近错误", "key": "error"},
                    ],
                    "items": items,
                    "items-per-page": 25,
                },
            }
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        if not self._enabled:
            return []
        return [
            {
                "id": "Qb115RapidUpload.Detect",
                "name": "qB 下载完成检测",
                "trigger": "interval",
                "func": self.detect_completed,
                "kwargs": {"seconds": 15},
            },
            {
                "id": "Qb115RapidUpload.Process",
                "name": "115 秒传任务处理",
                "trigger": "interval",
                "func": self.process_due_tasks,
                "kwargs": {"minutes": 1},
            },
        ]

    def stop_service(self):
        self._stop_event.set()

    def detect_completed(self):
        if not self._enabled or self._stop_event.is_set() or not self._detector:
            return
        count = self._detector.scan()
        if count:
            logger.info(f"{self.LOG_PREFIX} 本轮核对了 {count} 个 qB 完成任务")

    def process_due_tasks(self):
        if not self._enabled or self._stop_event.is_set() or not self._coordinator:
            return
        self._coordinator.process_due()

    @eventmanager.register(EventType.DownloadAdded)
    def on_download_added(self, event: Event):
        if not self._enabled or not self._detector or not event or not isinstance(event.event_data, dict):
            return
        data = event.event_data
        context = data.get("context")
        title = ""
        if context:
            torrent_info = getattr(context, "torrent_info", None)
            title = str(getattr(torrent_info, "title", "") or "")
        if self._detector.register_download(data.get("downloader"), data.get("hash"), title):
            logger.info(f"{self.LOG_PREFIX} 已登记 qB 下载任务：{str(data.get('hash'))[:12]}")

    @eventmanager.register([EventType.TransferComplete, EventType.TransferFailed])
    def on_transfer_finished(self, event: Event):
        if not self._enabled or not self._stop_after_organized or not self._repository:
            return
        data = event.event_data if event and isinstance(event.event_data, dict) else {}
        download_hash = data.get("download_hash") or data.get("hash")
        downloader = data.get("downloader")
        if not download_hash or not downloader:
            return
        result = "success" if event.event_type == EventType.TransferComplete else "failed"
        if self._repository.mark_organized(
            downloader=downloader,
            download_hash=download_hash,
            result=result,
            transfer_history_id=data.get("transfer_history_id"),
        ):
            logger.info(f"{self.LOG_PREFIX} MoviePilot 已执行整理，停止秒传：{str(download_hash)[:12]}")

    @eventmanager.register(ChainEventType.TransferIntercept, priority=1)
    def on_transfer_intercept(self, event: Event):
        if not self._enabled or not self._cancel_organize_after_success or not self._repository or not event:
            return
        data = event.event_data
        fileitem = data.get("fileitem") if isinstance(data, dict) else getattr(data, "fileitem", None)
        path = fileitem.get("path") if isinstance(fileitem, dict) else getattr(fileitem, "path", None)
        if not path or not self._repository.success_matches_path(str(path)):
            return
        reason = "115 秒传已成功，取消重复整理"
        if isinstance(data, dict):
            data["cancel"] = True
            data["source"] = self.__class__.__name__
            data["reason"] = reason
        else:
            data.cancel = True
            data.source = self.__class__.__name__
            data.reason = reason
        self._repository.record_intercept(str(path))
        logger.info(f"{self.LOG_PREFIX} {reason}：{Path(str(path)).name}")

    def api_tasks(self, limit: int = 100) -> Dict[str, Any]:
        return {"code": 0, "data": self._repository.list_tasks(limit) if self._repository else []}

    def api_retry(self, task_id: int) -> Dict[str, Any]:
        ok = bool(self._repository and self._repository.retry_now(task_id))
        return {"code": 0 if ok else 1, "data": {"ok": ok}}

    def api_cancel(self, task_id: int) -> Dict[str, Any]:
        ok = bool(self._repository and self._repository.cancel(task_id))
        return {"code": 0 if ok else 1, "data": {"ok": ok}}

    def api_test_cookie(self) -> Dict[str, Any]:
        if not self._client:
            return {"code": 1, "data": {"ok": False, "message": "115 Cookie 未配置"}}
        ok, message = self._client.test_cookie()
        return {"code": 0 if ok else 1, "data": {"ok": ok, "message": message}}

    def api_test_target(self) -> Dict[str, Any]:
        if not self._client:
            return {"code": 1, "data": {"ok": False, "message": "115 Cookie 未配置"}}
        ok, message = self._client.test_target(self._target_cid)
        return {"code": 0 if ok else 1, "data": {"ok": ok, "message": message}}

    def api_scan(self) -> Dict[str, Any]:
        count = self._detector.scan() if self._detector else 0
        return {"code": 0, "data": {"count": count}}
