"""Base places search class, from which places providers extend."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.llm import ToolResult

from .base_tool import BaseTool

_LOGGER = logging.getLogger(__name__)


class FindPlacesBaseTool(BaseTool):
    """Base tool for finding places, shared by all places providers."""

    name = "find_places"

    description = (
        "Use this tool to search for places when the user requests or infers they are after any of the following information for a business or location:\n"
        "- Address\n"
        "- Contact telephone number\n"
        "- Regular Open & Close times\n"
        "- Average user rating"
    )

    prompt_description = (
        f"Use the `{name}` tool to search for information about a business or public location:\n"
        "- This includes address, phone number, and opening hours."
    )

    response_directive = (
        "Use the search results to answer the users query.\n"
        "Focus on answering the users request directly, rather than repeating the entirety of the results to them."
    )

    parameters = vol.Schema(
        {
            vol.Required(
                "query",
                description="The place or location to search for. Results are limited to places near the home, so searching a business type alone returns the nearby locations.",
            ): str,
        },
    )

    async def async_search(self, query: str, **kwargs: Any) -> list:
        """Perform a places search in our subclasses."""

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> ToolResult:
        """Call the tool."""
        query = tool_input.tool_args["query"]

        _LOGGER.info("Places search requested for: %s", query)

        try:
            results = await self.async_search(query)
        except Exception as e:
            _LOGGER.exception("Places search encountered an error")
            return ToolResult(
                data={"error": f"Error finding places: {e!s}"}, error=True
            )

        if results:
            return ToolResult(data={"results": results})

        return ToolResult(data={"result": "No places found"})
