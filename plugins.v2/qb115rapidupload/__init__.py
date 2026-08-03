import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.event import Event, eventmanager
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import ChainEventType, EventType

from .client115 import RapidUpload115Client
from .coordinator import TaskCoordinator
from .detector import CompletionDetector
from .organizer import OrganizerCoordinator
from .repository import TaskRepository


class Qb115RapidUpload(_PluginBase):
    plugin_name = "qB 115 秒传整理联动"
    plugin_desc = "qB 完成任务先尝试 115 秒传，首轮失败后自动进入 MoviePilot 整理队列"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/upload.png"
    plugin_version = "0.5.0"
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
        self._rapid_upload_path = ""
        self._rapid_upload_paths: List[str] = []
        self._retry_interval_minutes = 30
        self._stop_after_organized = True
        self._cancel_organize_after_success = True
        self._auto_organize_enabled = True
        self._ignore_tags = "已整理,刷流"
        self._ignore_tag_set: set[str] = {"已整理", "刷流"}
        self._force_organize = False
        self._organize_lock = threading.Lock()
        self._repository: Optional[TaskRepository] = None
        self._client: Optional[RapidUpload115Client] = None
        self._detector: Optional[CompletionDetector] = None
        self._coordinator: Optional[TaskCoordinator] = None
        self._organizer: Optional[OrganizerCoordinator] = None
        self._stop_event = threading.Event()

    def init_plugin(self, config: dict = None):
        config = dict(config or {})
        self._enabled = bool(config.get("enabled", True))
        self._cookie_115 = str(config.get("cookie_115") or "").strip()
        self._target_cid = self._normalize_target_cid(config.get("target_cid", "0"))
        self._rapid_upload_paths = self._normalize_rapid_paths(config.get("rapid_upload_path"))
        self._rapid_upload_path = "\n".join(self._rapid_upload_paths)
        self._retry_interval_minutes = self._normalize_retry(config.get("retry_interval_minutes", 30))
        self._stop_after_organized = bool(config.get("stop_after_organized", True))
        self._cancel_organize_after_success = bool(config.get("cancel_organize_after_success", True))
        self._auto_organize_enabled = bool(config.get("auto_organize_enabled", True))
        self._ignore_tags = str(config.get("ignore_tags") or "已整理,刷流").strip()
        self._ignore_tag_set = self._parse_tags(self._ignore_tags)
        self._force_organize = bool(config.get("force_organize", False))
        self._stop_event.clear()

        self._repository = TaskRepository(self.get_data_path() / "qb115rapidupload.db")
        self._client = RapidUpload115Client(self._cookie_115) if self._cookie_115 else None
        self._detector = CompletionDetector(
            self._repository,
            lambda: self._target_cid,
            source_paths_getter=lambda: self._rapid_upload_paths,
            ignore_tags_getter=lambda: self._ignore_tag_set,
        )
        self._coordinator = TaskCoordinator(
            self._repository,
            client_getter=lambda: self._client,
            retry_minutes_getter=lambda: self._retry_interval_minutes,
            stop_requested=self._stop_event.is_set,
            success_callback=self._on_rapid_success,
            failure_callback=self._on_rapid_failure,
        )
        self._organizer = OrganizerCoordinator(
            self._repository,
            enabled_getter=lambda: self._auto_organize_enabled,
            force_getter=lambda: self._force_organize,
            stop_requested=self._stop_event.is_set,
        )
        recovered = self._coordinator.recover_source_paths(self._has_transfer_history)
        if recovered:
            logger.info(f"{self.LOG_PREFIX} 路径解析修复后恢复了 {recovered} 个秒传任务")
        if self._enabled and not self._cookie_115:
            logger.warning(f"{self.LOG_PREFIX} 插件已启用，但尚未配置 115 Cookie")

    @staticmethod
    def _has_transfer_history(download_hash: str) -> bool:
        try:
            from app.db.transferhistory_oper import TransferHistoryOper

            return bool(TransferHistoryOper().list_by_hash(download_hash))
        except Exception:
            return False

    @staticmethod
    def _normalize_target_cid(value: Any) -> str:
        value = str(value if value is not None else "0").strip()
        return value if re.fullmatch(r"\d+", value) else "0"

    @staticmethod
    def _default_rapid_upload_path() -> str:
        """Use MoviePilot's highest-priority local download directory by default."""
        try:
            from app.helper.directory import DirectoryHelper

            directories = DirectoryHelper().get_local_download_dirs()
            for directory in directories:
                path = str(getattr(directory, "download_path", "") or "").strip()
                if path:
                    return path
        except Exception:
            pass
        return ""

    @classmethod
    def _normalize_rapid_paths(cls, value: Any) -> List[str]:
        if isinstance(value, (list, tuple, set)):
            raw_values = value
        else:
            raw = str(value or "").strip()
            raw_values = re.split(r"[,\r\n]+", raw) if raw else []
        paths = []
        for item in raw_values:
            path = str(item or "").strip()
            if path and path not in paths:
                paths.append(path)
        if paths:
            return paths
        default_path = cls._default_rapid_upload_path()
        return [default_path] if default_path else []

    @staticmethod
    def _normalize_retry(value: Any) -> int:
        try:
            return min(1440, max(1, int(value)))
        except (TypeError, ValueError):
            return 30

    @staticmethod
    def _parse_tags(value: Any) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, (list, tuple, set)):
            parts = value
        else:
            parts = re.split(r"[,，\s]+", str(value))
        return {str(part).strip().casefold() for part in parts if str(part).strip()}

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    @staticmethod
    def get_render_mode() -> Tuple[str, str]:
        return "vue", "dist/assets"

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
            {
                "path": "/organize_records",
                "endpoint": self.api_organize_records,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "查询自动整理记录",
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
                                        "component": "VTextField",
                                        "props": {
                                            "model": "rapid_upload_path",
                                            "label": "秒传目录（本地）",
                                            "placeholder": self._default_rapid_upload_path() or "MoviePilot 默认下载目录",
                                            "hint": "只处理此目录下的 qB 完成种子；留空使用 MoviePilot 优先级最高的本地下载目录，可用逗号分隔多个目录",
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
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "auto_organize_enabled",
                                            "label": "启用自动整理联动",
                                            "hint": "首次秒传失败后自动加入 MoviePilot 整理队列",
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
                                            "model": "force_organize",
                                            "label": "强制整理",
                                            "hint": "整理时向 MoviePilot 传递 manual/force 参数",
                                        },
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
                                            "model": "ignore_tags",
                                            "label": "排除 qB 标签",
                                            "placeholder": "已整理,刷流",
                                            "hint": "逗号、空格或中文逗号分隔；命中任一标签的任务不会秒传，也不会自动整理",
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
            "rapid_upload_path": self._rapid_upload_path or self._default_rapid_upload_path(),
            "retry_interval_minutes": 30,
            "stop_after_organized": True,
            "cancel_organize_after_success": True,
            "auto_organize_enabled": True,
            "force_organize": False,
            "ignore_tags": "已整理,刷流",
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
        tasks = self._repository.successful_tasks(100) if self._repository else []
        if not tasks:
            return [
                {
                    "component": "VAlert",
                    "props": {
                        "type": "info",
                        "variant": "tonal",
                        "text": "暂无秒传成功记录。插件只会处理本次运行后新进入完成状态的 qB 种子。",
                    },
                }
            ]

        def format_time(value: Any) -> str:
            try:
                parsed = datetime.fromisoformat(str(value))
                return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S")
            except (TypeError, ValueError, OverflowError):
                return str(value or "-")

        def format_size(value: Any) -> str:
            try:
                size = max(0, int(value or 0))
            except (TypeError, ValueError):
                return "-"
            units = ("B", "KB", "MB", "GB", "TB", "PB")
            number = float(size)
            unit = units[0]
            for unit in units:
                if number < 1024 or unit == units[-1]:
                    break
                number /= 1024
            return f"{number:.1f} {unit}" if unit != "B" else f"{int(number)} B"

        def rapid_path(task: Dict[str, Any]) -> str:
            cid = str(task.get("target_cid") or "0")
            base = "115:/根目录" if cid == "0" else f"115:/目录ID/{cid}"
            remote_dirs = str(task.get("remote_dirs") or "").strip()
            return f"{base}/{remote_dirs}" if remote_dirs else base

        items = [
            {
                "id": task["id"],
                "name": task.get("torrent_name") or task.get("download_hash", "")[:12],
                "hash": task.get("download_hash", "")[:12],
                "success_time": format_time(task.get("rapid_uploaded_at")),
                "size": format_size(task.get("total_size")),
                "source_path": task.get("save_path") or task.get("content_path") or "-",
                "rapid_path": rapid_path(task),
            }
            for task in tasks
        ]
        return [
            {
                "component": "VRow",
                "content": [
                    {
                        "component": "VCol",
                        "props": {"cols": 12},
                        "content": [
                            {
                                "component": "VDataTableVirtual",
                                "props": {
                                    "headers": [
                                        {"title": "资源", "key": "name", "sortable": True},
                                        {"title": "成功时间", "key": "success_time", "sortable": True},
                                        {"title": "大小", "key": "size", "sortable": False},
                                        {"title": "本地来源", "key": "source_path", "sortable": False},
                                        {"title": "115 秒传路径", "key": "rapid_path", "sortable": False},
                                    ],
                                    "items": items,
                                    "height": "32rem",
                                    "density": "compact",
                                    "fixed-header": True,
                                    "hover": True,
                                    "hide-no-data": True,
                                },
                            }
                        ],
                    }
                ],
            }
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        if not self._enabled:
            return []
        return [
            {
                "id": "Qb115RapidUpload.Detect",
                "name": "qB 下载完成秒级检测",
                "trigger": "interval",
                "func": self.detect_completed,
                "kwargs": {"seconds": 1},
            },
            {
                "id": "Qb115RapidUpload.Process",
                "name": "115 秒传任务处理",
                "trigger": "interval",
                "func": self.process_due_tasks,
                "kwargs": {"seconds": 1},
            },
            {
                "id": "Qb115RapidUpload.Organize",
                "name": "秒传失败自动整理处理",
                "trigger": "interval",
                "func": self.process_organize_tasks,
                "kwargs": {"seconds": 1},
            },
        ]

    def stop_service(self):
        self._stop_event.set()

    def detect_completed(self):
        if not self._enabled or self._stop_event.is_set() or not self._detector:
            return
        count = self._detector.scan()
        if count:
            logger.info(f"{self.LOG_PREFIX} 本轮发现并登记了 {count} 个新的 qB 完成任务")

    def process_due_tasks(self):
        if not self._enabled or self._stop_event.is_set() or not self._coordinator:
            return
        self._coordinator.process_due()

    def process_organize_tasks(self):
        if not self._enabled or self._stop_event.is_set() or not self._organizer:
            return
        self._organizer.process_due()

    def get_coordination_status(self, download_hash: str) -> Dict[str, Any]:
        """Expose a tiny, read-only bridge for qB auto-organizer.

        The organizer uses this to give rapid upload a short head start.  The
        method deliberately returns plain data and never performs network or
        filesystem work, so the two plugins remain independently usable.
        """
        if not self._enabled or not self._repository:
            return {"status": "UNAVAILABLE", "download_hash": str(download_hash or "").lower()}
        task = self._repository.coordination_task(download_hash)
        if not task:
            return {"status": "UNKNOWN", "download_hash": str(download_hash or "").lower()}
        return {
            "status": str(task.get("status") or "UNKNOWN"),
            "download_hash": str(task.get("download_hash") or download_hash).lower(),
            "task_id": task.get("id"),
            "updated_at": task.get("updated_at"),
            "source_path": task.get("save_path") or task.get("content_path") or "",
        }

    def _on_rapid_failure(self, task_id: int, _code: str, _message: str) -> None:
        """The first failed rapid attempt is the organizer admission gate."""
        if self._auto_organize_enabled and self._organizer:
            self._organizer.enqueue_task(task_id)

    def _on_rapid_success(self, download_hash: str) -> None:
        if not self._repository or not self._cancel_organize_after_success:
            return
        task = self._repository.coordination_task(download_hash)
        if not task or str(task.get("organize_status") or "NONE") == "NONE":
            return
        source_path = str(task.get("organize_source_path") or "")
        removed = False
        if self._organizer and source_path:
            removed = self._organizer.remove_from_queue(source_path)
        changed = self._repository.mark_organize_cancelled_by_rapid(download_hash)
        if changed:
            action = "已从 MoviePilot 整理队列移除" if removed else "已标记取消，后续整理将被拦截"
            logger.info(f"{self.LOG_PREFIX} 秒传重试成功，{action}：{download_hash[:12]}")

    @eventmanager.register([EventType.TransferComplete, EventType.TransferFailed])
    def on_transfer_finished(self, event: Event):
        if not self._enabled or not self._repository or not event:
            return
        data = event.event_data if event and isinstance(event.event_data, dict) else {}
        download_hash = data.get("download_hash") or data.get("hash")
        downloader = data.get("downloader")
        if not download_hash:
            return
        result = "success" if event.event_type == EventType.TransferComplete else "failed"
        fileitem = data.get("fileitem")
        source_path = str(
            (fileitem.get("path") if isinstance(fileitem, dict) else getattr(fileitem, "path", ""))
            or ""
        )
        transferinfo = data.get("transferinfo")
        target_path = ""
        if transferinfo:
            target_diritem = getattr(transferinfo, "target_diritem", None)
            target_item = getattr(transferinfo, "target_item", None)
            target_path = str(
                getattr(target_diritem, "path", None)
                or getattr(target_item, "path", None)
                or ""
            )
        self._repository.mark_organize_result(
            download_hash=download_hash,
            success=result == "success",
            transfer_history_id=data.get("transfer_history_id"),
            message=str(getattr(transferinfo, "message", "") or ""),
            source_path=source_path,
            target_path=target_path,
        )
        if self._stop_after_organized and self._repository.mark_organized(
            downloader=str(downloader or "qbittorrent"),
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

    def api_organize_records(self, limit: int = 100) -> Dict[str, Any]:
        records = self._repository.organize_records(limit) if self._repository else []
        return {"code": 0, "data": records}
