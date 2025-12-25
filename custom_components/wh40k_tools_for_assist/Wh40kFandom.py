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
    CONF_WH40K_FANDOM_NUM_RESULTS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class SearchWh40kFandomTool(llm.Tool):
    """Tool for searching Warhammer 40k Fandom Wiki."""

    name = "search_wh40k_fandom"
    description = "Use this tool to retrieve Warhammer 40,000 lore and information from the Fandom Wiki. This includes detailed articles about factions, characters, battles, planets, weapons, vehicles, and all other aspects of the Warhammer 40k universe."

    parameters = vol.Schema(
        {
            vol.Required(
                "query", description="The Warhammer 40k subject to search for (e.g., 'Chaos Space Marines', 'Roboute Guilliman', 'Battle of Calth')"
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
        _LOGGER.info("Warhammer 40k Fandom Wiki search requested for: %s", query)

        num_results = config_data.get(CONF_WH40K_FANDOM_NUM_RESULTS, 1)

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
                "https://warhammer40k.fandom.com/api.php",
                params=search_params,
            ) as resp:
                if resp.status != 200:
                    _LOGGER.error(
                        f"Warhammer 40k Fandom Wiki search received a HTTP {resp.status} error"
                    )
                    return {
                        "error": f"Warhammer 40k Fandom Wiki search error: {resp.status}"
                    }

                search_data = await resp.json()
                search_results = search_data.get("query", {}).get("search", [])

                if not search_results:
                    return {
                        "result": f"No Warhammer 40k Fandom Wiki articles found for '{query}'"
                    }

                # Get full content for each result
                results = []
                for result in search_results:
                    title = result.get("title", "")
                    snippet = result.get("snippet", "")

                    # Clean HTML tags from snippet
                    snippet = re.sub(r"<[^>]+>", "", snippet)

                    # Try to get extract from page
                    content_params = {
                        "action": "query",
                        "format": "json",
                        "prop": "extracts",
                        "exintro": True,
                        "explaintext": True,
                        "titles": title,
                    }

                    try:
                        async with session.get(
                            "https://warhammer40k.fandom.com/api.php",
                            params=content_params,
                        ) as content_resp:
                            if content_resp.status == 200:
                                content_data = await content_resp.json()
                                pages = content_data.get("query", {}).get("pages", {})
                                # Get the first (and only) page from the response
                                page_data = next(iter(pages.values()), {})
                                extract = page_data.get("extract", snippet)
                            else:
                                extract = snippet
                    except Exception as e:
                        _LOGGER.debug(
                            "Failed to get full extract for %s: %s", title, e
                        )
                        extract = snippet

                    # Create the article URL
                    article_url = f"https://warhammer40k.fandom.com/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"

                    results.append(
                        {"title": title, "summary": extract, "url": article_url}
                    )

                if results:
                    cache.set(__name__, search_params, {"results": results})

                return {"results": results}

        except Exception as e:
            _LOGGER.error("Warhammer 40k Fandom Wiki search error: %s", e)
            return {"error": f"Error searching Warhammer 40k Fandom Wiki: {e!s}"}
