"""Config flow for the WH40k Tools for Assist integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

_LOGGER = logging.getLogger(__name__)

from .const import (
    ADDON_NAME,
    CONF_WH40K_FANDOM_ENABLED,
    CONF_WH40K_FANDOM_NUM_RESULTS,
    CONF_WH40K_LEXICANUM_ENABLED,
    CONF_WH40K_LEXICANUM_NUM_RESULTS,
    DOMAIN,
    SERVICE_DEFAULTS,
)

if TYPE_CHECKING:  # pragma: no cover
    from homeassistant.config_entries import ConfigEntry, OptionsFlow

# Home Assistant best practice: Use constants for step ids

STEP_USER = "user"
STEP_WH40K_LEXICANUM = "wh40k_lexicanum"
STEP_WH40K_FANDOM = "wh40k_fandom"
STEP_INIT = "init"


def get_step_user_data_schema(hass) -> vol.Schema:
    """Generate a static schema for the main menu to select services."""
    schema = {
        vol.Optional(CONF_WH40K_LEXICANUM_ENABLED, default=False): bool,
        vol.Optional(CONF_WH40K_FANDOM_ENABLED, default=False): bool,
    }
    return vol.Schema(schema)


def get_wh40k_lexicanum_schema(hass) -> vol.Schema:
    """Return the static schema for Warhammer 40k Lexicanum service configuration."""
    return vol.Schema(
        {
            vol.Required(
                CONF_WH40K_LEXICANUM_NUM_RESULTS,
                default=SERVICE_DEFAULTS.get(CONF_WH40K_LEXICANUM_NUM_RESULTS),
            ): vol.All(int, vol.Range(min=1, max=20)),
        }
    )


def get_wh40k_fandom_schema(hass) -> vol.Schema:
    """Return the static schema for Warhammer 40k Fandom service configuration."""
    return vol.Schema(
        {
            vol.Required(
                CONF_WH40K_FANDOM_NUM_RESULTS,
                default=SERVICE_DEFAULTS.get(CONF_WH40K_FANDOM_NUM_RESULTS),
            ): vol.All(int, vol.Range(min=1, max=20)),
        }
    )


STEP_ORDER = {
    STEP_USER: [None, get_step_user_data_schema],
    STEP_WH40K_LEXICANUM: [CONF_WH40K_LEXICANUM_ENABLED, get_wh40k_lexicanum_schema],
    STEP_WH40K_FANDOM: [CONF_WH40K_FANDOM_ENABLED, get_wh40k_fandom_schema],
}


def get_next_step(current_step: str, config_data: dict) -> tuple[str, callable] | None:
    """Get the next configuration step based on user selections."""
    keys = list(STEP_ORDER.keys())
    try:
        start = keys.index(current_step) + 1
    except ValueError:
        return None

    for key in keys[start:]:
        config_key, schema_func = STEP_ORDER[key]
        if config_key is None or config_data.get(config_key):
            return key, schema_func

    return None


class Wh40kToolsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the WH40k Tools for Assist integration."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.user_selections: dict[str, Any] = {}
        self.config_data: dict[str, Any] = {}

    async def handle_step(self, current_step: str, user_input: dict[str, Any] | None):
        """Handle a configuration step."""
        if user_input is None:
            return self.async_show_form(step_id=current_step)

        self.config_data.update(user_input)

        # Check if we need to configure other services
        next_step = get_next_step(current_step, self.user_selections)
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
            return self.async_abort(reason="single_instance_allowed")

        if user_input is None:
            # Display the main menu with checkboxes for WH40k tools
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
        next_step = get_next_step(STEP_USER, user_input)
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

    async def async_step_wh40k_lexicanum(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Warhammer 40k Lexicanum configuration step."""
        return await self.handle_step(STEP_WH40K_LEXICANUM, user_input)

    async def async_step_wh40k_fandom(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Warhammer 40k Fandom configuration step."""
        return await self.handle_step(STEP_WH40K_FANDOM, user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Provide an options flow for existing entries."""
        return Wh40kToolsOptionsFlow(config_entry)


class Wh40kToolsOptionsFlow(config_entries.OptionsFlowWithReload):
    """Handle an options flow for an existing WH40k Tools for Assist config entry."""

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
        """Handle the initial options step."""
        data = self.config_entry.data
        opts = self.config_entry.options or {}
        defaults = {**data, **opts}

        if user_input is None:
            schema_dict = {
                vol.Optional(
                    CONF_WH40K_LEXICANUM_ENABLED,
                    default=defaults.get(CONF_WH40K_LEXICANUM_ENABLED, False),
                ): bool,
                vol.Optional(
                    CONF_WH40K_FANDOM_ENABLED,
                    default=defaults.get(CONF_WH40K_FANDOM_ENABLED, False),
                ): bool,
            }
            schema = vol.Schema(schema_dict)
            return self.async_show_form(
                step_id=STEP_INIT,
                data_schema=schema,
                description_placeholders={
                    "current_services": self._get_current_services_description()
                },
            )

        # Store user selections and existing data
        self.user_selections = user_input.copy()
        self.config_data.update(user_input)

        next_step = get_next_step(STEP_USER, user_input)
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

        if data.get(CONF_WH40K_LEXICANUM_ENABLED):
            services.append("Warhammer 40k Lexicanum")
        if data.get(CONF_WH40K_FANDOM_ENABLED):
            services.append("Warhammer 40k Fandom")

        if services:
            return f"Currently configured: {', '.join(services)}"
        return "No services currently configured"

    async def handle_step(
        self, current_step: str, user_input: dict[str, Any] | None = None
    ):
        """Handle a configuration step in options flow."""
        if user_input is None:
            return self.async_show_form(step_id=current_step)
        self.config_data.update(user_input)

        next_step = get_next_step(current_step, self.user_selections)
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

        # Manual reload to match OptionsFlowWithReload behavior
        await self.hass.config_entries.async_reload(self.config_entry.entry_id)

        return self.async_create_entry(data=self.config_data)

    async def async_step_wh40k_lexicanum(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Warhammer 40k Lexicanum configuration step in options flow."""
        return await self.handle_step(STEP_WH40K_LEXICANUM, user_input)

    async def async_step_wh40k_fandom(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle Warhammer 40k Fandom configuration step in options flow."""
        return await self.handle_step(STEP_WH40K_FANDOM, user_input)
