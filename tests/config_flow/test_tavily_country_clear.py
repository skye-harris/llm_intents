"""
Tests for clearing the Tavily country in the options flow.

The frontend reports a cleared select as undefined, so the field is absent from
the submission, and the options flow merges the submission over the options
already stored. The country therefore has to be seeded on the way in, as the
Brave steps do, or a stored country can never be cleared.
"""

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.llm_intents.const import (
    CONF_PROVIDER_API_KEYS,
    CONF_SEARCH_PROVIDER,
    CONF_SEARCH_PROVIDER_TAVILY,
    CONF_TAVILY_API_KEY,
    CONF_TAVILY_COUNTRY,
    CONF_TAVILY_NUM_RESULTS,
    DOMAIN,
    PROVIDER_TAVILY,
)
from tests.utils import open_tavily_step

STORED_COUNTRY = "United States"


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Mock ConfigEntry with a country already stored."""
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id="test_tavily_country_clear",
        data={},
        options={
            CONF_SEARCH_PROVIDER: CONF_SEARCH_PROVIDER_TAVILY,
            CONF_PROVIDER_API_KEYS: {PROVIDER_TAVILY: "tvly-key"},
            CONF_TAVILY_NUM_RESULTS: 2,
            CONF_TAVILY_COUNTRY: STORED_COUNTRY,
        },
    )


async def test_omitted_country_is_cleared(
    recorder_mock: None,
    enable_custom_integrations: None,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Test the field the frontend leaves out when cleared is cleared."""
    config_entry.add_to_hass(hass)
    flow_id = await open_tavily_step(hass, config_entry)

    result = await hass.config_entries.options.async_configure(
        flow_id,
        {CONF_TAVILY_API_KEY: "tvly-key", CONF_TAVILY_NUM_RESULTS: 2},
    )

    assert result["type"] == "create_entry"
    assert config_entry.options[CONF_TAVILY_COUNTRY] is None


async def test_a_chosen_country_is_still_stored(
    recorder_mock: None,
    enable_custom_integrations: None,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Test picking a country still stores it."""
    config_entry.add_to_hass(hass)
    flow_id = await open_tavily_step(hass, config_entry)

    result = await hass.config_entries.options.async_configure(
        flow_id,
        {
            CONF_TAVILY_API_KEY: "tvly-key",
            CONF_TAVILY_NUM_RESULTS: 2,
            CONF_TAVILY_COUNTRY: "Germany",
        },
    )

    assert result["type"] == "create_entry"
    assert config_entry.options[CONF_TAVILY_COUNTRY] == "Germany"
