"""Module for handling Wikipedia search intents."""

import asyncio
import logging
import urllib.parse
from typing import Any, ClassVar

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import intent
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_WIKIPEDIA_NUM_RESULTS

_LOGGER = logging.getLogger(__name__)


class WikipediaSearch(intent.IntentHandler):
    """Handle searches via the Wikipedia API."""

    intent_type: str = "search_wikipedia"
    description: str = "Search Wikipedia for encyclopedia information"

    slot_schema: ClassVar[dict[str, vol.Schema]] = {
        vol.Required(
            "query", description="The topic to search for"
        ): intent.non_empty_string,
    }

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the WikipediaSearch handler."""
        super().__init__()
        self._hass = hass
        self._config_entry = config_entry
        data = config_entry.data
        self._num_results = data.get(CONF_WIKIPEDIA_NUM_RESULTS, 1)

    @property
    def config_entry(self) -> ConfigEntry:
        """Public accessor for the underlying ConfigEntry."""
        return self._config_entry

    @property
    def hass(self) -> HomeAssistant:
        """Public accessor for Home Assistant instance."""
        return self._hass

    @property
    def num_results(self) -> int:
        """Public accessor for number of results."""
        return self._num_results

    async def search_wikipedia(self, query: str) -> list[dict[str, Any]]:
        """
        Perform a search query using Wikipedia API.

        Raises:
            ServiceValidationError: If API request fails

        """
        search_url = (
            "https://en.wikipedia.org/w/api.php"
            "?action=query&format=json&list=search"
            f"&srsearch={urllib.parse.quote_plus(query)}"
        )

        session = async_get_clientsession(self._hass)
        try:
            # First request: search for pages
            async with session.get(search_url) as resp:
                resp.raise_for_status()
                search_result = await resp.json()

            search_hits = search_result.get("query", {}).get("search", [])
            if not search_hits:
                _LOGGER.info("No Wikipedia results for query: %s", query)
                return []

            limited_hits = search_hits[: self._num_results]

            async def fetch_summary(title: str) -> dict[str, str]:
                summary_url = (
                    "https://en.wikipedia.org/api/rest_v1/page/summary/"
                    f"{urllib.parse.quote(title)}"
                )
                async with session.get(summary_url) as resp:
                    resp.raise_for_status()
                    page_data = await resp.json()
                    return {
                        "title": title,
                        "summary": page_data.get("extract", "No summary available"),
                    }

            titles = [hit.get("title") for hit in limited_hits if hit.get("title")]
            tasks = [fetch_summary(title) for title in titles]
            return await asyncio.gather(*tasks)

        except aiohttp.ClientError as err:
            _LOGGER.exception("Error connecting to Wikipedia API")
            msg = f"Unable to connect to Wikipedia API: {err}"
            raise ServiceValidationError(msg) from err
        except Exception as err:
            _LOGGER.exception("Unexpected error during Wikipedia search")
            msg = f"Unexpected error during Wikipedia search: {err}"
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

            _LOGGER.debug("Searching Wikipedia for: %s", query)
            results = await self.search_wikipedia(query)

            response = intent_obj.create_response()
            response.response_type = intent.IntentResponseType.QUERY_ANSWER

            if results:
                # Format results for speech
                speech_text = self._format_results_for_speech(results)
                response.async_set_speech(speech_text)

                # Add structured data for further processing
                response.async_set_card(
                    title="Wikipedia Results",
                    content=self._format_results_for_card(results),
                )
            else:
                response.async_set_speech(f"No Wikipedia results found for '{query}'")

        except ServiceValidationError:
            # Re-raise service validation errors
            raise
        except Exception:
            _LOGGER.exception("Error handling Wikipedia search intent")
            response = intent_obj.create_response()
            response.response_type = intent.IntentResponseType.ERROR
            response.async_set_speech(
                "Sorry, I encountered an error searching Wikipedia."
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
            return f"{result['title']}: {result['summary']}"

        # Multiple results
        result_parts = []
        for i, result in enumerate(results, 1):
            result_parts.append(f"{i}. {result['title']}: {result['summary']}")

        return f"Here are the top results: {'; '.join(result_parts)}"

    def _format_results_for_card(self, results: list[dict[str, Any]]) -> str:
        """Format search results for card display."""
        formatted_results = []
        for result in results:
            formatted_results.append(f"**{result['title']}**\n{result['summary']}")

        return "\n\n".join(formatted_results)

    def format_results_for_speech(self, results: list[dict[str, Any]]) -> str:
        """Public method for formatting results for speech."""
        return self._format_results_for_speech(results)

    def format_results_for_card(self, results: list[dict[str, Any]]) -> str:
        """Public method for formatting results for card."""
        return self._format_results_for_card(results)
