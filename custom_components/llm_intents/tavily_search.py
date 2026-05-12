"""Tavily web search tool."""

import asyncio
import logging

from tavily import TavilyClient

from .base_web_search import SearchWebTool
from .const import (
    CONF_PROVIDER_API_KEYS,
    CONF_TAVILY_NUM_RESULTS,
    PROVIDER_TAVILY,
)

_LOGGER = logging.getLogger(__name__)


class TavilySearchTool(SearchWebTool):
    """Tavily web search tool."""

    async def async_search(
        self,
        query: str,
    ) -> list:
        """Call the tool."""
        provider_keys = self.config.get(CONF_PROVIDER_API_KEYS) or {}
        api_key = provider_keys.get(PROVIDER_TAVILY, "")
        num_results = int(self.config.get(CONF_TAVILY_NUM_RESULTS, 2))

        if not api_key:
            msg = "Tavily API key not configured"
            raise RuntimeError(msg)

        client = TavilyClient(api_key=api_key)
        response = await asyncio.to_thread(
            client.search,
            query=query,
            max_results=num_results,
            search_depth="basic",
        )

        results = []
        for result in response.get("results", []):
            title = result.get("title", "")
            content = await self.cleanup_text(result.get("content", ""))
            item = {"title": title, "content": content}
            results.append(item)
        return results
