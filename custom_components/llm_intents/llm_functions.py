"""LLM function implementations for search services."""

import logging
import types

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.llm import selector_serializer

from . import CONF_SEARCH_PROVIDER, CONF_SEARCH_PROVIDER_BRAVE
from .brave_llm_context_search import BraveLlmContextSearchTool
from .brave_web_search import BraveSearchTool
from .calculator import CalculatorTool
from .const import (
    BASIC_UTILITIES_API_NAME,
    BASIC_UTILITIES_SERVICES_PROMPT,
    CONF_CALCULATOR_ENABLED,
    CONF_DATE_INFO_ENABLED,
    CONF_GOOGLE_PLACES_ENABLED,
    CONF_GOOGLE_ROUTES_ENABLED,
    CONF_HOME_CONTROL_ENABLED,
    CONF_SEARCH_PROVIDER_BRAVE_LLM,
    CONF_SEARCH_PROVIDER_SEARXNG,
    CONF_UNIT_CONVERTER_ENABLED,
    CONF_WEATHER_ENABLED,
    CONF_WIKIPEDIA_ENABLED,
    CONF_YOUTUBE_ENABLED,
    DOMAIN,
    MEDIA_API_NAME,
    MEDIA_SERVICES_PROMPT,
    SEARCH_API_NAME,
    SEARCH_SERVICES_PROMPT,
    WEATHER_API_NAME,
    WEATHER_SERVICES_PROMPT,
)
from .date_info import DateInfoTool
from .google_places import FindPlacesTool
from .google_routes import GetRouteTool
from .home_control import HomeControlAPI
from .play_media import PlayVideoTool
from .searxng_search import SearXngSearchTool
from .unit_converter import UnitConverterTool
from .weather import WeatherForecastTool
from .wikipedia import SearchWikipediaTool
from .youtube import SearchYouTubeTool

_LOGGER = logging.getLogger(__name__)

SEARCH_CONF_ENABLED_MAP = [
    (
        lambda data: data.get(CONF_SEARCH_PROVIDER) == CONF_SEARCH_PROVIDER_BRAVE,
        BraveSearchTool,
    ),
    (
        lambda data: data.get(CONF_SEARCH_PROVIDER) == CONF_SEARCH_PROVIDER_BRAVE_LLM,
        BraveLlmContextSearchTool,
    ),
    (
        lambda data: data.get(CONF_SEARCH_PROVIDER) == CONF_SEARCH_PROVIDER_SEARXNG,
        SearXngSearchTool,
    ),
    (CONF_GOOGLE_PLACES_ENABLED, FindPlacesTool),
    (CONF_GOOGLE_ROUTES_ENABLED, GetRouteTool),
    (CONF_YOUTUBE_ENABLED, SearchYouTubeTool),
    (CONF_WIKIPEDIA_ENABLED, SearchWikipediaTool),
]

WEATHER_CONF_ENABLED_MAP = [
    (CONF_WEATHER_ENABLED, WeatherForecastTool),
]

# Media tools are enabled when YouTube is enabled
MEDIA_CONF_ENABLED_MAP = [
    (CONF_YOUTUBE_ENABLED, PlayVideoTool),
]

BASIC_UTILITIES_CONF_ENABLED_MAP = [
    (CONF_CALCULATOR_ENABLED, CalculatorTool),
    (CONF_UNIT_CONVERTER_ENABLED, UnitConverterTool),
    (CONF_DATE_INFO_ENABLED, DateInfoTool),
]


class BaseAPI(llm.API):
    """Base class for API implementations."""

    _TOOLS_CONF_MAP = None
    _API_PROMPT = ""

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict,
        name: str,
        id: str | None = None,  # noqa: A002
    ) -> None:
        """Initialize the API."""
        super().__init__(hass=hass, id=id or name.lower().replace(" ", "_"), name=name)
        self.config = config

    def get_enabled_tools(self) -> list:
        """Get all enabled tools for this service."""
        config_data = self.config
        tools = []

        for key, tool_class in self._TOOLS_CONF_MAP or []:
            tool_enabled = False

            if isinstance(key, str):
                tool_enabled = config_data.get(key)

            elif isinstance(key, types.FunctionType):
                tool_enabled = key(config_data)

            if tool_enabled:
                tool_class.update_args(self.hass)
                tools = [*tools, tool_class(config_data, self.hass)]

        return tools

    async def async_get_api_instance(
        self,
        llm_context: llm.LLMContext,
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
            custom_serializer=selector_serializer,
        )


class SearchAPI(BaseAPI):
    """Search API for LLM integration."""

    _TOOLS_CONF_MAP = SEARCH_CONF_ENABLED_MAP
    _API_PROMPT = SEARCH_SERVICES_PROMPT

    def __init__(self, hass: HomeAssistant, config: dict, name: str) -> None:
        """Initialise the API."""
        super().__init__(hass=hass, config=config, name=name, id=DOMAIN)


class WeatherAPI(BaseAPI):
    """Weather forecast API for LLM integration."""

    _TOOLS_CONF_MAP = WEATHER_CONF_ENABLED_MAP
    _API_PROMPT = WEATHER_SERVICES_PROMPT


class MediaAPI(BaseAPI):
    """Media services API for LLM integration."""

    _TOOLS_CONF_MAP = MEDIA_CONF_ENABLED_MAP
    _API_PROMPT = MEDIA_SERVICES_PROMPT


class BasicUtilitiesAPI(BaseAPI):
    """Basic Utilities API for LLM integration."""

    _TOOLS_CONF_MAP = BASIC_UTILITIES_CONF_ENABLED_MAP
    _API_PROMPT = BASIC_UTILITIES_SERVICES_PROMPT


async def setup_llm_functions(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up LLM functions for search services."""
    config = {**entry.data, **(entry.options or {})}

    # Check if already set up with same config to avoid unnecessary work
    existing = getattr(entry, "runtime_data", None)
    if existing and existing.get("config") == config:
        return

    # Clean up previous setup if present
    if existing and "api" in existing:
        await cleanup_llm_functions(entry)

    search_api = SearchAPI(hass, config, SEARCH_API_NAME)
    weather_api = WeatherAPI(hass, config, WEATHER_API_NAME)
    media_api = MediaAPI(hass, config, MEDIA_API_NAME)
    basic_utilities_api = BasicUtilitiesAPI(hass, config, BASIC_UTILITIES_API_NAME)
    home_control_api = HomeControlAPI(hass, config)

    apis = [search_api, weather_api, media_api, basic_utilities_api]
    unregister_api = [
        llm.async_register_api(hass, api) for api in apis if api.get_enabled_tools()
    ]
    if config.get(CONF_HOME_CONTROL_ENABLED, False):
        unregister_api.append(llm.async_register_api(hass, home_control_api))

    entry.runtime_data = {
        "config": config,
        "api": search_api,
        "weather_api": weather_api,
        "media_api": media_api,
        "basic_utilities_api": basic_utilities_api,
        "customised_assist": home_control_api,
        "unregister_api": unregister_api,
    }


async def cleanup_llm_functions(entry: ConfigEntry) -> None:
    """Clean up LLM functions."""
    runtime = entry.runtime_data
    if runtime:
        for unreg_func in runtime.get("unregister_api", []):
            try:
                unreg_func()
            except Exception as e:
                _LOGGER.debug("Error unregistering LLM API: %s", e)
    entry.runtime_data = None
