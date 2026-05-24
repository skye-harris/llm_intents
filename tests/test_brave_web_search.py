"""Tests for the Brave Web Search tool."""

import re
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.llm_intents.brave_web_search import BraveSearchTool
from custom_components.llm_intents.const import (
    CONF_BRAVE_COUNTRY_CODE,
    CONF_BRAVE_LATITUDE,
    CONF_BRAVE_LONGITUDE,
    CONF_BRAVE_NUM_RESULTS,
    CONF_BRAVE_POST_CODE,
    CONF_BRAVE_TIMEZONE,
    CONF_PROVIDER_API_KEYS,
    PROVIDER_BRAVE,
)

from .utils import mock_session


@pytest.fixture
def config() -> dict:
    """Return a default config."""
    return {
        CONF_PROVIDER_API_KEYS: {
            PROVIDER_BRAVE: "test_api_key",
        },
        CONF_BRAVE_NUM_RESULTS: 5,
        CONF_BRAVE_LATITUDE: "123.456",
        CONF_BRAVE_LONGITUDE: "-12.345",
        CONF_BRAVE_TIMEZONE: "",
        CONF_BRAVE_COUNTRY_CODE: None,
        CONF_BRAVE_POST_CODE: "",
    }


@pytest.fixture
def tool(config: dict, mock_hass: HomeAssistant) -> BraveSearchTool:
    """Create a BraveSearchTool instance."""
    return BraveSearchTool(config, mock_hass)


@pytest.fixture
def success_response() -> dict:
    """Return a successful response."""
    return {
        "web": {
            "results": [
                {
                    "title": "Test Result",
                    "description": "Test description",
                    "extra_snippets": ["Snippet 1", "Snippet 2"],
                }
            ]
        }
    }


async def test_brave_search_success(
    tool: BraveSearchTool, success_response: dict
) -> None:
    """Test successful search returns results."""
    with patch(
        "custom_components.llm_intents.brave_web_search.async_get_clientsession",
        return_value=mock_session(
            status=200,
            data=success_response,
        ),
    ):
        result = await tool.async_search("test query")

    assert len(result) == 1
    assert result[0]["title"] == "Test Result"
    assert result[0]["content"] == ["Snippet 1", "Snippet 2"]


async def test_brave_search_config_params_headers(
    tool: BraveSearchTool, success_response: dict
) -> None:
    """Test that config values are correctly passed as params and headers."""
    session = mock_session(
        status=200,
        data=success_response,
    )

    with patch(
        "custom_components.llm_intents.brave_web_search.async_get_clientsession",
        return_value=session,
    ):
        await tool.async_search("test query")

    # Verify the API was called with correct parameters
    assert session.get.called

    call_kwargs = session.get.call_args[1]
    headers = call_kwargs["headers"]
    params = call_kwargs["params"]

    # Verify params
    assert params["q"] == "test query"
    assert params["count"] == 5  # From config
    assert params["result_filter"] == "web"
    assert params["summary"] == "true"
    assert params["extra_snippets"] == "true"

    # Verify headers
    assert headers["Accept"] == "application/json"
    assert headers["X-Subscription-Token"] == "test_api_key"
    assert headers["X-Loc-Lat"] == "123.456"
    assert headers["X-Loc-Long"] == "-12.345"

    # Verify no timezone, country, or post code headers (not configured)
    assert "X-Loc-Timezone" not in headers
    assert "X-Loc-Country" not in headers
    assert "X-Loc-Postal-Code" not in headers


async def test_brave_search_request_failure(tool: BraveSearchTool) -> None:
    """Test that HTTP errors from Brave raise RuntimeError."""
    # Create a mock response with HTTP error status
    with (
        patch(
            "custom_components.llm_intents.brave_web_search.async_get_clientsession",
            return_value=mock_session(
                status=503,
                data={"error": "Brave API error"},
            ),
        ),
        pytest.raises(
            RuntimeError,
            match=re.escape(
                "Web search received a HTTP 503 error from Brave: {'error': 'Brave API error'}"
            ),
        ),
    ):
        await tool.async_search("test query")
