"""LLM function implementations for search services."""

import logging
import urllib.parse
from typing import Any
import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util.json import JsonObjectType

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class SearchWikipediaTool(llm.Tool):
    """Tool for searching Wikipedia."""

    name = "search_wikipedia"
    description = "Search Wikipedia for information about a topic"

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
        query = tool_input.tool_args["query"]
        _LOGGER.info("Wikipedia search requested for: %s", query)

        if not config_data.get("use_wikipedia"):
            return {"error": "Wikipedia search is not enabled"}

        num_results = config_data.get("wikipedia_num_results", 1)

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

            async with session.get(
                "https://en.wikipedia.org/w/api.php",
                params=search_params,
            ) as resp:
                if resp.status != 200:
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
                    import re

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

                return {"results": results}

        except Exception as e:
            _LOGGER.error("Wikipedia search error: %s", e)
            return {"error": f"Error searching Wikipedia: {e!s}"}


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
                        url = result.get("url", "")
                        description = result.get("description", "")
                        results.append(
                            {"title": title, "url": url, "description": description}
                        )

                    return (
                        {"results": results}
                        if results
                        else {"result": "No results found"}
                    )
                return {"error": f"Search error: {resp.status}"}

        except Exception as e:
            _LOGGER.error("Web search error: %s", e)
            return {"error": f"Error searching web: {e!s}"}


class FindPlacesTool(llm.Tool):
    """Tool for finding places."""

    name = "find_places"
    description = "Find places using Google Places API"

    parameters = vol.Schema(
        {
            vol.Required("query"): str,
            vol.Optional("location", default=""): str,
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Call the tool."""
        query = tool_input.tool_args["query"]
        location = tool_input.tool_args.get("location", "")
        _LOGGER.info(
            "Places search requested for: %s in %s",
            query,
            location or "any location",
        )

        if not config_data.get("use_google_places"):
            return {"error": "Places search is not enabled"}

        api_key = config_data.get("google_places_api_key")
        if not api_key:
            return {"error": "Google Places API key not configured"}

        try:
            session = async_get_clientsession(hass)
            params = {
                "query": f"{query} {location}".strip(),
                "key": api_key,
            }

            async with session.get(
                "https://maps.googleapis.com/maps/api/place/textsearch/json",
                params=params,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = []
                    max_results = config_data.get("google_places_num_results", 2)

                    for place in data.get("results", [])[:max_results]:
                        name = place.get("name", "")
                        address = place.get("formatted_address", "")
                        rating = place.get("rating", "")

                        place_data = {"name": name}
                        if address:
                            place_data["address"] = address
                        if rating:
                            place_data["rating"] = rating

                        results.append(place_data)

                    return (
                        {"results": results}
                        if results
                        else {"result": "No places found"}
                    )
                return {"error": f"Places search error: {resp.status}"}

        except Exception as e:
            _LOGGER.error("Places search error: %s", e)
            return {"error": f"Error finding places: {e!s}"}


class SearchAPI(llm.API):
    """Search API for LLM integration."""

    def __init__(self, hass: HomeAssistant, api_id: str, name: str) -> None:
        """Initialize the API."""
        super().__init__(hass=hass, id=api_id, name=name)
        self._tools = [
            SearchWikipediaTool(),
            SearchWebTool(),
            FindPlacesTool(),
        ]

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        """Get API instance."""
        return llm.APIInstance(
            api=self,
            api_prompt="Call the tools to search for information on the web, Wikipedia, and find places.",
            llm_context=llm_context,
            tools=self._tools,
        )


async def setup_llm_functions(hass: HomeAssistant, config_data: dict[str, Any]) -> None:
    """Set up LLM functions for search services."""

    # Check if already set up with same config to avoid unnecessary work
    if (
        DOMAIN in hass.data
        and "api" in hass.data[DOMAIN]
        and hass.data[DOMAIN].get("config") == config_data
    ):
        return

    # Only clean up if we already have an API registered
    if DOMAIN in hass.data and "api" in hass.data[DOMAIN]:
        await cleanup_llm_functions(hass)

    # Store API instance and config in hass.data
    hass.data.setdefault(DOMAIN, {})
    api = SearchAPI(hass, DOMAIN, "Search Services")
    hass.data[DOMAIN]["api"] = api
    hass.data[DOMAIN]["config"] = config_data.copy()

    # Register the API with Home Assistant's LLM system
    try:
        unregister_func = llm.async_register_api(hass, api)
        hass.data[DOMAIN]["unregister_api"] = unregister_func
    except Exception as e:
        _LOGGER.error("Failed to register LLM API: %s", e)
        raise


async def cleanup_llm_functions(hass: HomeAssistant) -> None:
    """Clean up LLM functions."""
    if DOMAIN in hass.data:
        # Unregister API if we have the unregister function
        if "unregister_api" in hass.data[DOMAIN]:
            try:
                hass.data[DOMAIN]["unregister_api"]()
            except Exception as e:
                _LOGGER.warning("Error unregistering LLM API: %s", e)

        # Clean up stored data
        hass.data.pop(DOMAIN, None)
