import logging

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .BaseWebSearch import SearchWebTool
from .const import (
    CONF_SEARXNG_NUM_RESULTS,
    CONF_SEARXNG_URL,
)

_LOGGER = logging.getLogger(__name__)


class SearXngSearchTool(SearchWebTool):
    async def async_search(
        self,
        query: str,
    ) -> list:
        """Call the tool."""
        url = self.config.get(CONF_SEARXNG_URL)
        num_results = int(self.config.get(CONF_SEARXNG_NUM_RESULTS, 2))

        if not url:
            raise RuntimeError("SearXNG server url not configured")

        session = async_get_clientsession(self.hass)
        headers = {
            "Accept": "application/json",
        }

        async with session.get(
            f"{url}?format=json&q={query}",
            headers=headers,
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                results = []
                for result in data.get("results", [])[0:num_results]:
                    title = result.get("title", "")
                    content = await self.cleanup_text(result.get("content", ""))

                    result = {"title": title, "content": content}

                    results.append(result)
                return results
            raise RuntimeError(
                f"Web search received a HTTP {resp.status} error from Brave"
            )
