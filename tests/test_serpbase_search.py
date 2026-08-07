"""Tests for the SerpBase Web Search tool."""

import re
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.llm_intents.const import (
    CONF_PROVIDER_API_KEYS,
    CONF_SERPBASE_NUM_RESULTS,
    PROVIDER_SERPBASE,
)
from custom_components.llm_intents.serpbase_web_search import SerpBaseSearchTool

from .utils import mock_session


@pytest.fixture
def config() -> dict:
    """Return a default config with API key set."""
    return {
        CONF_PROVIDER_API_KEYS: {
            PROVIDER_SERPBASE: "test_api_key_12345",
        },
        CONF_SERPBASE_NUM_RESULTS: 5,
    }


@pytest.fixture
def tool(config: dict, hass: HomeAssistant) -> SerpBaseSearchTool:
    """Create a SerpBaseSearchTool instance."""
    return SerpBaseSearchTool(config, hass)


@pytest.fixture
def success_response() -> dict:
    """Return a successful SerpBase API response."""
    return {
        "organic_results": [
            {
                "title": "SerpBase Test Result 1",
                "snippet": "This is the snippet for result 1.",
                "link": "https://example.com/1",
                "position": 1,
            },
            {
                "title": "SerpBase Test Result 2",
                "snippet": "This is the snippet for result 2.",
                "link": "https://example.com/2",
                "position": 2,
            },
        ]
    }


async def test_serpbase_search_success(
    tool: SerpBaseSearchTool, success_response: dict
) -> None:
    """Test successful SerpBase search returns results."""
    with patch(
        "custom_components.llm_intents.serpbase_web_search.async_get_clientsession",
        return_value=mock_session(
            status=200,
            data=success_response,
        ),
    ):
        result = await tool.async_search("test query")

    assert len(result) == 2
    assert result[0]["title"] == "SerpBase Test Result 1"
    assert result[0]["content"] == "This is the snippet for result 1."
    assert result[1]["title"] == "SerpBase Test Result 2"
    assert result[1]["content"] == "This is the snippet for result 2."


async def test_serpbase_search_config_params(
    tool: SerpBaseSearchTool, success_response: dict
) -> None:
    """Test that API key and num_results are correctly passed as query params."""
    session = mock_session(
        status=200,
        data=success_response,
    )

    with patch(
        "custom_components.llm_intents.serpbase_web_search.async_get_clientsession",
        return_value=session,
    ):
        await tool.async_search("test query")

    # Verify the API was called
    assert session.get.called

    call_kwargs = session.get.call_args[1]
    params = call_kwargs["params"]

    # Verify query params
    assert params["q"] == "test query"
    assert params["api_key"] == "test_api_key_12345"
    assert params["num"] == 5


async def test_serpbase_search_request_failure(tool: SerpBaseSearchTool) -> None:
    """Test that HTTP errors from SerpBase raise RuntimeError."""
    with (
        patch(
            "custom_components.llm_intents.serpbase_web_search.async_get_clientsession",
            return_value=mock_session(
                status=503,
                data={"error": "SerpBase API error"},
            ),
        ),
        pytest.raises(
            RuntimeError,
            match=re.escape(
                "Web search received a HTTP 503 error from SerpBase: {'error': 'SerpBase API error'}"
            ),
        ),
    ):
        await tool.async_search("test query")


async def test_serpbase_search_missing_api_key(hass: HomeAssistant) -> None:
    """Test that missing API key returns empty list without error."""
    config_no_key: dict = {
        CONF_PROVIDER_API_KEYS: {},
    }
    tool = SerpBaseSearchTool(config_no_key, hass)

    result = await tool.async_search("test query")
    assert result == []


async def test_serpbase_search_no_provider_keys(hass: HomeAssistant) -> None:
    """Test that missing provider_api_keys config returns empty list."""
    config_no_provider: dict = {}
    tool = SerpBaseSearchTool(config_no_provider, hass)

    result = await tool.async_search("test query")
    assert result == []


async def test_serpbase_search_cleanup_text_called(
    tool: SerpBaseSearchTool, success_response: dict
) -> None:
    """Test that cleanup_text is called on each result snippet."""
    mock_cleanup = AsyncMock(side_effect=lambda x: x)

    with (
        patch(
            "custom_components.llm_intents.serpbase_web_search.async_get_clientsession",
            return_value=mock_session(
                status=200,
                data=success_response,
            ),
        ),
        patch.object(tool, "cleanup_text", mock_cleanup),
    ):
        await tool.async_search("test query")

    assert mock_cleanup.call_count == 2
    mock_cleanup.assert_any_call("This is the snippet for result 1.")
    mock_cleanup.assert_any_call("This is the snippet for result 2.")
