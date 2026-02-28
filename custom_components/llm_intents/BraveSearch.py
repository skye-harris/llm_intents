import logging

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .BaseWebSearch import SearchWebTool
from .const import (
    CONF_BRAVE_COUNTRY_CODE,
    CONF_BRAVE_LATITUDE,
    CONF_BRAVE_LONGITUDE,
    CONF_BRAVE_MAX_SNIPPETS_PER_URL,
    CONF_BRAVE_NUM_RESULTS,
    CONF_BRAVE_POST_CODE,
    CONF_BRAVE_TIMEZONE,
    CONF_PROVIDER_API_KEYS,
    PROVIDER_BRAVE,
)

_LOGGER = logging.getLogger(__name__)


class BraveSearchTool(SearchWebTool):
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
        max_snippets_per_url = self.config.get(CONF_BRAVE_MAX_SNIPPETS_PER_URL, 2)

        if not api_key:
            raise RuntimeError("Brave API key not configured")

        session = async_get_clientsession(self.hass)
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
        }

        params = {
            "q": query,
            "count": num_results,
            "result_filter": "web",
            "summary": "true",
            "extra_snippets": "true",
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
            "https://api.search.brave.com/res/v1/web/search",
            headers=headers,
            params=params,
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                results = []
                for result in data.get("web", {}).get("results", []):
                    title = result.get("title", "")
                    content = result.get("description", "")
                    extra_snippets = result.get("extra_snippets", [])[
                        0:max_snippets_per_url
                    ]

                    if extra_snippets:
                        result_content = [
                            await self.cleanup_text(snippet)
                            for snippet in extra_snippets
                        ]
                    else:
                        result_content = await self.cleanup_text(content)

                    results.append({"title": title, "content": result_content})

                return results
            raise RuntimeError(
                f"Web search received a HTTP {resp.status} error from Brave"
            )
