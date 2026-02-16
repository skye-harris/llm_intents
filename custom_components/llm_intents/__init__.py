from .config_flow import LlmIntentsConfigFlow
from .const import (
    CONF_BRAVE_ENABLED,
    CONF_DAILY_WEATHER_ENTITY,
    CONF_GOOGLE_PLACES_API_KEY,
    CONF_HOURLY_WEATHER_ENTITY,
    CONF_PROVIDER_API_KEYS,
    CONF_SEARCH_PROVIDER,
    CONF_SEARCH_PROVIDER_BRAVE,
    DOMAIN,
    PROVIDER_GOOGLE,
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
    entry_options = (entry.options or {}).copy()
    current_version = entry.version

    if current_version == 1:
        entry_data[CONF_SEARCH_PROVIDER] = (
            CONF_SEARCH_PROVIDER_BRAVE
            if entry_data.get(CONF_BRAVE_ENABLED, False)
            else None
        )

        if entry_data.get(CONF_HOURLY_WEATHER_ENTITY) == "None":
            entry_data[CONF_HOURLY_WEATHER_ENTITY] = None

        entry_data.pop(CONF_BRAVE_ENABLED, None)
        hass.config_entries.async_update_entry(entry, version=2, data=entry_data)
        current_version = 2
        # Refresh entry data after update
        entry_data = entry.data.copy()
        entry_options = (entry.options or {}).copy()

    if current_version == 2:
        # Migrate CONF_GOOGLE_PLACES_API_KEY to CONF_PROVIDER_API_KEYS
        provider_keys = entry_data.get(CONF_PROVIDER_API_KEYS, {})
        if not isinstance(provider_keys, dict):
            provider_keys = {}

        # Check data first
        if CONF_GOOGLE_PLACES_API_KEY in entry_data:
            places_key = entry_data[CONF_GOOGLE_PLACES_API_KEY]
            if places_key and PROVIDER_GOOGLE not in provider_keys:
                provider_keys[PROVIDER_GOOGLE] = places_key
                _LOGGER.info(
                    "Migrating google_places_api_key from data to provider_api_keys"
                )
            entry_data.pop(CONF_GOOGLE_PLACES_API_KEY, None)

        # Check options
        if CONF_GOOGLE_PLACES_API_KEY in entry_options:
            places_key = entry_options[CONF_GOOGLE_PLACES_API_KEY]
            if places_key and PROVIDER_GOOGLE not in provider_keys:
                provider_keys[PROVIDER_GOOGLE] = places_key
                _LOGGER.info(
                    "Migrating google_places_api_key from options to provider_api_keys"
                )
            entry_options.pop(CONF_GOOGLE_PLACES_API_KEY, None)

        # Always update to version 3, even if no keys to migrate
        if provider_keys:
            entry_data[CONF_PROVIDER_API_KEYS] = provider_keys

        hass.config_entries.async_update_entry(
            entry, version=3, data=entry_data, options=entry_options
        )

    return True
