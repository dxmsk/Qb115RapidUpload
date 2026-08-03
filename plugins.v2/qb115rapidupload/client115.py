import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .hashing import sha1_range
from .models import RapidUploadResult


class RapidUpload115Client:
    """Cookie-authenticated 115 rapid-upload adapter. Never performs normal upload."""

    def __init__(self, cookie: str):
        self._cookie = (cookie or "").strip()
        self._client = None
        self._lock = threading.RLock()

    def _get_client(self):
        if not self._cookie:
            raise ValueError("115 Cookie 未配置")
        with self._lock:
            if self._client is None:
                from p115client import P115Client

                self._client = P115Client(self._cookie, console_qrcode=False)
            return self._client

    @staticmethod
    def _error_message(response: dict) -> str:
        return str(
            response.get("error")
            or response.get("error_msg")
            or response.get("message")
            or response.get("msg")
            or "115 返回未知错误"
        )

    def rapid_upload(
        self,
        path: Path,
        file_name: str,
        size: int,
        sha1: str,
        target_cid: str,
        remote_relative_dir: str = "",
        cancelled: Optional[Callable[[], bool]] = None,
    ) -> RapidUploadResult:
        if cancelled and cancelled():
            return RapidUploadResult(False, "CANCELLED", "任务已取消")
        try:
            client = self._get_client()

            def read_range(requested_range: str) -> str:
                return sha1_range(path, requested_range, cancelled=cancelled)

            response = client.upload_file_init(
                filename=file_name,
                filesha1=sha1,
                filesize=size,
                dirname=remote_relative_dir or "",
                read_range_bytes_or_hash=read_range,
                pid=str(target_cid or "0"),
            )
            if not isinstance(response, dict):
                return RapidUploadResult(False, "PROTOCOL_ERROR", "115 返回的数据格式无效")
            status = response.get("status")
            if response.get("reuse") is True or status == 2:
                remote_id = response.get("file_id") or response.get("fileid") or response.get("pickcode")
                return RapidUploadResult(True, "SUCCESS", "秒传成功", str(remote_id) if remote_id else None)
            if status == 1:
                return RapidUploadResult(
                    False,
                    "NOT_REUSABLE",
                    "115 未命中秒传；插件不会回退为普通上传",
                )
            message = self._error_message(response)
            lower_message = message.lower()
            if any(word in lower_message for word in ("cookie", "login", "登录", "认证", "过期", "unauthorized")):
                code = "AUTH_EXPIRED"
            else:
                code = "PROTOCOL_ERROR"
            return RapidUploadResult(False, code, message)
        except Exception as exc:
            name = exc.__class__.__name__.lower()
            message = str(exc) or exc.__class__.__name__
            lower_message = message.lower()
            if any(word in name for word in ("timeout", "connection", "http")):
                code = "NETWORK_ERROR"
            elif any(word in lower_message for word in ("401", "403", "cookie", "登录", "认证", "过期")):
                code = "AUTH_EXPIRED"
            elif "cancel" in name or "取消" in message:
                code = "CANCELLED"
            else:
                code = "PROTOCOL_ERROR"
            return RapidUploadResult(False, code, message)

    def test_cookie(self) -> Tuple[bool, str]:
        try:
            response = self._get_client().user_info()
            if isinstance(response, dict) and response.get("state") is not False:
                data = response.get("data") or {}
                display = data.get("user_name") or data.get("name") or data.get("user_id") or "有效账号"
                return True, f"Cookie 有效：{display}"
            return False, self._error_message(response if isinstance(response, dict) else {})
        except Exception as exc:
            return False, str(exc) or exc.__class__.__name__

    def test_target(self, target_cid: str) -> Tuple[bool, str]:
        try:
            listing = self.list_directories(str(target_cid or "0"))
            return True, f"目标目录有效：{listing['path']}"
        except Exception as exc:
            return False, str(exc) or exc.__class__.__name__

    @staticmethod
    def _directory_path(response: Dict[str, Any]) -> str:
        nodes = response.get("path") or []
        names = []
        if isinstance(nodes, list):
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                name = str(node.get("name") or node.get("n") or node.get("file_name") or "").strip()
                if name and name not in {"根目录", "全部文件"}:
                    names.append(name.strip("/"))
        return "/" + "/".join(names) if names else "/"

    @staticmethod
    def _directory_item(item: Dict[str, Any]) -> Optional[Dict[str, str]]:
        try:
            is_dir = bool(item.get("is_dir"))
            if "fc" in item:
                is_dir = int(item.get("fc") or 0) == 0
            elif "cid" in item:
                is_dir = "fid" not in item
            elif item.get("sha") or item.get("sha1") or item.get("s") or item.get("fs"):
                is_dir = False
            if not is_dir:
                return None
            directory_id = item.get("id") or item.get("cid") or item.get("file_id")
            name = item.get("name") or item.get("n") or item.get("file_name")
            if directory_id is None or not str(name or "").strip():
                return None
            return {
                "id": str(directory_id),
                "parent_id": str(item.get("parent_id") or item.get("pid") or "0"),
                "name": str(name).strip(),
            }
        except (TypeError, ValueError):
            return None

    def list_directories(self, cid: str = "0") -> Dict[str, Any]:
        """List one 115 directory level for the authenticated folder picker."""
        normalized_cid = str(cid or "0").strip()
        if not normalized_cid.isdigit():
            raise ValueError("115 目录 ID 无效")
        response = self._get_client().fs_files({
            "cid": normalized_cid,
            "limit": 1150,
            "offset": 0,
            "show_dir": 1,
            "cur": 1,
            "nf": 1,
            "fc_mix": 0,
            "o": "file_name",
            "asc": 1,
        })
        if not isinstance(response, dict):
            raise RuntimeError("115 返回的数据格式无效")
        if response.get("state") is False:
            raise RuntimeError(self._error_message(response))
        data = response.get("data") or []
        if isinstance(data, dict):
            data = data.get("list") or data.get("data") or []
        directories: List[Dict[str, str]] = []
        if isinstance(data, list):
            for raw in data:
                if not isinstance(raw, dict):
                    continue
                item = self._directory_item(raw)
                if item:
                    directories.append(item)
        directories.sort(key=lambda item: item["name"].casefold())
        return {
            "cid": normalized_cid,
            "path": self._directory_path(response),
            "directories": directories,
            "truncated": len(directories) >= 1150,
        }
