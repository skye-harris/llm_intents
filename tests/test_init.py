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
        hass = Mock(spec=HomeAssistant)
        hass.data = {}
        return hass

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
        hass = Mock(spec=HomeAssistant)
        hass.data = {}
        return hass

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

        with (
            patch("custom_components.llm_intents.intent.async_register"),
            patch("custom_components.llm_intents._LOGGER.debug") as mock_logger,
        ):
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
        hass = Mock(spec=HomeAssistant)
        hass.data = {}
        return hass

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
        with (
            patch(
                "custom_components.llm_intents.BraveSearch",
                side_effect=Exception("Init failed"),
            ),
            patch(
                "custom_components.llm_intents.intent.async_register"
            ) as mock_register,
            patch("custom_components.llm_intents._LOGGER.exception") as mock_logger,
        ):
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

    async def test_setup_entry_handles_key_error_in_handler_init(
        self, hass, mock_config_entry
    ):
        """Test that setup handles KeyError during handler initialization."""
        with (
            patch(
                "custom_components.llm_intents.BraveSearch",
                side_effect=KeyError("Missing required key"),
            ),
            patch(
                "custom_components.llm_intents.intent.async_register"
            ) as mock_register,
            patch("custom_components.llm_intents._LOGGER.warning") as mock_logger,
        ):
            result = await async_setup_entry(hass, mock_config_entry)

            assert result is True
            assert mock_register.call_count == 0
            # Should log a warning for KeyError
            mock_logger.assert_called_once()
            assert "Failed to initialize handler" in mock_logger.call_args[0][0]

    async def test_setup_entry_handles_value_error_in_handler_init(
        self, hass, mock_config_entry
    ):
        """Test that setup handles ValueError during handler initialization."""
        with (
            patch(
                "custom_components.llm_intents.BraveSearch",
                side_effect=ValueError("Invalid value"),
            ),
            patch(
                "custom_components.llm_intents.intent.async_register"
            ) as mock_register,
            patch("custom_components.llm_intents._LOGGER.warning") as mock_logger,
        ):
            result = await async_setup_entry(hass, mock_config_entry)

            assert result is True
            assert mock_register.call_count == 0
            # Should log a warning for ValueError
            mock_logger.assert_called_once()
            assert "Failed to initialize handler" in mock_logger.call_args[0][0]

    async def test_setup_entry_handles_type_error_in_handler_init(
        self, hass, mock_config_entry
    ):
        """Test that setup handles TypeError during handler initialization."""
        with (
            patch(
                "custom_components.llm_intents.BraveSearch",
                side_effect=TypeError("Type error"),
            ),
            patch(
                "custom_components.llm_intents.intent.async_register"
            ) as mock_register,
            patch("custom_components.llm_intents._LOGGER.warning") as mock_logger,
        ):
            result = await async_setup_entry(hass, mock_config_entry)

            assert result is True
            assert mock_register.call_count == 0
            # Should log a warning for TypeError
            mock_logger.assert_called_once()
            assert "Failed to initialize handler" in mock_logger.call_args[0][0]

    async def test_unload_entry_with_existing_data(self, hass):
        """Test unload entry when data exists in hass.data."""
        # Set up existing data
        hass.data[DOMAIN] = {"test_entry_id": {"some": "data"}}

        mock_config_entry = Mock(spec=ConfigEntry)
        mock_config_entry.entry_id = "test_entry_id"

        result = await async_unload_entry(hass, mock_config_entry)

        assert result is True
        # Verify the entry was removed from hass.data
        assert "test_entry_id" not in hass.data[DOMAIN]

    async def test_unload_entry_with_no_domain_data(self, hass):
        """Test unload entry when no domain data exists."""
        # Don't set up any data in hass.data[DOMAIN]
        mock_config_entry = Mock(spec=ConfigEntry)
        mock_config_entry.entry_id = "test_entry_id"

        result = await async_unload_entry(hass, mock_config_entry)

        assert result is True

    async def test_setup_entry_with_empty_nested_intent_config(self, hass):
        """Test setup entry with empty nested intent configuration."""
        mock_config_entry = Mock(spec=ConfigEntry)
        mock_config_entry.entry_id = "test_entry_id"
        # Use nested config that exists but is empty/falsy
        mock_config_entry.data = {
            CONF_BRAVE_INTENT: {},  # Empty dict should be falsy
            CONF_BRAVE_API_KEY: "test_key",  # This should trigger flat config
        }
        mock_config_entry.options = None

        with patch(
            "custom_components.llm_intents.intent.async_register"
        ) as mock_register:
            result = await async_setup_entry(hass, mock_config_entry)

            assert result is True
            # Should register 1 handler from flat config, not nested
            assert mock_register.call_count == 1

    async def test_setup_entry_data_storage(self, hass):
        """Test that setup entry stores data correctly in hass.data."""
        mock_config_entry = Mock(spec=ConfigEntry)
        mock_config_entry.entry_id = "test_entry_id"
        mock_config_entry.data = {CONF_BRAVE_API_KEY: "test_key"}
        mock_config_entry.options = None

        with patch("custom_components.llm_intents.intent.async_register"):
            result = await async_setup_entry(hass, mock_config_entry)

            assert result is True
            # Verify data was stored correctly
            assert DOMAIN in hass.data
            assert "test_entry_id" in hass.data[DOMAIN]
            stored_data = hass.data[DOMAIN]["test_entry_id"]
            assert "registered_intents" in stored_data
            assert "config" in stored_data
            assert CONF_BRAVE_INTENT in stored_data["registered_intents"]

    async def test_setup_entry_duplicate_handler_prevention(self, hass):
        """Test that duplicate handlers are not registered."""
        mock_config_entry = Mock(spec=ConfigEntry)
        mock_config_entry.entry_id = "test_entry_id"
        # Set up config that would create duplicate handlers
        mock_config_entry.data = {
            CONF_BRAVE_API_KEY: "test_key",  # Flat config
            CONF_BRAVE_INTENT: {"enabled": True},  # Nested config for same handler
        }
        mock_config_entry.options = None

        with (
            patch("custom_components.llm_intents.BraveSearch") as mock_brave_class,
            patch(
                "custom_components.llm_intents.intent.async_register"
            ) as mock_register,
        ):
            # Mock the handler class to return a mock instance
            mock_handler = Mock()
            mock_brave_class.return_value = mock_handler

            result = await async_setup_entry(hass, mock_config_entry)

            assert result is True
            # Should only register 1 handler despite duplicate config
            assert mock_register.call_count == 1
            # Should only create handler once due to duplicate prevention
            assert mock_brave_class.call_count == 1
        """Test that duplicate handlers are not registered."""
        mock_config_entry = Mock(spec=ConfigEntry)
        mock_config_entry.entry_id = "test_entry_id"
        # Set up config that would create duplicate handlers
        mock_config_entry.data = {
            CONF_BRAVE_API_KEY: "test_key",  # Flat config
            CONF_BRAVE_INTENT: {  # Nested config for same handler
                CONF_BRAVE_API_KEY: "nested_key",
                "some_config": "value",
            },
        }
        mock_config_entry.options = None

        with (
            patch("custom_components.llm_intents.BraveSearch") as mock_brave_class,
            patch(
                "custom_components.llm_intents.intent.async_register"
            ) as mock_register,
        ):
            # Mock the handler class to return a mock instance
            mock_handler = Mock()
            mock_brave_class.return_value = mock_handler

            result = await async_setup_entry(hass, mock_config_entry)

            assert result is True
            # Should only register 1 handler despite duplicate config
            assert mock_register.call_count == 1
            # Should only create handler once due to duplicate prevention
            mock_brave_class.assert_called_once()
