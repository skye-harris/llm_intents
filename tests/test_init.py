"""Test the LLM Intents integration."""

from unittest.mock import Mock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.llm_intents import (
    DOMAIN,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)


class TestLlmIntentsIntegration:
    """Test the LLM Intents integration setup and teardown."""

    @pytest.fixture
    def hass(self):
        """Create a mock Home Assistant instance."""
        hass = Mock(spec=HomeAssistant)
        hass.data = {}
        return hass

    @pytest.fixture
    def config_entry(self):
        """Create a mock config entry."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry_id"
        entry.data = {
            "use_brave": True,
            "brave_api_key": "test_key",
            "use_wikipedia": True,
        }
        return entry

    async def test_async_setup(self, hass):
        """Test the async_setup function."""
        result = await async_setup(hass, {})

        assert result is True
        assert DOMAIN in hass.data

    async def test_async_setup_entry(self, hass, config_entry):
        """Test setting up a config entry."""
        with patch(
            "custom_components.llm_intents.llm_functions.setup_llm_functions"
        ) as mock_setup:
            # Mock the add_update_listener method
            config_entry.add_update_listener = Mock()
            config_entry.async_on_unload = Mock()

            result = await async_setup_entry(hass, config_entry)

            assert result is True
            assert DOMAIN in hass.data
            # Check that the current config is stored
            assert "current_config" in hass.data[DOMAIN]
            assert hass.data[DOMAIN]["current_config"] == config_entry.data
            mock_setup.assert_called_once_with(hass, config_entry.data)
            # Verify update listener was added
            config_entry.async_on_unload.assert_called_once()

    async def test_async_unload_entry(self, hass, config_entry):
        """Test unloading a config entry."""
        # Set up initial data as it would be after setup
        hass.data[DOMAIN] = {
            "api": Mock(),
            "current_config": config_entry.data,
            "unregister_api": Mock(),
        }

        with patch(
            "custom_components.llm_intents.llm_functions.cleanup_llm_functions"
        ) as mock_cleanup:
            result = await async_unload_entry(hass, config_entry)

            assert result is True
            mock_cleanup.assert_called_once_with(hass)

    async def test_async_update_options(self, hass, config_entry):
        """Test updating options."""
        from custom_components.llm_intents import async_update_options

        # Set up initial state
        hass.data[DOMAIN] = {
            "current_config": {"use_brave": True, "brave_api_key": "old_key"}
        }

        # Test with same config (should not reload)
        config_entry.data = {"use_brave": True, "brave_api_key": "old_key"}

        with patch(
            "custom_components.llm_intents.llm_functions.setup_llm_functions"
        ) as mock_setup:
            await async_update_options(hass, config_entry)
            mock_setup.assert_not_called()

        # Test with changed config (should reload)
        config_entry.data = {"use_brave": True, "brave_api_key": "new_key"}

        with patch(
            "custom_components.llm_intents.llm_functions.setup_llm_functions"
        ) as mock_setup:
            await async_update_options(hass, config_entry)
            mock_setup.assert_called_once_with(hass, config_entry.data)
            assert hass.data[DOMAIN]["current_config"] == config_entry.data
