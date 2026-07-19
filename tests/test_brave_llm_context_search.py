"""Tests for the Brave LLM Context search tool."""

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.llm_intents.brave_llm_context_search import (
    BraveLlmContextSearchTool,
)
from custom_components.llm_intents.const import (
    CONF_BRAVE_CONTEXT_THRESHOLD_MODE,
    CONF_BRAVE_COUNTRY_CODE,
    CONF_BRAVE_LATITUDE,
    CONF_BRAVE_LONGITUDE,
    CONF_BRAVE_MAX_SNIPPETS_PER_URL,
    CONF_BRAVE_MAX_TOKENS_PER_URL,
    CONF_BRAVE_NUM_RESULTS,
    CONF_BRAVE_POST_CODE,
    CONF_BRAVE_TIMEZONE,
    CONF_PROVIDER_API_KEYS,
    PROVIDER_BRAVE,
    PROVIDER_BRAVE_LLM,
)

from .utils import mock_session


@pytest.fixture
def config() -> dict:
    """Return a default config."""
    return {
        CONF_PROVIDER_API_KEYS: {
            PROVIDER_BRAVE: "test_api_key",
            PROVIDER_BRAVE_LLM: "test_llm_api_key",
        },
        CONF_BRAVE_NUM_RESULTS: 3,
        CONF_BRAVE_LATITUDE: "123.456",
        CONF_BRAVE_LONGITUDE: "-12.345",
        CONF_BRAVE_TIMEZONE: "America/New_York",
        CONF_BRAVE_COUNTRY_CODE: "US",
        CONF_BRAVE_POST_CODE: "12345",
        CONF_BRAVE_MAX_SNIPPETS_PER_URL: 2,
        CONF_BRAVE_MAX_TOKENS_PER_URL: 512,
        CONF_BRAVE_CONTEXT_THRESHOLD_MODE: "balanced",
    }


@pytest.fixture
def tool(config: dict, hass: HomeAssistant) -> BraveLlmContextSearchTool:
    """Create a BraveLlmContextSearchTool instance."""
    return BraveLlmContextSearchTool(config, hass)


@pytest.fixture
def success_response() -> dict:
    """Return a sample Brave LLM Context API response."""
    return {
        "grounding": {
            "generic": [
                {
                    "title": "Test Result",
                    "snippets": [
                        "This is snippet one from the search result.",
                        "This is snippet two from the search result.",
                    ],
                }
            ]
        }
    }


async def test_brave_llm_context_search_success(
    tool: BraveLlmContextSearchTool, success_response: dict
) -> None:
    """Test successful search returns results."""
    with patch(
        "custom_components.llm_intents.brave_llm_context_search.async_get_clientsession",
        return_value=mock_session(
            status=200,
            data=success_response,
        ),
    ):
        result = await tool.async_search("test query")

    assert len(result) == 1
    assert result[0]["title"] == "Test Result"
    assert result[0]["content"] == [
        "This is snippet one from the search result.",
        "This is snippet two from the search result.",
    ]


async def test_brave_llm_context_search_config_params_headers(
    tool: BraveLlmContextSearchTool, success_response: dict
) -> None:
    """Test that config values are correctly passed as params and headers."""
    session = mock_session(
        status=200,
        data=success_response,
    )

    with patch(
        "custom_components.llm_intents.brave_llm_context_search.async_get_clientsession",
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
    assert params["count"] == 3  # From config
    assert params["maximum_number_of_snippets"] == 6  # count * max_snippets_per_url
    assert params["maximum_number_of_tokens"] == 1536  # count * max_tokens_per_url
    assert params["maximum_number_of_tokens_per_url"] == 512  # From config
    assert params["maximum_number_of_snippets_per_url"] == 2  # From config
    assert params["context_threshold_mode"] == "balanced"  # From config

    # Verify headers
    assert headers["Accept"] == "application/json"
    assert headers["X-Subscription-Token"] == "test_api_key"
    assert headers["X-Loc-Lat"] == "123.456"
    assert headers["X-Loc-Long"] == "-12.345"
    assert headers["X-Loc-Timezone"] == "America/New_York"
    assert headers["X-Loc-Country"] == "US"
    assert headers["X-Loc-Postal-Code"] == "12345"


async def test_brave_llm_context_search_request_failure(
    tool: BraveLlmContextSearchTool, hass: HomeAssistant
) -> None:
    """Test that HTTP errors from Brave raise RuntimeError."""
    error_response = {
        "grounding": {
            "generic": [],
            "error": "Brave API error",
        }
    }

    with (
        patch(
            "custom_components.llm_intents.brave_llm_context_search.async_get_clientsession",
            return_value=mock_session(
                status=503,
                data=error_response,
            ),
        ),
        pytest.raises(
            RuntimeError,
            match=r"Web search received a HTTP 503 error from Brave: \{'grounding': \{'generic': \[\], 'error': 'Brave API error'\}\}",
        ),
    ):
        await tool.async_search("test query")


async def test_brave_llm_context_search_cleanup_text_image_removal(
    tool: BraveLlmContextSearchTool,
) -> None:
    """Test that image placeholders are removed in cleanup_text."""
    text_with_images = """
    Here is some text [Image: https://example.com/image.jpg] and more text.
    Another image [Image: https://example.com/another.jpg] here.
    """

    result = await tool.cleanup_text(text_with_images)

    assert "[Image:" not in result
    assert "Here is some text" in result
    assert "and more text." in result
    assert "Another image" in result
    assert "here." in result


async def test_brave_llm_context_search_cleanup_text_html_unescape(
    tool: BraveLlmContextSearchTool,
) -> None:
    """Test that HTML entities are unescaped in cleanup_text."""
    html_text = "This is &lt;html&gt; encoded text with &amp; entities."

    result = await tool.cleanup_text(html_text)

    # HTML entities are unescaped by base class, HTML tags are removed
    assert result == "This is encoded text with & entities."


async def test_brave_llm_context_search_cleanup_text_multiple_whitespace(
    tool: BraveLlmContextSearchTool,
) -> None:
    """Test that multiple whitespace characters are collapsed in cleanup_text."""
    whitespace_text = "This   has\tmultiple\nwhitespace\tcharacters.\n\n\n"

    result = await tool.cleanup_text(whitespace_text)

    assert result == "This has multiple whitespace characters."


async def test_brave_llm_context_search_cleanup_text_json_decode_error(
    tool: BraveLlmContextSearchTool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that JSON decode errors are handled gracefully in cleanup_text."""
    invalid_json = "{bad data}"

    result = await tool.cleanup_text(invalid_json)

    assert result == invalid_json
    assert "Failed to decode JSON" in caplog.text


async def test_brave_llm_context_search_cleanup_text_json_decode_success(
    tool: BraveLlmContextSearchTool,
) -> None:
    """Test that valid JSON objects wrapped in braces are parsed in cleanup_text."""
    json_text = '{"key": "value", "nested": {"a": 1}}'

    result = await tool.cleanup_text(json_text)

    assert result == {"key": "value", "nested": {"a": 1}}


async def test_brave_llm_context_search_missing_api_key(
    hass: HomeAssistant,
) -> None:
    """Test that missing Brave API key raises RuntimeError."""
    config = {
        CONF_BRAVE_NUM_RESULTS: 2,
    }
    tool = BraveLlmContextSearchTool(config, hass)

    with pytest.raises(
        RuntimeError,
        match="Brave API key not configured",
    ):
        await tool.async_search("test query")


async def test_brave_llm_context_search_no_optional_location_headers(
    hass: HomeAssistant,
) -> None:
    """Test that optional location headers are omitted when not configured."""
    config = {
        CONF_PROVIDER_API_KEYS: {
            PROVIDER_BRAVE: "test_api_key",
            PROVIDER_BRAVE_LLM: "test_llm_api_key",
        },
        CONF_BRAVE_NUM_RESULTS: 2,
        CONF_BRAVE_LATITUDE: None,
        CONF_BRAVE_LONGITUDE: None,
        CONF_BRAVE_TIMEZONE: "",
        CONF_BRAVE_COUNTRY_CODE: None,
        CONF_BRAVE_POST_CODE: "",
        CONF_BRAVE_MAX_SNIPPETS_PER_URL: 2,
        CONF_BRAVE_MAX_TOKENS_PER_URL: 512,
        CONF_BRAVE_CONTEXT_THRESHOLD_MODE: "balanced",
    }
    tool = BraveLlmContextSearchTool(config, hass)

    response = {
        "grounding": {
            "generic": [
                {
                    "title": "Test Result",
                    "snippets": ["Snippet 1"],
                }
            ]
        }
    }

    session = mock_session(
        status=200,
        data=response,
    )

    with patch(
        "custom_components.llm_intents.brave_llm_context_search.async_get_clientsession",
        return_value=session,
    ):
        await tool.async_search("test query")

    headers = session.get.call_args[1]["headers"]

    assert "X-Loc-Lat" not in headers
    assert "X-Loc-Long" not in headers
    assert "X-Loc-Timezone" not in headers
    assert "X-Loc-Country" not in headers
    assert "X-Loc-Postal-Code" not in headers
