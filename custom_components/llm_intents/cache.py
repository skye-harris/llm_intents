import os
import sqlite3
import hashlib
import json
import time
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)


class SQLiteCache:
    _instance = None
    DEFAULT_MAX_AGE = 43200  # 12 hours

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_db()
        return cls._instance

    def _init_db(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))  # this file’s directory
        db_path = os.path.join(base_dir, "cache.db")
        os.makedirs(base_dir, exist_ok=True)  # ensure folder exists

        self._conn = sqlite3.connect(db_path)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL UNIQUE,
                expires_at INTEGER NOT NULL,
                data TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def _make_key(self, tool: str, params: Optional[dict]) -> str:
        params_str = (
            ""
            if params is None
            else json.dumps(params, sort_keys=True, separators=(",", ":"))
        )
        combined = tool + params_str
        return hashlib.md5(combined.encode()).hexdigest()

    def _cleanup(self):
        now = int(time.time())
        deleted = self._conn.execute(
            "DELETE FROM cache WHERE expires_at < ?", (now,)
        ).rowcount
        self._conn.commit()
        if deleted:
            logger.debug(f"Cache cleanup ran, deleted {deleted} expired entries")

    def get(self, tool: str, params: Optional[dict]) -> Optional[Any]:
        self._cleanup()
        key = self._make_key(tool, params)
        cursor = self._conn.execute("SELECT data FROM cache WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row:
            logger.debug(f"Cache hit for tool: {tool} Params: {params}")
            try:
                return json.loads(row[0])
            except json.JSONDecodeError:
                logger.warning(
                    f"Failed to decode cached data for tool: {tool} Params: {params}"
                )
                return None
        else:
            logger.debug(f"Cache miss for tool: {tool} Params: {params}")
            return None

    def set(
        self,
        tool: str,
        params: Optional[dict],
        data: Any,
        max_age_seconds: int = DEFAULT_MAX_AGE,
    ):
        key = self._make_key(tool, params)
        expires_at = int(time.time()) + max_age_seconds
        data_json = json.dumps(data)
        self._conn.execute(
            """
            INSERT INTO cache (key, expires_at, data)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                expires_at=excluded.expires_at,
                data=excluded.data
        """,
            (key, expires_at, data_json),
        )
        self._conn.commit()
