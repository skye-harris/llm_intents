import logging
import re
import urllib.parse

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util.json import JsonObjectType

from .cache import SQLiteCache
from .const import (
    CONF_WIKIPEDIA_NUM_RESULTS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class SearchWikipediaTool(llm.Tool):
    """Tool for searching Wikipedia."""

    name = "search_wikipedia"
    description = "Use this tool to retrieve information from Wikipedia on a specified subject matter"

    parameters = vol.Schema(
        {
            vol.Required(
                "query", description="The subject matter to search Wikipedia for"
            ): str,
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
        _LOGGER.info("Wikipedia search requested for: %s", query)

        num_results = config_data.get(CONF_WIKIPEDIA_NUM_RESULTS, 1)

        try:
            session = async_get_clientsession(hass)

            # First, search for pages
            search_params = {
                "action": "query",
                "format": "json",
                "list": "search",
                "srsearch": query,
                "srlimit": num_results,
            }

            cache = SQLiteCache()
            cached_response = cache.get(__name__, search_params)
            if cached_response:
                return cached_response

            async with session.get(
                "https://en.wikipedia.org/w/api.php",
                params=search_params,
            ) as resp:
                if resp.status != 200:
                    _LOGGER.error(
                        f"Wikipedia search received a HTTP {resp.status} error from Wikipedia"
                    )
                    return {"error": f"Wikipedia search error: {resp.status}"}

                search_data = await resp.json()
                search_results = search_data.get("query", {}).get("search", [])

                if not search_results:
                    return {"result": f"No Wikipedia articles found for '{query}'"}

                # Get summaries for each result
                results = []
                for result in search_results:
                    title = result.get("title", "")
                    snippet = result.get("snippet", "")

                    # Clean HTML tags from snippet
                    snippet = re.sub(r"<[^>]+>", "", snippet)

                    # Try to get full summary
                    summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
                    try:
                        async with session.get(summary_url) as summary_resp:
                            if summary_resp.status == 200:
                                summary_data = await summary_resp.json()
                                extract = summary_data.get("extract", snippet)
                            else:
                                extract = snippet
                    except Exception:
                        extract = snippet

                    results.append({"title": title, "summary": extract})

                if results:
                    cache.set(__name__, search_params, {"results": results})

                return {"results": results}

        except Exception as e:
            _LOGGER.error("Wikipedia search error: %s", e)
            return {"error": f"Error searching Wikipedia: {e!s}"}
