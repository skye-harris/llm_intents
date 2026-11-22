"""Tests for the in-memory cache module."""

import time
from typing import Any

import pytest

from custom_components.llm_intents.cache import InMemoryCache


def _reset_cache() -> None:
    """Reset the class-level store."""
    InMemoryCache._store.clear()


@pytest.fixture
def cache() -> InMemoryCache:
    """Reset store for each test."""
    _reset_cache()
    c = InMemoryCache()
    yield c
    _reset_cache()


def _insert_expired(
    cache: InMemoryCache, tool: str, params: dict | None, data: Any, age_seconds: float
) -> None:
    """Insert an entry into the store with an old timestamp."""
    key = cache._make_key(tool, params)
    cache._store[key] = (time.time() - age_seconds, data)


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
        cache: InMemoryCache,
        tool: str,
        params: dict | None,
        expected_len: int,
    ) -> None:
        """Cache keys are 32-character hex digests."""
        key = cache._make_key(tool, params)
        assert len(key) == expected_len
        assert all(c in "0123456789abcdef" for c in key)

    def test_make_key_different_params_different_key(
        self, cache: InMemoryCache
    ) -> None:
        """Different params produce different keys."""
        key1 = cache._make_key("weather", {"location": "London"})
        key2 = cache._make_key("weather", {"location": "Paris"})
        assert key1 != key2

    def test_make_key_none_vs_empty_dict_different(self, cache: InMemoryCache) -> None:
        """params=None and params={} produce different keys."""
        key_none = cache._make_key("weather", None)
        key_empty = cache._make_key("weather", {})
        assert key_none != key_empty

    def test_make_key_same_params_same_key(self, cache: InMemoryCache) -> None:
        """Same tool+params always produce the same key."""
        params = {"query": "hello world", "count": 5}
        key1 = cache._make_key("search", params)
        key2 = cache._make_key("search", params)
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
        cache: InMemoryCache,
        tool: str,
        params: dict | None,
        data: dict,
        expected: Any,
    ) -> None:
        """Setting a value allows retrieving it."""
        cache.set(tool, params, data)
        result = cache.get(tool, params)
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
        self, cache: InMemoryCache, tool: str, params: dict | None
    ) -> None:
        """Getting a non-existent key returns None."""
        assert cache.get(tool, params) is None

    def test_none_vs_empty_dict_not_hit(self, cache: InMemoryCache) -> None:
        """params=None and params={} are different cache keys."""
        cache.set("weather", None, {"temp": 20})
        assert cache.get("weather", None) == {"temp": 20}
        assert cache.get("weather", {}) is None
        cache.set("weather", {}, {"temp": 21})
        assert cache.get("weather", {}) == {"temp": 21}
        assert cache.get("weather", None) == {"temp": 20}

    def test_upsert_overwrites(self, cache: InMemoryCache) -> None:
        """Setting the same key twice updates the value."""
        cache.set("weather", {"location": "London"}, {"temp": 20})
        cache.set("weather", {"location": "London"}, {"temp": 25})
        result = cache.get("weather", {"location": "London"})
        assert result == {"temp": 25}

    def test_different_tools_different_keys(self, cache: InMemoryCache) -> None:
        """Same params with different tools don't collide."""
        cache.set("weather", {"location": "London"}, {"temp": 20})
        cache.set("search", {"location": "London"}, {"results": []})
        assert cache.get("weather", {"location": "London"}) == {"temp": 20}
        assert cache.get("search", {"location": "London"}) == {"results": []}

    def test_complex_nested_data(self, cache: InMemoryCache) -> None:
        """Complex nested structures round-trip correctly."""
        data = {
            "locations": [
                {"city": "London", "forecast": [{"day": "Mon", "temp": 15}]},
                {"city": "Paris", "forecast": [{"day": "Mon", "temp": 18}]},
            ],
            "metadata": {"units": "C", "updated": True},
        }
        cache.set("weather", {"location": "Europe"}, data)
        result = cache.get("weather", {"location": "Europe"})
        assert result == data

    def test_list_data(self, cache: InMemoryCache) -> None:
        """Storing a list as data works."""
        data = ["item1", "item2", "item3"]
        cache.set("search", {"query": "test"}, data)
        result = cache.get("search", {"query": "test"})
        assert result == data


class TestTTL:
    """Test cache TTL/expiration behavior."""

    def test_get_expired_entry(self, cache: InMemoryCache) -> None:
        """Entries older than DEFAULT_MAX_AGE are returned as None."""
        _insert_expired(
            cache,
            "weather",
            {"location": "London"},
            {"temp": 20},
            cache.DEFAULT_MAX_AGE + 100,
        )
        assert cache.get("weather", {"location": "London"}) is None

    def test_get_non_expired_entry(self, cache: InMemoryCache) -> None:
        """Fresh entries are returned."""
        cache.set("weather", {"location": "London"}, {"temp": 20})
        result = cache.get("weather", {"location": "London"})
        assert result == {"temp": 20}

    def test_manually_inserted_future_entry(self, cache: InMemoryCache) -> None:
        """Manually inserted row with future created_at survives."""
        _insert_expired(cache, "weather", {"location": "London"}, {"temp": 20}, -10000)
        assert cache.get("weather", {"location": "London"}) == {"temp": 20}


class TestCleanup:
    """Test cache cleanup of expired entries."""

    def test_cleanup_removes_expired(self, cache: InMemoryCache) -> None:
        """Cleanup removes only expired entries."""
        _insert_expired(cache, "old", {"x": 1}, {"old": True}, 8000)
        cache.set("fresh", {"x": 2}, {"fresh": True})
        assert cache.get("old", {"x": 1}) is None
        assert cache.get("fresh", {"x": 2}) == {"fresh": True}

    def test_cleanup_no_expired(self, cache: InMemoryCache) -> None:
        """Cleanup does nothing when no entries are expired."""
        cache.set("weather", {"location": "London"}, {"temp": 20})
        assert cache.get("weather", {"location": "London"}) == {"temp": 20}

    def test_cleanup_removes_all_expired(self, cache: InMemoryCache) -> None:
        """Cleanup removes all expired entries."""
        _insert_expired(cache, "old1", {}, {"a": 1}, 9000)
        _insert_expired(cache, "old2", {}, {"b": 2}, 9000)
        cache.set("fresh", {}, {"c": 3})
        assert cache.get("old1", {}) is None
        assert cache.get("old2", {}) is None
        assert cache.get("fresh", {}) == {"c": 3}

    def test_get_triggers_cleanup_of_unrelated_expired(
        self, cache: InMemoryCache
    ) -> None:
        """Calling get() on a fresh key cleans up unrelated expired entries."""
        _insert_expired(cache, "old1", {"x": 1}, {"old": True}, 8000)
        _insert_expired(cache, "old2", {"x": 2}, {"old": True}, 9000)
        cache.set("fresh", {"x": 3}, {"fresh": True})
        assert len(cache._store) == 3
        result = cache.get("fresh", {"x": 3})
        assert result == {"fresh": True}
        assert len(cache._store) == 1
        assert cache.get("old1", {"x": 1}) is None
        assert cache.get("old2", {"x": 2}) is None

    def test_get_triggers_cleanup_of_accessed_expired(
        self, cache: InMemoryCache
    ) -> None:
        """Calling get() on an expired key cleans it up."""
        _insert_expired(cache, "old", {"x": 1}, {"old": True}, 8000)
        cache.set("fresh", {"x": 2}, {"fresh": True})
        assert len(cache._store) == 2
        result = cache.get("old", {"x": 1})
        assert result is None
        assert len(cache._store) == 1
        assert cache.get("fresh", {"x": 2}) == {"fresh": True}

    def test_get_preserves_fresh_when_mix(self, cache: InMemoryCache) -> None:
        """get() cleans expired entries but preserves fresh ones."""
        _insert_expired(cache, "expired", {}, {"a": 1}, 8000)
        cache.set("fresh1", {}, {"a": 2})
        cache.set("fresh2", {}, {"a": 3})
        assert len(cache._store) == 3
        cache.get("fresh1", {})
        assert len(cache._store) == 2
        assert cache.get("fresh1", {}) == {"a": 2}
        assert cache.get("fresh2", {}) == {"a": 3}


class TestErrorHandling:
    """Test error handling in cache operations."""

    def test_set_non_dict_data(self, cache: InMemoryCache) -> None:
        """Setting non-dict data works (cache stores whatever is passed)."""
        cache.set("test", {"key": "val"}, "string_data")
        result = cache.get("test", {"key": "val"})
        assert result == "string_data"

    def test_set_none_data(self, cache: InMemoryCache) -> None:
        """Setting None as data works."""
        cache.set("test", {"key": "val"}, None)
        result = cache.get("test", {"key": "val"})
        assert result is None


class TestIdempotency:
    """Test cache idempotency and consistency."""

    def test_double_set_same_key(self, cache: InMemoryCache) -> None:
        """Two sets with the same key result in a single entry with latest value."""
        cache.set("weather", {"location": "London"}, {"temp": 20})
        cache.set("weather", {"location": "London"}, {"temp": 25})
        result = cache.get("weather", {"location": "London"})
        assert result == {"temp": 25}
        assert len(cache._store) == 1

    def test_get_after_set_consistent(self, cache: InMemoryCache) -> None:
        """Get immediately after set returns the set value."""
        data = {"key": "value", "nested": {"a": 1, "b": [1, 2, 3]}}
        cache.set("test", {"param": "x"}, data)
        assert cache.get("test", {"param": "x"}) == data

    def test_multiple_instances_share_store(self) -> None:
        """Multiple instances share the same class-level store."""
        cache1 = InMemoryCache()
        cache1.set("test", {"a": 1}, {"val": 1})
        cache2 = InMemoryCache()
        assert cache1 is not cache2
        assert cache2.get("test", {"a": 1}) == {"val": 1}


class TestStoreSize:
    """Test that the store grows and shrinks correctly."""

    def test_store_grows_with_unique_keys(self, cache: InMemoryCache) -> None:
        """Each unique key adds one entry to the store."""
        for i in range(10):
            cache.set("tool", {"i": i}, {"val": i})
        assert len(cache._store) == 10

    def test_store_does_not_grow_on_duplicate_set(self, cache: InMemoryCache) -> None:
        """Setting the same key multiple times doesn't add new entries."""
        for _ in range(5):
            cache.set("tool", {"i": 0}, {"val": 0})
        assert len(cache._store) == 1

    def test_store_shrinks_on_expire(self, cache: InMemoryCache) -> None:
        """Expired entries are removed from the store via cleanup()."""
        _insert_expired(cache, "old", {}, {"a": 1}, 8000)
        cache.set("fresh", {}, {"b": 2})
        assert len(cache._store) == 2
        cache._cleanup()
        assert len(cache._store) == 1
        key = cache._make_key("fresh", {})
        assert key in cache._store
