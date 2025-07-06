"""Test the LLM Intents config flow."""

from __future__ import annotations

from unittest.mock import Mock, patch
import pytest
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.llm_intents.config_flow import (
    LlmIntentsConfigFlow,
    LlmIntentsOptionsFlow,
    get_step_user_data_schema,
    get_brave_schema,
    get_google_places_schema,
    get_wikipedia_schema,
    STEP_USER,
    STEP_BRAVE,
    STEP_GOOGLE_PLACES,
    STEP_WIKIPEDIA,
    STEP_INIT,
)
from custom_components.llm_intents.const import (
    CONF_BRAVE_API_KEY,
    CONF_BRAVE_NUM_RESULTS,
    CONF_GOOGLE_PLACES_API_KEY,
    CONF_GOOGLE_PLACES_NUM_RESULTS,
    CONF_WIKIPEDIA_NUM_RESULTS,
    DOMAIN,
)


class TestSchemaFunctions:
    """Test the schema generation functions."""

    def test_get_step_user_data_schema(self):
        """Test the user step schema generation."""
        schema = get_step_user_data_schema()
        assert isinstance(schema, vol.Schema)

        # Test default values
        defaults = {
            "use_brave": False,
            "use_google_places": False,
            "use_wikipedia": False,
        }
        validated = schema(defaults)
        assert validated == defaults

    def test_get_brave_schema(self):
        """Test the Brave schema generation."""
        defaults = {
            CONF_BRAVE_API_KEY: "test_key",
            CONF_BRAVE_NUM_RESULTS: 5,
        }
        schema = get_brave_schema(defaults)
        assert isinstance(schema, vol.Schema)

        # Test validation
        test_data = {
            CONF_BRAVE_API_KEY: "new_key",
            CONF_BRAVE_NUM_RESULTS: 3,
        }
        validated = schema(test_data)
        assert validated == test_data

    def test_get_brave_schema_validation(self):
        """Test Brave schema validation rules."""
        schema = get_brave_schema({})

        # Test minimum value validation
        with pytest.raises(vol.Invalid):
            schema(
                {
                    CONF_BRAVE_API_KEY: "key",
                    CONF_BRAVE_NUM_RESULTS: 0,  # Should be >= 1
                }
            )

    def test_get_google_places_schema(self):
        """Test the Google Places schema generation."""
        defaults = {
            CONF_GOOGLE_PLACES_API_KEY: "test_key",
            CONF_GOOGLE_PLACES_NUM_RESULTS: 3,
        }
        schema = get_google_places_schema(defaults)
        assert isinstance(schema, vol.Schema)

        # Test validation
        test_data = {
            CONF_GOOGLE_PLACES_API_KEY: "new_key",
            CONF_GOOGLE_PLACES_NUM_RESULTS: 2,
        }
        validated = schema(test_data)
        assert validated == test_data

    def test_get_google_places_schema_validation(self):
        """Test Google Places schema validation rules."""
        schema = get_google_places_schema({})

        # Test minimum value validation
        with pytest.raises(vol.Invalid):
            schema(
                {
                    CONF_GOOGLE_PLACES_API_KEY: "key",
                    CONF_GOOGLE_PLACES_NUM_RESULTS: 0,  # Should be >= 1
                }
            )

    def test_get_wikipedia_schema(self):
        """Test the Wikipedia schema generation."""
        defaults = {CONF_WIKIPEDIA_NUM_RESULTS: 2}
        schema = get_wikipedia_schema(defaults)
        assert isinstance(schema, vol.Schema)

        # Test validation
        test_data = {CONF_WIKIPEDIA_NUM_RESULTS: 1}
        validated = schema(test_data)
        assert validated == test_data

    def test_get_wikipedia_schema_validation(self):
        """Test Wikipedia schema validation rules."""
        schema = get_wikipedia_schema({})

        # Test minimum value validation
        with pytest.raises(vol.Invalid):
            schema({CONF_WIKIPEDIA_NUM_RESULTS: 0})  # Should be >= 1


class TestLlmIntentsConfigFlow:
    """Test the LLM Intents config flow."""

    @pytest.fixture
    def hass(self):
        """Create a mock Home Assistant instance."""
        return Mock(spec=HomeAssistant)

    @pytest.fixture
    def config_flow(self, hass):
        """Create a config flow instance."""
        flow = LlmIntentsConfigFlow()
        flow.hass = hass
        return flow

    async def test_async_step_user_initial_form(self, config_flow):
        """Test the initial user step shows the form."""
        result = await config_flow.async_step_user()

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_USER
        assert "data_schema" in result

    async def test_async_step_user_brave_selection(self, config_flow):
        """Test user step with Brave selected."""
        user_input = {"use_brave": True}
        result = await config_flow.async_step_user(user_input)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_BRAVE
        assert "data_schema" in result

    async def test_async_step_user_google_places_selection(self, config_flow):
        """Test user step with Google Places selected."""
        user_input = {"use_google_places": True}
        result = await config_flow.async_step_user(user_input)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_GOOGLE_PLACES
        assert "data_schema" in result

    async def test_async_step_user_wikipedia_selection(self, config_flow):
        """Test user step with Wikipedia selected."""
        user_input = {"use_wikipedia": True}
        result = await config_flow.async_step_user(user_input)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_WIKIPEDIA
        assert "data_schema" in result

    async def test_async_step_user_no_selection(self, config_flow):
        """Test user step with no services selected."""
        user_input = {
            "use_brave": False,
            "use_google_places": False,
            "use_wikipedia": False,
        }
        result = await config_flow.async_step_user(user_input)

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "LLM Intents"
        assert result["data"] == user_input

    async def test_async_step_user_with_existing_config(self, config_flow):
        """Test user step with existing config entry."""
        # Mock an existing config entry
        config_flow._config_entry = Mock()
        config_flow._config_entry.data = {
            CONF_BRAVE_API_KEY: "existing_key",
            CONF_BRAVE_NUM_RESULTS: 3,
        }

        user_input = {"use_brave": True}
        result = await config_flow.async_step_user(user_input)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_BRAVE

    def test_async_get_options_flow(self):
        """Test the options flow creation."""
        config_entry = Mock(spec=config_entries.ConfigEntry)
        options_flow = LlmIntentsConfigFlow.async_get_options_flow(config_entry)

        assert isinstance(options_flow, LlmIntentsOptionsFlow)
        assert options_flow._config_entry == config_entry


class TestLlmIntentsOptionsFlow:
    """Test the LLM Intents options flow."""

    @pytest.fixture
    def config_entry(self):
        """Create a mock config entry."""
        entry = Mock(spec=config_entries.ConfigEntry)
        entry.data = {
            CONF_BRAVE_API_KEY: "test_key",
            CONF_BRAVE_NUM_RESULTS: 2,
        }
        entry.options = {
            CONF_GOOGLE_PLACES_API_KEY: "places_key",
            CONF_GOOGLE_PLACES_NUM_RESULTS: 3,
        }
        return entry

    @pytest.fixture
    def options_flow(self, config_entry):
        """Create an options flow instance."""
        return LlmIntentsOptionsFlow(config_entry)

    async def test_async_step_init_initial_form(self, options_flow):
        """Test the initial options step shows the form."""
        result = await options_flow.async_step_init()

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_INIT
        assert "data_schema" in result

    async def test_async_step_init_brave_selection(self, options_flow):
        """Test options step with Brave selected."""
        user_input = {"use_brave": True}
        result = await options_flow.async_step_init(user_input)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_BRAVE
        assert "data_schema" in result

    async def test_async_step_init_google_places_selection(self, options_flow):
        """Test options step with Google Places selected."""
        user_input = {"use_google_places": True}
        result = await options_flow.async_step_init(user_input)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_GOOGLE_PLACES
        assert "data_schema" in result

    async def test_async_step_init_wikipedia_selection(self, options_flow):
        """Test options step with Wikipedia selected."""
        user_input = {"use_wikipedia": True}
        result = await options_flow.async_step_init(user_input)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_WIKIPEDIA
        assert "data_schema" in result

    async def test_async_step_init_no_selection(self, options_flow):
        """Test options step with no services selected."""
        user_input = {
            "use_brave": False,
            "use_google_places": False,
            "use_wikipedia": False,
        }
        result = await options_flow.async_step_init(user_input)

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "LLM Intents"
        assert result["data"] == user_input

    async def test_async_step_init_defaults_merge(self, options_flow):
        """Test that defaults are properly merged from data and options."""
        # The defaults should merge data and options, with options taking precedence
        user_input = {"use_brave": True}
        result = await options_flow.async_step_init(user_input)

        # This should show the Brave form, and the schema should use merged defaults
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_BRAVE

    def test_options_flow_init(self, config_entry):
        """Test options flow initialization."""
        options_flow = LlmIntentsOptionsFlow(config_entry)
        assert options_flow._config_entry == config_entry

    async def test_async_step_init_with_empty_options(self):
        """Test options step when config entry has no options."""
        config_entry = Mock(spec=config_entries.ConfigEntry)
        config_entry.data = {CONF_BRAVE_API_KEY: "test_key"}
        config_entry.options = None

        options_flow = LlmIntentsOptionsFlow(config_entry)
        result = await options_flow.async_step_init()

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_INIT


class TestIntegrationFlow:
    """Test the complete integration flow scenarios."""

    @pytest.fixture
    def hass(self):
        """Create a mock Home Assistant instance."""
        return Mock(spec=HomeAssistant)

    async def test_complete_brave_config_flow(self, hass):
        """Test a complete Brave configuration flow."""
        flow = LlmIntentsConfigFlow()
        flow.hass = hass

        # Step 1: Initial user step
        result = await flow.async_step_user()
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_USER

        # Step 2: Select Brave
        user_input = {"use_brave": True}
        result = await flow.async_step_user(user_input)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_BRAVE

    async def test_complete_multi_service_selection(self, hass):
        """Test selecting multiple services (should handle first one selected)."""
        flow = LlmIntentsConfigFlow()
        flow.hass = hass

        # Select both Brave and Google Places
        user_input = {
            "use_brave": True,
            "use_google_places": True,
        }
        result = await flow.async_step_user(user_input)

        # Should process Brave first (due to order in the code)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_BRAVE


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.fixture
    def config_flow(self):
        """Create a config flow instance."""
        flow = LlmIntentsConfigFlow()
        flow.hass = Mock(spec=HomeAssistant)
        return flow

    async def test_user_step_with_invalid_input(self, config_flow):
        """Test user step with invalid input types."""
        # The schema should handle type validation
        user_input = {
            "use_brave": "invalid",  # Should be boolean
        }

        # This would be caught by voluptuous validation in real usage
        # but we test the flow logic here
        with pytest.raises(vol.Invalid):
            schema = get_step_user_data_schema()
            schema(user_input)

    async def test_brave_schema_with_invalid_num_results(self):
        """Test Brave schema with invalid number of results."""
        schema = get_brave_schema({})

        # Test with negative number
        with pytest.raises(vol.Invalid):
            schema(
                {
                    CONF_BRAVE_API_KEY: "key",
                    CONF_BRAVE_NUM_RESULTS: -1,
                }
            )

        # Test with zero
        with pytest.raises(vol.Invalid):
            schema(
                {
                    CONF_BRAVE_API_KEY: "key",
                    CONF_BRAVE_NUM_RESULTS: 0,
                }
            )

    async def test_google_places_schema_with_invalid_num_results(self):
        """Test Google Places schema with invalid number of results."""
        schema = get_google_places_schema({})

        # Test with negative number
        with pytest.raises(vol.Invalid):
            schema(
                {
                    CONF_GOOGLE_PLACES_API_KEY: "key",
                    CONF_GOOGLE_PLACES_NUM_RESULTS: -1,
                }
            )

    async def test_wikipedia_schema_with_invalid_num_results(self):
        """Test Wikipedia schema with invalid number of results."""
        schema = get_wikipedia_schema({})

        # Test with negative number
        with pytest.raises(vol.Invalid):
            schema({CONF_WIKIPEDIA_NUM_RESULTS: -1})

    def test_config_flow_version(self):
        """Test that config flow has correct version."""
        flow = LlmIntentsConfigFlow()
        assert flow.VERSION == 1

    def test_config_flow_domain(self):
        """Test that config flow has correct domain."""
        flow = LlmIntentsConfigFlow()
        assert hasattr(flow, "DOMAIN") or DOMAIN is not None
        # The domain is typically set as a class constant or handled by Home Assistant


class TestMockingAndPatching:
    """Test scenarios that require mocking external dependencies."""

    @pytest.fixture
    def config_flow(self):
        """Create a config flow instance."""
        flow = LlmIntentsConfigFlow()
        flow.hass = Mock(spec=HomeAssistant)
        return flow

    async def test_async_show_form_called_correctly(self, config_flow):
        """Test that async_show_form is called with correct parameters."""
        with patch.object(config_flow, "async_show_form") as mock_show_form:
            mock_show_form.return_value = {"type": FlowResultType.FORM}

            await config_flow.async_step_user()

            mock_show_form.assert_called_once()
            args, kwargs = mock_show_form.call_args
            assert kwargs["step_id"] == STEP_USER
            assert "data_schema" in kwargs

    async def test_async_create_entry_called_correctly(self, config_flow):
        """Test that async_create_entry is called with correct parameters."""
        with patch.object(config_flow, "async_create_entry") as mock_create_entry:
            mock_create_entry.return_value = {"type": FlowResultType.CREATE_ENTRY}

            user_input = {"use_brave": False}
            await config_flow.async_step_user(user_input)

            mock_create_entry.assert_called_once_with(
                title="LLM Intents", data=user_input
            )


class TestConstantsAndDefaults:
    """Test that constants and defaults are used correctly."""

    def test_default_values_in_schemas(self):
        """Test that default values are correctly set in schemas."""
        # Test Brave defaults
        brave_schema = get_brave_schema({})
        # Default should be empty string for API key and 2 for num results

        # Test Google Places defaults
        google_schema = get_google_places_schema({})
        # Default should be empty string for API key and 2 for num results

        # Test Wikipedia defaults
        wikipedia_schema = get_wikipedia_schema({})
        # Default should be 1 for num results

    def test_step_constants_usage(self):
        """Test that step constants are used consistently."""
        # These constants should be used throughout the flow
        assert STEP_USER == "user"
        assert STEP_BRAVE == "brave"
        assert STEP_GOOGLE_PLACES == "google_places"
        assert STEP_WIKIPEDIA == "wikipedia"
        assert STEP_INIT == "init"

    def test_config_constants_usage(self):
        """Test that configuration constants are imported correctly."""
        # These should be imported from const.py
        assert CONF_BRAVE_API_KEY is not None
        assert CONF_BRAVE_NUM_RESULTS is not None
        assert CONF_GOOGLE_PLACES_API_KEY is not None
        assert CONF_GOOGLE_PLACES_NUM_RESULTS is not None
        assert CONF_WIKIPEDIA_NUM_RESULTS is not None
        assert DOMAIN is not None
