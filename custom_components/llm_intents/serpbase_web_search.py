"""SerpBase Web search tool."""

import logging
from http import HTTPStatus
from typing import Any

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .base_web_search import SearchWebTool
from .const import (
    CONF_PROVIDER_API_KEYS,
    CONF_SERPBASE_NUM_RESULTS,
    PROVIDER_SERPBASE,
)

_LOGGER = logging.getLogger(__name__)

_SERPBASE_API_URL = "https://api.serpbase.dev/google/search"
# SerpBase returns HTTP 200 with a JSON error body for failures; the
# envelope's `status` field is the source of truth (0 == success).
_SERPBASE_STATUS_OK = 0


class SerpBaseSearchTool(SearchWebTool):
    """Tool for searching the web via SerpBase Google Search API."""

    async def async_search(
        self,
        query: str,
        **kwargs: Any,
    ) -> list:
        """Call the tool."""
        provider_keys = self.config.get(CONF_PROVIDER_API_KEYS) or {}
        api_key = provider_keys.get(PROVIDER_SERPBASE, "")
        num_results = int(self.config.get(CONF_SERPBASE_NUM_RESULTS, 10))

        if not api_key:
            _LOGGER.warning(
                "SERPBASE_API_KEY not set — skipping SerpBase. "
                "Get a key at https://serpbase.dev"
            )
            return []

        session = async_get_clientsession(self.hass)

        async with session.post(
            _SERPBASE_API_URL,
            json={"q": query},
            headers={"X-API-Key": api_key},
        ) as resp:
            response_content = await resp.json()
            if (
                resp.status != HTTPStatus.OK
                or response_content.get("status") != _SERPBASE_STATUS_OK
            ):
                error_msg = (
                    f"Web search received a HTTP {resp.status} error from SerpBase: "
                    f"{response_content.get('error', response_content)}"
                )
                raise RuntimeError(error_msg)

            results = []
            for result in response_content.get("organic", [])[:num_results]:
                title = result.get("title", "")
                snippet = result.get("snippet", "")
                content = await self.cleanup_text(snippet)

                results.append({"title": title, "content": content})

            return results
