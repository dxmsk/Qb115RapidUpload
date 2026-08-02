import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .models import FileSnapshot, TaskStatus, TERMINAL_TASK_STATUSES


NONTERMINAL = (
    TaskStatus.WATCHING.value,
    TaskStatus.WAITING.value,
    TaskStatus.PROCESSING.value,
    TaskStatus.RETRY_WAIT.value,
)


class ClosingConnection(sqlite3.Connection):
    """Commit or roll back a transaction, then release the SQLite handle."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TaskRepository:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self.db_path),
            timeout=5,
            check_same_thread=False,
            factory=ClosingConnection,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _init_db(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    downloader TEXT NOT NULL,
                    download_hash TEXT NOT NULL,
                    torrent_name TEXT NOT NULL DEFAULT '',
                    save_path TEXT NOT NULL DEFAULT '',
                    content_path TEXT NOT NULL DEFAULT '',
                    target_cid TEXT NOT NULL DEFAULT '0',
                    status TEXT NOT NULL,
                    reason_code TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    next_retry_at TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    last_error_code TEXT,
                    last_error_message TEXT,
                    organized_result TEXT,
                    transfer_history_id INTEGER,
                    detected_at TEXT,
                    completed_at TEXT,
                    organized_at TEXT,
                    rapid_uploaded_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 0,
                    UNIQUE (downloader, download_hash)
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_due
                ON tasks(status, next_retry_at);

                CREATE TABLE IF NOT EXISTS task_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    relative_path TEXT NOT NULL,
                    absolute_path TEXT NOT NULL,
                    remote_relative_dir TEXT NOT NULL DEFAULT '',
                    expected_size INTEGER NOT NULL,
                    observed_size INTEGER,
                    observed_mtime_ns INTEGER,
                    sha1 TEXT,
                    status TEXT NOT NULL DEFAULT 'WAITING',
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    remote_file_id TEXT,
                    last_error_code TEXT,
                    last_error_message TEXT,
                    uploaded_at TEXT,
                    UNIQUE (task_id, relative_path)
                );

                CREATE INDEX IF NOT EXISTS idx_task_files_status
                ON task_files(task_id, status);

                CREATE TABLE IF NOT EXISTS task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL,
                    old_status TEXT,
                    new_status TEXT,
                    detail_json TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            db_version = connection.execute("PRAGMA user_version").fetchone()[0]
            if db_version < 2:
                # v0.1 scanned every historical qB completion. Do not carry that
                # automatically-created backlog into the incremental detector.
                connection.execute(
                    """UPDATE tasks SET status='CANCELLED',reason_code='LEGACY_BULK_SCAN_RESET',
                           cancel_requested=1,last_error_message='升级后已停止旧版全量扫描任务',
                           next_retry_at=NULL,updated_at=?,version=version+1
                       WHERE status IN ('WAITING','PROCESSING','RETRY_WAIT')""",
                    (utcnow(),),
                )
                connection.execute("PRAGMA user_version = 2")
            now = utcnow()
            rows = connection.execute(
                "SELECT id, status FROM tasks WHERE status = ?",
                (TaskStatus.PROCESSING.value,),
            ).fetchall()
            for row in rows:
                connection.execute(
                    """UPDATE tasks
                       SET status=?, next_retry_at=?, last_error_code=?, last_error_message=?,
                           updated_at=?, version=version+1
                       WHERE id=?""",
                    (
                        TaskStatus.RETRY_WAIT.value,
                        now,
                        "PROCESS_INTERRUPTED",
                        "插件重启，恢复未完成的秒传任务",
                        now,
                        row["id"],
                    ),
                )
                self._event(connection, row["id"], "RECOVER", row["status"], TaskStatus.RETRY_WAIT.value)

    @staticmethod
    def _event(
        connection: sqlite3.Connection,
        task_id: Optional[int],
        event_type: str,
        old_status: Optional[str] = None,
        new_status: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        connection.execute(
            """INSERT INTO task_events(task_id,event_type,old_status,new_status,detail_json,created_at)
               VALUES(?,?,?,?,?,?)""",
            (
                task_id,
                event_type,
                old_status,
                new_status,
                json.dumps(detail or {}, ensure_ascii=False, default=str)[:4000],
                utcnow(),
            ),
        )

    def register_watching(self, downloader: str, download_hash: str, torrent_name: str = "") -> int:
        now = utcnow()
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT INTO tasks(
                       downloader, download_hash, torrent_name, status, detected_at, created_at, updated_at
                   ) VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(downloader, download_hash) DO UPDATE SET
                       torrent_name=CASE WHEN excluded.torrent_name <> '' THEN excluded.torrent_name ELSE tasks.torrent_name END,
                       updated_at=excluded.updated_at""",
                (
                    downloader,
                    download_hash.lower(),
                    torrent_name or "",
                    TaskStatus.WATCHING.value,
                    now,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT id FROM tasks WHERE downloader=? AND download_hash=?",
                (downloader, download_hash.lower()),
            ).fetchone()
            return int(row["id"])

    def watching_tasks(self) -> List[Dict[str, Any]]:
        now = utcnow()
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """SELECT id,downloader,download_hash,torrent_name,next_retry_at
                   FROM tasks
                   WHERE status='WATCHING' AND cancel_requested=0
                     AND (next_retry_at IS NULL OR next_retry_at <= ?)
                   ORDER BY id""",
                (now,),
            ).fetchall()
            return [dict(row) for row in rows]

    def schedule_watch_retry(self, task_id: int, minutes: int, message: str) -> bool:
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat(timespec="seconds")
        retry_at = (now_dt + timedelta(minutes=max(1, int(minutes)))).isoformat(timespec="seconds")
        with self._lock, self._connect() as connection:
            return bool(
                connection.execute(
                    """UPDATE tasks SET next_retry_at=?,last_error_code='QB_FILE_LIST_ERROR',
                           last_error_message=?,updated_at=?,version=version+1
                       WHERE id=? AND status='WATCHING' AND cancel_requested=0""",
                    (retry_at, (message or "qB 文件列表读取失败")[:1000], now, task_id),
                ).rowcount
            )

    def snapshot_completed(
        self,
        downloader: str,
        download_hash: str,
        torrent_name: str,
        save_path: str,
        content_path: str,
        target_cid: str,
        files: Iterable[FileSnapshot],
        organized: bool = False,
    ) -> Optional[int]:
        snapshots = list(files)
        if not snapshots:
            return None
        now = utcnow()
        new_status = TaskStatus.ABANDONED_ORGANIZED.value if organized else TaskStatus.WAITING.value
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO tasks(
                       downloader,download_hash,torrent_name,save_path,content_path,target_cid,status,
                       detected_at,completed_at,organized_at,reason_code,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(downloader,download_hash) DO NOTHING""",
                (
                    downloader,
                    download_hash.lower(),
                    torrent_name or "",
                    save_path,
                    content_path or "",
                    str(target_cid or "0"),
                    new_status,
                    now,
                    now,
                    now if organized else None,
                    "ORGANIZED" if organized else None,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM tasks WHERE downloader=? AND download_hash=?",
                (downloader, download_hash.lower()),
            ).fetchone()
            if not row:
                return None
            task_id = int(row["id"])
            old_status = row["status"]
            if old_status in TERMINAL_TASK_STATUSES:
                return task_id
            connection.execute(
                """UPDATE tasks SET torrent_name=?, save_path=?, content_path=?, target_cid=?,
                       status=?, completed_at=COALESCE(completed_at,?), organized_at=?, reason_code=?,
                       cancel_requested=?, next_retry_at=NULL,last_error_code=NULL,last_error_message=NULL,
                       updated_at=?, version=version+1
                   WHERE id=?""",
                (
                    torrent_name or row["torrent_name"],
                    save_path,
                    content_path or "",
                    str(target_cid or "0"),
                    new_status,
                    now,
                    now if organized else None,
                    "ORGANIZED" if organized else None,
                    1 if organized else 0,
                    now,
                    task_id,
                ),
            )
            for item in snapshots:
                connection.execute(
                    """INSERT INTO task_files(
                           task_id,relative_path,absolute_path,remote_relative_dir,expected_size,status
                       ) VALUES(?,?,?,?,?,'WAITING')
                       ON CONFLICT(task_id,relative_path) DO UPDATE SET
                           absolute_path=excluded.absolute_path,
                           remote_relative_dir=excluded.remote_relative_dir,
                           expected_size=excluded.expected_size""",
                    (
                        task_id,
                        item.relative_path,
                        item.absolute_path,
                        item.remote_relative_dir,
                        item.expected_size,
                    ),
                )
            self._event(connection, task_id, "DOWNLOAD_COMPLETED", old_status, new_status)
            return task_id

    def mark_organized(
        self,
        downloader: str,
        download_hash: str,
        result: str,
        transfer_history_id: Optional[int] = None,
    ) -> bool:
        now = utcnow()
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT id,status FROM tasks WHERE downloader=? AND download_hash=?",
                (downloader, download_hash.lower()),
            ).fetchone()
            if not row:
                connection.execute(
                    """INSERT INTO tasks(
                           downloader,download_hash,status,reason_code,cancel_requested,organized_result,
                           transfer_history_id,organized_at,created_at,updated_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        downloader,
                        download_hash.lower(),
                        TaskStatus.ABANDONED_ORGANIZED.value,
                        "ORGANIZED",
                        1,
                        result,
                        transfer_history_id,
                        now,
                        now,
                        now,
                    ),
                )
                return True
            if row["status"] in TERMINAL_TASK_STATUSES:
                return False
            updated = connection.execute(
                f"""UPDATE tasks SET status=?,reason_code=?,cancel_requested=1,organized_result=?,
                           transfer_history_id=?,organized_at=?,updated_at=?,version=version+1
                       WHERE id=? AND status IN ({','.join('?' for _ in NONTERMINAL)})""",
                (
                    TaskStatus.ABANDONED_ORGANIZED.value,
                    "ORGANIZED",
                    result,
                    transfer_history_id,
                    now,
                    now,
                    row["id"],
                    *NONTERMINAL,
                ),
            ).rowcount
            if updated:
                self._event(
                    connection,
                    row["id"],
                    "ORGANIZED",
                    row["status"],
                    TaskStatus.ABANDONED_ORGANIZED.value,
                    {"result": result},
                )
            return bool(updated)

    def due_tasks(self, limit: int = 2) -> List[Dict[str, Any]]:
        now = utcnow()
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM tasks
                   WHERE cancel_requested=0 AND (
                       status='WAITING' OR (status='RETRY_WAIT' AND (next_retry_at IS NULL OR next_retry_at <= ?))
                   ) ORDER BY COALESCE(next_retry_at, completed_at, created_at) LIMIT ?""",
                (now, max(1, int(limit))),
            ).fetchall()
            return [dict(row) for row in rows]

    def claim(self, task_id: int) -> bool:
        now = utcnow()
        with self._lock, self._connect() as connection:
            return bool(
                connection.execute(
                    """UPDATE tasks SET status='PROCESSING',attempt_count=attempt_count+1,
                           updated_at=?,version=version+1
                       WHERE id=? AND status IN ('WAITING','RETRY_WAIT') AND cancel_requested=0""",
                    (now, task_id),
                ).rowcount
            )

    def task(self, task_id: int) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            return dict(row) if row else None

    def files(self, task_id: int) -> List[Dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM task_files WHERE task_id=? ORDER BY id", (task_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def is_cancel_requested(self, task_id: int) -> bool:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT cancel_requested,status FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
            return not row or bool(row["cancel_requested"]) or row["status"] != TaskStatus.PROCESSING.value

    def update_file_hash(self, file_id: int, sha1: str, size: int, mtime_ns: int) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """UPDATE task_files SET sha1=?,observed_size=?,observed_mtime_ns=?,
                       last_error_code=NULL,last_error_message=NULL WHERE id=?""",
                (sha1, size, mtime_ns, file_id),
            )

    def mark_file_success(self, file_id: int, remote_file_id: Optional[str] = None) -> None:
        now = utcnow()
        with self._lock, self._connect() as connection:
            connection.execute(
                """UPDATE task_files SET status='SUCCESS',attempt_count=attempt_count+1,
                       remote_file_id=?,last_error_code=NULL,last_error_message=NULL,uploaded_at=? WHERE id=?""",
                (remote_file_id, now, file_id),
            )

    def schedule_retry(self, task_id: int, minutes: int, code: str, message: str) -> bool:
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat(timespec="seconds")
        retry_at = (now_dt + timedelta(minutes=max(1, int(minutes)))).isoformat(timespec="seconds")
        safe_message = (message or "")[:1000]
        with self._lock, self._connect() as connection:
            updated = connection.execute(
                """UPDATE tasks SET status='RETRY_WAIT',next_retry_at=?,last_error_code=?,
                       last_error_message=?,updated_at=?,version=version+1
                   WHERE id=? AND status='PROCESSING' AND cancel_requested=0""",
                (retry_at, code, safe_message, now, task_id),
            ).rowcount
            if updated:
                connection.execute(
                    """UPDATE task_files SET last_error_code=?,last_error_message=?
                       WHERE task_id=? AND status<>'SUCCESS'""",
                    (code, safe_message, task_id),
                )
                self._event(connection, task_id, "RETRY", TaskStatus.PROCESSING.value, TaskStatus.RETRY_WAIT.value,
                            {"code": code, "retry_at": retry_at})
            return bool(updated)

    def mark_success(self, task_id: int) -> bool:
        now = utcnow()
        with self._lock, self._connect() as connection:
            waiting = connection.execute(
                "SELECT COUNT(*) AS count FROM task_files WHERE task_id=? AND status<>'SUCCESS'",
                (task_id,),
            ).fetchone()["count"]
            if waiting:
                return False
            updated = connection.execute(
                """UPDATE tasks SET status='SUCCESS',rapid_uploaded_at=?,next_retry_at=NULL,
                       last_error_code=NULL,last_error_message=NULL,updated_at=?,version=version+1
                   WHERE id=? AND status='PROCESSING' AND cancel_requested=0""",
                (now, now, task_id),
            ).rowcount
            if updated:
                self._event(connection, task_id, "RAPID_UPLOAD_SUCCESS", TaskStatus.PROCESSING.value,
                            TaskStatus.SUCCESS.value)
            return bool(updated)

    def abandon_missing(self, task_id: int, relative_path: str) -> bool:
        now = utcnow()
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row or row["status"] in TERMINAL_TASK_STATUSES:
                return False
            updated = connection.execute(
                """UPDATE tasks SET status='ABANDONED_SOURCE_MISSING',reason_code='SOURCE_MISSING',
                       cancel_requested=1,last_error_code='SOURCE_MISSING',last_error_message=?,
                       updated_at=?,version=version+1 WHERE id=? AND status IN ('WAITING','RETRY_WAIT','PROCESSING')""",
                (f"原始文件不存在：{relative_path}"[:1000], now, task_id),
            ).rowcount
            if updated:
                self._event(connection, task_id, "SOURCE_MISSING", row["status"],
                            TaskStatus.ABANDONED_SOURCE_MISSING.value, {"path": relative_path})
            return bool(updated)

    def cancel(
        self,
        task_id: int,
        reason: str = "手动取消",
        reason_code: str = "MANUAL_CANCEL",
    ) -> bool:
        now = utcnow()
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row or row["status"] in TERMINAL_TASK_STATUSES:
                return False
            updated = connection.execute(
                f"""UPDATE tasks SET status='CANCELLED',reason_code=?,cancel_requested=1,
                       last_error_message=?,updated_at=?,version=version+1
                   WHERE id=? AND status IN ({','.join('?' for _ in NONTERMINAL)})""",
                (reason_code, (reason or "手动取消")[:1000], now, task_id, *NONTERMINAL),
            ).rowcount
            if updated:
                self._event(connection, task_id, "MANUAL_CANCEL", row["status"], TaskStatus.CANCELLED.value)
            return bool(updated)

    def retry_now(self, task_id: int) -> bool:
        now = utcnow()
        with self._lock, self._connect() as connection:
            return bool(
                connection.execute(
                    """UPDATE tasks SET status='RETRY_WAIT',next_retry_at=?,cancel_requested=0,
                           updated_at=?,version=version+1
                       WHERE id=? AND status IN ('WAITING','RETRY_WAIT')""",
                    (now, now, task_id),
                ).rowcount
            )

    def success_matches_path(self, source_path: str) -> bool:
        try:
            source = os.path.normcase(os.path.realpath(source_path))
        except Exception:
            return False
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """SELECT f.absolute_path FROM task_files f
                   JOIN tasks t ON t.id=f.task_id
                   WHERE t.status='SUCCESS' AND f.status='SUCCESS'"""
            ).fetchall()
        for row in rows:
            candidate = os.path.normcase(os.path.realpath(row["absolute_path"]))
            if source == candidate:
                return True
            try:
                if os.path.commonpath((source, candidate)) == source:
                    return True
            except ValueError:
                continue
        return False

    def record_intercept(self, source_path: str) -> None:
        with self._lock, self._connect() as connection:
            self._event(connection, None, "ORGANIZE_INTERCEPTED", detail={"path": source_path})

    def list_tasks(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """SELECT t.*,
                          (SELECT COUNT(*) FROM task_files f WHERE f.task_id=t.id) AS file_count,
                          (SELECT COUNT(*) FROM task_files f WHERE f.task_id=t.id AND f.status='SUCCESS') AS success_count
                   FROM tasks t ORDER BY t.id DESC LIMIT ?""",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
            return [dict(row) for row in rows]

    def successful_tasks(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """SELECT t.*,
                          (SELECT COUNT(*) FROM task_files f WHERE f.task_id=t.id) AS file_count,
                          (SELECT COALESCE(SUM(
                              CASE
                                  WHEN f.observed_size >= 0 THEN f.observed_size
                                  WHEN f.expected_size >= 0 THEN f.expected_size
                                  ELSE 0
                              END
                          ), 0) FROM task_files f WHERE f.task_id=t.id) AS total_size,
                          (SELECT GROUP_CONCAT(DISTINCT f.remote_relative_dir)
                           FROM task_files f
                           WHERE f.task_id=t.id AND f.remote_relative_dir <> '') AS remote_dirs
                   FROM tasks t
                   WHERE t.status='SUCCESS'
                   ORDER BY t.rapid_uploaded_at DESC, t.id DESC
                   LIMIT ?""",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
            return [dict(row) for row in rows]
