"""Tests for google_api_key schema in config_flow."""

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant

from custom_components.llm_intents.config_flow import get_google_api_key_schema


class TestGoogleApiKeySchemaValidation:
    """Tests for the google_api_key schema validation."""

    @pytest.mark.parametrize(
        ("user_input", "expected"),
        [
            ({"google_api_key": "valid key"}, {"google_api_key": "valid key"}),
            ({"google_api_key": None}, vol.Invalid),
            ({"google_api_key": 12345}, vol.Invalid),
            ({"google_api_key": True}, vol.Invalid),
            ({"google_api_key": []}, vol.Invalid),
        ],
    )
    async def test_google_api_key_schema_validation(
        self,
        hass: HomeAssistant,
        user_input: dict,
        expected: dict | type[Exception],
    ) -> None:
        """Test schema validation."""
        schema = await get_google_api_key_schema(hass)
        if expected is vol.Invalid:
            with pytest.raises(vol.Invalid):
                schema(user_input)
        else:
            assert schema(user_input) == expected
