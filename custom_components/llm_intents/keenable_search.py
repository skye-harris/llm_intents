"""Keenable web search tool."""

import logging
from http import HTTPStatus
from typing import Any

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .base_web_search import SearchWebTool
from .const import (
    CONF_KEENABLE_NUM_RESULTS,
    CONF_PROVIDER_API_KEYS,
    PROVIDER_KEENABLE,
)

_LOGGER = logging.getLogger(__name__)

KEENABLE_PUBLIC_URL = "https://api.keenable.ai/v1/search/public"
KEENABLE_KEYED_URL = "https://api.keenable.ai/v1/search"
KEENABLE_TITLE = "llm_intents"


class KeenableSearchTool(SearchWebTool):
    """Keenable web search tool. A key is optional."""

    async def async_search(
        self,
        query: str,
        **kwargs: Any,
    ) -> list:
        """Call the tool."""
        provider_keys = self.config.get(CONF_PROVIDER_API_KEYS) or {}
        api_key = (provider_keys.get(PROVIDER_KEENABLE) or "").strip()
        num_results = int(self.config.get(CONF_KEENABLE_NUM_RESULTS, 5))

        session = async_get_clientsession(self.hass)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Keenable-Title": KEENABLE_TITLE,
        }
        url = KEENABLE_PUBLIC_URL
        request_kwargs: dict[str, Any] = {}
        if api_key:
            headers["X-API-Key"] = api_key
            url = KEENABLE_KEYED_URL
            # Do not follow redirects with X-API-Key still attached.
            request_kwargs["allow_redirects"] = False

        async with session.post(
            url,
            headers=headers,
            json={"query": query, "max_results": num_results},
            **request_kwargs,
        ) as resp:
            if resp.status != HTTPStatus.OK:
                error_msg = (
                    f"Web search received a HTTP {resp.status} error from Keenable"
                )
                raise RuntimeError(error_msg)

            response_content = await resp.json()
            results = []
            for result in response_content.get("results", [])[0:num_results]:
                content = result.get("snippet") or result.get("description") or ""
                content = await self.cleanup_text(content)
                results.append(
                    {
                        "title": result.get("title", ""),
                        "content": content,
                        "url": result.get("url"),
                    }
                )
            return results
