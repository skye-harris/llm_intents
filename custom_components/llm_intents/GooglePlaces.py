import logging
import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util.json import JsonObjectType

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


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
        config_data = hass.data[DOMAIN].get("config")
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
