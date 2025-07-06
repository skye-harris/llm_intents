"""Module for handling Brave Search intents."""

import logging

import aiohttp
import voluptuous as vol
from homeassistant.helpers import intent

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


class BraveSearch(intent.IntentHandler):
    """Handle web searches via the Brave Search API."""

    # Type of intent to handle
    intent_type = "search_internet"
    description = "Perform an immediate internet search for a given query"

    def __init__(self, config: dict) -> None:
        """Initialize the BraveSearch handler with the user's configuration."""
        # Store slot requirements in a separate dict so we don't shadow the internal _slot_schema
        self._slot_schema_dict: dict = {
            vol.Required("query", description="The query to search for"): intent.non_empty_string,
        }
        self.api_key = config.get(CONF_BRAVE_API_KEY)
        self.num_results = config.get(CONF_BRAVE_NUM_RESULTS, 2)
        self.country_code = config.get(CONF_BRAVE_COUNTRY_CODE)
        self.latitude = config.get(CONF_BRAVE_LATITUDE)
        self.longitude = config.get(CONF_BRAVE_LONGITUDE)
        self.timezone = config.get(CONF_BRAVE_TIMEZONE)
        self.post_code = config.get(CONF_BRAVE_POST_CODE)

    @property
    def slot_schema(self) -> dict:
        """Return the raw dict for slot validation; the base class will wrap it in a Schema."""
        return self._slot_schema_dict

    async def search_brave_ai(self, query: str):
        """Perform a search query using Brave's API and return results."""
        url = "https://api.search.brave.com/res/v1/web/search"
        params = {
            "count": self.num_results,
            "result_filter": "web",
            "summary": "true",
            "extra_snippets": "true",
            "q": query,
        }

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key,
        }

        if self.latitude is not None:
            headers["X-Loc-Lat"] = str(self.latitude)
        if self.longitude is not None:
            headers["X-Loc-Long"] = str(self.longitude)
        if self.timezone is not None:
            headers["X-Loc-Timezone"] = self.timezone
        if self.country_code is not None:
            headers["X-Loc-Country"] = self.country_code
            params["country"] = self.country_code
        if self.post_code is not None:
            headers["X-Loc-Postal-Code"] = str(self.post_code)

        async with (
            aiohttp.ClientSession() as session,
            session.get(url, params=params, headers=headers) as resp,
        ):
            resp.raise_for_status()
            raw_results = await resp.json()
            results = []
            for result in raw_results.get("web", {}).get("results", []):
                results.append(
                    {
                        "title": result.get("title", "No Data"),
                        "description": result.get("description", "No Data"),
                        "snippets": result.get("extra_snippets", ["No Data"]),
                        "url": result.get("url", "No Data"),
                    }
                )
            return results

    async def async_handle(self, intent_obj) -> intent.IntentResponseType:
        """Handle the intent by validating slots and returning results."""
        slots = self.async_validate_slots(intent_obj.slots)
        query = slots.get("query", {}).get("value", "")

        search_results = await self.search_brave_ai(query)

        response = intent_obj.create_response()
        response.response_type = intent.IntentResponseType.QUERY_ANSWER
        response.async_set_speech(f"{search_results}")

        return response
