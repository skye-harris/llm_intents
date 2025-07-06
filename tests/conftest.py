# pylint: disable=protected-access,redefined-outer-name
"""Global fixtures for LLM Intents integration tests."""

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.llm_intents import DOMAIN
from tests import async_init_integration, patch_async_setup_entry

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture
def mock_config_entry():
    """Return a MockConfigEntry for llm_intents with minimal required data."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            "api_key": "dummy_key",
            "num_results": 2,
            "country_code": "US",
            "latitude": 0.0,
            "longitude": 0.0,
            "timezone": "UTC",
        },
    )


# Automatically enable loading custom integrations in all tests
@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Turn on custom integration loading."""
    return


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> MockConfigEntry:
    """Set up the LLM Intents integration for testing."""
    # Patch llm_intents.async_setup_entry so HA will accept our entry
    with patch_async_setup_entry(return_value=True):
        await async_init_integration(hass, mock_config_entry)

    return mock_config_entry
