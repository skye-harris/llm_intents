from .const import DOMAIN

__all__ = ["DOMAIN"]

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .llm_functions import setup_llm_functions, cleanup_llm_functions

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the LLM Intents integration."""
    hass.data.setdefault(DOMAIN, {})
    _LOGGER.info("Setting up LLM Intents integration")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up LLM Intents from a config entry."""
    _LOGGER.info("Setting up LLM Intents for entry: %s", entry.entry_id)
    await setup_llm_functions(hass, entry.data)
    _LOGGER.info("LLM Intents functions successfully set up")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading LLM Intents for entry: %s", entry.entry_id)
    await cleanup_llm_functions(hass)
    _LOGGER.info("LLM Intents functions successfully unloaded")
    return True
