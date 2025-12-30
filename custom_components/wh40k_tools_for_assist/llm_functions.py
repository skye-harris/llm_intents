"""LLM function implementations for Warhammer 40k lore services."""

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from .const import (
    CONF_WH40K_FANDOM_ENABLED,
    CONF_WH40K_LEXICANUM_ENABLED,
    CONF_WH40K_WAHAPEDIA_ENABLED,
    DOMAIN,
    WH40K_API_NAME,
    WH40K_SERVICES_PROMPT,
)
from .Wh40kFandom import SearchWh40kFandomTool
from .Wh40kLexicanum import SearchWh40kLexicanumTool
from .Wh40kWahapedia import SearchWh40kWahapediaTool

_LOGGER = logging.getLogger(__name__)

WH40K_CONF_ENABLED_MAP = [
    (CONF_WH40K_LEXICANUM_ENABLED, SearchWh40kLexicanumTool),
    (CONF_WH40K_FANDOM_ENABLED, SearchWh40kFandomTool),
    (CONF_WH40K_WAHAPEDIA_ENABLED, SearchWh40kWahapediaTool),
]


class Wh40kAPI(llm.API):
    """Warhammer 40k Lore API for LLM integration."""

    def __init__(self, hass: HomeAssistant, name: str) -> None:
        """Initialize the API."""
        super().__init__(hass=hass, id=DOMAIN, name=name)

    def get_enabled_tools(self) -> list:
        """Get list of enabled WH40k tools."""
        config_data = self.hass.data[DOMAIN].get("config", {})
        entry = next(iter(self.hass.config_entries.async_entries(DOMAIN)))
        config_data = {**config_data, **entry.options}
        tools = []

        for key, tool_class in WH40K_CONF_ENABLED_MAP:
            tool_enabled = config_data.get(key)
            if tool_enabled:
                tools.append(tool_class())

        return tools

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        """Get API instance."""
        return llm.APIInstance(
            api=self,
            api_prompt=WH40K_SERVICES_PROMPT,
            llm_context=llm_context,
            tools=self.get_enabled_tools(),
        )


async def setup_llm_functions(hass: HomeAssistant, config_data: dict[str, Any]) -> None:
    """Set up LLM functions for Warhammer 40k lore services."""
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
    wh40k_api = Wh40kAPI(hass, WH40K_API_NAME)

    hass.data[DOMAIN]["api"] = wh40k_api
    hass.data[DOMAIN]["config"] = config_data.copy()
    hass.data[DOMAIN]["unregister_api"] = None

    # Register the API with Home Assistant's LLM system
    try:
        if wh40k_api.get_enabled_tools():
            hass.data[DOMAIN]["unregister_api"] = llm.async_register_api(hass, wh40k_api)
    except Exception as e:
        _LOGGER.error("Failed to register WH40k LLM API: %s", e)
        raise


async def cleanup_llm_functions(hass: HomeAssistant) -> None:
    """Clean up LLM functions."""
    if DOMAIN in hass.data:
        # Unregister API if we have the unregister function
        unreg_func = hass.data[DOMAIN].get("unregister_api")
        if unreg_func:
            try:
                unreg_func()
            except Exception as e:
                _LOGGER.debug("Error unregistering WH40k LLM API: %s", e)

        # Clean up stored data
        hass.data.pop(DOMAIN, None)
