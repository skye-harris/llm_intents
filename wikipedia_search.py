from homeassistant.helpers import intent
import aiohttp
import urllib.parse
import logging
import voluptuous as vol

from .const import (
    CONF_WIKIPEDIA_NUM_RESULTS,
)


_LOGGER = logging.getLogger(__name__)


class WikipediaSearch(intent.IntentHandler):
    # Type of intent to handle
    intent_type = "search_wikipedia"
    description = "Search Wikipedia for information on a topic"

    # Validation schema for slots
    slot_schema = {
        vol.Required("query", description="The topic to search for"): intent.non_empty_string,
    }

    def __init__(self, config):
        self.num_results = config.get(CONF_WIKIPEDIA_NUM_RESULTS, 1) if config is dict else 1
        pass

    async def search_wikipedia(self, query: str):
        search_url = f"https://en.wikipedia.org/w/api.php?action=query&format=json&list=search&srsearch={urllib.parse.quote_plus(query)}"

        async with aiohttp.ClientSession() as session:
            # First request: search for pages
            async with session.get(search_url) as resp:
                resp.raise_for_status()
                search_result = await resp.json()

            search_hits = search_result.get("query", {}).get("search", [])
            if not search_hits:
                return "No search results matched the query"

            # Limit to requested number of results
            num_results = getattr(self, "num_results", 1)
            limited_hits = search_hits[:num_results]

            results = []
            for hit in limited_hits:
                title = hit.get("title")
                if not title:
                    continue

                summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
                async with session.get(summary_url) as resp:
                    resp.raise_for_status()
                    page_data = await resp.json()

                results.append({
                    "title": title,
                    "summary": page_data.get("extract", "No summary available")
                })

            return results or "No summaries available"

    async def async_handle(self, intent_obj):
        """Handle the intent."""

        slots = self.async_validate_slots(intent_obj.slots)
        query = slots.get("query", "")["value"]

        search_results = await self.search_wikipedia(query)

        response = intent_obj.create_response()
        response.response_type = intent.IntentResponseType.QUERY_ANSWER
        response.async_set_speech(f"{search_results}")

        return response