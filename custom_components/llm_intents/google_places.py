"""Module for handling Google Places search intents."""

import logging
from typing import ClassVar

import aiohttp
import voluptuous as vol
from homeassistant.helpers import intent

from .const import (
    CONF_GOOGLE_PLACES_API_KEY,
    CONF_GOOGLE_PLACES_NUM_RESULTS,
)

_LOGGER = logging.getLogger(__name__)


class GooglePlaces(intent.IntentHandler):
    """Handle location searches via the Google Places API."""

    # Type of intent to handle

    intent_type: str = "search_google_places"
    description: str = (
        "Search Google Places for realtime information locations, addresses, "
        "and destinations"
    )

    # Validation schema for slots

    slot_schema: ClassVar[dict] = {
        vol.Required(
            "query", description="The location to search for"
        ): intent.non_empty_string,
    }

    def __init__(self, config: dict) -> None:
        """Initialize the GooglePlaces handler with the user's config."""
        self.api_key = config.get(CONF_GOOGLE_PLACES_API_KEY)
        self.num_results = config.get(CONF_GOOGLE_PLACES_NUM_RESULTS, 2)

    async def search_google_places(self, query: str):
        """Perform a search query using Google Places API."""
        url = "https://places.googleapis.com/v1/places:searchText"

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": (
                "places.displayName,places.formattedAddress,places.location"
            ),
        }

        payload = {
            "textQuery": query,
            "pageSize": self.num_results,
        }

        async with (
            aiohttp.ClientSession() as session,
            session.post(url, json=payload, headers=headers) as resp,
        ):
            resp.raise_for_status()
            raw = await resp.json()
            return [
                {
                    "name": place.get("displayName", {}).get("text", "No Name"),
                    "address": place.get("formattedAddress", "No Address"),
                }
                for place in raw.get("places", [])
            ]

    async def async_handle(self, intent_obj) -> intent.IntentResponseType:
        """Handle the intent by validating slots and returning results."""
        slots = self.async_validate_slots(intent_obj.slots)
        query = slots.get("query", {}).get("value", "")

        search_results = await self.search_google_places(query)

        response = intent_obj.create_response()
        response.response_type = intent.IntentResponseType.QUERY_ANSWER
        response.async_set_speech(f"{search_results}")

        return response
