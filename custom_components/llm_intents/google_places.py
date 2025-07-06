"""Module for handling Google Places search intents."""

import logging
from typing import ClassVar

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import intent
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_GOOGLE_PLACES_API_KEY,
    CONF_GOOGLE_PLACES_INTENT,
    CONF_GOOGLE_PLACES_NUM_RESULTS,
)

_LOGGER = logging.getLogger(__name__)

# Constants for API
GOOGLE_PLACES_API_URL = "https://places.googleapis.com/v1/places:searchText"
DEFAULT_TIMEOUT = 10


class GooglePlaces(intent.IntentHandler):
    """Handle location searches via the Google Places API."""

    intent_type: str = CONF_GOOGLE_PLACES_INTENT
    description: str = (
        "Search Google Places for realtime information locations, addresses, "
        "and destinations"
    )

    slot_schema: ClassVar[dict[str, vol.Schema]] = {
        vol.Required(
            "query", description="The location to search for"
        ): intent.non_empty_string,
    }

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the GooglePlaces handler with the user's config entry."""
        super().__init__()
        self._hass = hass
        self._config_entry = config_entry
        data = config_entry.data
        self._api_key = data[CONF_GOOGLE_PLACES_API_KEY]
        self._num_results = data.get(CONF_GOOGLE_PLACES_NUM_RESULTS, 2)

    @property
    def config_entry(self) -> ConfigEntry:
        """Public accessor for the underlying ConfigEntry."""
        return self._config_entry

    async def search_google_places(self, query: str) -> list[dict[str, str]]:
        """
        Perform a search query using Google Places API.

        Args:
            query: The search query string

        Returns:
            List of place dictionaries with name and address

        Raises:
            ServiceValidationError: If API request fails

        """
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
        }
        payload = {"textQuery": query, "pageSize": self._num_results}

        # Use HA's shared aiohttp session
        session = async_get_clientsession(self._hass)

        try:
            async with session.post(
                GOOGLE_PLACES_API_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
            ) as resp:
                resp.raise_for_status()
                raw = await resp.json()

                places = raw.get("places", [])
                if not places:
                    _LOGGER.info("No places found for query: %s", query)
                    return []

                return [
                    {
                        "name": place.get("displayName", {}).get("text", "Unknown"),
                        "address": place.get(
                            "formattedAddress", "Address not available"
                        ),
                    }
                    for place in places
                ]

        except aiohttp.ClientError as err:
            _LOGGER.exception("Error connecting to Google Places API")
            msg = f"Unable to connect to Google Places API: {err}"
            raise ServiceValidationError(msg) from err
        except Exception as err:
            _LOGGER.exception("Unexpected error during Google Places search")
            msg = f"Unexpected error during search: {err}"
            raise ServiceValidationError(msg) from err

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        """
        Handle the intent by validating slots and returning results.

        Args:
            intent_obj: The intent object containing slots and context

        Returns:
            IntentResponse with search results

        """
        try:
            slots = self.async_validate_slots(intent_obj.slots)
            query = slots["query"]["value"]

            _LOGGER.debug("Searching Google Places for: %s", query)
            results = await self.search_google_places(query)

            response = intent_obj.create_response()
            response.response_type = intent.IntentResponseType.QUERY_ANSWER

            if results:
                # Format results for speech
                places_text = self._format_places_for_speech(results)
                response.async_set_speech(places_text)

                # Add structured data for further processing
                response.async_set_card(
                    title="Google Places Results",
                    content=self._format_places_for_card(results),
                )
            else:
                response.async_set_speech(f"No places found for '{query}'")

        except ServiceValidationError:
            # Re-raise service validation errors
            raise
        except Exception:
            _LOGGER.exception("Error handling Google Places intent")
            response = intent_obj.create_response()
            response.response_type = intent.IntentResponseType.ERROR
            response.async_set_speech(
                "Sorry, I encountered an error searching for places."
            )
            return response
        else:
            return response

    def _format_places_for_speech(self, places: list[dict[str, str]]) -> str:
        """Format places data for speech output."""
        if len(places) == 1:
            place = places[0]
            return f"I found {place['name']} at {place['address']}"

        place_list = []
        for i, place in enumerate(places, 1):
            place_list.append(f"{i}. {place['name']} at {place['address']}")

        return f"I found {len(places)} places: " + "; ".join(place_list)

    def _format_places_for_card(self, places: list[dict[str, str]]) -> str:
        """Format places data for card display."""
        formatted_places = []
        for place in places:
            formatted_places.append(f"**{place['name']}**\n{place['address']}")

        return "\n\n".join(formatted_places)
