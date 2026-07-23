"""SearXNG web search tool."""

import logging
from http import HTTPStatus
from typing import Any

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .base_web_search import SearchWebTool
from .const import (
    CONF_SEARXNG_NUM_RESULTS,
    CONF_SEARXNG_URL,
)

_LOGGER = logging.getLogger(__name__)


class SearXngSearchTool(SearchWebTool):
    """SearXNG web search tool."""

    async def async_search(
        self,
        query: str,
        **kwargs: Any,
    ) -> list:
        """Call the tool."""
        url = self.config.get(CONF_SEARXNG_URL)
        num_results = int(self.config.get(CONF_SEARXNG_NUM_RESULTS, 2))

        if not url:
            msg = "SearXNG server url not configured"
            raise RuntimeError(msg)

        session = async_get_clientsession(self.hass)
        headers = {
            "Accept": "application/json",
        }

        async with session.get(
            f"{url}?format=json&q={query}",
            headers=headers,
        ) as resp:
            data = await resp.json()
            if resp.status == HTTPStatus.OK:
                results = []
                for result in data.get("results", [])[0:num_results]:
                    title = result.get("title", "")
                    content = await self.cleanup_text(result.get("content", ""))

                    item = {"title": title, "content": content}
                    results.append(item)
                return results
            err_msg = (
                f"Web search received a HTTP {resp.status} error from SearXNG: {data}"
            )
            raise RuntimeError(err_msg)
