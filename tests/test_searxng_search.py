"""Tests for the SearXNG Web Search tool."""

import re
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.llm_intents.const import (
    CONF_SEARXNG_NUM_RESULTS,
    CONF_SEARXNG_URL,
)
from custom_components.llm_intents.searxng_search import SearXngSearchTool

from .utils import mock_session


@pytest.fixture
def config() -> dict:
    """Return a default config."""
    return {
        CONF_SEARXNG_URL: "http://localhost:8080",
        CONF_SEARXNG_NUM_RESULTS: 5,
    }


@pytest.fixture
def tool(config: dict, hass: HomeAssistant) -> SearXngSearchTool:
    """Create a SearXngSearchTool instance."""
    return SearXngSearchTool(config, hass)


@pytest.fixture
def success_response() -> dict:
    """Return a successful response."""
    return {
        "results": [
            {
                "title": "Test Result 1",
                "content": "This is the content for result 1.",
                "url": "http://example.com",
            },
            {
                "title": "Test Result 2",
                "content": "This is the content for result 2.",
                "url": "http://example.com",
            },
        ]
    }


async def test_searxng_search_success(
    tool: SearXngSearchTool, success_response: dict
) -> None:
    """Test successful search returns results."""
    with patch(
        "custom_components.llm_intents.searxng_search.async_get_clientsession",
        return_value=mock_session(
            status=200,
            data=success_response,
        ),
    ):
        result = await tool.async_search("test query")

    assert len(result) == 2
    assert result[0]["title"] == "Test Result 1"
    assert result[0]["content"] == "This is the content for result 1."
    assert result[1]["title"] == "Test Result 2"
    assert result[1]["content"] == "This is the content for result 2."


async def test_searxng_search_config_params_headers(
    tool: SearXngSearchTool, success_response: dict
) -> None:
    """Test that config values are correctly passed as params and headers."""
    session = mock_session(
        status=200,
        data=success_response,
    )

    with patch(
        "custom_components.llm_intents.searxng_search.async_get_clientsession",
        return_value=session,
    ):
        await tool.async_search("test query")

    # Verify the API was called
    assert session.get.called

    call_kwargs = session.get.call_args[1]
    headers = call_kwargs["headers"]

    # Verify headers
    assert headers["Accept"] == "application/json"
    # Note: SearXNG doesn't require an API key header


async def test_searxng_search_request_failure(tool: SearXngSearchTool) -> None:
    """Test that HTTP errors from SearXNG raise RuntimeError."""
    # Create a mock response with HTTP error status
    with (
        patch(
            "custom_components.llm_intents.searxng_search.async_get_clientsession",
            return_value=mock_session(
                status=503,
                data={"error": "SearXNG API error"},
            ),
        ),
        pytest.raises(
            RuntimeError,
            match=re.escape(
                "Web search received a HTTP 503 error from SearXNG: {'error': 'SearXNG API error'}"
            ),
        ),
    ):
        await tool.async_search("test query")


async def test_searxng_search_missing_url() -> None:
    """Test that missing SearXNG URL raises RuntimeError."""
    empty_config: dict = {}
    tool = SearXngSearchTool(empty_config, None)

    with pytest.raises(
        RuntimeError,
        match="SearXNG server url not configured",
    ):
        await tool.async_search("test query")


async def test_searxng_search_cleanup_text_called(
    tool: SearXngSearchTool, success_response: dict
) -> None:
    """Test that cleanup_text is called on each result content."""
    mock_cleanup = AsyncMock(side_effect=lambda x: x)

    with (
        patch(
            "custom_components.llm_intents.searxng_search.async_get_clientsession",
            return_value=mock_session(
                status=200,
                data=success_response,
            ),
        ),
        patch.object(tool, "cleanup_text", mock_cleanup),
    ):
        await tool.async_search("test query")

    assert mock_cleanup.call_count == 2
    mock_cleanup.assert_any_call("This is the content for result 1.")
    mock_cleanup.assert_any_call("This is the content for result 2.")
