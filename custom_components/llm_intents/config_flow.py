"""Config flow for the Tools for Assist integration."""

from __future__ import annotations

import logging
import types
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.weather import WeatherEntityFeature
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    ADDON_NAME,
    CONF_BRAVE_API_KEY,
    CONF_BRAVE_COUNTRY_CODE,
    CONF_BRAVE_COUNTRY_CODES,
    CONF_BRAVE_LATITUDE,
    CONF_BRAVE_LONGITUDE,
    CONF_BRAVE_NUM_RESULTS,
    CONF_BRAVE_POST_CODE,
    CONF_BRAVE_TIMEZONE,
    CONF_DAILY_WEATHER_ENTITY,
    CONF_GOOGLE_API_KEY,
    CONF_GOOGLE_PLACES_API_KEY,
    CONF_GOOGLE_PLACES_ENABLED,
    CONF_GOOGLE_PLACES_LATITUDE,
    CONF_GOOGLE_PLACES_LONGITUDE,
    CONF_GOOGLE_PLACES_NUM_RESULTS,
    CONF_GOOGLE_PLACES_RADIUS,
    CONF_GOOGLE_PLACES_RANKING,
    CONF_HOURLY_WEATHER_ENTITY,
    CONF_PROVIDER_API_KEYS,
    CONF_SEARCH_PROVIDER,
    CONF_SEARCH_PROVIDER_BRAVE,
    CONF_SEARCH_PROVIDER_SEARXNG,
    CONF_SEARCH_PROVIDERS,
    CONF_SEARXNG_NUM_RESULTS,
    CONF_SEARXNG_URL,
    CONF_WEATHER_ENABLED,
    CONF_WEATHER_TEMPERATURE_SENSOR,
    CONF_WIKIPEDIA_ENABLED,
    CONF_WIKIPEDIA_NUM_RESULTS,
    CONF_YOUTUBE_ENABLED,
    DOMAIN,
    PROVIDER_BRAVE,
    PROVIDER_GOOGLE,
    SERVICE_DEFAULTS,
    get_provider_api_key,
)

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    from homeassistant.config_entries import ConfigEntry, OptionsFlow

# Individual steps
STEP_INIT = "init"
STEP_USER = "user"
STEP_BRAVE = "brave"
STEP_SEARXNG = "searxng"
STEP_GOOGLE_PLACES = "google_places"
STEP_YOUTUBE = "youtube"
STEP_WIKIPEDIA = "wikipedia"
STEP_WEATHER = "weather"
STEP_CONFIGURE_SEARCH = "configure"
STEP_CONFIGURE_WEATHER = "configure_weather"


def get_step_user_data_schema(hass) -> vol.Schema:
    """Generate a static schema for the main menu to select services."""
    schema = {
        vol.Optional(
            CONF_SEARCH_PROVIDER,
        ): SelectSelector(
            SelectSelectorConfig(
                mode=SelectSelectorMode.DROPDOWN,
                options=options_to_selections_dict(CONF_SEARCH_PROVIDERS),
            )
        ),
        vol.Optional(CONF_GOOGLE_PLACES_ENABLED, default=False): bool,
        vol.Optional(CONF_YOUTUBE_ENABLED, default=False): bool,
        vol.Optional(CONF_WIKIPEDIA_ENABLED, default=False): bool,
        vol.Optional(CONF_WEATHER_ENABLED, default=False): bool,
    }
    return vol.Schema(schema)


def options_to_selections_dict(opts: dict) -> list[SelectOptionDict]:
    return [SelectOptionDict(value=key, label=opts[key]) for key in opts]


def expand_config_for_schema(config: dict) -> dict:
    """Add form field values for provider API keys so schemas get correct defaults."""
    result = dict(config)
    result[CONF_GOOGLE_API_KEY] = get_provider_api_key(config, PROVIDER_GOOGLE)
    result[CONF_BRAVE_API_KEY] = get_provider_api_key(config, PROVIDER_BRAVE)
    return result


def merge_provider_api_keys_from_input(config_data: dict, user_input: dict) -> None:
    """Merge provider API keys from form input into config_data in-place."""
    provider_keys = dict(config_data.get(CONF_PROVIDER_API_KEYS) or {})

    if CONF_BRAVE_API_KEY in user_input:
        provider_keys[PROVIDER_BRAVE] = user_input[CONF_BRAVE_API_KEY]
    if CONF_GOOGLE_API_KEY in user_input:
        provider_keys[PROVIDER_GOOGLE] = user_input[CONF_GOOGLE_API_KEY]

    if PROVIDER_BRAVE not in provider_keys and config_data.get(CONF_BRAVE_API_KEY):
        provider_keys[PROVIDER_BRAVE] = config_data[CONF_BRAVE_API_KEY]

    if PROVIDER_GOOGLE not in provider_keys and config_data.get(
        CONF_GOOGLE_PLACES_API_KEY
    ):
        provider_keys[PROVIDER_GOOGLE] = config_data[CONF_GOOGLE_PLACES_API_KEY]

    config_data[CONF_PROVIDER_API_KEYS] = provider_keys
    # Remove form/legacy keys - store only in provider_api_keys
    config_data.pop(CONF_BRAVE_API_KEY, None)
    config_data.pop(CONF_GOOGLE_API_KEY, None)
    config_data.pop(CONF_GOOGLE_PLACES_API_KEY, None)


def get_brave_schema(hass) -> vol.Schema:
    """Return the static schema for Brave service configuration."""
    return vol.Schema(
        {
            vol.Required(
                CONF_BRAVE_API_KEY, default=SERVICE_DEFAULTS.get(CONF_BRAVE_API_KEY)
            ): str,
            vol.Required(
                CONF_BRAVE_NUM_RESULTS,
                default=SERVICE_DEFAULTS.get(CONF_BRAVE_NUM_RESULTS),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1,
                    max=20,
                    step=1,
                    mode=NumberSelectorMode.SLIDER,
                    unit_of_measurement="Results",
                )
            ),
            vol.Optional(
                CONF_BRAVE_COUNTRY_CODE,
            ): SelectSelector(
                SelectSelectorConfig(
                    mode=SelectSelectorMode.DROPDOWN,
                    options=options_to_selections_dict(CONF_BRAVE_COUNTRY_CODES),
                )
            ),
            vol.Optional(
                CONF_BRAVE_LATITUDE, default=SERVICE_DEFAULTS.get(CONF_BRAVE_LATITUDE)
            ): str,
            vol.Optional(
                CONF_BRAVE_LONGITUDE, default=SERVICE_DEFAULTS.get(CONF_BRAVE_LONGITUDE)
            ): str,
            vol.Optional(
                CONF_BRAVE_TIMEZONE, default=SERVICE_DEFAULTS.get(CONF_BRAVE_TIMEZONE)
            ): str,
            vol.Optional(
                CONF_BRAVE_POST_CODE, default=SERVICE_DEFAULTS.get(CONF_BRAVE_POST_CODE)
            ): str,
        }
    )


def get_searxng_schema(hass) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_SEARXNG_URL, default=SERVICE_DEFAULTS.get(CONF_SEARXNG_URL)
            ): str,
            vol.Required(
                CONF_SEARXNG_NUM_RESULTS,
                default=SERVICE_DEFAULTS.get(CONF_SEARXNG_NUM_RESULTS),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1,
                    max=20,
                    step=1,
                    mode=NumberSelectorMode.SLIDER,
                    unit_of_measurement="Results",
                )
            ),
        }
    )


def get_google_places_schema(hass) -> vol.Schema:
    """Return the static schema for Google Places service configuration."""
    return vol.Schema(
        {
            vol.Required(
                CONF_GOOGLE_API_KEY,
                default=SERVICE_DEFAULTS.get(CONF_GOOGLE_API_KEY, ""),
            ): str,
            vol.Required(
                CONF_GOOGLE_PLACES_NUM_RESULTS,
                default=SERVICE_DEFAULTS.get(CONF_GOOGLE_PLACES_NUM_RESULTS),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1,
                    max=20,
                    step=1,
                    mode=NumberSelectorMode.SLIDER,
                    unit_of_measurement="Results",
                )
            ),
            vol.Optional(
                CONF_GOOGLE_PLACES_LATITUDE,
                default=SERVICE_DEFAULTS.get(CONF_GOOGLE_PLACES_LATITUDE),
            ): str,
            vol.Optional(
                CONF_GOOGLE_PLACES_LONGITUDE,
                default=SERVICE_DEFAULTS.get(CONF_GOOGLE_PLACES_LONGITUDE),
            ): str,
            vol.Required(
                CONF_GOOGLE_PLACES_RADIUS,
                default=SERVICE_DEFAULTS.get(CONF_GOOGLE_PLACES_RADIUS),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1,
                    max=50,
                    step=1,
                    mode=NumberSelectorMode.SLIDER,
                    unit_of_measurement="km",
                )
            ),
            vol.Required(
                CONF_GOOGLE_PLACES_RANKING,
                default=SERVICE_DEFAULTS.get(CONF_GOOGLE_PLACES_RANKING),
            ): SelectSelector(
                SelectSelectorConfig(
                    mode=SelectSelectorMode.DROPDOWN,
                    options=["None", "Distance", "Relevance"],
                )
            ),
        }
    )


def get_youtube_schema(hass) -> vol.Schema:
    """Return the static schema for YouTube service configuration."""
    return vol.Schema(
        {
            vol.Required(
                CONF_GOOGLE_API_KEY,
                default=SERVICE_DEFAULTS.get(CONF_GOOGLE_API_KEY, ""),
            ): str,
        }
    )


def get_wikipedia_schema(hass) -> vol.Schema:
    """Return the static schema for Wikipedia service configuration."""
    return vol.Schema(
        {
            vol.Required(
                CONF_WIKIPEDIA_NUM_RESULTS,
                default=SERVICE_DEFAULTS.get(CONF_WIKIPEDIA_NUM_RESULTS),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1,
                    max=20,
                    step=1,
                    mode=NumberSelectorMode.SLIDER,
                    unit_of_measurement="Results",
                )
            ),
        }
    )


def get_weather_schema(hass) -> vol.Schema:
    """Return the static schema for Weather configuration."""
    daily_entities = []
    hourly_entities = []
    temperature_sensors = []

    for state in hass.states.async_all("weather"):
        entity_id = state.entity_id
        features = state.attributes.get("supported_features", 0)

        if (
            features & WeatherEntityFeature.FORECAST_DAILY
            or features & WeatherEntityFeature.FORECAST_TWICE_DAILY
        ):
            daily_entities.append(entity_id)

        if features & WeatherEntityFeature.FORECAST_HOURLY:
            hourly_entities.append(entity_id)

    # Get all sensor entities with temperature device class
    for state in hass.states.async_all("sensor"):
        device_class = state.attributes.get("device_class")
        if device_class == "temperature":
            temperature_sensors.append(state.entity_id)

    return vol.Schema(
        {
            vol.Required(CONF_DAILY_WEATHER_ENTITY): EntitySelector(
                EntitySelectorConfig(
                    domain="weather",
                    include_entities=daily_entities,
                )
            ),
            vol.Optional(CONF_HOURLY_WEATHER_ENTITY): EntitySelector(
                EntitySelectorConfig(
                    domain="weather",
                    include_entities=hourly_entities,
                )
            ),
            vol.Optional(CONF_WEATHER_TEMPERATURE_SENSOR): EntitySelector(
                EntitySelectorConfig(
                    domain="sensor",
                    include_entities=temperature_sensors,
                )
            ),
        }
    )


SEARCH_STEP_ORDER = {
    STEP_USER: [None, get_step_user_data_schema],
    STEP_BRAVE: [
        lambda data: data.get(CONF_SEARCH_PROVIDER) == CONF_SEARCH_PROVIDER_BRAVE,
        get_brave_schema,
    ],
    STEP_SEARXNG: [
        lambda data: data.get(CONF_SEARCH_PROVIDER) == CONF_SEARCH_PROVIDER_SEARXNG,
        get_searxng_schema,
    ],
    STEP_GOOGLE_PLACES: [CONF_GOOGLE_PLACES_ENABLED, get_google_places_schema],
    STEP_YOUTUBE: [CONF_YOUTUBE_ENABLED, get_youtube_schema],
    STEP_WIKIPEDIA: [CONF_WIKIPEDIA_ENABLED, get_wikipedia_schema],
}

WEATHER_STEP_ORDER = {
    STEP_CONFIGURE_WEATHER: [None, None],
    STEP_WEATHER: [CONF_WEATHER_ENABLED, get_weather_schema],
}

# TODO: handle better
INITIAL_CONFIG_STEP_ORDER = {
    **SEARCH_STEP_ORDER,
    STEP_WEATHER: [CONF_WEATHER_ENABLED, get_weather_schema],
}


def get_next_step(
    current_step: str, config_data: dict, step_order: dict
) -> tuple[str, Callable] | None:
    """Determine the next configuration step."""
    keys = list(step_order.keys())
    try:
        start = keys.index(current_step) + 1
    except ValueError:
        return None

    for key in keys[start:]:
        config_key, schema_func = step_order[key]

        if (
            config_key is None
            or (isinstance(config_key, str) and config_data.get(config_key))
            or (isinstance(config_key, types.FunctionType) and config_key(config_data))
        ):
            return key, schema_func

    return None


class LlmIntentsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Tools for Assist integration."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.user_selections: dict[str, Any] = {}
        self.config_data: dict[str, Any] = {}

    async def handle_step(self, current_step: str, user_input: dict[str, Any] | None):
        """Handle a configuration step."""
        if user_input is None:
            return self.async_show_form(step_id=current_step)

        self.config_data.update(user_input)
        merge_provider_api_keys_from_input(self.config_data, user_input)

        # Check if we need to configure other services

        next_step = get_next_step(
            current_step, self.user_selections, INITIAL_CONFIG_STEP_ORDER
        )
        if next_step:
            step_id, schema_func = next_step
            schema = schema_func(self.hass)
            return self.async_show_form(
                step_id=step_id,
                data_schema=schema,
            )

        # All done, create the entry
        return self.async_create_entry(title=ADDON_NAME, data=self.config_data)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial configuration step for the user."""
        errors = {}

        # Check if entry already exists
        if self._async_current_entries():
            # TODO: support a single instance of multiple LLM API types (diff tools)
            return self.async_abort(reason="single_instance_allowed")

        if user_input is None:
            # Display the main menu with checkboxes for Brave, Google Places, and Wikipedia

            schema = get_step_user_data_schema(self.hass)
            return self.async_show_form(
                step_id=STEP_USER,
                data_schema=schema,
                errors=errors,
            )
        # Store user selections
        self.user_selections = user_input.copy()
        self.config_data.update(user_input)

        # Set a unique ID for this integration instance
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        # Handle each service configuration based on user selection

        next_step = get_next_step(STEP_USER, user_input, INITIAL_CONFIG_STEP_ORDER)
        if next_step:
            step_id, schema_func = next_step
            schema = schema_func(self.hass)
            return self.async_show_form(
                step_id=step_id,
                data_schema=schema,
            )

        # If no service is selected, create the entry with the selected data
        return self.async_create_entry(
            title=ADDON_NAME, data=self.config_data, options={}
        )

    async def async_step_brave(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Brave configuration step."""
        return await self.handle_step(STEP_BRAVE, user_input)

    async def async_step_searxng(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle SearXNG configuration step."""
        return await self.handle_step(STEP_SEARXNG, user_input)

    async def async_step_google_places(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Google Places configuration step."""
        return await self.handle_step(STEP_GOOGLE_PLACES, user_input)

    async def async_step_youtube(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle YouTube configuration step."""
        return await self.handle_step(STEP_YOUTUBE, user_input)

    async def async_step_wikipedia(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Wikipedia configuration step."""
        return await self.handle_step(STEP_WIKIPEDIA, user_input)

    async def async_step_weather(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Weather configuration step."""
        return await self.handle_step(STEP_WEATHER, user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Provide an options flow for existing entries."""
        return LlmIntentsOptionsFlow(config_entry)


class LlmIntentsOptionsFlow(config_entries.OptionsFlowWithReload):
    """Handle an options flow for an existing Tools for Assist config entry."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow with the existing entry."""
        super().__init__()
        self._config_entry = config_entry
        self.user_selections: dict[str, Any] = {}
        self.config_data = {
            **self.config_entry.data,
            **(self.config_entry.options or {}),
        }

    @property
    def config_entry(self) -> ConfigEntry:
        """Return the config entry."""
        return self._config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Present a menu to configure services the integration."""
        if user_input is None:
            return self.async_show_menu(
                step_id=STEP_INIT,
                menu_options=[STEP_CONFIGURE_SEARCH, "configure_weather"],
            )
        return None

    async def async_step_configure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the configure menu option."""
        if user_input is None:
            schema_dict = {
                vol.Optional(
                    CONF_SEARCH_PROVIDER,
                ): SelectSelector(
                    SelectSelectorConfig(
                        mode=SelectSelectorMode.DROPDOWN,
                        options=options_to_selections_dict(CONF_SEARCH_PROVIDERS),
                    )
                ),
                vol.Optional(
                    CONF_GOOGLE_PLACES_ENABLED,
                    default=False,
                ): bool,
                vol.Optional(
                    CONF_YOUTUBE_ENABLED,
                    default=False,
                ): bool,
                vol.Optional(
                    CONF_WIKIPEDIA_ENABLED,
                    default=False,
                ): bool,
            }
            schema = vol.Schema(schema_dict)

            schema = self.add_suggested_values_to_schema(schema, self.config_data)
            return self.async_show_form(
                step_id=STEP_CONFIGURE_SEARCH,
                data_schema=schema,
            )

        # Store user selections and existing data
        self.user_selections = user_input.copy()
        self.config_data.update(user_input)
        merge_provider_api_keys_from_input(self.config_data, user_input)

        next_step = get_next_step(STEP_USER, user_input, SEARCH_STEP_ORDER)
        if next_step:
            step_id, schema_func = next_step
            schema = schema_func(self.hass)
            schema = self.add_suggested_values_to_schema(
                schema, expand_config_for_schema(self.config_data)
            )
            return self.async_show_form(
                step_id=step_id,
                data_schema=schema,
            )

        # No services selected, just update with current selections
        return self.async_create_entry(data=self.config_data)

    async def async_step_configure_weather(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the configure menu option."""
        data = self.config_entry.data
        opts = self.config_entry.options or {}
        defaults = {**data, **opts}

        if user_input is None:
            schema_dict = {
                vol.Optional(
                    CONF_WEATHER_ENABLED,
                    default=defaults.get(CONF_WEATHER_ENABLED, False),
                ): bool,
            }
            schema = vol.Schema(schema_dict)
            return self.async_show_form(
                step_id=STEP_CONFIGURE_WEATHER,
                data_schema=schema,
            )

        # Store user selections and existing data
        self.user_selections = user_input.copy()
        self.config_data.update(user_input)

        next_step = get_next_step(
            STEP_CONFIGURE_WEATHER, user_input, WEATHER_STEP_ORDER
        )
        if next_step:
            step_id, schema_func = next_step
            schema = schema_func(self.hass)
            schema = self.add_suggested_values_to_schema(schema, defaults)
            return self.async_show_form(
                step_id=step_id,
                data_schema=schema,
            )

        # No services selected, just update with current selections
        return self.async_create_entry(data=self.config_data)

    async def handle_step(
        self, current_step: str, user_input: dict[str, Any] | None = None
    ):
        """Handle the current configuration step"""
        if user_input is None:
            opts = {**self.config_entry.data, **(self.config_entry.options or {})}
            _, schema_func = SEARCH_STEP_ORDER[current_step]
            schema = schema_func(self.hass)
            schema = self.add_suggested_values_to_schema(
                schema, expand_config_for_schema(opts)
            )
            return self.async_show_form(
                step_id=current_step,
                data_schema=schema,
            )

        self.config_data.update(user_input)
        merge_provider_api_keys_from_input(self.config_data, user_input)

        next_step = get_next_step(current_step, self.user_selections, SEARCH_STEP_ORDER)
        opts = {**self.config_entry.data, **(self.config_entry.options or {})}
        if next_step:
            step_id, schema_func = next_step
            schema = schema_func(self.hass)
            schema = self.add_suggested_values_to_schema(
                schema, expand_config_for_schema(opts)
            )
            return self.async_show_form(
                step_id=step_id,
                data_schema=schema,
            )

        return self.async_create_entry(data=self.config_data)

    async def async_step_brave(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Brave configuration step in options flow."""
        if user_input is not None:
            self.config_data[CONF_BRAVE_COUNTRY_CODE] = None
        return await self.handle_step(STEP_BRAVE, user_input)

    async def async_step_searxng(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle SearXNG configuration step in options flow."""
        return await self.handle_step(STEP_SEARXNG, user_input)

    async def async_step_google_places(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Google Places configuration step in options flow."""
        return await self.handle_step(STEP_GOOGLE_PLACES, user_input)

    async def async_step_youtube(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle YouTube configuration step in options flow."""
        return await self.handle_step(STEP_YOUTUBE, user_input)

    async def async_step_wikipedia(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Wikipedia configuration step in options flow."""
        return await self.handle_step(STEP_WIKIPEDIA, user_input)

    async def async_step_weather(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Weather configuration step in options flow."""
        if user_input:
            # The config dict .update wont remove values where they arent present in the update data
            # Without a selection our dict will not contain a value for this, so lets just clear it here and itll be updated in .handle_step by existing logic if a value exists
            self.config_data[CONF_HOURLY_WEATHER_ENTITY] = None
            self.config_data[CONF_WEATHER_TEMPERATURE_SENSOR] = None
        return await self.handle_step(STEP_WEATHER, user_input)
