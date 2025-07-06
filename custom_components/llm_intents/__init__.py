"""LLM Intents integration."""

from .const import DOMAIN

__all__ = ["DOMAIN"]

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent

from .brave_search import BraveSearch
from .const import (
    CONF_BRAVE_API_KEY,
    CONF_BRAVE_INTENT,
    CONF_GOOGLE_PLACES_API_KEY,
    CONF_GOOGLE_PLACES_INTENT,
    CONF_WIKIPEDIA_INTENT,
    CONF_WIKIPEDIA_NUM_RESULTS,
)
from .google_places import GooglePlaces
from .wikipedia_search import WikipediaSearch

_LOGGER = logging.getLogger(__name__)

INTENTS = [
    (CONF_BRAVE_INTENT, BraveSearch),
    (CONF_GOOGLE_PLACES_INTENT, GooglePlaces),
    (CONF_WIKIPEDIA_INTENT, WikipediaSearch),
]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the LLM Intents integration (configuration via config entries)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up LLM Intents handlers from a config entry."""
    conf = entry.options or entry.data

    # Handle case where both options and data are None
    if conf is None:
        _LOGGER.warning("Config entry %s has no data or options", entry.entry_id)
        return True

    # Check if any of the required API keys are present directly in config
    # This handles the flat config structure
    handlers_to_register = []

    # Check for Brave Search
    if conf.get(CONF_BRAVE_API_KEY):
        handlers_to_register.append((CONF_BRAVE_INTENT, BraveSearch))

    # Check for Google Places
    if conf.get(CONF_GOOGLE_PLACES_API_KEY):
        handlers_to_register.append((CONF_GOOGLE_PLACES_INTENT, GooglePlaces))

    # Check for Wikipedia (always available, no API key needed)
    if conf.get(CONF_WIKIPEDIA_NUM_RESULTS) is not None:
        handlers_to_register.append((CONF_WIKIPEDIA_INTENT, WikipediaSearch))

    # Also check for nested intent configuration structure
    for intent_key, handler_cls in INTENTS:
        intent_conf = conf.get(intent_key)
        if intent_conf:
            handlers_to_register.append((intent_key, handler_cls))

    # Register unique handlers (avoid duplicates)
    registered_intents = set()
    for intent_key, handler_cls in handlers_to_register:
        if intent_key in registered_intents:
            continue

        try:
            handler = handler_cls(hass, entry)
            intent.async_register(hass, handler)
            registered_intents.add(intent_key)
            _LOGGER.debug(
                "Registered intent handler %s with config entry %s",
                intent_key,
                entry.entry_id,
            )
        except (KeyError, ValueError, TypeError) as err:
            _LOGGER.warning(
                "Failed to initialize handler %s: %s. Skipping.",
                intent_key,
                err,
            )
            continue
        except Exception as err:
            _LOGGER.exception(
                "Unexpected error initializing handler %s: %s",
                intent_key,
                err,
            )
            continue

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload LLM Intents config entry."""
    # Optionally unregister intent handlers here if needed
    return True
