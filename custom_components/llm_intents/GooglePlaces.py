import logging
import re

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt
from homeassistant.util.json import JsonObjectType

from .BaseTool import BaseTool
from .cache import SQLiteCache
from .const import (
    CONF_GOOGLE_PLACES_LATITUDE,
    CONF_GOOGLE_PLACES_LONGITUDE,
    CONF_GOOGLE_PLACES_NUM_RESULTS,
    CONF_GOOGLE_PLACES_RADIUS,
    CONF_GOOGLE_PLACES_RANKING,
    CONF_PROVIDER_API_KEYS,
    DOMAIN,
    PROVIDER_GOOGLE,
    SERVICE_DEFAULTS,
)

_LOGGER = logging.getLogger(__name__)


class FindPlacesTool(BaseTool):
    """Tool for finding places."""

    name = "find_places"

    description = "\n".join(
        [
            "Use this tool to search Google Places when the user requests or infers they are after any of the following information for a business or location:",
            "- Address",
            "- Contact telephone number",
            "- Regular Open & Close times",
            "- Average user rating",
        ]
    )

    prompt_description = "\n".join(
        [
            "Use the `find_places` tool to search for information about a business or public location:",
            "- This includes address, phone number, and opening hours.",
        ]
    )

    response_directive = "\n".join(
        [
            "Use the search results to answer the users query.",
            "Focus on answering the users request directly, rather than repeating the entirety of the results to them.",
        ]
    )

    parameters = vol.Schema(
        {
            vol.Required(
                "query", description="The place or location to search for"
            ): str,
        }
    )

    def wrap_response(self, response: dict) -> dict:
        """Wrap the response with our instructions"""
        response["instruction"] = self.response_instruction
        return response

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

        provider_keys = config_data.get(CONF_PROVIDER_API_KEYS) or {}
        api_key = provider_keys.get(PROVIDER_GOOGLE, "")
        num_results = int(
            config_data.get(
                CONF_GOOGLE_PLACES_NUM_RESULTS,
                SERVICE_DEFAULTS.get(CONF_GOOGLE_PLACES_NUM_RESULTS),
            )
        )
        latitude = config_data.get(CONF_GOOGLE_PLACES_LATITUDE)
        longitude = config_data.get(CONF_GOOGLE_PLACES_LONGITUDE)
        radius = config_data.get(
            CONF_GOOGLE_PLACES_RADIUS, SERVICE_DEFAULTS.get(CONF_GOOGLE_PLACES_RADIUS)
        )
        rank_pref = config_data.get(
            CONF_GOOGLE_PLACES_RANKING, SERVICE_DEFAULTS.get(CONF_GOOGLE_PLACES_RANKING)
        ).upper()

        if not api_key:
            return {"error": "Google Places API key not configured"}

        try:
            session = async_get_clientsession(hass)
            params = {
                "textQuery": query,
                "pageSize": num_results,
            }

            if rank_pref != "None":
                params["rankPreference"] = rank_pref.upper()

            if latitude and longitude:
                params["locationBias"] = {
                    "circle": {
                        "center": {
                            "latitude": latitude,
                            "longitude": longitude,
                        },
                        "radius": radius * 1000,
                    },
                }

            cache = SQLiteCache()
            cached_response = cache.get(__name__, params)
            if cached_response:
                return cached_response

            field_mask = ",".join(
                [
                    "places.displayName",
                    "places.location",
                    "places.rating",
                    "places.nationalPhoneNumber",
                    "places.regularOpeningHours",
                    "places.shortFormattedAddress",
                ]
            )

            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": field_mask,
            }

            async with session.post(
                "https://places.googleapis.com/v1/places:searchText",
                json=params,
                headers=headers,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = []

                    for place in data.get("places", []):
                        this_place = {
                            "name": place.get("displayName", {}).get("text", None),
                            "address": place.get("shortFormattedAddress", None),
                            "rating": f"{place.get('rating')} out of 5"
                            if place.get("rating")
                            else "Not rated",
                            "phone": place.get("nationalPhoneNumber", "Not available"),
                        }

                        opening_hours = place.get("regularOpeningHours")
                        if opening_hours:
                            this_place["open_now"] = opening_hours.get("openNow", False)
                            next_closes = opening_hours.get("nextCloseTime")
                            next_opens = opening_hours.get("nextOpenTime")
                            weekday_descriptions = opening_hours.get(
                                "weekdayDescriptions"
                            )

                            if next_closes:
                                utc_time = dt.parse_datetime(next_closes)
                                local_time = dt.as_local(utc_time).strftime(
                                    "%Y-%m-%d %H:%M"
                                )
                                this_place["next_closes_at"] = local_time

                            if next_opens:
                                utc_time = dt.parse_datetime(next_opens)
                                local_time = dt.as_local(utc_time).strftime(
                                    "%Y-%m-%d %H:%M"
                                )
                                this_place["next_opens_at"] = local_time

                            if weekday_descriptions:
                                this_place["regular_open_hours"] = [
                                    re.sub(r"[\u2000-\u200F\u202F]", " ", desc)
                                    for desc in weekday_descriptions
                                ]

                        results.append(this_place)

                    if results:
                        cache.set(
                            __name__,
                            params,
                            {
                                "results": results,
                                "instructions": self.response_directive,
                            },
                        )

                    return (
                        {"results": results, "instruction": self.response_directive}
                        if results
                        else {"result": "No places found"}
                    )

                _LOGGER.error(
                    f"Places search received a HTTP {resp.status} error from Google: {await resp.text()}"
                )
                return {"error": f"Places search error: {resp.status}"}

        except Exception as e:
            _LOGGER.error("Places search error: %s", e)
            return {"error": f"Error finding places: {e!s}"}
