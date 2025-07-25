"""LLM function implementations for search services."""

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from .BraveSearch import SearchWebTool
from .const import (
    CONF_BRAVE_ENABLED,
    CONF_GOOGLE_PLACES_ENABLED,
    CONF_WIKIPEDIA_ENABLED,
    DOMAIN,
    SEARCH_API_NAME,
)
from .GooglePlaces import FindPlacesTool
from .Wikipedia import SearchWikipediaTool

_LOGGER = logging.getLogger(__name__)

TOOLS_CONF_ENABLED_MAP = [
    (CONF_BRAVE_ENABLED, SearchWebTool),
    (CONF_GOOGLE_PLACES_ENABLED, FindPlacesTool),
    (CONF_WIKIPEDIA_ENABLED, SearchWikipediaTool),
]


class SearchAPI(llm.API):
    """Search API for LLM integration."""

    def __init__(self, hass: HomeAssistant, api_id: str, name: str) -> None:
        """Initialize the API."""
        super().__init__(hass=hass, id=api_id, name=name)

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        """Get API instance."""
        config_data = self.hass.data[DOMAIN].get("config", {})
        entry = next(iter(self.hass.config_entries.async_entries(DOMAIN)))
        config_data = {**config_data, **entry.options}
        tools = []

        for key, tool_class in TOOLS_CONF_ENABLED_MAP:
            tool_enabled = config_data.get(key)
            if tool_enabled:
                tools = tools + [tool_class()]

        return llm.APIInstance(
            api=self,
            api_prompt="Call the tools to search for information on the web.",
            llm_context=llm_context,
            tools=tools,
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
    api = SearchAPI(hass, DOMAIN, SEARCH_API_NAME)
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
