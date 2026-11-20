"""Tools for Assist."""

from .const import (
    CONF_BRAVE_ENABLED,
    CONF_GOOGLE_PLACES_API_KEY,
    CONF_GOOGLE_PLACES_ENABLED,
    CONF_HOURLY_WEATHER_ENTITY,
    CONF_PLACES_PROVIDER,
    CONF_PLACES_PROVIDER_GOOGLE,
    CONF_PROVIDER_API_KEYS,
    CONF_SEARCH_PROVIDER,
    CONF_SEARCH_PROVIDER_BRAVE,
    CONFIG_VERSION_1,
    CONFIG_VERSION_2,
    CONFIG_VERSION_3,
    CONFIG_VERSION_4,
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
    _LOGGER.info("Setting up %s", ADDON_NAME)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tools for Assist from a config entry."""
    _LOGGER.info("Setting up %s for entry: %s", ADDON_NAME, entry.entry_id)
    await setup_llm_functions(hass, entry)
    _LOGGER.info("%s functions successfully set up", ADDON_NAME)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading %s for entry: %s", ADDON_NAME, entry.entry_id)
    await cleanup_llm_functions(entry)
    _LOGGER.info("%s functions successfully unloaded", ADDON_NAME)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate entry."""
    _LOGGER.debug("Migrating from version %s", entry.version)
    entry_data = entry.data.copy()
    entry_options = (entry.options or {}).copy()
    current_version = entry.version

    if current_version == CONFIG_VERSION_1:
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

    if current_version == CONFIG_VERSION_2:
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
                    "Migrating google_places_api_key from data to provider_api_keys",
                )
            entry_data.pop(CONF_GOOGLE_PLACES_API_KEY, None)

        # Check options
        if CONF_GOOGLE_PLACES_API_KEY in entry_options:
            places_key = entry_options[CONF_GOOGLE_PLACES_API_KEY]
            if places_key and PROVIDER_GOOGLE not in provider_keys:
                provider_keys[PROVIDER_GOOGLE] = places_key
                _LOGGER.info(
                    "Migrating google_places_api_key from options to provider_api_keys",
                )
            entry_options.pop(CONF_GOOGLE_PLACES_API_KEY, None)

        # Always update to version 3, even if no keys to migrate
        if provider_keys:
            entry_data[CONF_PROVIDER_API_KEYS] = provider_keys

        hass.config_entries.async_update_entry(
            entry,
            version=3,
            data=entry_data,
            options=entry_options,
        )
        current_version = CONFIG_VERSION_3

    if current_version == CONFIG_VERSION_3:
        # Places search became a provider choice: migrate the old
        # google_places_enabled boolean to the places_provider selector so
        # existing setups keep the places tool they already had. A provider
        # counts as already chosen if either store holds one — checking the
        # merged view alone would miss a provider stored in data behind an
        # empty selection in options.
        provider_set = bool(entry_data.get(CONF_PLACES_PROVIDER)) or bool(
            entry_options.get(CONF_PLACES_PROVIDER)
        )
        if not provider_set:
            merged_config = {**entry_data, **entry_options}
            if merged_config.get(CONF_GOOGLE_PLACES_ENABLED):
                entry_data[CONF_PLACES_PROVIDER] = CONF_PLACES_PROVIDER_GOOGLE
                # An empty selection stored in options would shadow the
                # provider migrated into data (options win when the runtime
                # merges them), so drop it.
                entry_options.pop(CONF_PLACES_PROVIDER, None)
                _LOGGER.info(
                    "Migrating google_places_enabled to places_provider: Google",
                )
        # The boolean is fully replaced by the selector; remove it the
        # same way earlier migrations removed their replaced keys.
        entry_data.pop(CONF_GOOGLE_PLACES_ENABLED, None)
        entry_options.pop(CONF_GOOGLE_PLACES_ENABLED, None)

        hass.config_entries.async_update_entry(
            entry,
            version=CONFIG_VERSION_4,
            data=entry_data,
            options=entry_options,
        )

    return True
