"""Tests for the LLM Intents integration initialization."""

from unittest.mock import Mock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.llm_intents import (
    INTENTS,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.llm_intents.brave_search import BraveSearch
from custom_components.llm_intents.const import (
    CONF_BRAVE_API_KEY,
    CONF_BRAVE_INTENT,
    CONF_GOOGLE_PLACES_API_KEY,
    CONF_GOOGLE_PLACES_INTENT,
    CONF_WIKIPEDIA_INTENT,
    CONF_WIKIPEDIA_NUM_RESULTS,
    DOMAIN,
)
from custom_components.llm_intents.google_places import GooglePlaces
from custom_components.llm_intents.wikipedia_search import WikipediaSearch


class TestIntegrationSetup:
    """Test the integration setup functions."""

    @pytest.fixture
    def hass(self):
        """Create a mock Home Assistant instance."""
        return Mock(spec=HomeAssistant)

    @pytest.fixture
    def mock_config_entry(self):
        """Create a mock config entry."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry_id"
        entry.data = {
            CONF_BRAVE_API_KEY: "test_brave_key",
            CONF_GOOGLE_PLACES_API_KEY: "test_google_key",
            CONF_WIKIPEDIA_NUM_RESULTS: 2,
        }
        entry.options = None
        return entry

    async def test_async_setup(self, hass):
        """Test the main integration setup."""
        result = await async_setup(hass, {})
        assert result is True

    async def test_async_setup_entry_with_all_handlers(self, hass, mock_config_entry):
        """Test setup entry with all intent handlers configured."""
        # Configure all intent types with flat structure
        mock_config_entry.data = {
            CONF_BRAVE_API_KEY: "test_key",
            CONF_GOOGLE_PLACES_API_KEY: "test_key",
            CONF_WIKIPEDIA_NUM_RESULTS: 2,
        }

        with patch(
            "custom_components.llm_intents.intent.async_register"
        ) as mock_register:
            result = await async_setup_entry(hass, mock_config_entry)

            assert result is True
            # Should register 3 handlers
            assert mock_register.call_count == 3

            # Check that handlers are registered with correct types
            registered_handlers = [
                call.args[1] for call in mock_register.call_args_list
            ]
            handler_types = [type(handler) for handler in registered_handlers]

            assert BraveSearch in handler_types
            assert GooglePlaces in handler_types
            assert WikipediaSearch in handler_types

    async def test_async_setup_entry_with_single_handler(self, hass, mock_config_entry):
        """Test setup entry with only one intent handler configured."""
        # Configure only Brave search with flat structure
        mock_config_entry.data = {CONF_BRAVE_API_KEY: "test_key"}

        with patch(
            "custom_components.llm_intents.intent.async_register"
        ) as mock_register:
            result = await async_setup_entry(hass, mock_config_entry)

            assert result is True
            # Should register only 1 handler
            assert mock_register.call_count == 1

            # Check that the correct handler was registered
            registered_handler = mock_register.call_args_list[0].args[1]
            assert isinstance(registered_handler, BraveSearch)

    async def test_async_setup_entry_with_no_handlers(self, hass, mock_config_entry):
        """Test setup entry with no intent handlers configured."""
        # Empty configuration
        mock_config_entry.data = {}

        with patch(
            "custom_components.llm_intents.intent.async_register"
        ) as mock_register:
            result = await async_setup_entry(hass, mock_config_entry)

            assert result is True
            # Should not register any handlers
            assert mock_register.call_count == 0

    async def test_async_setup_entry_uses_options_over_data(
        self, hass, mock_config_entry
    ):
        """Test that options are used over data when both are present."""
        mock_config_entry.data = {CONF_BRAVE_API_KEY: "data_key"}
        mock_config_entry.options = {CONF_WIKIPEDIA_NUM_RESULTS: 3}

        with patch(
            "custom_components.llm_intents.intent.async_register"
        ) as mock_register:
            result = await async_setup_entry(hass, mock_config_entry)

            assert result is True
            # Should register only Wikipedia handler (from options)
            assert mock_register.call_count == 1

            registered_handler = mock_register.call_args_list[0].args[1]
            assert isinstance(registered_handler, WikipediaSearch)

    async def test_async_setup_entry_handler_initialization(
        self, hass, mock_config_entry
    ):
        """Test that handlers are initialized with correct parameters."""
        mock_config_entry.data = {CONF_BRAVE_API_KEY: "test_key"}

        with patch(
            "custom_components.llm_intents.intent.async_register"
        ) as mock_register:
            await async_setup_entry(hass, mock_config_entry)

            # Get the registered handler
            registered_handler = mock_register.call_args_list[0].args[1]

            # Check that handler was initialized with correct parameters
            assert registered_handler.hass is hass
            assert registered_handler.config_entry is mock_config_entry

    async def test_async_unload_entry(self, hass, mock_config_entry):
        """Test the unload entry function."""
        result = await async_unload_entry(hass, mock_config_entry)
        assert result is True


class TestIntentsConfiguration:
    """Test the INTENTS configuration."""

    def test_intents_list_structure(self):
        """Test that INTENTS list has correct structure."""
        assert isinstance(INTENTS, list)
        assert len(INTENTS) == 3

        # Check that all items are tuples with intent key and handler class
        for intent_item in INTENTS:
            assert isinstance(intent_item, tuple)
            assert len(intent_item) == 2
            intent_key, handler_cls = intent_item
            assert isinstance(intent_key, str)
            assert callable(handler_cls)

    def test_intents_contains_expected_handlers(self):
        """Test that INTENTS contains expected handler mappings."""
        intent_dict = dict(INTENTS)

        assert CONF_BRAVE_INTENT in intent_dict
        assert intent_dict[CONF_BRAVE_INTENT] == BraveSearch

        assert CONF_GOOGLE_PLACES_INTENT in intent_dict
        assert intent_dict[CONF_GOOGLE_PLACES_INTENT] == GooglePlaces

        assert CONF_WIKIPEDIA_INTENT in intent_dict
        assert intent_dict[CONF_WIKIPEDIA_INTENT] == WikipediaSearch


class TestIntegrationLogging:
    """Test logging behavior in the integration."""

    @pytest.fixture
    def hass(self):
        """Create a mock Home Assistant instance."""
        return Mock(spec=HomeAssistant)

    @pytest.fixture
    def mock_config_entry(self):
        """Create a mock config entry."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry_id"
        entry.data = {CONF_BRAVE_INTENT: {CONF_BRAVE_API_KEY: "test_key"}}
        entry.options = None
        return entry

    async def test_setup_entry_logs_registration(self, hass, mock_config_entry):
        """Test that handler registration is logged."""
        # Configure with flat structure that __init__.py now supports
        mock_config_entry.data = {CONF_BRAVE_API_KEY: "test_key"}
        mock_config_entry.options = None

        with patch("custom_components.llm_intents.intent.async_register"), patch(
            "custom_components.llm_intents._LOGGER.debug"
        ) as mock_logger:

            await async_setup_entry(hass, mock_config_entry)

            # Check that debug log was called
            mock_logger.assert_called_once()
            log_call = mock_logger.call_args[0]
            assert "Registered intent handler" in log_call[0]
            assert CONF_BRAVE_INTENT in log_call[1]
            assert "test_entry_id" in log_call[2]


class TestErrorHandling:
    """Test error handling in the integration."""

    @pytest.fixture
    def hass(self):
        """Create a mock Home Assistant instance."""
        return Mock(spec=HomeAssistant)

    @pytest.fixture
    def mock_config_entry(self):
        """Create a mock config entry."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry_id"
        entry.data = {CONF_BRAVE_API_KEY: "test_key"}  # Use flat structure
        entry.options = None
        return entry

    async def test_setup_entry_handles_handler_init_failure(
        self, hass, mock_config_entry
    ):
        """Test that setup continues if handler initialization fails."""
        with patch(
            "custom_components.llm_intents.BraveSearch",
            side_effect=Exception("Init failed"),
        ), patch(
            "custom_components.llm_intents.intent.async_register"
        ) as mock_register, patch(
            "custom_components.llm_intents._LOGGER.exception"
        ) as mock_logger:

            # Should not raise an exception, but should skip the failed handler
            result = await async_setup_entry(hass, mock_config_entry)

            assert result is True
            # Should not register any handlers due to init failure
            assert mock_register.call_count == 0
            # Should log the exception
            mock_logger.assert_called_once()

    async def test_setup_entry_handles_missing_config_gracefully(self, hass):
        """Test that setup handles config entries with missing data gracefully."""
        mock_config_entry = Mock(spec=ConfigEntry)
        mock_config_entry.entry_id = "test_entry_id"
        mock_config_entry.data = None
        mock_config_entry.options = None

        with patch(
            "custom_components.llm_intents.intent.async_register"
        ) as mock_register:
            # Should handle None data gracefully by catching AttributeError
            result = await async_setup_entry(hass, mock_config_entry)
            assert result is True
            assert mock_register.call_count == 0


class TestIntegrationImports:
    """Test that all required modules are properly imported."""

    def test_domain_import(self):
        """Test that DOMAIN constant is properly imported."""
        # DOMAIN is already imported at the module level
        assert isinstance(DOMAIN, str)

    def test_handler_classes_imported(self):
        """Test that handler classes are properly imported."""
        # This test ensures the imports work correctly
        assert BraveSearch is not None
        assert GooglePlaces is not None
        assert WikipediaSearch is not None

    def test_const_imports(self):
        """Test that constants are properly imported."""
        # This test ensures all required constants are available
        assert CONF_BRAVE_INTENT is not None
        assert CONF_GOOGLE_PLACES_INTENT is not None
        assert CONF_WIKIPEDIA_INTENT is not None


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def hass(self):
        """Create a mock Home Assistant instance."""
        return Mock(spec=HomeAssistant)

    async def test_setup_with_empty_config(self, hass):
        """Test setup with completely empty configuration."""
        result = await async_setup(hass, {})
        assert result is True

    async def test_setup_entry_with_malformed_config(self, hass):
        """Test setup entry with malformed configuration data."""
        mock_config_entry = Mock(spec=ConfigEntry)
        mock_config_entry.entry_id = "test_entry_id"
        mock_config_entry.data = {
            CONF_BRAVE_INTENT: "invalid_config_type"  # Should be dict
        }
        mock_config_entry.options = None

        with patch(
            "custom_components.llm_intents.intent.async_register"
        ) as mock_register, patch(
            "custom_components.llm_intents._LOGGER.warning"
        ) as mock_logger:
            # Should handle malformed entries gracefully
            result = await async_setup_entry(hass, mock_config_entry)
            assert result is True
            # Should not register any handlers due to malformed config
            assert mock_register.call_count == 0
            # Should log a warning about the failed initialization
            mock_logger.assert_called_once()

    async def test_unload_entry_always_succeeds(self, hass):
        """Test that unload entry always returns True."""
        mock_config_entry = Mock(spec=ConfigEntry)

        # Should always succeed regardless of config
        result = await async_unload_entry(hass, mock_config_entry)
        assert result is True
