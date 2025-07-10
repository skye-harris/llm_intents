import logging
import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util.json import JsonObjectType

from .const import (
    DOMAIN,
    CONF_BRAVE_API_KEY,
    CONF_BRAVE_NUM_RESULTS,
    CONF_BRAVE_COUNTRY_CODE,
    CONF_BRAVE_LATITUDE,
    CONF_BRAVE_LONGITUDE,
    CONF_BRAVE_TIMEZONE,
    CONF_BRAVE_POST_CODE,
)
from .cache import SQLiteCache

_LOGGER = logging.getLogger(__name__)


class SearchWebTool(llm.Tool):
    """Tool for searching the web."""

    name = "search_web"
    description = "Search the web using Brave Search"

    parameters = vol.Schema(
        {
            vol.Required("query"): str,
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Call the tool."""
        config_data = hass.data[DOMAIN].get("config", {})
        entry = next(iter(hass.config_entries.async_entries(DOMAIN)))
        config_data = {**config_data, **entry.options}

        query = tool_input.tool_args["query"]
        _LOGGER.info("Web search requested for: %s", query)

        api_key = config_data.get(CONF_BRAVE_API_KEY)
        num_results = config_data.get(CONF_BRAVE_NUM_RESULTS, 2)
        latitude = config_data.get(CONF_BRAVE_LATITUDE)
        longitude = config_data.get(CONF_BRAVE_LONGITUDE)
        timezone = config_data.get(CONF_BRAVE_TIMEZONE)
        country_code = config_data.get(CONF_BRAVE_COUNTRY_CODE)
        post_code = config_data.get(CONF_BRAVE_POST_CODE)

        if not api_key:
            return {"error": "Brave API key not configured"}

        try:
            session = async_get_clientsession(hass)
            headers = {
                "Accept": "application/json",
                "X-Subscription-Token": api_key,
            }

            params = {
                "q": query,
                "count": num_results,
            }

            if latitude is not None:
                headers["X-Loc-Lat"] = str(latitude)

            if longitude is not None:
                headers["X-Loc-Long"] = str(longitude)

            if timezone is not None:
                headers["X-Loc-Timezone"] = timezone

            if country_code is not None:
                headers["X-Loc-Country"] = country_code
                params["country"] = country_code

            if post_code is not None:
                headers["X-Loc-Postal-Code"] = str(post_code)

            cache = SQLiteCache()
            cached_response = cache.get(__name__, params)

            if cached_response:
                return cached_response

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
                        description = result.get("description", "")
                        results.append({"title": title, "description": description})

                    if results:
                        cache.set(__name__, params, {"results": results})

                    return (
                        {"results": results}
                        if results
                        else {"result": "No results found"}
                    )
                return {"error": f"Search error: {resp.status}"}

        except Exception as e:
            _LOGGER.error("Web search error: %s", e)
            return {"error": f"Error searching web: {e!s}"}
