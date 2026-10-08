"""Wikipedia tool."""

import logging
import re
import urllib.parse
from http import HTTPStatus

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util.json import JsonObjectType

from .base_tool import BaseTool
from .cache import SQLiteCache
from .const import (
    CONF_WIKIPEDIA_NUM_RESULTS,
)

_LOGGER = logging.getLogger(__name__)

# Wikimedia rejects/throttles requests with generic client signatures
# (e.g. a bare aiohttp default User-Agent) per its API etiquette policy:
# https://meta.wikimedia.org/wiki/User-Agent_policy - without this,
# both calls below can 403/429 even under normal, light usage.
WIKIPEDIA_HEADERS = {
    "User-Agent": "HomeAssistant-llm_intents/1.0 (https://github.com/skye-harris/llm_intents)"
}


class SearchWikipediaTool(BaseTool):
    """Tool for searching Wikipedia."""

    name = "search_wikipedia"
    description = "Use this tool to retrieve information from Wikipedia on a specified subject matter"
    prompt_description = None

    parameters = vol.Schema(
        {
            vol.Required(
                "query",
                description="The subject matter to search Wikipedia for",
            ): str,
        },
    )

    annotations = llm.ToolAnnotations(
        read_only=True,
        destructive=False,
        idempotent=True,
        open_world=True,
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Call the tool."""
        config_data = self.config

        query = tool_input.tool_args["query"]
        _LOGGER.info("Wikipedia search requested for: %s", query)

        num_results = int(config_data.get(CONF_WIKIPEDIA_NUM_RESULTS, 1))

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
                headers=WIKIPEDIA_HEADERS,
            ) as resp:
                if resp.status != HTTPStatus.OK:
                    _LOGGER.error(
                        "Wikipedia search received a HTTP %s error from Wikipedia",
                        resp.status,
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
                        async with session.get(
                            summary_url, headers=WIKIPEDIA_HEADERS
                        ) as summary_resp:
                            if summary_resp.status == HTTPStatus.OK:
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
            _LOGGER.exception(msg="Wikipedia search encountered an error")
            return {"error": f"Error searching Wikipedia: {e!s}"}
