"""Config flow for the Tools for Assist integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.weather import WeatherEntityFeature
from homeassistant.core import callback

_LOGGER = logging.getLogger(__name__)

from .const import (
    ADDON_NAME,
    CONF_BRAVE_API_KEY,
    CONF_BRAVE_COUNTRY_CODE,
    CONF_BRAVE_ENABLED,
    CONF_BRAVE_LATITUDE,
    CONF_BRAVE_LONGITUDE,
    CONF_BRAVE_NUM_RESULTS,
    CONF_BRAVE_POST_CODE,
    CONF_BRAVE_TIMEZONE,
    CONF_DAILY_WEATHER_ENTITY,
    CONF_GOOGLE_PLACES_API_KEY,
    CONF_GOOGLE_PLACES_ENABLED,
    CONF_GOOGLE_PLACES_LATITUDE,
    CONF_GOOGLE_PLACES_LONGITUDE,
    CONF_GOOGLE_PLACES_NUM_RESULTS,
    CONF_GOOGLE_PLACES_RADIUS,
    CONF_GOOGLE_PLACES_RANKING,
    CONF_HOURLY_WEATHER_ENTITY,
    CONF_WEATHER_ENABLED,
    CONF_WIKIPEDIA_ENABLED,
    CONF_WIKIPEDIA_NUM_RESULTS,
    DOMAIN,
    SERVICE_DEFAULTS,
)

if TYPE_CHECKING:  # pragma: no cover
    from homeassistant.config_entries import ConfigEntry, OptionsFlow
# Home Assistant best practice: Use constants for step ids


STEP_USER = "user"
STEP_BRAVE = "brave"
STEP_GOOGLE_PLACES = "google_places"
STEP_WIKIPEDIA = "wikipedia"
STEP_WEATHER = "weather"
STEP_INIT = "init"
STEP_CONFIGURE_SEARCH = "configure"
STEP_CONFIGURE_WEATHER = "configure_weather"


def get_step_user_data_schema(hass) -> vol.Schema:
    """Generate a static schema for the main menu to select services."""
    schema = {
        vol.Optional(CONF_BRAVE_ENABLED, default=False): bool,
        vol.Optional(CONF_GOOGLE_PLACES_ENABLED, default=False): bool,
        vol.Optional(CONF_WIKIPEDIA_ENABLED, default=False): bool,
        vol.Optional(CONF_WEATHER_ENABLED, default=False): bool,
    }
    return vol.Schema(schema)


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
            ): vol.All(int, vol.Range(min=1, max=20)),
            vol.Optional(
                CONF_BRAVE_COUNTRY_CODE,
                default=SERVICE_DEFAULTS.get(CONF_BRAVE_COUNTRY_CODE),
            ): str,
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


def get_google_places_schema(hass) -> vol.Schema:
    """Return the static schema for Google Places service configuration."""
    return vol.Schema(
        {
            vol.Required(
                CONF_GOOGLE_PLACES_API_KEY,
                default=SERVICE_DEFAULTS.get(CONF_GOOGLE_PLACES_API_KEY),
            ): str,
            vol.Required(
                CONF_GOOGLE_PLACES_NUM_RESULTS,
                default=SERVICE_DEFAULTS.get(CONF_GOOGLE_PLACES_NUM_RESULTS),
            ): vol.All(int, vol.Range(min=1, max=20)),
            vol.Optional(
                CONF_GOOGLE_PLACES_LATITUDE,
                default=SERVICE_DEFAULTS.get(CONF_GOOGLE_PLACES_LATITUDE),
            ): str,
            vol.Optional(
                CONF_GOOGLE_PLACES_LONGITUDE,
                default=SERVICE_DEFAULTS.get(CONF_GOOGLE_PLACES_LONGITUDE),
            ): str,
            vol.Optional(
                CONF_GOOGLE_PLACES_RADIUS,
                default=SERVICE_DEFAULTS.get(CONF_GOOGLE_PLACES_RADIUS),
            ): vol.All(int, vol.Range(min=1, max=50)),
            vol.Optional(
                CONF_GOOGLE_PLACES_RANKING,
                default=SERVICE_DEFAULTS.get(CONF_GOOGLE_PLACES_RANKING),
            ): vol.In(["None", "Distance", "Relevance"]),
        }
    )


def get_wikipedia_schema(hass) -> vol.Schema:
    """Return the static schema for Wikipedia service configuration."""
    return vol.Schema(
        {
            vol.Required(
                CONF_WIKIPEDIA_NUM_RESULTS,
                default=SERVICE_DEFAULTS.get(CONF_WIKIPEDIA_NUM_RESULTS),
            ): vol.All(int, vol.Range(min=1, max=20)),
        }
    )


def get_weather_schema(hass) -> vol.Schema:
    """Return the static schema for Weather configuration."""
    daily_entities = []
    hourly_entities = ["None"]

    for state in hass.states.async_all("weather"):
        entity_id = state.entity_id
        features = state.attributes.get("supported_features", 0)

        if features & WeatherEntityFeature.FORECAST_DAILY:
            daily_entities.append(entity_id)

        if features & WeatherEntityFeature.FORECAST_HOURLY:
            hourly_entities.append(entity_id)

    return vol.Schema(
        {
            vol.Required(CONF_DAILY_WEATHER_ENTITY): vol.In(daily_entities),
            vol.Required(CONF_HOURLY_WEATHER_ENTITY): vol.In(hourly_entities),
        }
    )


SEARCH_STEP_ORDER = {
    STEP_USER: [None, get_step_user_data_schema],
    STEP_BRAVE: [CONF_BRAVE_ENABLED, get_brave_schema],
    STEP_GOOGLE_PLACES: [CONF_GOOGLE_PLACES_ENABLED, get_google_places_schema],
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
    keys = list(step_order.keys())
    try:
        start = keys.index(current_step) + 1
    except ValueError:
        return None

    for key in keys[start:]:
        config_key, schema_func = step_order[key]
        if config_key is None or config_data.get(config_key):
            return key, schema_func

    return None


class LlmIntentsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Tools for Assist integration."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.user_selections: dict[str, Any] = {}
        self.config_data: dict[str, Any] = {}

    async def handle_step(self, current_step: str, user_input: dict[str, Any] | None):
        if user_input is None:
            return self.async_show_form(step_id=current_step)

        self.config_data.update(user_input)

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

    async def async_step_google_places(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Google Places configuration step."""
        return await self.handle_step(STEP_GOOGLE_PLACES, user_input)

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
        self.config_data: dict[str, Any] = {}

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
                description_placeholders={
                    "current_services": self._get_current_services_description()
                },
            )
        return None

    async def async_step_configure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the configure menu option."""
        data = self.config_entry.data
        opts = self.config_entry.options or {}
        defaults = {**data, **opts}

        if user_input is None:
            schema_dict = {
                vol.Optional(
                    CONF_BRAVE_ENABLED, default=defaults.get(CONF_BRAVE_ENABLED, False)
                ): bool,
                vol.Optional(
                    CONF_GOOGLE_PLACES_ENABLED,
                    default=defaults.get(CONF_GOOGLE_PLACES_ENABLED, False),
                ): bool,
                vol.Optional(
                    CONF_WIKIPEDIA_ENABLED,
                    default=defaults.get(CONF_WIKIPEDIA_ENABLED, False),
                ): bool,
            }
            schema = vol.Schema(schema_dict)
            return self.async_show_form(
                step_id=STEP_CONFIGURE_SEARCH,
                data_schema=schema,
                description_placeholders={
                    "current_services": self._get_current_services_description()
                },
            )

        # Store user selections and existing data
        self.user_selections = user_input.copy()
        self.config_data.update(user_input)

        next_step = get_next_step(STEP_USER, user_input, SEARCH_STEP_ORDER)
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
                description_placeholders={
                    "current_services": self._get_current_services_description()
                },
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

    def _get_current_services_description(self) -> str:
        """Get a description of currently configured services."""
        services = []
        data = {**self.config_entry.data, **(self.config_entry.options or {})}

        if data.get(CONF_BRAVE_ENABLED):
            services.append("Brave Search")
        if data.get(CONF_GOOGLE_PLACES_ENABLED):
            services.append("Google Places")
        if data.get(CONF_WIKIPEDIA_ENABLED):
            services.append("Wikipedia")
        if data.get(CONF_WEATHER_ENABLED):
            services.append("Weather")

        if services:
            return f"Currently configured: {', '.join(services)}"
        return "No services currently configured"

    async def handle_step(
        self, current_step: str, user_input: dict[str, Any] | None = None
    ):
        if user_input is None:
            return self.async_show_form(step_id=current_step)
        self.config_data.update(user_input)

        next_step = get_next_step(current_step, self.user_selections, SEARCH_STEP_ORDER)
        opts = {**self.config_entry.data, **(self.config_entry.options or {})}
        if next_step:
            step_id, schema_func = next_step
            schema = schema_func(self.hass)
            schema = self.add_suggested_values_to_schema(schema, opts)
            return self.async_show_form(
                step_id=step_id,
                data_schema=schema,
            )

        self.hass.config_entries.async_update_entry(self.config_entry, options=opts)

        # Manual reload to match OptionsFlowWithReload behavior as we cant seem to import that successfully
        await self.hass.config_entries.async_reload(self.config_entry.entry_id)

        return self.async_create_entry(data=self.config_data)

    async def async_step_brave(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Brave configuration step in options flow."""
        return await self.handle_step(STEP_BRAVE, user_input)

    async def async_step_google_places(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Google Places configuration step in options flow."""
        return await self.handle_step(STEP_GOOGLE_PLACES, user_input)

    async def async_step_wikipedia(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Wikipedia configuration step in options flow."""
        return await self.handle_step(STEP_WIKIPEDIA, user_input)

    async def async_step_weather(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Weather configuration step in options flow."""
        return await self.handle_step(STEP_WEATHER, user_input)
