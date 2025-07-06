"""Module for handling Brave Search intents."""

import logging
from typing import Any, ClassVar

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import intent
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_BRAVE_API_KEY,
    CONF_BRAVE_COUNTRY_CODE,
    CONF_BRAVE_LATITUDE,
    CONF_BRAVE_LONGITUDE,
    CONF_BRAVE_NUM_RESULTS,
    CONF_BRAVE_POST_CODE,
    CONF_BRAVE_TIMEZONE,
)

_LOGGER = logging.getLogger(__name__)

# Constants for API
BRAVE_SEARCH_API_URL = "https://api.search.brave.com/res/v1/web/search"
DEFAULT_TIMEOUT = 10


class BraveSearch(intent.IntentHandler):
    """Handle web searches via the Brave Search API."""

    intent_type: str = "search_internet"
    description: str = "Perform an immediate internet search for a given query"

    slot_schema: ClassVar[dict[str, vol.Schema]] = {
        vol.Required(
            "query", description="The query to search for"
        ): intent.non_empty_string,
    }

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the BraveSearch handler with the user's config entry."""
        super().__init__()
        self._hass = hass
        self._config_entry = config_entry
        data = config_entry.data
        self._api_key = data[CONF_BRAVE_API_KEY]
        self._num_results = data.get(CONF_BRAVE_NUM_RESULTS, 2)
        self._country_code = data.get(CONF_BRAVE_COUNTRY_CODE)
        self._latitude = data.get(CONF_BRAVE_LATITUDE)
        self._longitude = data.get(CONF_BRAVE_LONGITUDE)
        self._timezone = data.get(CONF_BRAVE_TIMEZONE)
        self._post_code = data.get(CONF_BRAVE_POST_CODE)

    @property
    def config_entry(self) -> ConfigEntry:
        """Public accessor for the underlying ConfigEntry."""
        return self._config_entry

    @property
    def hass(self) -> HomeAssistant:
        """Public accessor for Home Assistant instance."""
        return self._hass

    # Add public property accessors for tests
    @property
    def api_key(self) -> str:
        """Public accessor for API key."""
        return self._api_key

    @property
    def num_results(self) -> int:
        """Public accessor for number of results."""
        return self._num_results

    @property
    def country_code(self) -> str | None:
        """Public accessor for country code."""
        return self._country_code

    @property
    def latitude(self) -> float | None:
        """Public accessor for latitude."""
        return self._latitude

    @property
    def longitude(self) -> float | None:
        """Public accessor for longitude."""
        return self._longitude

    @property
    def timezone(self) -> str | None:
        """Public accessor for timezone."""
        return self._timezone

    @property
    def post_code(self) -> str | None:
        """Public accessor for post code."""
        return self._post_code

    async def search_brave_ai(self, query: str) -> list[dict[str, Any]]:
        """
        Perform a search query using Brave's API and return results.

        Raises:
            ServiceValidationError: If API request fails

        """
        params = {
            "count": self._num_results,
            "result_filter": "web",
            "summary": "true",
            "extra_snippets": "true",
            "q": query,
        }

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self._api_key,
        }

        # Location headers
        if self._latitude is not None:
            headers["X-Loc-Lat"] = str(self._latitude)
        if self._longitude is not None:
            headers["X-Loc-Lon"] = str(self._longitude)
        if self._timezone:
            headers["X-Loc-TZ"] = self._timezone
        if self._country_code:
            headers["X-Loc-Country"] = self._country_code
            params["country"] = self._country_code
        if self._post_code:
            headers["X-Loc-PostalCode"] = str(self._post_code)

        session = async_get_clientsession(self._hass)
        try:
            async with session.get(
                BRAVE_SEARCH_API_URL,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
            ) as resp:
                resp.raise_for_status()
                raw = await resp.json()

            return [
                {
                    "title": item.get("title", "No Data"),
                    "description": item.get("description", "No Data"),
                    "snippets": item.get("extra_snippets", ["No Data"]),
                    "url": item.get("url", "No Data"),
                }
                for item in raw.get("web", {}).get("results", [])
            ]

        except aiohttp.ClientError as err:
            _LOGGER.exception("Error connecting to Brave Search API")
            msg = f"Unable to connect to Brave Search API: {err}"
            raise ServiceValidationError(msg) from err
        except Exception as err:
            _LOGGER.exception("Unexpected error during Brave Search")
            msg = f"Unexpected error during Brave Search: {err}"
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

            _LOGGER.debug("Searching Brave for: %s", query)
            results = await self.search_brave_ai(query)

            response = intent_obj.create_response()
            response.response_type = intent.IntentResponseType.QUERY_ANSWER

            if results:
                # Format results for speech
                speech_text = self._format_results_for_speech(results)
                response.async_set_speech(speech_text)

                # Add structured data for further processing
                response.async_set_card(
                    title="Brave Search Results",
                    content=self._format_results_for_card(results),
                )
            else:
                response.async_set_speech(f"No results found for '{query}'")

        except ServiceValidationError:
            # Re-raise service validation errors
            raise
        except Exception:
            _LOGGER.exception("Error handling Brave Search intent")
            response = intent_obj.create_response()
            response.response_type = intent.IntentResponseType.ERROR
            response.async_set_speech(
                "Sorry, I encountered an error searching the internet."
            )
            return response
        else:
            return response

    def _format_results_for_speech(self, results: list[dict[str, Any]]) -> str:
        """Format search results for speech output."""
        if not results:
            return "No results found."

        if len(results) == 1:
            result = results[0]
            return f"Top result: {result['title']}. {result['description']}"

        # Multiple results
        result_parts = []
        for i, result in enumerate(results, 1):
            result_parts.append(f"{i}. {result['title']}: {result['description']}")

        return f"Here are the top results: {'; '.join(result_parts)}"

    def _format_results_for_card(self, results: list[dict[str, Any]]) -> str:
        """Format search results for card display."""
        formatted_results = []
        for result in results:
            formatted_results.append(
                f"**{result['title']}**\n{result['description']}\n{result['url']}"
            )

        return "\n\n".join(formatted_results)

    # Add public method accessors for tests
    def format_results_for_speech(self, results: list[dict[str, Any]]) -> str:
        """Public method for formatting results for speech."""
        return self._format_results_for_speech(results)

    def format_results_for_card(self, results: list[dict[str, Any]]) -> str:
        """Public method for formatting results for card."""
        return self._format_results_for_card(results)
