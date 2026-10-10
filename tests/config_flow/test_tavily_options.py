"""Tests for the Tavily options flow."""

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.llm_intents.const import (
    CONF_PROVIDER_API_KEYS,
    CONF_SEARCH_PROVIDER,
    CONF_SEARCH_PROVIDER_TAVILY,
    CONF_TAVILY_API_KEY,
    CONF_TAVILY_NUM_RESULTS,
    DOMAIN,
    PROVIDER_TAVILY,
)

STORED_KEY = "tvly-stored-key"


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Mock ConfigEntry holding a stored Tavily API key."""
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id="test_tavily_options_entry",
        data={},
        options={
            CONF_SEARCH_PROVIDER: CONF_SEARCH_PROVIDER_TAVILY,
            CONF_PROVIDER_API_KEYS: {PROVIDER_TAVILY: STORED_KEY},
            CONF_TAVILY_NUM_RESULTS: 2,
        },
    )


async def _walk_to_tavily(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    """Open the options flow and stop at the Tavily step, returning its flow id."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "configure"},
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SEARCH_PROVIDER: CONF_SEARCH_PROVIDER_TAVILY},
    )

    assert result["step_id"] == "tavily"
    return result["flow_id"]


async def test_options_flow_keeps_the_stored_key_when_blank(
    recorder_mock: None,
    enable_custom_integrations: None,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """
    Test that clearing the key field does not wipe the stored key.

    The form offers the stored key as a suggested value, and the field is
    required, so an empty submission has to mean "keep what is stored" rather
    than "store an empty key".
    """
    config_entry.add_to_hass(hass)
    flow_id = await _walk_to_tavily(hass, config_entry)

    result = await hass.config_entries.options.async_configure(
        flow_id,
        {CONF_TAVILY_API_KEY: "", CONF_TAVILY_NUM_RESULTS: 5},
    )

    assert result["type"] == "create_entry"
    assert config_entry.options[CONF_PROVIDER_API_KEYS][PROVIDER_TAVILY] == STORED_KEY
    assert config_entry.options[CONF_TAVILY_NUM_RESULTS] == 5


async def test_options_flow_stores_a_replaced_key(
    recorder_mock: None,
    enable_custom_integrations: None,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Test that a key entered in the form replaces the stored one."""
    config_entry.add_to_hass(hass)
    flow_id = await _walk_to_tavily(hass, config_entry)

    result = await hass.config_entries.options.async_configure(
        flow_id,
        {CONF_TAVILY_API_KEY: "tvly-replaced-key", CONF_TAVILY_NUM_RESULTS: 2},
    )

    assert result["type"] == "create_entry"
    assert (
        config_entry.options[CONF_PROVIDER_API_KEYS][PROVIDER_TAVILY]
        == "tvly-replaced-key"
    )
