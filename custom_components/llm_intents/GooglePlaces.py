import logging
import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util.json import JsonObjectType

from .const import DOMAIN
from .cache import SQLiteCache

_LOGGER = logging.getLogger(__name__)


class FindPlacesTool(llm.Tool):
    """Tool for finding places."""

    name = "find_places"
    description = "Find places using Google Places API"

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

        _LOGGER.info(
            "Places search requested for: %s",
            query
        )

        if not config_data.get("use_google_places"):
            return {"error": "Places search is not enabled"}

        api_key = config_data.get("google_places_api_key")
        if not api_key:
            return {"error": "Google Places API key not configured"}

        try:
            session = async_get_clientsession(hass)
            params = {
                "textQuery": query,
                "pageSize": config_data.get("google_places_num_results", 2),
            }

            cache = SQLiteCache()
            cached_response = cache.get(__name__, params)
            if cached_response:
                return cached_response

            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
            }

            async with session.post(
                "https://places.googleapis.com/v1/places:searchText",
                params=params,
                headers=headers,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = []

                    results = [
                        {
                            "name": place.get("displayName", {}).get("text", None),
                            "address": place.get("formattedAddress", None),
                        }
                        for place in data.get("places", [])
                    ]

                    if results:
                        cache.set(__name__, params, {"results": results})

                    return (
                        {"results": results}
                        if results
                        else {"result": "No places found"}
                    )
                return {"error": f"Places search error: {resp.status}"}

        except Exception as e:
            _LOGGER.error("Places search error: %s", e)
            return {"error": f"Error finding places: {e!s}"}
