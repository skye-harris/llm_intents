"""LLM function implementations for search services."""

import logging
import types
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from . import CONF_SEARCH_PROVIDER, CONF_SEARCH_PROVIDER_BRAVE
from .BraveSearch import BraveSearchTool
from .const import (
    CONF_GOOGLE_PLACES_ENABLED,
    CONF_SEARCH_PROVIDER_SEARXNG,
    CONF_WEATHER_ENABLED,
    CONF_WIKIPEDIA_ENABLED,
    DOMAIN,
    SEARCH_API_NAME,
    SEARCH_SERVICES_PROMPT,
    WEATHER_API_NAME,
    WEATHER_SERVICES_PROMPT,
)
from .GooglePlaces import FindPlacesTool
from .SearXngSearch import SearXngSearchTool
from .Weather import WeatherForecastTool
from .Wikipedia import SearchWikipediaTool

_LOGGER = logging.getLogger(__name__)

SEARCH_CONF_ENABLED_MAP = [
    (
        lambda data: data.get(CONF_SEARCH_PROVIDER) == CONF_SEARCH_PROVIDER_BRAVE,
        BraveSearchTool,
    ),
    (
        lambda data: data.get(CONF_SEARCH_PROVIDER) == CONF_SEARCH_PROVIDER_SEARXNG,
        SearXngSearchTool,
    ),
    (CONF_GOOGLE_PLACES_ENABLED, FindPlacesTool),
    (CONF_WIKIPEDIA_ENABLED, SearchWikipediaTool),
]

WEATHER_CONF_ENABLED_MAP = [
    (CONF_WEATHER_ENABLED, WeatherForecastTool),
]


class BaseAPI(llm.API):
    _TOOLS_CONF_MAP = []
    _API_PROMPT = ""

    def __init__(self, hass: HomeAssistant, name: str, id: str | None = None) -> None:
        """Initialize the API."""
        super().__init__(
            hass=hass, id=id if id else name.lower().replace(" ", "_"), name=name
        )

    def get_enabled_tools(self) -> list:
        """Get all enabled tools for this service"""
        config_data = self.hass.data[DOMAIN].get("config", {})
        entry = next(iter(self.hass.config_entries.async_entries(DOMAIN)))
        config_data = {**config_data, **entry.options}
        tools = []

        for key, tool_class in self._TOOLS_CONF_MAP:
            tool_enabled = False

            if isinstance(key, str):
                tool_enabled = config_data.get(key)

            elif isinstance(key, types.FunctionType):
                tool_enabled = key(config_data)

            if tool_enabled:
                tools = tools + [tool_class(config_data, self.hass)]

        return tools

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        """Get API instance."""
        tools = self.get_enabled_tools()
        tool_prompts = "\n".join(
            tool.prompt_description for tool in tools if tool.prompt_description
        )

        prompt = [self._API_PROMPT]
        if tool_prompts:
            prompt.append(tool_prompts)

        return llm.APIInstance(
            api=self,
            api_prompt="\n\n".join(prompt),
            llm_context=llm_context,
            tools=self.get_enabled_tools(),
        )


class SearchAPI(BaseAPI):
    """Search API for LLM integration."""

    _TOOLS_CONF_MAP = SEARCH_CONF_ENABLED_MAP
    _API_PROMPT = SEARCH_SERVICES_PROMPT

    def __init__(self, hass: HomeAssistant, name: str) -> None:
        # Maintain compatibility with prior version
        super().__init__(hass=hass, id=DOMAIN, name=name)


class WeatherAPI(BaseAPI):
    """Weather forecast API for LLM integration."""

    _TOOLS_CONF_MAP = WEATHER_CONF_ENABLED_MAP
    _API_PROMPT = WEATHER_SERVICES_PROMPT


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
    search_api = SearchAPI(hass, SEARCH_API_NAME)
    weather_api = WeatherAPI(hass, WEATHER_API_NAME)

    hass.data[DOMAIN]["api"] = search_api
    hass.data[DOMAIN]["weather_api"] = weather_api
    hass.data[DOMAIN]["config"] = config_data.copy()
    hass.data[DOMAIN]["unregister_api"] = []

    # Register the API with Home Assistant's LLM system
    try:
        if search_api.get_enabled_tools():
            hass.data[DOMAIN]["unregister_api"].append(
                llm.async_register_api(hass, search_api)
            )

        if weather_api.get_enabled_tools():
            hass.data[DOMAIN]["unregister_api"].append(
                llm.async_register_api(hass, weather_api)
            )
    except Exception as e:
        _LOGGER.error("Failed to register LLM API: %s", e)
        raise


async def cleanup_llm_functions(hass: HomeAssistant) -> None:
    """Clean up LLM functions."""
    if DOMAIN in hass.data:
        # Unregister API if we have the unregister function
        for unreg_func in hass.data[DOMAIN].get("unregister_api", []):
            try:
                unreg_func()
            except Exception as e:
                _LOGGER.debug("Error unregistering LLM API: %s", e)

        # Clean up stored data
        hass.data.pop(DOMAIN, None)
