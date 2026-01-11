import html
import logging
import re

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.util.json import JsonObjectType

from .BaseTool import BaseTool
from .cache import SQLiteCache

_LOGGER = logging.getLogger(__name__)


class SearchWebTool(BaseTool):
    """Tool for searching the web."""

    name = "search_web"
    description = "Search the web to lookup information and answer user queries. You should use this tool to access additional information about the world"
    response_instruction = """
    Review the results to provide the user with a clear and concise answer to their query.
    If the search results provided do not answer the user request, advise the user of this.
    You may offer to perform related searches for the user, and if confirmed, search new queries to continue assisting the user.
    Your response must be in plain-text, without the use of any formatting, and should be kept to 2-3 sentences.
    """

    prompt_description = "\n".join(
        [
            "General knowledge questions should be deferred to the web search tool for data:",
            "- Do not rely upon your trained knowledge.",
        ]
    )

    parameters = vol.Schema(
        {
            vol.Required("query", description="The query to search for"): str,
        }
    )

    def with_instructions(self, response: dict) -> dict:
        response["instruction"] = self.response_instruction
        return response

    async def cleanup_text(self, text: str) -> str:
        text = html.unescape(text)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\s+", " ", text).strip()

        return text

    async def async_search(self, query: str) -> list:
        pass

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Call the tool."""
        query = tool_input.tool_args["query"]
        _LOGGER.info("Web search requested for: %s", query)

        try:
            cache = SQLiteCache()
            cached_response = cache.get(__name__, {"query": query})
            if cached_response:
                return self.with_instructions(cached_response)

            results = await self.async_search(query)
            response = {"results": results if results else "No results found"}

            if results:
                cache.set(__name__, {"query": query}, response)
                return self.with_instructions(response)

            return response
        except Exception as e:
            _LOGGER.error("Web search error: %s", e)
            return {"error": f"Error searching web: {e!s}"}
