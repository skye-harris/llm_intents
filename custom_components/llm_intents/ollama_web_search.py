"""Ollama Web search tool."""

import logging

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .base_web_search import SearchWebTool
from .const import (
    CONF_OLLAMA_NUM_RESULTS,
    CONF_PROVIDER_API_KEYS,
    PROVIDER_OLLAMA,
)

_LOGGER = logging.getLogger(__name__)


class OllamaSearchTool(SearchWebTool):
    async def async_search(
        self,
        query: str,
    ) -> list:
        """Call the tool."""
        provider_keys = self.config.get(CONF_PROVIDER_API_KEYS) or {}
        api_key = provider_keys.get(PROVIDER_OLLAMA, "")
        num_results = int(self.config.get(CONF_OLLAMA_NUM_RESULTS, 2))

        if not api_key:
            raise RuntimeError("Ollama API key not configured")

        session = async_get_clientsession(self.hass)
        headers = {"Authorization": f"Bearer {api_key}"}

        params = {
            "query": query,
            "max_results": num_results,
        }

        async with session.post(
            "https://ollama.com/api/web_search",
            headers=headers,
            json=params,
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                results = []
                for result in data.get("results", []):
                    title = result.get("title", "")
                    content = result.get("content", "")
                    result_content = await self.cleanup_text(content)
                    results.append({"title": title, "content": result_content})
                return results
            _LOGGER.warning(await resp.text())
            raise RuntimeError(
                f"Web search received a HTTP {resp.status} error from Ollama"
            )
