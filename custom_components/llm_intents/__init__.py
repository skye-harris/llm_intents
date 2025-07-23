from .const import DOMAIN

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
    await setup_llm_functions(hass, entry.data)
    _LOGGER.info(f"{ADDON_NAME} functions successfully set up")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info(f"Unloading {ADDON_NAME} for entry: %s", entry.entry_id)
    await cleanup_llm_functions(hass)
    _LOGGER.info(f"{ADDON_NAME} functions successfully unloaded")
    return True
