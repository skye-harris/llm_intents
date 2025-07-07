"""Config flow for the LLM Intents integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from custom_components.llm_intents.const import (
    CONF_BRAVE_API_KEY,
    CONF_BRAVE_COUNTRY_CODE,
    CONF_BRAVE_LATITUDE,
    CONF_BRAVE_LONGITUDE,
    CONF_BRAVE_NUM_RESULTS,
    CONF_BRAVE_POST_CODE,
    CONF_BRAVE_TIMEZONE,
    CONF_GOOGLE_PLACES_API_KEY,
    CONF_GOOGLE_PLACES_NUM_RESULTS,
    CONF_WIKIPEDIA_NUM_RESULTS,
    DOMAIN,
)

if TYPE_CHECKING:  # pragma: no cover
    from homeassistant.config_entries import ConfigEntry, OptionsFlow
# Home Assistant best practice: Use constants for step ids

STEP_USER = "user"
STEP_BRAVE = "brave"
STEP_GOOGLE_PLACES = "google_places"
STEP_WIKIPEDIA = "wikipedia"
STEP_INIT = "init"


def get_step_user_data_schema() -> vol.Schema:
    """Generate a static schema for the main menu to select services."""
    schema = {
        vol.Optional("use_brave", default=False): bool,
        vol.Optional("use_google_places", default=False): bool,
        vol.Optional("use_wikipedia", default=False): bool,
    }
    return vol.Schema(schema)


def get_brave_schema(defaults: dict) -> vol.Schema:
    """Return the static schema for Brave service configuration."""
    return vol.Schema(
        {
            vol.Required(
                CONF_BRAVE_API_KEY, default=defaults.get(CONF_BRAVE_API_KEY, "")
            ): str,
            vol.Optional(
                CONF_BRAVE_NUM_RESULTS, default=defaults.get(CONF_BRAVE_NUM_RESULTS, 2)
            ): vol.All(int, vol.Range(min=1)),
            vol.Optional(
                CONF_BRAVE_COUNTRY_CODE,
                default=defaults.get(CONF_BRAVE_COUNTRY_CODE, ""),
            ): str,
            vol.Optional(
                CONF_BRAVE_LATITUDE, default=defaults.get(CONF_BRAVE_LATITUDE, "")
            ): str,
            vol.Optional(
                CONF_BRAVE_LONGITUDE, default=defaults.get(CONF_BRAVE_LONGITUDE, "")
            ): str,
            vol.Optional(
                CONF_BRAVE_TIMEZONE, default=defaults.get(CONF_BRAVE_TIMEZONE, "")
            ): str,
            vol.Optional(
                CONF_BRAVE_POST_CODE, default=defaults.get(CONF_BRAVE_POST_CODE, "")
            ): str,
        }
    )


def get_google_places_schema(defaults: dict) -> vol.Schema:
    """Return the static schema for Google Places service configuration."""
    return vol.Schema(
        {
            vol.Required(
                CONF_GOOGLE_PLACES_API_KEY,
                default=defaults.get(CONF_GOOGLE_PLACES_API_KEY, ""),
            ): str,
            vol.Optional(
                CONF_GOOGLE_PLACES_NUM_RESULTS,
                default=defaults.get(CONF_GOOGLE_PLACES_NUM_RESULTS, 2),
            ): vol.All(int, vol.Range(min=1)),
        }
    )


def get_wikipedia_schema(defaults: dict) -> vol.Schema:
    """Return the static schema for Wikipedia service configuration."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_WIKIPEDIA_NUM_RESULTS,
                default=defaults.get(CONF_WIKIPEDIA_NUM_RESULTS, 1),
            ): vol.All(int, vol.Range(min=1)),
        }
    )


class LlmIntentsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the LLM Intents integration."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._user_selections: dict[str, Any] = {}
        self._config_data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial configuration step for the user."""
        if user_input is None:
            # Display the main menu with checkboxes for Brave, Google Places, and Wikipedia

            schema = get_step_user_data_schema()
            return self.async_show_form(
                step_id=STEP_USER,
                data_schema=schema,
            )
        # Store user selections

        self._user_selections = user_input.copy()
        self._config_data.update(user_input)

        # Handle each service configuration based on user selection

        if user_input.get("use_brave"):
            defaults = {}
            schema = get_brave_schema(defaults)
            return self.async_show_form(
                step_id=STEP_BRAVE,
                data_schema=schema,
            )
        if user_input.get("use_google_places"):
            defaults = {}
            schema = get_google_places_schema(defaults)
            return self.async_show_form(
                step_id=STEP_GOOGLE_PLACES,
                data_schema=schema,
            )
        if user_input.get("use_wikipedia"):
            defaults = {}
            schema = get_wikipedia_schema(defaults)
            return self.async_show_form(
                step_id=STEP_WIKIPEDIA,
                data_schema=schema,
            )
        # If no service is selected, create the entry with the selected data

        return self.async_create_entry(title="LLM Intents", data=self._config_data)

    async def async_step_brave(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Brave configuration step."""
        if user_input is None:
            return self.async_show_form(step_id=STEP_BRAVE)
        # Store Brave configuration

        self._config_data.update(user_input)

        # Check if we need to configure other services

        if self._user_selections.get("use_google_places"):
            defaults = {}
            schema = get_google_places_schema(defaults)
            return self.async_show_form(
                step_id=STEP_GOOGLE_PLACES,
                data_schema=schema,
            )
        if self._user_selections.get("use_wikipedia"):
            defaults = {}
            schema = get_wikipedia_schema(defaults)
            return self.async_show_form(
                step_id=STEP_WIKIPEDIA,
                data_schema=schema,
            )
        # All done, create the entry

        return self.async_create_entry(title="LLM Intents", data=self._config_data)

    async def async_step_google_places(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Google Places configuration step."""
        if user_input is None:
            return self.async_show_form(step_id=STEP_GOOGLE_PLACES)
        # Store Google Places configuration

        self._config_data.update(user_input)

        # Check if we need to configure Wikipedia

        if self._user_selections.get("use_wikipedia"):
            defaults = {}
            schema = get_wikipedia_schema(defaults)
            return self.async_show_form(
                step_id=STEP_WIKIPEDIA,
                data_schema=schema,
            )
        # All done, create the entry

        return self.async_create_entry(title="LLM Intents", data=self._config_data)

    async def async_step_wikipedia(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Wikipedia configuration step."""
        if user_input is None:
            return self.async_show_form(step_id=STEP_WIKIPEDIA)
        # Store Wikipedia configuration

        self._config_data.update(user_input)

        # All done, create the entry

        return self.async_create_entry(title="LLM Intents", data=self._config_data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Provide an options flow for existing entries."""
        return LlmIntentsOptionsFlow(config_entry)


class LlmIntentsOptionsFlow(config_entries.OptionsFlow):
    """Handle an options flow for an existing LLM Intents config entry."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow with the existing entry."""
        self._config_entry = config_entry
        self._user_selections: dict[str, Any] = {}
        self._config_data: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Present a form to update API keys and result counts."""
        data = self._config_entry.data
        opts = self._config_entry.options or {}

        # Use defaults from the entry's data or options

        defaults = {**data, **opts}

        if user_input is None:
            schema = get_step_user_data_schema()
            return self.async_show_form(step_id=STEP_INIT, data_schema=schema)
        # Store user selections and existing data

        self._user_selections = user_input.copy()
        self._config_data.update(defaults)
        self._config_data.update(user_input)

        if user_input.get("use_brave"):
            schema = get_brave_schema(defaults)
            return self.async_show_form(step_id=STEP_BRAVE, data_schema=schema)
        if user_input.get("use_google_places"):
            schema = get_google_places_schema(defaults)
            return self.async_show_form(step_id=STEP_GOOGLE_PLACES, data_schema=schema)
        if user_input.get("use_wikipedia"):
            schema = get_wikipedia_schema(defaults)
            return self.async_show_form(step_id=STEP_WIKIPEDIA, data_schema=schema)
        # Finalize and create the entry

        return self.async_create_entry(title="LLM Intents", data=self._config_data)

    async def async_step_brave(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Brave configuration step in options flow."""
        if user_input is None:
            return self.async_show_form(step_id=STEP_BRAVE)
        self._config_data.update(user_input)

        if self._user_selections.get("use_google_places"):
            defaults = {**self._config_entry.data, **(self._config_entry.options or {})}
            schema = get_google_places_schema(defaults)
            return self.async_show_form(step_id=STEP_GOOGLE_PLACES, data_schema=schema)
        if self._user_selections.get("use_wikipedia"):
            defaults = {**self._config_entry.data, **(self._config_entry.options or {})}
            schema = get_wikipedia_schema(defaults)
            return self.async_show_form(step_id=STEP_WIKIPEDIA, data_schema=schema)
        return self.async_create_entry(title="", data=self._config_data)

    async def async_step_google_places(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Google Places configuration step in options flow."""
        if user_input is None:
            return self.async_show_form(step_id=STEP_GOOGLE_PLACES)
        self._config_data.update(user_input)

        if self._user_selections.get("use_wikipedia"):
            defaults = {**self._config_entry.data, **(self._config_entry.options or {})}
            schema = get_wikipedia_schema(defaults)
            return self.async_show_form(step_id=STEP_WIKIPEDIA, data_schema=schema)
        return self.async_create_entry(title="", data=self._config_data)

    async def async_step_wikipedia(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Wikipedia configuration step in options flow."""
        if user_input is None:
            return self.async_show_form(step_id=STEP_WIKIPEDIA)
        self._config_data.update(user_input)
        return self.async_create_entry(title="", data=self._config_data)
