"""Tests for the YouTube search tool."""

from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.llm_intents.const import (
    CONF_PROVIDER_API_KEYS,
    DOMAIN,
    PROVIDER_GOOGLE,
)
from custom_components.llm_intents.youtube import SearchYouTubeTool

from .utils import MockContext, mock_session

MOCK_YOUTUBE_RESPONSE = {
    "items": [
        {
            "id": {"videoId": "dQw4w9WgXcQ"},
            "snippet": {
                "title": "Rick Astley - Never Gonna Give You Up",
                "channelTitle": "Rick Astley",
                "description": "Official music video",
                "publishedAt": "2009-10-25T06:57:33Z",
            },
        }
    ]
}


def _tool_input(**args: Any) -> Mock:
    tool_input = Mock()
    tool_input.tool_args = args
    return tool_input


@pytest.fixture
def config() -> dict:
    """Minimal config with Google API key."""
    return {
        CONF_PROVIDER_API_KEYS: {PROVIDER_GOOGLE: "test_key"},
    }


@pytest.fixture
def youtube_hass(hass: HomeAssistant, config: dict) -> HomeAssistant:
    """Configure a mock HA instance for the YouTube tool."""
    hass.data = {DOMAIN: {"config": config}}
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    return hass


@pytest.fixture
def tool(youtube_hass: HomeAssistant, config: dict) -> SearchYouTubeTool:
    """Construct the tool under test."""
    return SearchYouTubeTool(config, youtube_hass)


@pytest.fixture
def cache_miss() -> Any:
    """Patch SQLiteCache so every lookup is a miss."""
    with patch(
        "custom_components.llm_intents.youtube.SQLiteCache",
    ) as cache_cls:
        cache_cls.return_value.get.return_value = None
        yield cache_cls


async def test_missing_api_key_returns_error(
    tool: SearchYouTubeTool,
    youtube_hass: HomeAssistant,
    config: dict,
) -> None:
    """Missing Google API key surfaces a clear error."""
    config[CONF_PROVIDER_API_KEYS] = {}
    result = await tool.async_call(
        youtube_hass,
        _tool_input(query="test"),
        Mock(),
    )
    assert result == {"error": "Google API key not configured"}


@pytest.mark.parametrize(
    ("query", "num_results", "expected_count"),
    [
        ("python tutorial", 1, 1),
        ("music", 5, 5),
        ("recipe", 3, 2),
    ],
)
async def test_successful_search_returns_results(
    tool: SearchYouTubeTool,
    youtube_hass: HomeAssistant,
    cache_miss: Any,
    query: str,
    num_results: int,
    expected_count: int,
) -> None:
    """Successful search returns parsed video results with URLs."""
    response = {"items": []}
    for i in range(expected_count):
        response["items"].append(
            {
                "id": {"videoId": f"video_id_{i}"},
                "snippet": {
                    "title": f"Video {i}",
                    "channelTitle": f"Channel {i}",
                    "description": f"Description {i}",
                    "publishedAt": "2024-01-01T00:00:00Z",
                },
            },
        )

    session = mock_session(200, response)

    with patch(
        "custom_components.llm_intents.youtube.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            youtube_hass,
            _tool_input(query=query, num_results=num_results),
            Mock(),
        )

    assert "results" in result
    assert len(result["results"]) == expected_count
    assert "instruction" in result
    assert result["results"][0]["url"] == "https://www.youtube.com/watch?v=video_id_0"


async def test_empty_results_returns_no_videos(
    tool: SearchYouTubeTool,
    youtube_hass: HomeAssistant,
    cache_miss: Any,
) -> None:
    """API returns 200 with empty items → 'No videos found'."""
    session = mock_session(200, {"items": []})

    with patch(
        "custom_components.llm_intents.youtube.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            youtube_hass,
            _tool_input(query="nonexistent"),
            Mock(),
        )

    assert result == {"result": "No videos found"}


@pytest.mark.parametrize(
    ("status_code", "expected_msg"),
    [
        (400, "YouTube search error: 400"),
        (403, "YouTube search error: 403"),
        (500, "YouTube search error: 500"),
    ],
)
async def test_http_error_returns_error(
    tool: SearchYouTubeTool,
    youtube_hass: HomeAssistant,
    cache_miss: Any,
    status_code: int,
    expected_msg: str,
) -> None:
    """Non-200 status returns a structured error."""
    response = AsyncMock()
    response.status = status_code
    response.text = AsyncMock(return_value="error body")

    session = AsyncMock()

    def mock_get(*_args: object, **_kwargs: object) -> MockContext:
        return MockContext(response)

    session.get = Mock(side_effect=mock_get)

    with patch(
        "custom_components.llm_intents.youtube.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            youtube_hass,
            _tool_input(query="test"),
            Mock(),
        )

    assert result == {"error": expected_msg}


async def test_cache_hit_skips_api_call(
    tool: SearchYouTubeTool,
    youtube_hass: HomeAssistant,
) -> None:
    """A cached response is returned without making an HTTP call."""
    cached_value = {
        "results": [
            {
                "title": "Cached Video",
                "url": "https://www.youtube.com/watch?v=cached",
                "channel": "Cached Channel",
                "description": "Cached desc",
                "published_at": "2024-01-01T00:00:00Z",
            },
        ],
        "instruction": tool.response_directive,
    }

    with (
        patch(
            "custom_components.llm_intents.youtube.SQLiteCache",
        ) as cache_cls,
        patch(
            "custom_components.llm_intents.youtube.async_get_clientsession",
        ) as session_patch,
    ):
        cache_cls.return_value.get.return_value = cached_value
        result = await tool.async_call(
            youtube_hass,
            _tool_input(query="cached query"),
            Mock(),
        )

    session_patch.assert_not_called()
    assert result == cached_value


async def test_exception_returns_error(
    tool: SearchYouTubeTool,
    youtube_hass: HomeAssistant,
    cache_miss: Any,
) -> None:
    """Any exception during search returns a generic error."""
    session = AsyncMock()

    def mock_get(*_args: object, **_kwargs: object) -> MockContext:
        raise RuntimeError("network failure")

    session.get = Mock(side_effect=mock_get)

    with patch(
        "custom_components.llm_intents.youtube.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            youtube_hass,
            _tool_input(query="test"),
            Mock(),
        )

    assert result == {"error": "Error searching YouTube"}
