"""You.com web search tool."""

import logging
from http import HTTPStatus
from typing import Any

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .base_web_search import SearchWebTool
from .const import (
    CONF_PROVIDER_API_KEYS,
    CONF_YOUCOM_NUM_RESULTS,
    PROVIDER_YOUCOM,
    YOUCOM_BASE_URL,
    YOUCOM_FREE_URL,
)

_LOGGER = logging.getLogger(__name__)


class YoucomSearchTool(SearchWebTool):
    """Tool for searching the web via You.com Search API."""

    async def async_search(
        self,
        query: str,
        **kwargs: Any,
    ) -> list:
        """Call the tool."""
        provider_keys = self.config.get(CONF_PROVIDER_API_KEYS) or {}
        api_key = provider_keys.get(PROVIDER_YOUCOM, "")
        num_results = int(self.config.get(CONF_YOUCOM_NUM_RESULTS, 4))

        session = async_get_clientsession(self.hass)
        headers = {
            "Content-Type": "application/json",
        }

        # Keyless mode: no API key, use the profile=free endpoint
        if not api_key:
            url = YOUCOM_FREE_URL
        else:
            url = YOUCOM_BASE_URL
            headers["Authorization"] = f"Bearer {api_key}"

        # MCP JSON-RPC call
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "you-search",
                "arguments": {
                    "query": query,
                    "count": num_results,
                },
            },
        }

        async with session.post(
            url,
            headers=headers,
            json=payload,
        ) as resp:
            data = await resp.json()
            if resp.status == HTTPStatus.OK:
                results = []
                # Parse MCP tool result
                mcp_result = data.get("result", {})
                content_list = mcp_result.get("content", [])
                for content_item in content_list:
                    if content_item.get("type") == "text":
                        text = content_item.get("text", "")
                        # Parse the text result — it's formatted markdown with citations
                        results.append(
                            {
                                "title": "You.com search result",
                                "content": await self.cleanup_text(text),
                            }
                        )
                return results
            error_msg = (
                f"Web search received a HTTP {resp.status} error from You.com: {data}"
            )
            raise RuntimeError(error_msg)
