import logging
import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util.json import JsonObjectType

from .const import DOMAIN
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
        config_data = hass.data[DOMAIN].get("config")
        query = tool_input.tool_args["query"]
        _LOGGER.info("Web search requested for: %s", query)

        if not config_data.get("use_brave"):
            return {"error": "Web search is not enabled"}

        api_key = config_data.get("brave_api_key")
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
                "count": config_data.get("brave_num_results", 2),
            }

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
