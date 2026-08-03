"""Persistent qBittorrent Web API client shared by rapid upload and organizing."""

import threading
import time
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

import requests


class QbWebApiError(RuntimeError):
    pass


class QbWebApiClient:
    REQUEST_TIMEOUT = (5, 20)

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = str(base_url or "").strip().rstrip("/")
        self.username = str(username or "").strip()
        self.password = str(password or "")
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise QbWebApiError("qBittorrent 地址必须是有效的 http(s) URL")
        self._lock = threading.RLock()
        self._session = None
        self._logged_in = False

    def _api_url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _ensure_session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
            # MoviePilot containers are often configured with a global HTTP
            # proxy.  Requests would otherwise send private-LAN qB traffic to
            # that proxy, which commonly answers 403 before qB ever sees it.
            self._session.trust_env = False
            self._session.headers.update({
                "Accept": "application/json, text/plain, */*",
                "User-Agent": "MoviePilot-Qb115RapidUpload/0.7.2",
            })
        return self._session

    def _allows_unauthenticated_api(self, session: requests.Session) -> bool:
        """Detect qB's local-auth bypass before forcing a login request."""
        try:
            response = session.get(
                self._api_url("/api/v2/app/version"),
                timeout=self.REQUEST_TIMEOUT,
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def _login(self) -> None:
        session = self._ensure_session()
        if self._allows_unauthenticated_api(session):
            self._logged_in = True
            return
        try:
            response = None
            # qB versions and reverse proxies disagree on whether Origin is
            # required.  Try the documented Referer form first, then a strict
            # same-origin form, and finally a proxy-friendly header set.
            header_variants = (
                {"Referer": f"{self.base_url}/"},
                {
                    "Referer": self.base_url,
                    "Origin": self.base_url,
                    "X-Requested-With": "XMLHttpRequest",
                },
                {},
            )
            for headers in header_variants:
                response = session.post(
                    self._api_url("/api/v2/auth/login"),
                    data={"username": self.username, "password": self.password},
                    headers=headers,
                    timeout=self.REQUEST_TIMEOUT,
                )
                if response.status_code != 403:
                    break
            if response is None or response.status_code == 403:
                detail = response.text.strip().replace("\r", " ").replace("\n", " ")[:200] if response else ""
                suffix = f"；qB 响应：{detail}" if detail else ""
                raise QbWebApiError(
                    "qBittorrent 拒绝登录（HTTP 403）。插件已绕过容器 HTTP 代理并尝试多种同源头。"
                    "请在 qB WebUI 设置中检查 Host Header/CSRF，或解除当前 MoviePilot IP 的登录封禁"
                    f"{suffix}"
                )
            response.raise_for_status()
        except requests.Timeout as exc:
            raise QbWebApiError("登录 qBittorrent 超时") from exc
        except QbWebApiError:
            raise
        except requests.RequestException as exc:
            raise QbWebApiError(f"无法连接 qBittorrent：{exc}") from exc
        if response.text.strip().lower() != "ok.":
            raise QbWebApiError("qBittorrent 用户名或密码错误")
        self._logged_in = True

    def _get(self, path: str, params: Dict[str, Any] = None):
        with self._lock:
            if not self._logged_in:
                self._login()
            session = self._ensure_session()
            for attempt in range(2):
                try:
                    response = session.get(
                        self._api_url(path),
                        params=params,
                        timeout=self.REQUEST_TIMEOUT,
                    )
                    if response.status_code in {401, 403} and attempt == 0:
                        self._logged_in = False
                        self._login()
                        continue
                    response.raise_for_status()
                    return response
                except requests.Timeout as exc:
                    raise QbWebApiError("qBittorrent 请求超时") from exc
                except requests.RequestException as exc:
                    raise QbWebApiError(f"qBittorrent 请求失败：{exc}") from exc
            raise QbWebApiError("qBittorrent 登录状态失效")

    @staticmethod
    def _json_list(response, action: str) -> List[Dict[str, Any]]:
        try:
            data = response.json()
        except ValueError as exc:
            raise QbWebApiError(f"{action}返回了无效 JSON") from exc
        if not isinstance(data, list):
            raise QbWebApiError(f"{action}返回格式异常")
        return [item for item in data if isinstance(item, dict)]

    def completed_torrents(self) -> List[Dict[str, Any]]:
        response = self._get("/api/v2/torrents/info", {"filter": "completed"})
        return self._json_list(response, "查询 qB 完成任务")

    def torrent_files(self, download_hash: str) -> List[Dict[str, Any]]:
        response = self._get("/api/v2/torrents/files", {"hash": download_hash})
        return self._json_list(response, "查询 qB 种子文件")

    def test_connection(self) -> tuple[bool, str, Dict[str, Any]]:
        try:
            version = self._get("/api/v2/app/version").text.strip() or "未知"
            count = len(self.completed_torrents())
            return True, f"连接成功：qBittorrent {version}，当前已完成任务 {count} 个", {
                "version": version,
                "completed_count": count,
            }
        except Exception as exc:
            return False, str(exc) or exc.__class__.__name__, {}

    def close(self) -> None:
        with self._lock:
            if self._session is not None:
                self._session.close()
            self._session = None
            self._logged_in = False


class _DirectQbModule:
    @staticmethod
    def normalize_return_path(path: Path, _service_name: str) -> Path:
        return path


class _DirectQbInstance:
    def __init__(self, client: QbWebApiClient):
        self.client = client

    @staticmethod
    def is_inactive() -> bool:
        return False

    def get_completed_torrents(self):
        return self.client.completed_torrents()

    def get_files(self, tid: str, retry: int = 0, interval: int = 1):
        last_error = None
        for attempt in range(max(1, int(retry or 0) + 1)):
            try:
                return self.client.torrent_files(tid)
            except Exception as exc:
                last_error = exc
                if attempt < int(retry or 0):
                    time.sleep(max(0, min(float(interval or 0), 2)))
        raise last_error


class DirectQbService:
    """Adapter matching the small downloader-service surface used by the detector."""

    name = "qbittorrent"

    def __init__(self, client: QbWebApiClient):
        self.module = _DirectQbModule()
        self.instance = _DirectQbInstance(client)
