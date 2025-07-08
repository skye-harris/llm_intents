"""LLM function implementations for search services."""

import logging
import urllib.parse
from typing import Any
from .BraveSearch import SearchWebTool
from .GooglePlaces import FindPlacesTool
from .Wikipedia import SearchWikipediaTool
import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util.json import JsonObjectType

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class SearchAPI(llm.API):
    """Search API for LLM integration."""

    def __init__(self, hass: HomeAssistant, api_id: str, name: str) -> None:
        """Initialize the API."""
        super().__init__(hass=hass, id=api_id, name=name)

        self._tools = [
            SearchWikipediaTool(),
            SearchWebTool(),
            FindPlacesTool(),
        ]

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        """Get API instance."""

        # Retrieve the tools that the Assist API makes available
        assist_api = await llm.async_get_api(self.hass, llm.LLM_API_ASSIST, llm_context)
        assist_tools = assist_api.tools

        return llm.APIInstance(
            api=self,
            api_prompt="Call the tools to search for information on the web, Wikipedia, and find places.",
            llm_context=llm_context,
            tools=self._tools + assist_tools,
        )


async def setup_llm_functions(hass: HomeAssistant, config_data: dict[str, Any]) -> None:
    """Set up LLM functions for search services."""

    # Check if already set up with same config to avoid unnecessary work
    if (
        DOMAIN in hass.data
        and "api" in hass.data[DOMAIN]
        and hass.data[DOMAIN].get("config") == config_data
    ):
        return

    # Only clean up if we already have an API registered
    if DOMAIN in hass.data and "api" in hass.data[DOMAIN]:
        await cleanup_llm_functions(hass)

    # Store API instance and config in hass.data
    hass.data.setdefault(DOMAIN, {})
    api = SearchAPI(hass, DOMAIN, "Search Services")
    hass.data[DOMAIN]["api"] = api
    hass.data[DOMAIN]["config"] = config_data.copy()

    # Register the API with Home Assistant's LLM system
    try:
        unregister_func = llm.async_register_api(hass, api)
        hass.data[DOMAIN]["unregister_api"] = unregister_func
    except Exception as e:
        _LOGGER.error("Failed to register LLM API: %s", e)
        raise


async def cleanup_llm_functions(hass: HomeAssistant) -> None:
    """Clean up LLM functions."""
    if DOMAIN in hass.data:
        # Unregister API if we have the unregister function
        if "unregister_api" in hass.data[DOMAIN]:
            try:
                hass.data[DOMAIN]["unregister_api"]()
            except Exception as e:
                _LOGGER.warning("Error unregistering LLM API: %s", e)

        # Clean up stored data
        hass.data.pop(DOMAIN, None)
