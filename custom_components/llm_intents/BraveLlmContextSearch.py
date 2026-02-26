import json
import logging
import re

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .BaseWebSearch import SearchWebTool
from .const import (
    CONF_BRAVE_COUNTRY_CODE,
    CONF_BRAVE_LATITUDE,
    CONF_BRAVE_LONGITUDE,
    CONF_BRAVE_NUM_RESULTS,
    CONF_BRAVE_POST_CODE,
    CONF_BRAVE_TIMEZONE,
    CONF_PROVIDER_API_KEYS,
    PROVIDER_BRAVE,
)

_LOGGER = logging.getLogger(__name__)


class BraveLlmContextSearchTool(SearchWebTool):

    async def cleanup_text(self, text: str) -> str:
        text = await super().cleanup_text(text)
        text = re.sub(r"\[Image: [^\]]+\]", "", text)

        if text[0] == '{' and text[-1] == '}':
            # decode JSON objects
            try:
                return json.loads(text)
            except json.decoder.JSONDecodeError:
                _LOGGER.warning("Failed to decode JSON: %s", text)

        return text

    async def async_search(
        self,
        query: str,
    ) -> list:
        """Call the tool."""
        provider_keys = self.config.get(CONF_PROVIDER_API_KEYS) or {}
        api_key = provider_keys.get(PROVIDER_BRAVE, "")
        num_results = int(self.config.get(CONF_BRAVE_NUM_RESULTS, 2))
        latitude = self.config.get(CONF_BRAVE_LATITUDE)
        longitude = self.config.get(CONF_BRAVE_LONGITUDE)
        timezone = self.config.get(CONF_BRAVE_TIMEZONE)
        country_code = self.config.get(CONF_BRAVE_COUNTRY_CODE)
        post_code = self.config.get(CONF_BRAVE_POST_CODE)

        if not api_key:
            raise RuntimeError("Brave API key not configured")

        session = async_get_clientsession(self.hass)
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
        }

        snippets_per_url = 2
        max_tokens_per_url = 1024

        params = {
            "q": query,
            "count": num_results,
            "maximum_number_of_snippets": num_results * snippets_per_url,
            "maximum_number_of_tokens": num_results * max_tokens_per_url,
            "maximum_number_of_tokens_per_url": max_tokens_per_url,
            "maximum_number_of_snippets_per_url": snippets_per_url,
            "context_threshold_mode": "strict", # disabled strict lenient balanced
        }

        if latitude:
            headers["X-Loc-Lat"] = str(latitude)

        if longitude:
            headers["X-Loc-Long"] = str(longitude)

        if timezone:
            headers["X-Loc-Timezone"] = timezone

        if country_code:
            headers["X-Loc-Country"] = country_code
            params["country"] = country_code

        if post_code:
            headers["X-Loc-Postal-Code"] = str(post_code)

        async with session.get(
            "https://api.search.brave.com/res/v1/llm/context",
            headers=headers,
            params=params,
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                results = []
                for result in data.get("grounding", {}).get("generic", []):
                    title = result.get("title")
                    snippets = result.get("snippets")

                    result_content = [
                        await self.cleanup_text(snippet)
                        for snippet in snippets
                    ]

                    result = {"title": title, "content": result_content}

                    results.append(result)

                return results
            raise RuntimeError(
                f"Web search received a HTTP {resp.status} error from Brave"
            )
