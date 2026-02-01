from .config_flow import LlmIntentsConfigFlow
from .const import (
    CONF_BRAVE_ENABLED,
    CONF_DAILY_WEATHER_ENTITY,
    CONF_HOURLY_WEATHER_ENTITY,
    CONF_SEARCH_PROVIDER,
    CONF_SEARCH_PROVIDER_BRAVE,
    DOMAIN,
)

__all__ = ["DOMAIN"]

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import ADDON_NAME
from .llm_functions import cleanup_llm_functions, setup_llm_functions

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Tools for Assist integration."""
    hass.data.setdefault(DOMAIN, {})
    _LOGGER.info(f"Setting up {ADDON_NAME} integration")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tools for Assist from a config entry."""
    _LOGGER.info(f"Setting up {ADDON_NAME} for entry: %s", entry.entry_id)
    config = {**entry.data, **(entry.options or {})}
    await setup_llm_functions(hass, config)
    _LOGGER.info(f"{ADDON_NAME} functions successfully set up")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info(f"Unloading {ADDON_NAME} for entry: %s", entry.entry_id)
    await cleanup_llm_functions(hass)
    _LOGGER.info(f"{ADDON_NAME} functions successfully unloaded")
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate entry."""
    _LOGGER.debug("Migrating from version %s", entry.version)
    entry_data = entry.data.copy()

    if entry.version == 1:
        entry_data[CONF_SEARCH_PROVIDER] = (
            CONF_SEARCH_PROVIDER_BRAVE
            if entry_data.get(CONF_BRAVE_ENABLED, False)
            else None
        )

        if entry_data.get(CONF_HOURLY_WEATHER_ENTITY) == "None":
            entry_data[CONF_HOURLY_WEATHER_ENTITY] = None

        entry_data.pop(CONF_BRAVE_ENABLED, None)
        hass.config_entries.async_update_entry(entry, version=2, data=entry_data)

    return True
