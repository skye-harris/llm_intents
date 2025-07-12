"""Config flow for the Tools for Assist integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er

import logging

_LOGGER = logging.getLogger(__name__)

from .const import (
    ADDON_NAME,
    CONF_BRAVE_ENABLED,
    CONF_BRAVE_API_KEY,
    CONF_BRAVE_COUNTRY_CODE,
    CONF_BRAVE_LATITUDE,
    CONF_BRAVE_LONGITUDE,
    CONF_BRAVE_NUM_RESULTS,
    CONF_BRAVE_POST_CODE,
    CONF_BRAVE_TIMEZONE,
    CONF_GOOGLE_PLACES_ENABLED,
    CONF_GOOGLE_PLACES_API_KEY,
    CONF_GOOGLE_PLACES_NUM_RESULTS,
    CONF_WIKIPEDIA_ENABLED,
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
STEP_CONFIGURE = "configure"


def get_step_user_data_schema() -> vol.Schema:
    """Generate a static schema for the main menu to select services."""
    schema = {
        vol.Optional(CONF_BRAVE_ENABLED, default=False): bool,
        vol.Optional(CONF_GOOGLE_PLACES_ENABLED, default=False): bool,
        vol.Optional(CONF_WIKIPEDIA_ENABLED, default=False): bool,
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
    """Handle a config flow for the Tools for Assist integration."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.user_selections: dict[str, Any] = {}
        self.config_data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial configuration step for the user."""
        errors = {}

        # Check if entry already exists
        if self._async_current_entries():
            # todo: support a single instance of multiple LLM API types (diff tools)
            return self.async_abort(reason="single_instance_allowed")

        if user_input is None:
            # Display the main menu with checkboxes for Brave, Google Places, and Wikipedia

            schema = get_step_user_data_schema()
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

        if user_input.get(CONF_BRAVE_ENABLED):
            defaults = {}
            schema = get_brave_schema(defaults)
            return self.async_show_form(
                step_id=STEP_BRAVE,
                data_schema=schema,
            )
        if user_input.get(CONF_GOOGLE_PLACES_ENABLED):
            defaults = {}
            schema = get_google_places_schema(defaults)
            return self.async_show_form(
                step_id=STEP_GOOGLE_PLACES,
                data_schema=schema,
            )
        if user_input.get(CONF_WIKIPEDIA_ENABLED):
            defaults = {}
            schema = get_wikipedia_schema(defaults)
            return self.async_show_form(
                step_id=STEP_WIKIPEDIA,
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
        if user_input is None:
            return self.async_show_form(step_id=STEP_BRAVE)
        # Store Brave configuration

        self.config_data.update(user_input)

        # Check if we need to configure other services

        if self.user_selections.get(CONF_GOOGLE_PLACES_ENABLED):
            defaults = {}
            schema = get_google_places_schema(defaults)
            return self.async_show_form(
                step_id=STEP_GOOGLE_PLACES,
                data_schema=schema,
            )
        if self.user_selections.get(CONF_WIKIPEDIA_ENABLED):
            defaults = {}
            schema = get_wikipedia_schema(defaults)
            return self.async_show_form(
                step_id=STEP_WIKIPEDIA,
                data_schema=schema,
            )
        # All done, create the entry

        return self.async_create_entry(title=ADDON_NAME, data=self.config_data)

    async def async_step_google_places(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Google Places configuration step."""
        if user_input is None:
            return self.async_show_form(step_id=STEP_GOOGLE_PLACES)
        # Store Google Places configuration

        self.config_data.update(user_input)

        # Check if we need to configure Wikipedia

        if self.user_selections.get(CONF_WIKIPEDIA_ENABLED):
            defaults = {}
            schema = get_wikipedia_schema(defaults)
            return self.async_show_form(
                step_id=STEP_WIKIPEDIA,
                data_schema=schema,
            )
        # All done, create the entry

        return self.async_create_entry(title=ADDON_NAME, data=self.config_data)

    async def async_step_wikipedia(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Wikipedia configuration step."""
        if user_input is None:
            return self.async_show_form(step_id=STEP_WIKIPEDIA)
        # Store Wikipedia configuration

        self.config_data.update(user_input)

        # All done, create the entry

        return self.async_create_entry(title=ADDON_NAME, data=self.config_data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Provide an options flow for existing entries."""
        return LlmIntentsOptionsFlow(config_entry)


class LlmIntentsOptionsFlow(config_entries.OptionsFlow):
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
                menu_options=["configure"],
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
                step_id=STEP_CONFIGURE,
                data_schema=schema,
                description_placeholders={
                    "current_services": self._get_current_services_description()
                },
            )

        # Store user selections and existing data
        self.user_selections = user_input.copy()
        self.config_data.update(defaults)
        self.config_data.update(user_input)

        if user_input.get(CONF_BRAVE_ENABLED):
            schema = get_brave_schema(defaults)
            return self.async_show_form(step_id=STEP_BRAVE, data_schema=schema)
        if user_input.get(CONF_GOOGLE_PLACES_ENABLED):
            schema = get_google_places_schema(defaults)
            return self.async_show_form(step_id=STEP_GOOGLE_PLACES, data_schema=schema)
        if user_input.get(CONF_WIKIPEDIA_ENABLED):
            schema = get_wikipedia_schema(defaults)
            return self.async_show_form(step_id=STEP_WIKIPEDIA, data_schema=schema)

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

        if services:
            return f"Currently configured: {', '.join(services)}"
        return "No services currently configured"

    async def async_step_brave(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Brave configuration step in options flow."""
        if user_input is None:
            return self.async_show_form(step_id=STEP_BRAVE)
        self.config_data.update(user_input)

        if self.user_selections.get(CONF_BRAVE_ENABLED):
            defaults = {**self.config_entry.data, **(self.config_entry.options or {})}
            schema = get_google_places_schema(defaults)
            return self.async_show_form(step_id=STEP_GOOGLE_PLACES, data_schema=schema)
        if self.user_selections.get(CONF_WIKIPEDIA_ENABLED):
            defaults = {**self.config_entry.data, **(self.config_entry.options or {})}
            schema = get_wikipedia_schema(defaults)
            return self.async_show_form(step_id=STEP_WIKIPEDIA, data_schema=schema)
        return self.async_create_entry(data=self.config_data)

    async def async_step_google_places(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Google Places configuration step in options flow."""
        if user_input is None:
            return self.async_show_form(step_id=STEP_GOOGLE_PLACES)
        self.config_data.update(user_input)

        if self.user_selections.get(CONF_WIKIPEDIA_ENABLED):
            defaults = {**self.config_entry.data, **(self.config_entry.options or {})}
            schema = get_wikipedia_schema(defaults)
            return self.async_show_form(step_id=STEP_WIKIPEDIA, data_schema=schema)
        return self.async_create_entry(data=self.config_data)

    async def async_step_wikipedia(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Wikipedia configuration step in options flow."""
        if user_input is None:
            return self.async_show_form(step_id=STEP_WIKIPEDIA)
        self.config_data.update(user_input)
        return self.async_create_entry(data=self.config_data)
