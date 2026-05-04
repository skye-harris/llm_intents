"""SQLite cache."""

import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Self

logger = logging.getLogger(__name__)


class SQLiteCache:
    """Simple SQLite cache for our network requests."""

    _instance = None
    DEFAULT_MAX_AGE = 7200  # 2 hour

    def __new__(cls) -> Self:
        """Singleton."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_db()  # noqa:  SLF001
        return cls._instance

    def _init_db(self) -> None:
        """Init the DB for our cache."""
        base_dir = Path(__file__).resolve().parent
        db_path = base_dir / "cache.db"
        Path.mkdir(base_dir, exist_ok=True)  # ensure folder exists

        if Path.exists(db_path):
            # Recreate cache file when addon is initialised
            Path.unlink(db_path)

        self._conn = sqlite3.connect(db_path)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL UNIQUE,
                created_at INTEGER NOT NULL,
                data TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def _make_key(self, tool: str, params: dict | None) -> str:
        """Build our cache key from the input."""
        params_str = (
            ""
            if params is None
            else json.dumps(params, sort_keys=True, separators=(",", ":"))
        )
        combined = tool + params_str
        return hashlib.md5(combined.encode()).hexdigest()  # noqa: S324

    def _cleanup(self) -> None:
        """Remove old cached values that have expired."""
        now = int(time.time())
        cutoff = now - self.DEFAULT_MAX_AGE
        deleted = self._conn.execute(
            "DELETE FROM cache WHERE created_at < ?",
            (cutoff,),
        ).rowcount
        self._conn.commit()
        if deleted:
            logger.debug("Cache cleanup ran, deleted %d expired entries", deleted)

    def get(self, tool: str, params: dict | None) -> Any | None:
        """Get a value from the cache."""
        self._cleanup()
        key = self._make_key(tool, params)
        cursor = self._conn.execute("SELECT data FROM cache WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row:
            logger.debug("Cache hit for tool: %s Params: %s", tool, params)
            try:
                return json.loads(row[0])
            except json.JSONDecodeError:
                logger.debug(
                    "Failed to decode cached data for tool: %s Params: %s",
                    tool,
                    params,
                )
                return None
        else:
            logger.debug("Cache miss for tool: %s Params: %s", tool, params)
            return None

    def set(self, tool: str, params: dict | None, data: dict) -> None:
        """Set a value into the cache."""
        key = self._make_key(tool, params)
        created_at = int(time.time())
        data_json = json.dumps(data)
        self._conn.execute(
            """
            INSERT INTO cache (key, created_at, data)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                created_at=excluded.created_at,
                data=excluded.data
        """,
            (key, created_at, data_json),
        )
        self._conn.commit()
