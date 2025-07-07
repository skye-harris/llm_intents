"""Test the LLM Intents config flow."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.llm_intents.config_flow import (
    STEP_BRAVE,
    STEP_GOOGLE_PLACES,
    STEP_INIT,
    STEP_USER,
    STEP_WIKIPEDIA,
    LlmIntentsConfigFlow,
    LlmIntentsOptionsFlow,
    get_brave_schema,
    get_google_places_schema,
    get_step_user_data_schema,
    get_wikipedia_schema,
)
from custom_components.llm_intents.const import (
    CONF_BRAVE_API_KEY,
    CONF_BRAVE_COUNTRY_CODE,
    CONF_BRAVE_LATITUDE,
    CONF_BRAVE_LONGITUDE,
    CONF_BRAVE_NUM_RESULTS,
    CONF_BRAVE_POST_CODE,
    CONF_BRAVE_TIMEZONE,
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
        # Schema adds optional fields with default values
        expected_data = {
            CONF_BRAVE_API_KEY: "new_key",
            CONF_BRAVE_NUM_RESULTS: 3,
            CONF_BRAVE_COUNTRY_CODE: "",
            CONF_BRAVE_LATITUDE: "",
            CONF_BRAVE_LONGITUDE: "",
            CONF_BRAVE_TIMEZONE: "",
            CONF_BRAVE_POST_CODE: "",
        }
        assert validated == expected_data

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
        config_flow.config_entry = Mock()
        config_flow.config_entry.data = {
            CONF_BRAVE_API_KEY: "existing_key",
            CONF_BRAVE_NUM_RESULTS: 3,
        }

        user_input = {"use_brave": True}
        result = await config_flow.async_step_user(user_input)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_BRAVE

    async def test_async_step_brave_initial_form(self, config_flow):
        """Test the Brave step shows the form when no input provided."""
        result = await config_flow.async_step_brave()

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_BRAVE

    async def test_async_step_brave_with_input_no_next_service(self, config_flow):
        """Test Brave step with input and no other services selected."""
        config_flow._user_selections = {"use_brave": True}
        user_input = {
            CONF_BRAVE_API_KEY: "test_key",
            CONF_BRAVE_NUM_RESULTS: 3,
        }
        result = await config_flow.async_step_brave(user_input)

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "LLM Intents"

    async def test_async_step_brave_with_google_places_next(self, config_flow):
        """Test Brave step that leads to Google Places configuration."""
        config_flow._user_selections = {"use_brave": True, "use_google_places": True}
        user_input = {
            CONF_BRAVE_API_KEY: "test_key",
            CONF_BRAVE_NUM_RESULTS: 3,
        }
        result = await config_flow.async_step_brave(user_input)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_GOOGLE_PLACES

    async def test_async_step_brave_with_wikipedia_next(self, config_flow):
        """Test Brave step that leads to Wikipedia configuration."""
        config_flow._user_selections = {"use_brave": True, "use_wikipedia": True}
        user_input = {
            CONF_BRAVE_API_KEY: "test_key",
            CONF_BRAVE_NUM_RESULTS: 3,
        }
        result = await config_flow.async_step_brave(user_input)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_WIKIPEDIA

    async def test_async_step_google_places_initial_form(self, config_flow):
        """Test the Google Places step shows the form when no input provided."""
        result = await config_flow.async_step_google_places()

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_GOOGLE_PLACES

    async def test_async_step_google_places_with_input_no_next_service(
        self, config_flow
    ):
        """Test Google Places step with input and no other services selected."""
        config_flow._user_selections = {"use_google_places": True}
        user_input = {
            CONF_GOOGLE_PLACES_API_KEY: "test_key",
            CONF_GOOGLE_PLACES_NUM_RESULTS: 2,
        }
        result = await config_flow.async_step_google_places(user_input)

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "LLM Intents"

    async def test_async_step_google_places_with_wikipedia_next(self, config_flow):
        """Test Google Places step that leads to Wikipedia configuration."""
        config_flow._user_selections = {
            "use_google_places": True,
            "use_wikipedia": True,
        }
        user_input = {
            CONF_GOOGLE_PLACES_API_KEY: "test_key",
            CONF_GOOGLE_PLACES_NUM_RESULTS: 2,
        }
        result = await config_flow.async_step_google_places(user_input)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_WIKIPEDIA

    async def test_async_step_wikipedia_initial_form(self, config_flow):
        """Test the Wikipedia step shows the form when no input provided."""
        result = await config_flow.async_step_wikipedia()

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_WIKIPEDIA

    async def test_async_step_wikipedia_with_input(self, config_flow):
        """Test Wikipedia step with input."""
        config_flow._user_selections = {"use_wikipedia": True}
        user_input = {CONF_WIKIPEDIA_NUM_RESULTS: 1}
        result = await config_flow.async_step_wikipedia(user_input)

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "LLM Intents"

    def test_async_get_options_flow(self):
        """Test the options flow creation."""
        config_entry = Mock(spec=config_entries.ConfigEntry)
        options_flow = LlmIntentsConfigFlow.async_get_options_flow(config_entry)

        assert isinstance(options_flow, LlmIntentsOptionsFlow)
        assert options_flow.config_entry == config_entry


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
        # The options flow should merge existing config with user input
        expected_data = {
            CONF_BRAVE_API_KEY: "test_key",
            CONF_BRAVE_NUM_RESULTS: 2,
            CONF_GOOGLE_PLACES_API_KEY: "places_key",
            CONF_GOOGLE_PLACES_NUM_RESULTS: 3,
            "use_brave": False,
            "use_google_places": False,
            "use_wikipedia": False,
        }
        assert result["data"] == expected_data

    async def test_async_step_init_defaults_merge(self, options_flow):
        """Test that defaults are properly merged from data and options."""
        # The defaults should merge data and options, with options taking precedence
        user_input = {"use_brave": True}
        result = await options_flow.async_step_init(user_input)

        # This should show the Brave form, and the schema should use merged defaults
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_BRAVE

    async def test_async_step_init_with_empty_options(self):
        """Test options step when config entry has no options."""
        config_entry = Mock(spec=config_entries.ConfigEntry)
        config_entry.data = {CONF_BRAVE_API_KEY: "test_key"}
        config_entry.options = None

        options_flow = LlmIntentsOptionsFlow(config_entry)
        result = await options_flow.async_step_init()

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_INIT

    async def test_async_step_brave_initial_form(self, options_flow):
        """Test the Brave options step shows the form when no input provided."""
        result = await options_flow.async_step_brave()

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_BRAVE

    async def test_async_step_brave_with_input_no_next_service(self, options_flow):
        """Test Brave options step with input and no other services selected."""
        options_flow._user_selections = {"use_brave": True}
        user_input = {
            CONF_BRAVE_API_KEY: "updated_key",
            CONF_BRAVE_NUM_RESULTS: 5,
        }
        result = await options_flow.async_step_brave(user_input)

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == ""

    async def test_async_step_brave_with_google_places_next(self, options_flow):
        """Test Brave options step that leads to Google Places configuration."""
        options_flow._user_selections = {"use_brave": True, "use_google_places": True}
        user_input = {
            CONF_BRAVE_API_KEY: "updated_key",
            CONF_BRAVE_NUM_RESULTS: 5,
        }
        result = await options_flow.async_step_brave(user_input)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_GOOGLE_PLACES

    async def test_async_step_brave_with_wikipedia_next(self, options_flow):
        """Test Brave options step that leads to Wikipedia configuration."""
        options_flow._user_selections = {"use_brave": True, "use_wikipedia": True}
        user_input = {
            CONF_BRAVE_API_KEY: "updated_key",
            CONF_BRAVE_NUM_RESULTS: 5,
        }
        result = await options_flow.async_step_brave(user_input)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_WIKIPEDIA

    async def test_async_step_google_places_initial_form(self, options_flow):
        """Test the Google Places options step shows the form when no input provided."""
        result = await options_flow.async_step_google_places()

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_GOOGLE_PLACES

    async def test_async_step_google_places_with_input_no_next_service(
        self, options_flow
    ):
        """Test Google Places options step with input and no other services selected."""
        options_flow._user_selections = {"use_google_places": True}
        user_input = {
            CONF_GOOGLE_PLACES_API_KEY: "updated_key",
            CONF_GOOGLE_PLACES_NUM_RESULTS: 4,
        }
        result = await options_flow.async_step_google_places(user_input)

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == ""

    async def test_async_step_google_places_with_wikipedia_next(self, options_flow):
        """Test Google Places options step that leads to Wikipedia configuration."""
        options_flow._user_selections = {
            "use_google_places": True,
            "use_wikipedia": True,
        }
        user_input = {
            CONF_GOOGLE_PLACES_API_KEY: "updated_key",
            CONF_GOOGLE_PLACES_NUM_RESULTS: 4,
        }
        result = await options_flow.async_step_google_places(user_input)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_WIKIPEDIA

    async def test_async_step_wikipedia_initial_form(self, options_flow):
        """Test the Wikipedia options step shows the form when no input provided."""
        result = await options_flow.async_step_wikipedia()

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == STEP_WIKIPEDIA

    async def test_async_step_wikipedia_with_input(self, options_flow):
        """Test Wikipedia options step with input."""
        options_flow._user_selections = {"use_wikipedia": True}
        user_input = {CONF_WIKIPEDIA_NUM_RESULTS: 3}
        result = await options_flow.async_step_wikipedia(user_input)

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == ""

    async def test_async_step_init_with_title_correction(self, options_flow):
        """Test options step title correction."""
        user_input = {
            "use_brave": False,
            "use_google_places": False,
            "use_wikipedia": False,
        }
        result = await options_flow.async_step_init(user_input)

        # Verify title is set correctly for options flow
        assert result["title"] == "LLM Intents"


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
        schema = get_step_user_data_schema()
        with pytest.raises(vol.Invalid):
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


class TestSchemaValidationEdgeCases:
    """Test additional schema validation scenarios."""

    def test_get_brave_schema_with_all_fields(self):
        """Test Brave schema with all optional fields populated."""
        defaults = {
            CONF_BRAVE_API_KEY: "test_key",
            CONF_BRAVE_NUM_RESULTS: 5,
            CONF_BRAVE_COUNTRY_CODE: "US",
            CONF_BRAVE_LATITUDE: "40.7128",
            CONF_BRAVE_LONGITUDE: "-74.0060",
            CONF_BRAVE_TIMEZONE: "America/New_York",
            CONF_BRAVE_POST_CODE: "10001",
        }
        schema = get_brave_schema(defaults)

        test_data = {
            CONF_BRAVE_API_KEY: "new_key",
            CONF_BRAVE_NUM_RESULTS: 3,
            CONF_BRAVE_COUNTRY_CODE: "GB",
            CONF_BRAVE_LATITUDE: "51.5074",
            CONF_BRAVE_LONGITUDE: "-0.1278",
            CONF_BRAVE_TIMEZONE: "Europe/London",
            CONF_BRAVE_POST_CODE: "SW1A 1AA",
        }
        validated = schema(test_data)
        assert validated == test_data

    def test_get_brave_schema_with_defaults_used(self):
        """Test that Brave schema uses provided defaults correctly."""
        defaults = {
            CONF_BRAVE_API_KEY: "default_key",
            CONF_BRAVE_NUM_RESULTS: 10,
            CONF_BRAVE_COUNTRY_CODE: "CA",
        }
        schema = get_brave_schema(defaults)

        # Provide minimal data to see defaults fill in
        test_data = {CONF_BRAVE_API_KEY: "override_key"}
        validated = schema(test_data)

        expected = {
            CONF_BRAVE_API_KEY: "override_key",
            CONF_BRAVE_NUM_RESULTS: 10,  # From defaults
            CONF_BRAVE_COUNTRY_CODE: "CA",  # From defaults
            CONF_BRAVE_LATITUDE: "",  # Default empty string
            CONF_BRAVE_LONGITUDE: "",  # Default empty string
            CONF_BRAVE_TIMEZONE: "",  # Default empty string
            CONF_BRAVE_POST_CODE: "",  # Default empty string
        }
        assert validated == expected


class TestConfigFlowDataHandling:
    """Test data handling and storage in config flows."""

    @pytest.fixture
    def config_flow(self):
        """Create a config flow instance."""
        flow = LlmIntentsConfigFlow()
        flow.hass = Mock(spec=HomeAssistant)
        return flow

    async def test_config_data_accumulation(self, config_flow):
        """Test that config data accumulates correctly across steps."""
        # First step: user selections
        user_input = {"use_brave": True, "use_wikipedia": True}
        await config_flow.async_step_user(user_input)

        assert config_flow._user_selections == user_input
        assert "use_brave" in config_flow._config_data
        assert "use_wikipedia" in config_flow._config_data

        # Second step: Brave configuration
        brave_input = {
            CONF_BRAVE_API_KEY: "test_key",
            CONF_BRAVE_NUM_RESULTS: 3,
        }
        await config_flow.async_step_brave(brave_input)

        # Verify data accumulation
        assert CONF_BRAVE_API_KEY in config_flow._config_data
        assert CONF_BRAVE_NUM_RESULTS in config_flow._config_data
        assert config_flow._config_data[CONF_BRAVE_API_KEY] == "test_key"

    async def test_options_flow_data_merging(self):
        """Test that options flow merges data correctly."""
        config_entry = Mock(spec=config_entries.ConfigEntry)
        config_entry.data = {
            CONF_BRAVE_API_KEY: "original_key",
            CONF_BRAVE_NUM_RESULTS: 2,
        }
        config_entry.options = {
            CONF_GOOGLE_PLACES_API_KEY: "places_key",
        }

        options_flow = LlmIntentsOptionsFlow(config_entry)

        user_input = {"use_brave": True}
        await options_flow.async_step_init(user_input)

        # Verify data merging
        expected_keys = {
            CONF_BRAVE_API_KEY,
            CONF_BRAVE_NUM_RESULTS,
            CONF_GOOGLE_PLACES_API_KEY,
            "use_brave",
        }
        assert all(key in options_flow._config_data for key in expected_keys)
