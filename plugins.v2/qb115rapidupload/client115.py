import threading
from pathlib import Path
from typing import Callable, Optional, Tuple

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
        if str(target_cid) == "0":
            return True, "根目录"
        try:
            response = self._get_client().fs_file(str(target_cid))
            if isinstance(response, dict) and response.get("state") is not False:
                data = response.get("data") or []
                if isinstance(data, list) and data:
                    data = data[0]
                if isinstance(data, dict):
                    name = data.get("file_name") or data.get("n") or target_cid
                else:
                    name = target_cid
                return True, f"目标目录有效：{name}"
            return False, self._error_message(response if isinstance(response, dict) else {})
        except Exception as exc:
            return False, str(exc) or exc.__class__.__name__
