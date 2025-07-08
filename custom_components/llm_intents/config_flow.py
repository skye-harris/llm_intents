"""Config flow for the LLM Intents integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er

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
STEP_DELETE = "delete"
STEP_CONFIGURE = "configure"


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
        self.user_selections: dict[str, Any] = {}
        self.config_data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial configuration step for the user."""
        errors = {}

        # Check if entry already exists
        if self._async_current_entries():
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
        return self.async_create_entry(
            title="LLM Intents", data=self.config_data, options={}
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

        if self.user_selections.get("use_google_places"):
            defaults = {}
            schema = get_google_places_schema(defaults)
            return self.async_show_form(
                step_id=STEP_GOOGLE_PLACES,
                data_schema=schema,
            )
        if self.user_selections.get("use_wikipedia"):
            defaults = {}
            schema = get_wikipedia_schema(defaults)
            return self.async_show_form(
                step_id=STEP_WIKIPEDIA,
                data_schema=schema,
            )
        # All done, create the entry

        return self.async_create_entry(title="LLM Intents", data=self.config_data)

    async def async_step_google_places(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Google Places configuration step."""
        if user_input is None:
            return self.async_show_form(step_id=STEP_GOOGLE_PLACES)
        # Store Google Places configuration

        self.config_data.update(user_input)

        # Check if we need to configure Wikipedia

        if self.user_selections.get("use_wikipedia"):
            defaults = {}
            schema = get_wikipedia_schema(defaults)
            return self.async_show_form(
                step_id=STEP_WIKIPEDIA,
                data_schema=schema,
            )
        # All done, create the entry

        return self.async_create_entry(title="LLM Intents", data=self.config_data)

    async def async_step_wikipedia(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Wikipedia configuration step."""
        if user_input is None:
            return self.async_show_form(step_id=STEP_WIKIPEDIA)
        # Store Wikipedia configuration

        self.config_data.update(user_input)

        # All done, create the entry

        return self.async_create_entry(title="LLM Intents", data=self.config_data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Provide an options flow for existing entries."""
        return LlmIntentsOptionsFlow(config_entry)


class LlmIntentsOptionsFlow(config_entries.OptionsFlow):
    """Handle an options flow for an existing LLM Intents config entry."""

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
        """Present a menu to configure services or delete the integration."""
        if user_input is None:
            return self.async_show_menu(
                step_id=STEP_INIT,
                menu_options=["configure", "delete"],
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
                    "use_brave", default=defaults.get("use_brave", False)
                ): bool,
                vol.Optional(
                    "use_google_places",
                    default=defaults.get("use_google_places", False),
                ): bool,
                vol.Optional(
                    "use_wikipedia", default=defaults.get("use_wikipedia", False)
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

        if user_input.get("use_brave"):
            schema = get_brave_schema(defaults)
            return self.async_show_form(step_id=STEP_BRAVE, data_schema=schema)
        if user_input.get("use_google_places"):
            schema = get_google_places_schema(defaults)
            return self.async_show_form(step_id=STEP_GOOGLE_PLACES, data_schema=schema)
        if user_input.get("use_wikipedia"):
            schema = get_wikipedia_schema(defaults)
            return self.async_show_form(step_id=STEP_WIKIPEDIA, data_schema=schema)

        # No services selected, just update with current selections
        return self.async_create_entry(title="", data=self.config_data)

    async def async_step_delete(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle deletion confirmation."""
        if user_input is None:
            return self.async_show_form(
                step_id=STEP_DELETE,
                data_schema=vol.Schema(
                    {
                        vol.Required("confirm_delete", default=False): bool,
                    }
                ),
                description_placeholders={
                    "entry_title": self.config_entry.title or "LLM Intents"
                },
            )

        if user_input.get("confirm_delete"):
            # Remove any created entities first
            entity_registry = er.async_get(self.hass)
            entities = er.async_entries_for_config_entry(
                entity_registry, self.config_entry.entry_id
            )

            for entity in entities:
                entity_registry.async_remove(entity.entity_id)

            # Remove the config entry
            await self.hass.config_entries.async_remove(self.config_entry.entry_id)

            # Return a proper abort result manually
            return {"type": "abort", "reason": "instance_deleted"}

        # User cancelled, go back to menu
        return await self.async_step_init()

    def _get_current_services_description(self) -> str:
        """Get a description of currently configured services."""
        services = []
        data = {**self.config_entry.data, **(self.config_entry.options or {})}

        if data.get("use_brave"):
            services.append("Brave Search")
        if data.get("use_google_places"):
            services.append("Google Places")
        if data.get("use_wikipedia"):
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

        if self.user_selections.get("use_google_places"):
            defaults = {**self.config_entry.data, **(self.config_entry.options or {})}
            schema = get_google_places_schema(defaults)
            return self.async_show_form(step_id=STEP_GOOGLE_PLACES, data_schema=schema)
        if self.user_selections.get("use_wikipedia"):
            defaults = {**self.config_entry.data, **(self.config_entry.options or {})}
            schema = get_wikipedia_schema(defaults)
            return self.async_show_form(step_id=STEP_WIKIPEDIA, data_schema=schema)
        return self.async_create_entry(title="", data=self.config_data)

    async def async_step_google_places(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Google Places configuration step in options flow."""
        if user_input is None:
            return self.async_show_form(step_id=STEP_GOOGLE_PLACES)
        self.config_data.update(user_input)

        if self.user_selections.get("use_wikipedia"):
            defaults = {**self.config_entry.data, **(self.config_entry.options or {})}
            schema = get_wikipedia_schema(defaults)
            return self.async_show_form(step_id=STEP_WIKIPEDIA, data_schema=schema)
        return self.async_create_entry(title="", data=self.config_data)

    async def async_step_wikipedia(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Wikipedia configuration step in options flow."""
        if user_input is None:
            return self.async_show_form(step_id=STEP_WIKIPEDIA)
        self.config_data.update(user_input)
        return self.async_create_entry(title="", data=self.config_data)
