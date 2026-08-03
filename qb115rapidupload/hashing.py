import hashlib
import os
import re
from pathlib import Path
from typing import Callable, Optional, Tuple

from .models import FileChangedDuringHash, HashingCancelled, UnsafeSourcePath


BUFFER_SIZE = 8 * 1024 * 1024
RANGE_RE = re.compile(r"^(?:bytes=)?(\d+)-(\d+)$", re.IGNORECASE)


def resolve_source_path(root: str, relative_path: str) -> Path:
    """Resolve a qB relative path without allowing it to escape save_path."""
    if not root or not relative_path:
        raise UnsafeSourcePath("下载保存目录或相对路径为空")
    root_path = Path(root).expanduser().resolve(strict=True)
    candidate = (root_path / Path(relative_path)).resolve(strict=True)
    try:
        candidate.relative_to(root_path)
    except ValueError as exc:
        raise UnsafeSourcePath("文件路径越过下载保存目录") from exc
    if not candidate.is_file():
        raise FileNotFoundError(str(candidate))
    return candidate


def resolve_snapshot_path(
    save_path: str,
    content_path: str,
    relative_path: str,
    absolute_path: str = "",
) -> Path:
    """Resolve qB file paths across Original/Subfolder/NoSubfolder layouts.

    Depending on qB content layout and MoviePilot path mapping, ``save_path``
    can be either the download parent or the torrent content directory while
    the file name can still include the torrent directory.  Try the explicit
    snapshot, save path and content path variants, then require the result to
    remain inside one of the qB-provided roots.
    """
    relative = Path(str(relative_path or "").replace("\\", "/"))
    if not relative.parts or relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise UnsafeSourcePath("qB 文件相对路径不安全")

    save = Path(str(save_path or "")).expanduser() if save_path else None
    content = Path(str(content_path or "")).expanduser() if content_path else None
    candidates = []

    def add(candidate: Optional[Path]) -> None:
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    if absolute_path:
        add(Path(str(absolute_path)).expanduser())
    if save:
        add(save.joinpath(*relative.parts))
        if len(relative.parts) > 1 and relative.parts[0] == save.name:
            add(save.joinpath(*relative.parts[1:]))
    if content:
        if content.is_file():
            add(content)
        else:
            add(content.joinpath(*relative.parts))
            if len(relative.parts) > 1 and relative.parts[0] == content.name:
                add(content.joinpath(*relative.parts[1:]))
            add(content / relative.name)

    allowed_roots = []
    for root in (save, content.parent if content and content.is_file() else content):
        if not root:
            continue
        try:
            resolved_root = root.resolve(strict=True)
        except (FileNotFoundError, OSError):
            continue
        if resolved_root.is_dir() and resolved_root not in allowed_roots:
            allowed_roots.append(resolved_root)

    attempted = []
    for candidate in candidates:
        attempted.append(str(candidate))
        try:
            resolved = candidate.resolve(strict=True)
        except (FileNotFoundError, OSError):
            continue
        if not resolved.is_file():
            continue
        if not allowed_roots:
            raise UnsafeSourcePath("qB 保存目录和内容目录均不可访问")
        if any(_is_within(resolved, root) for root in allowed_roots):
            return resolved
    raise FileNotFoundError("；尝试路径=" + " | ".join(attempted))


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def sha1_file(
    path: Path,
    expected_size: Optional[int] = None,
    cancelled: Optional[Callable[[], bool]] = None,
) -> Tuple[str, int, int]:
    before = path.stat()
    if expected_size is not None and expected_size >= 0 and before.st_size != expected_size:
        raise FileChangedDuringHash(
            f"文件大小与 qB 快照不一致：expected={expected_size}, actual={before.st_size}"
        )
    digest = hashlib.sha1()
    with path.open("rb") as stream:
        while True:
            if cancelled and cancelled():
                raise HashingCancelled("任务已被取消")
            chunk = stream.read(BUFFER_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise FileChangedDuringHash("文件在 SHA1 计算期间发生变化")
    return digest.hexdigest().upper(), after.st_size, after.st_mtime_ns


def sha1_range(
    path: Path,
    sign_check: str,
    cancelled: Optional[Callable[[], bool]] = None,
) -> str:
    """Calculate the exact byte-range SHA1 requested by 115's second check."""
    match = RANGE_RE.fullmatch(str(sign_check or "").strip())
    if not match:
        raise ValueError(f"115 返回了无效的范围校验参数：{sign_check!r}")
    start, end = int(match.group(1)), int(match.group(2))
    size = path.stat().st_size
    if start < 0 or end < start or end >= size:
        raise ValueError(f"115 范围校验越界：{start}-{end}/{size}")
    remaining = end - start + 1
    digest = hashlib.sha1()
    with path.open("rb") as stream:
        stream.seek(start, os.SEEK_SET)
        while remaining:
            if cancelled and cancelled():
                raise HashingCancelled("任务已被取消")
            chunk = stream.read(min(BUFFER_SIZE, remaining))
            if not chunk:
                raise IOError("读取 115 范围校验数据时提前到达文件末尾")
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest().upper()
