"""
SQLite 历史记录数据库 (遵循 python_exe_build_skill.md 规范)
WAL 模式 + 线程锁 + 原子 Upsert
"""
import sqlite3
import threading
import time
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

from src.utils.paths import get_user_data_dir


@dataclass
class HistoryRecord:
    id: Optional[int]
    text: str
    engine: str
    voice: str
    speed: float
    audio_path: str
    created_at: str
    duration_sec: float = 0.0


class HistoryDB:
    def __init__(self):
        db_dir = get_user_data_dir() / "db"
        db_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = str(db_dir / "history.db")
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._connect()

    def _connect(self):
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA busy_timeout = 5000;")
        self._conn.execute("PRAGMA synchronous = NORMAL;")
        self._create_tables()

    def _create_tables(self):
        with self._lock:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    text        TEXT NOT NULL,
                    engine      TEXT NOT NULL,
                    voice       TEXT NOT NULL,
                    speed       REAL NOT NULL DEFAULT 1.0,
                    audio_path  TEXT NOT NULL,
                    duration_sec REAL NOT NULL DEFAULT 0.0,
                    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                )
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    key         TEXT PRIMARY KEY,
                    value       TEXT NOT NULL,
                    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                )
            """)
            self._conn.commit()

    def get_setting(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM app_settings WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        with self._lock:
            self._conn.execute(
                """INSERT INTO app_settings (key, value, updated_at)
                   VALUES (?, ?, datetime('now', 'localtime'))
                   ON CONFLICT(key) DO UPDATE SET
                       value = excluded.value,
                       updated_at = excluded.updated_at""",
                (key, str(value))
            )
            self._conn.commit()

    def add_record(self, text: str, engine: str, voice: str,
                   speed: float, audio_path: str, duration_sec: float = 0.0) -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO history (text, engine, voice, speed, audio_path, duration_sec)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (text, engine, voice, speed, audio_path, duration_sec)
            )
            self._conn.commit()
            return cur.lastrowid

    def get_recent(self, limit: int = 50) -> List[HistoryRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [HistoryRecord(
            id=r["id"], text=r["text"], engine=r["engine"],
            voice=r["voice"], speed=r["speed"], audio_path=r["audio_path"],
            created_at=r["created_at"], duration_sec=r["duration_sec"]
        ) for r in rows]

    def delete_record(self, record_id: int):
        with self._lock:
            self._conn.execute("DELETE FROM history WHERE id = ?", (record_id,))
            self._conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
