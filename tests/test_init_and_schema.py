"""Tests for the llm_intents custom component initialization and schema."""

import pytest
import voluptuous as vol
from homeassistant.helpers import intent as intent_helpers

from custom_components.llm_intents import (
    CONF_BRAVE_INTENT,
    CONF_GOOGLE_PLACES_INTENT,
    CONF_WIKIPEDIA_INTENT,
    DOMAIN,
    PLATFORM_SCHEMA,
    async_setup,
)
from custom_components.llm_intents.brave_search import BraveSearch
from custom_components.llm_intents.google_places import GooglePlaces
from custom_components.llm_intents.wikipedia_search import WikipediaSearch


def test_platform_schema_all_options():
    """Platform schema should accept all valid intent configurations."""
    PLATFORM_SCHEMA({})  # Completely empty configuration is allowed

    # All three intents enabled with minimal settings

    config = {
        CONF_BRAVE_INTENT: {"api_key": "key", "num_results": 3},
        CONF_GOOGLE_PLACES_INTENT: {"api_key": "gkey", "num_results": 4},
        CONF_WIKIPEDIA_INTENT: {"num_results": 2},
    }
    PLATFORM_SCHEMA(config)

    # Explicit True for Wikipedia intent

    PLATFORM_SCHEMA({CONF_WIKIPEDIA_INTENT: True})


def test_platform_schema_invalid():
    """Platform schema should reject invalid configurations."""
    bad = {CONF_BRAVE_INTENT: {"num_results": 1}}  # missing api_key
    with pytest.raises(vol.Invalid):
        PLATFORM_SCHEMA(bad)
    bad2 = {CONF_GOOGLE_PLACES_INTENT: {"api_key": "k", "num_results": "two"}}
    with pytest.raises(vol.Invalid):
        PLATFORM_SCHEMA(bad2)


@pytest.mark.asyncio
async def test_async_setup_no_config(hass):
    """async_setup should return True and do nothing if domain not present."""
    hass.data.clear()
    calls = []
    monkey = pytest.MonkeyPatch()
    monkey.setattr(
        intent_helpers, "async_register", lambda _h, inst: calls.append(inst)
    )
    result = await async_setup(hass, {})
    assert result is True
    assert calls == []
    monkey.undo()


@pytest.mark.asyncio
async def test_async_setup_registers_handlers(hass):
    """async_setup should register handlers for configured intents."""
    registered = []
    monkey = pytest.MonkeyPatch()
    monkey.setattr(
        intent_helpers,
        "async_register",
        lambda _h, inst: registered.append(inst.__class__),
    )

    cfg = {
        CONF_BRAVE_INTENT: {"api_key": "bkey", "num_results": 1},
        CONF_GOOGLE_PLACES_INTENT: {"api_key": "gkey", "num_results": 2},
        CONF_WIKIPEDIA_INTENT: {"num_results": 3},
    }
    config = {DOMAIN: [cfg]}

    result = await async_setup(hass, config)
    assert result is True

    assert BraveSearch in registered
    assert GooglePlaces in registered
    assert WikipediaSearch in registered
    monkey.undo()


@pytest.mark.asyncio
async def test_async_setup_skips_and_handles_true(hass):
    """async_setup should skip disabled intents and accept True for config."""
    registered = []
    monkey = pytest.MonkeyPatch()
    monkey.setattr(
        intent_helpers,
        "async_register",
        lambda _h, inst: registered.append(inst.__class__),
    )

    cfg = {
        CONF_BRAVE_INTENT: None,
        CONF_GOOGLE_PLACES_INTENT: True,
    }
    config = {DOMAIN: [cfg]}

    result = await async_setup(hass, config)
    assert result is True
    assert registered == [GooglePlaces]
    monkey.undo()
