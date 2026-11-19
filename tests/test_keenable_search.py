"""Tests for the Keenable web search tool."""

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.llm_intents.const import (
    CONF_KEENABLE_NUM_RESULTS,
    CONF_PROVIDER_API_KEYS,
    PROVIDER_KEENABLE,
)
from custom_components.llm_intents.keenable_search import KeenableSearchTool

from .utils import mock_session


@pytest.fixture
def config() -> dict:
    """Return a default keyless config."""
    return {
        CONF_KEENABLE_NUM_RESULTS: 5,
        CONF_PROVIDER_API_KEYS: {},
    }


@pytest.fixture
def tool(config: dict, hass: HomeAssistant) -> KeenableSearchTool:
    """Create a KeenableSearchTool instance."""
    return KeenableSearchTool(config, hass)


@pytest.fixture
def success_response() -> dict:
    """Return a successful Keenable response."""
    return {
        "results": [
            {
                "title": "Test Result 1",
                "snippet": "This is the content for result 1.",
                "url": "http://example.com/1",
                "acquired_at": "2026-11-19T00:00:00Z",
            },
            {
                "title": "Test Result 2",
                "description": "This is the content for result 2.",
                "url": "http://example.com/2",
            },
        ]
    }


async def test_keenable_search_keyless(
    tool: KeenableSearchTool, success_response: dict
) -> None:
    """Keyless search posts to the public endpoint with the title header."""
    session = mock_session(status=200, data=success_response)
    with patch(
        "custom_components.llm_intents.keenable_search.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_search("test query")

    assert len(result) == 2
    assert result[0]["title"] == "Test Result 1"
    assert result[0]["content"] == "This is the content for result 1."
    assert result[0]["url"] == "http://example.com/1"
    assert result[1]["content"] == "This is the content for result 2."
    session.post.assert_called_once()
    args, kwargs = session.post.call_args
    assert args[0] == "https://api.keenable.ai/v1/search/public"
    assert kwargs["headers"]["X-Keenable-Title"] == "llm_intents"
    assert "X-API-Key" not in kwargs["headers"]
    assert kwargs["json"] == {"query": "test query", "max_results": 5}
    assert "allow_redirects" not in kwargs


async def test_keenable_search_keyed(
    hass: HomeAssistant, success_response: dict
) -> None:
    """A key uses /v1/search, sends X-API-Key, and does not follow redirects."""
    tool = KeenableSearchTool(
        {
            CONF_KEENABLE_NUM_RESULTS: 3,
            CONF_PROVIDER_API_KEYS: {PROVIDER_KEENABLE: "secret"},
        },
        hass,
    )
    session = mock_session(status=200, data=success_response)
    with patch(
        "custom_components.llm_intents.keenable_search.async_get_clientsession",
        return_value=session,
    ):
        await tool.async_search("test query")

    args, kwargs = session.post.call_args
    assert args[0] == "https://api.keenable.ai/v1/search"
    assert kwargs["headers"]["X-API-Key"] == "secret"
    assert kwargs["headers"]["X-Keenable-Title"] == "llm_intents"
    assert kwargs["allow_redirects"] is False
    assert kwargs["json"]["max_results"] == 3


async def test_keenable_search_http_error(tool: KeenableSearchTool) -> None:
    """Non-OK responses raise RuntimeError without the raw body."""
    session = mock_session(status=500, data={"error": "nope"}, text="secret body")
    with (
        patch(
            "custom_components.llm_intents.keenable_search.async_get_clientsession",
            return_value=session,
        ),
        pytest.raises(RuntimeError, match="HTTP 500"),
    ):
        await tool.async_search("test query")
