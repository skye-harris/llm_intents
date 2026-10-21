"""In-memory cache for network requests."""

import hashlib
import json
import logging
import time
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


class InMemoryCache:
    """

    Simple in-memory cache with TTL for our network requests.

    All instances share the same store via the class-level ``_store``
    attribute, so the singleton pattern is unnecessary.
    """

    _store: ClassVar[dict[str, tuple[float, Any]]] = {}

    DEFAULT_MAX_AGE = 7200  # 2 hour

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
        """Remove all expired entries from the cache."""
        now = time.time()
        expired_keys = [
            key
            for key, (created_at, _) in self._store.items()
            if now - created_at >= self.DEFAULT_MAX_AGE
        ]
        for key in expired_keys:
            del self._store[key]

    def get(self, tool: str, params: dict | None) -> Any | None:
        """Get a value from the cache."""
        self._cleanup()
        key = self._make_key(tool, params)
        now = time.time()
        entry = self._store.get(key)
        if entry is not None:
            created_at, data = entry
            if now - created_at < self.DEFAULT_MAX_AGE:
                logger.debug("Cache hit for tool: %s Params: %s", tool, params)
                return data

            del self._store[key]

        logger.debug("Cache miss for tool: %s Params: %s", tool, params)
        return None

    def set(self, tool: str, params: dict | None, data: dict) -> None:
        """Set a value into the cache."""
        key = self._make_key(tool, params)
        self._store[key] = (time.time(), data)
