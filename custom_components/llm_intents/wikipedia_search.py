"""Module for handling Wikipedia search intents."""

import asyncio
import logging
import urllib.parse
from typing import ClassVar

import aiohttp
import voluptuous as vol
from homeassistant.helpers import intent

from .const import (
    CONF_WIKIPEDIA_NUM_RESULTS,
)

_LOGGER = logging.getLogger(__name__)


class WikipediaSearch(intent.IntentHandler):
    """Handle topic searches via the Wikipedia API."""

    # Type of intent to handle
    intent_type: str = "search_wikipedia"
    description: str = "Search Wikipedia for information on a topic"

    # Validation schema for slots
    slot_schema: ClassVar[dict] = {
        vol.Required(
            "query", description="The topic to search for"
        ): intent.non_empty_string,
    }

    def __init__(self, config: dict) -> None:
        """Initialize the WikipediaSearch handler with the user's config."""
        # config may be True or a dict
        if isinstance(config, dict):
            self.num_results: int = config.get(CONF_WIKIPEDIA_NUM_RESULTS, 1)
        else:
            self.num_results: int = 1

    async def search_wikipedia(self, query: str) -> str | list[dict]:
        """Perform a search query using Wikipedia API."""
        search_url = (
            "https://en.wikipedia.org/w/api.php"
            "?action=query&format=json&list=search"
            f"&srsearch={urllib.parse.quote_plus(query)}"
        )

        async with aiohttp.ClientSession() as session:
            # First request: search for pages
            async with session.get(search_url) as resp:
                resp.raise_for_status()
                search_result = await resp.json()

            search_hits = search_result.get("query", {}).get("search", [])
            if not search_hits:
                return "No search results matched the query"

            # Limit to requested number of results
            limited_hits = search_hits[: self.num_results]

            async def fetch_summary(title: str) -> dict:
                summary_url = (
                    "https://en.wikipedia.org/api/rest_v1/page/summary/"
                    f"{urllib.parse.quote(title)}"
                )
                async with session.get(summary_url) as resp:
                    resp.raise_for_status()
                    page_data = await resp.json()
                    return {
                        "title": title,
                        "summary": page_data.get(
                            "extract", "No summary available"
                        ),
                    }

            # Fetch summaries concurrently
            titles = [
                hit.get("title")
                for hit in limited_hits
                if hit.get("title")
            ]
            tasks = (fetch_summary(title) for title in titles)
            results = await asyncio.gather(*tasks)
            return results or "No summaries available"

    async def async_handle(self, intent_obj) -> intent.IntentResponseType:
        """Handle the intent by validating slots and return search results."""
        slots = self.async_validate_slots(intent_obj.slots)
        query = slots.get("query", {}).get("value", "")

        search_results = await self.search_wikipedia(query)

        response = intent_obj.create_response()
        response.response_type = intent.IntentResponseType.QUERY_ANSWER
        response.async_set_speech(f"{search_results}")

        return response
