"""Tests for the SQLite cache module."""

import json
import sqlite3
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from custom_components.llm_intents.cache import SQLiteCache


class _InMemoryCache(SQLiteCache):
    """SQLiteCache subclass that uses in-memory SQLite."""

    def _init_db(self) -> None:
        """Override _init_db to use in-memory SQLite."""
        self._conn = sqlite3.connect(":memory:")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL UNIQUE,
                created_at INTEGER NOT NULL,
                data TEXT NOT NULL
            )
        """)
        self._conn.commit()


def _reset_cache_singleton() -> None:
    """Reset the singleton state for both SQLiteCache and _InMemoryCache."""
    SQLiteCache._instance = None
    SQLiteCache._conn = None
    _InMemoryCache._instance = None
    _InMemoryCache._conn = None


@pytest.fixture
def sqlite_cache() -> SQLiteCache:
    """Reset singleton and use in-memory SQLite for each test."""
    _reset_cache_singleton()
    cache = _InMemoryCache()
    yield cache
    # Teardown: close connection and reset singleton
    if cache._conn is not None:
        cache._conn.close()
    _reset_cache_singleton()


def _make_mock_path(exists: bool) -> tuple:
    """
    Create mocks for Path class and instance for _init_db testing.

    Returns (path_class_mock, path_instance_mock) tuple.
    """
    path_instance = MagicMock(spec=Path)
    path_instance.exists.return_value = exists
    path_instance.__truediv__ = lambda _self, _other: path_instance

    path_class = MagicMock(return_value=path_instance)
    path_class.mkdir = MagicMock()
    path_class.exists = MagicMock(return_value=exists)
    path_class.unlink = MagicMock()

    return path_class, path_instance


class TestMakeKey:
    """Test cache key generation."""

    @pytest.mark.parametrize(
        ("tool", "params", "expected_len"),
        [
            ("weather", {"location": "London"}, 32),
            ("weather", None, 32),
            ("search", {"query": "test"}, 32),
            ("search", {}, 32),
            ("calculator", {"expression": "2+2"}, 32),
        ],
    )
    def test_make_key_length(
        self,
        sqlite_cache: SQLiteCache,
        tool: str,
        params: dict | None,
        expected_len: int,
    ) -> None:
        """Cache keys are 32-character hex digests."""
        key = sqlite_cache._make_key(tool, params)
        assert len(key) == expected_len
        assert all(c in "0123456789abcdef" for c in key)

    def test_make_key_different_params_different_key(
        self, sqlite_cache: SQLiteCache
    ) -> None:
        """Different params produce different keys."""
        key1 = sqlite_cache._make_key("weather", {"location": "London"})
        key2 = sqlite_cache._make_key("weather", {"location": "Paris"})
        assert key1 != key2

    def test_make_key_none_vs_empty_dict_different(
        self, sqlite_cache: SQLiteCache
    ) -> None:
        """params=None and params={} produce different keys."""
        key_none = sqlite_cache._make_key("weather", None)
        key_empty = sqlite_cache._make_key("weather", {})
        assert key_none != key_empty

    def test_make_key_same_params_same_key(self, sqlite_cache: SQLiteCache) -> None:
        """Same tool+params always produce the same key."""
        params = {"query": "hello world", "count": 5}
        key1 = sqlite_cache._make_key("search", params)
        key2 = sqlite_cache._make_key("search", params)
        assert key1 == key2


class TestSetGet:
    """Test set and get operations."""

    @pytest.mark.parametrize(
        ("tool", "params", "data", "expected"),
        [
            (
                "weather",
                {"location": "London"},
                {"temp": 20, "unit": "C"},
                {"temp": 20, "unit": "C"},
            ),
            (
                "search",
                {"query": "test"},
                [{"title": "Result 1"}],
                [{"title": "Result 1"}],
            ),
            ("calculator", {"expression": "2+2"}, 4, 4),
            (
                "youtube",
                {"video_id": "abc"},
                {"title": "Test Video"},
                {"title": "Test Video"},
            ),
        ],
    )
    def test_set_get_hit(
        self,
        sqlite_cache: SQLiteCache,
        tool: str,
        params: dict | None,
        data: dict,
        expected: Any,
    ) -> None:
        """Setting a value allows retrieving it."""
        sqlite_cache.set(tool, params, data)
        result = sqlite_cache.get(tool, params)
        assert result == expected

    @pytest.mark.parametrize(
        ("tool", "params"),
        [
            ("weather", {"location": "London"}),
            ("search", {"query": "test"}),
            ("calculator", None),
        ],
    )
    def test_get_miss(
        self, sqlite_cache: SQLiteCache, tool: str, params: dict | None
    ) -> None:
        """Getting a non-existent key returns None."""
        assert sqlite_cache.get(tool, params) is None

    def test_none_vs_empty_dict_not_hit(self, sqlite_cache: SQLiteCache) -> None:
        """params=None and params={} are different cache keys."""
        sqlite_cache.set("weather", None, {"temp": 20})
        assert sqlite_cache.get("weather", None) == {"temp": 20}
        assert sqlite_cache.get("weather", {}) is None
        sqlite_cache.set("weather", {}, {"temp": 21})
        assert sqlite_cache.get("weather", {}) == {"temp": 21}
        assert sqlite_cache.get("weather", None) == {"temp": 20}

    def test_upsert_overwrites(self, sqlite_cache: SQLiteCache) -> None:
        """Setting the same key twice updates the value."""
        sqlite_cache.set("weather", {"location": "London"}, {"temp": 20})
        sqlite_cache.set("weather", {"location": "London"}, {"temp": 25})
        result = sqlite_cache.get("weather", {"location": "London"})
        assert result == {"temp": 25}

    def test_different_tools_different_keys(self, sqlite_cache: SQLiteCache) -> None:
        """Same params with different tools don't collide."""
        sqlite_cache.set("weather", {"location": "London"}, {"temp": 20})
        sqlite_cache.set("search", {"location": "London"}, {"results": []})
        assert sqlite_cache.get("weather", {"location": "London"}) == {"temp": 20}
        assert sqlite_cache.get("search", {"location": "London"}) == {"results": []}

    def test_complex_nested_data(self, sqlite_cache: SQLiteCache) -> None:
        """Complex nested structures round-trip correctly."""
        data = {
            "locations": [
                {"city": "London", "forecast": [{"day": "Mon", "temp": 15}]},
                {"city": "Paris", "forecast": [{"day": "Mon", "temp": 18}]},
            ],
            "metadata": {"units": "C", "updated": True},
        }
        sqlite_cache.set("weather", {"location": "Europe"}, data)
        result = sqlite_cache.get("weather", {"location": "Europe"})
        assert result == data

    def test_list_data(self, sqlite_cache: SQLiteCache) -> None:
        """Storing a list as data works."""
        data = ["item1", "item2", "item3"]
        sqlite_cache.set("search", {"query": "test"}, data)
        result = sqlite_cache.get("search", {"query": "test"})
        assert result == data


class TestTTL:
    """Test cache TTL/expiration behavior."""

    def test_get_expired_entry(self, sqlite_cache: SQLiteCache) -> None:
        """Entries older than DEFAULT_MAX_AGE are returned as None."""
        key = sqlite_cache._make_key("weather", {"location": "London"})
        old_time = int(time.time()) - SQLiteCache.DEFAULT_MAX_AGE - 100
        sqlite_cache._conn.execute(
            "INSERT OR REPLACE INTO cache (key, created_at, data) VALUES (?, ?, ?)",
            (key, old_time, json.dumps({"temp": 20})),
        )
        sqlite_cache._conn.commit()
        assert sqlite_cache.get("weather", {"location": "London"}) is None

    def test_get_non_expired_entry(self, sqlite_cache: SQLiteCache) -> None:
        """Fresh entries are returned."""
        sqlite_cache.set("weather", {"location": "London"}, {"temp": 20})
        result = sqlite_cache.get("weather", {"location": "London"})
        assert result == {"temp": 20}

    def test_manually_inserted_future_entry(self, sqlite_cache: SQLiteCache) -> None:
        """Manually inserted row with future created_at survives cleanup."""
        key = sqlite_cache._make_key("weather", {"location": "London"})
        future_time = int(time.time()) + 10000
        sqlite_cache._conn.execute(
            "INSERT OR REPLACE INTO cache (key, created_at, data) VALUES (?, ?, ?)",
            (key, future_time, json.dumps({"temp": 20})),
        )
        sqlite_cache._conn.commit()
        assert sqlite_cache.get("weather", {"location": "London"}) == {"temp": 20}


class TestCleanup:
    """Test cache cleanup of expired entries."""

    def test_cleanup_removes_expired(self, sqlite_cache: SQLiteCache) -> None:
        """Cleanup removes only expired entries."""
        now = int(time.time())
        sqlite_cache._conn.execute(
            "INSERT OR REPLACE INTO cache (key, created_at, data) VALUES (?, ?, ?)",
            (
                sqlite_cache._make_key("old", {"x": 1}),
                now - 8000,
                json.dumps({"old": True}),
            ),
        )
        sqlite_cache._conn.execute(
            "INSERT OR REPLACE INTO cache (key, created_at, data) VALUES (?, ?, ?)",
            (
                sqlite_cache._make_key("fresh", {"x": 2}),
                now - 100,
                json.dumps({"fresh": True}),
            ),
        )
        sqlite_cache._conn.commit()
        sqlite_cache._cleanup()
        assert sqlite_cache.get("old", {"x": 1}) is None
        assert sqlite_cache.get("fresh", {"x": 2}) == {"fresh": True}

    def test_cleanup_no_expired(self, sqlite_cache: SQLiteCache) -> None:
        """Cleanup does nothing when no entries are expired."""
        sqlite_cache.set("weather", {"location": "London"}, {"temp": 20})
        sqlite_cache._cleanup()
        assert sqlite_cache.get("weather", {"location": "London"}) == {"temp": 20}

    def test_cleanup_removes_all_expired(self, sqlite_cache: SQLiteCache) -> None:
        """Cleanup removes all expired entries."""
        now = int(time.time())
        sqlite_cache._conn.execute(
            "INSERT OR REPLACE INTO cache (key, created_at, data) VALUES (?, ?, ?)",
            (sqlite_cache._make_key("old1", {}), now - 9000, json.dumps({"a": 1})),
        )
        sqlite_cache._conn.execute(
            "INSERT OR REPLACE INTO cache (key, created_at, data) VALUES (?, ?, ?)",
            (sqlite_cache._make_key("old2", {}), now - 9000, json.dumps({"b": 2})),
        )
        sqlite_cache._conn.execute(
            "INSERT OR REPLACE INTO cache (key, created_at, data) VALUES (?, ?, ?)",
            (sqlite_cache._make_key("fresh", {}), now - 100, json.dumps({"c": 3})),
        )
        sqlite_cache._conn.commit()
        sqlite_cache._cleanup()
        assert sqlite_cache.get("old1", {}) is None
        assert sqlite_cache.get("old2", {}) is None
        assert sqlite_cache.get("fresh", {}) == {"c": 3}


class TestErrorHandling:
    """Test error handling in cache operations."""

    def test_get_corrupt_json_returns_none(self, sqlite_cache: SQLiteCache) -> None:
        """Corrupt JSON in cache returns None instead of raising."""
        key = sqlite_cache._make_key("weather", {"location": "London"})
        sqlite_cache._conn.execute(
            "INSERT OR REPLACE INTO cache (key, created_at, data) VALUES (?, ?, ?)",
            (key, int(time.time()), "not valid json{{{"),
        )
        sqlite_cache._conn.commit()
        assert sqlite_cache.get("weather", {"location": "London"}) is None

    def test_get_corrupt_json_does_not_affect_other_entries(
        self, sqlite_cache: SQLiteCache
    ) -> None:
        """Corrupt entry doesn't affect other cache entries."""
        sqlite_cache.set("weather", {"location": "London"}, {"temp": 20})
        corrupt_key = sqlite_cache._make_key("weather", {"location": "Paris"})
        sqlite_cache._conn.execute(
            "INSERT OR REPLACE INTO cache (key, created_at, data) VALUES (?, ?, ?)",
            (corrupt_key, int(time.time()), "corrupt data"),
        )
        sqlite_cache._conn.commit()
        assert sqlite_cache.get("weather", {"location": "Paris"}) is None
        assert sqlite_cache.get("weather", {"location": "London"}) == {"temp": 20}


class TestIdempotency:
    """Test cache idempotency and consistency."""

    def test_double_set_same_key(self, sqlite_cache: SQLiteCache) -> None:
        """Two sets with the same key result in a single row with latest value."""
        sqlite_cache.set("weather", {"location": "London"}, {"temp": 20})
        sqlite_cache.set("weather", {"location": "London"}, {"temp": 25})
        result = sqlite_cache.get("weather", {"location": "London"})
        assert result == {"temp": 25}
        count = sqlite_cache._conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        assert count == 1

    def test_get_after_set_consistent(self, sqlite_cache: SQLiteCache) -> None:
        """Get immediately after set returns the set value."""
        data = {"key": "value", "nested": {"a": 1, "b": [1, 2, 3]}}
        sqlite_cache.set("test", {"param": "x"}, data)
        assert sqlite_cache.get("test", {"param": "x"}) == data

    def test_singleton_reset(self) -> None:
        """Resetting singleton creates a fresh in-memory instance."""
        _reset_cache_singleton()
        cache1 = _InMemoryCache()
        conn1 = cache1._conn
        _reset_cache_singleton()
        cache1._conn.close()
        cache2 = _InMemoryCache()
        conn2 = cache2._conn
        assert conn1 is not conn2


@pytest.fixture
def sqlite_cache_reset() -> None:
    """Reset singleton for tests that need a fresh SQLiteCache instance."""
    _reset_cache_singleton()
    yield
    _reset_cache_singleton()


class TestInitDB:
    """Test _init_db with mocked filesystem."""

    def test_init_db_creates_table_and_connects(self, sqlite_cache_reset: None) -> None:
        """_init_db creates the table and connects to the DB."""
        path_class, _path_instance = _make_mock_path(exists=False)
        mock_conn = MagicMock()
        with (
            patch("custom_components.llm_intents.cache.Path", path_class),
            patch(
                "custom_components.llm_intents.cache.sqlite3.connect",
                return_value=mock_conn,
            ),
        ):
            _cache = SQLiteCache()
            path_class.mkdir.assert_called_once()
            path_class.unlink.assert_not_called()
            sqlite3.connect.assert_called_once()
            mock_conn.execute.assert_called()
            mock_conn.commit.assert_called_once()

    def test_init_db_deletes_existing_db(self, sqlite_cache_reset: None) -> None:
        """_init_db deletes the DB file if it already exists."""
        path_class, _path_instance = _make_mock_path(exists=True)
        mock_conn = MagicMock()
        with (
            patch("custom_components.llm_intents.cache.Path", path_class),
            patch(
                "custom_components.llm_intents.cache.sqlite3.connect",
                return_value=mock_conn,
            ),
        ):
            _cache = SQLiteCache()
            path_class.unlink.assert_called_once()

    def test_init_db_skips_delete_when_missing(self, sqlite_cache_reset: None) -> None:
        """_init_db does not try to delete when DB file is absent."""
        path_class, _path_instance = _make_mock_path(exists=False)
        mock_conn = MagicMock()
        with (
            patch("custom_components.llm_intents.cache.Path", path_class),
            patch(
                "custom_components.llm_intents.cache.sqlite3.connect",
                return_value=mock_conn,
            ),
        ):
            _cache = SQLiteCache()
            path_class.unlink.assert_not_called()
