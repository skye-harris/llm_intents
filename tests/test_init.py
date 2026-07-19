"""Test the LLM Intents integration."""

from typing import Any
from unittest.mock import Mock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.llm_intents import (
    DOMAIN,
    async_migrate_entry,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.llm_intents.const import (
    CONF_GOOGLE_PLACES_API_KEY,
    CONF_PROVIDER_API_KEYS,
    PROVIDER_GOOGLE,
)


class TestLlmIntentsIntegration:
    """Test the LLM Intents integration setup and teardown."""

    @pytest.fixture
    def config_entry(self) -> ConfigEntry:
        """Create a mock config entry."""
        return MockConfigEntry(
            domain=DOMAIN,
            entry_id="test_entry_id",
            data={
                "use_brave": True,
                "brave_api_key": "test_key",
                "use_wikipedia": True,
            },
            options={},
        )

    async def test_async_setup(self, hass: HomeAssistant) -> None:
        """Test the async_setup function."""
        result = await async_setup(hass, {})

        assert result is True
        assert DOMAIN in hass.data

    async def test_async_setup_entry(
        self, hass: HomeAssistant, config_entry: ConfigEntry
    ) -> None:
        """Test setting up a config entry."""
        config_entry.add_to_hass(hass)

        with patch("custom_components.llm_intents.setup_llm_functions") as mock_setup:
            result = await async_setup_entry(hass, config_entry)

            assert result is True
            mock_setup.assert_called_once_with(hass, config_entry.data)

    async def test_async_unload_entry(
        self, hass: HomeAssistant, config_entry: ConfigEntry
    ) -> None:
        """Test unloading a config entry."""
        # Set up initial data as it would be after setup
        hass.data[DOMAIN] = {
            "api": Mock(),
            "current_config": config_entry.data,
            "unregister_api": [],
        }

        with patch(
            "custom_components.llm_intents.cleanup_llm_functions"
        ) as mock_cleanup:
            result = await async_unload_entry(hass, config_entry)

            assert result is True
            mock_cleanup.assert_called_once_with(hass)

    async def test_async_migrate_entry_v2_to_v3_migrates_places_key(
        self, hass: HomeAssistant
    ) -> None:
        """Test migrating from version 2 to 3 migrates google_places_api_key to provider_api_keys."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            entry_id="test_entry",
            version=2,
            data={
                CONF_GOOGLE_PLACES_API_KEY: "test_google_api_key",
                "other_config": "value",
            },
            options={},
        )

        # Track what gets updated
        updated_data = {}
        updated_options = {}
        updated_version = None

        def mock_update_entry(entry_obj: ConfigEntry, **kwargs: Any) -> None:
            nonlocal updated_data, updated_options, updated_version
            updated_data = kwargs.get("data", {})
            updated_options = kwargs.get("options", {})
            updated_version = kwargs.get("version")

        hass.config_entries.async_update_entry = Mock(side_effect=mock_update_entry)

        result = await async_migrate_entry(hass, entry)

        assert result is True
        assert updated_version == 3
        assert CONF_PROVIDER_API_KEYS in updated_data
        assert (
            updated_data[CONF_PROVIDER_API_KEYS][PROVIDER_GOOGLE]
            == "test_google_api_key"
        )
        assert CONF_GOOGLE_PLACES_API_KEY not in updated_data
        assert "other_config" in updated_data
        assert updated_data["other_config"] == "value"

        # Verify that the migrated key can be accessed the new way
        # (simulating how tools would access it)
        config_data = {**updated_data, **updated_options}
        provider_keys = config_data.get(CONF_PROVIDER_API_KEYS) or {}
        api_key = provider_keys.get(PROVIDER_GOOGLE, "")
        assert api_key == "test_google_api_key"
