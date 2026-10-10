"""Tests for the Tavily Web Search tool."""

import re
from unittest.mock import patch

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant

from custom_components.llm_intents.const import (
    CONF_PROVIDER_API_KEYS,
    CONF_TAVILY_CHUNKS_PER_SOURCE,
    CONF_TAVILY_COUNTRY,
    CONF_TAVILY_INCLUDE_ANSWER,
    CONF_TAVILY_INCLUDE_RAW_CONTENT,
    CONF_TAVILY_NUM_RESULTS,
    CONF_TAVILY_SEARCH_DEPTH,
    PROVIDER_TAVILY,
)
from custom_components.llm_intents.tavily_search import (
    TAVILY_SEARCH_URL,
    TavilySearchTool,
)

from .utils import mock_session

TAVILY_SESSION_PATCH = (
    "custom_components.llm_intents.tavily_search.async_get_clientsession"
)


@pytest.fixture
def config() -> dict:
    """Return a default config."""
    return {
        CONF_PROVIDER_API_KEYS: {
            PROVIDER_TAVILY: "tvly-test-key",
        },
        CONF_TAVILY_NUM_RESULTS: 3,
        CONF_TAVILY_CHUNKS_PER_SOURCE: 1,
        CONF_TAVILY_SEARCH_DEPTH: "advanced",
        CONF_TAVILY_INCLUDE_ANSWER: False,
        CONF_TAVILY_INCLUDE_RAW_CONTENT: False,
        CONF_TAVILY_COUNTRY: "",
    }


@pytest.fixture
def tool(config: dict, hass: HomeAssistant) -> TavilySearchTool:
    """Create a TavilySearchTool instance."""
    return TavilySearchTool(config, hass)


@pytest.fixture
def success_response() -> dict:
    """Return a successful response."""
    return {
        "query": "test query",
        "results": [
            {
                "title": "Test Result",
                "url": "https://example.com",
                "content": "Test content",
                "score": 0.9,
            },
            {
                "title": "Second Result",
                "url": "https://example.org",
                "content": "<b>Markup</b>   content",
                "score": 0.5,
            },
        ],
    }


async def test_tavily_search_success(
    tool: TavilySearchTool, success_response: dict
) -> None:
    """Test successful search returns cleaned results."""
    with patch(
        TAVILY_SESSION_PATCH,
        return_value=mock_session(status=200, data=success_response),
    ):
        result = await tool.async_search("test query")

    assert len(result) == 2
    assert result[0] == {"title": "Test Result", "content": "Test content"}
    assert result[1] == {"title": "Second Result", "content": "Markup content"}


async def test_tavily_search_payload_and_headers(
    tool: TavilySearchTool, success_response: dict
) -> None:
    """Test that config values are sent as the request payload."""
    session = mock_session(status=200, data=success_response)

    with patch(TAVILY_SESSION_PATCH, return_value=session):
        await tool.async_search("test query")

    assert session.post.called

    args, call_kwargs = session.post.call_args
    headers = call_kwargs["headers"]
    payload = call_kwargs["json"]

    assert args[0] == TAVILY_SEARCH_URL
    assert headers["Authorization"] == "Bearer tvly-test-key"
    assert headers["Content-Type"] == "application/json"
    assert payload["query"] == "test query"
    assert payload["max_results"] == 3
    assert payload["search_depth"] == "advanced"
    assert payload["include_answer"] is False
    assert payload["include_raw_content"] is False
    assert "country" not in payload
    assert "topic" not in payload
    assert "time_range" not in payload


async def test_tavily_search_country_sent_for_general_search(
    tool: TavilySearchTool, success_response: dict
) -> None:
    """Test the country boost reaches the payload on a general search."""
    tool.config[CONF_TAVILY_COUNTRY] = "united states"
    session = mock_session(status=200, data=success_response)

    with patch(TAVILY_SESSION_PATCH, return_value=session):
        await tool.async_search("test query")

    assert session.post.call_args[1]["json"]["country"] == "united states"


async def test_tavily_search_country_normalised(
    tool: TavilySearchTool, success_response: dict
) -> None:
    """Test a country value is lowercased and trimmed before it is sent."""
    tool.config[CONF_TAVILY_COUNTRY] = "  United States  "
    session = mock_session(status=200, data=success_response)

    with patch(TAVILY_SESSION_PATCH, return_value=session):
        await tool.async_search("test query")

    assert session.post.call_args[1]["json"]["country"] == "united states"


@pytest.mark.parametrize("depth", ["fast", "ultra-fast"])
async def test_tavily_search_country_omitted_for_beta_depths(
    tool: TavilySearchTool, success_response: dict, depth: str
) -> None:
    """
    Test the country boost is dropped on the depths that reject it.

    Tavily answers with a HTTP 400 "Country parameter is not supported for fast
    or ultra-fast search_depth" when the two are combined.
    """
    tool.config[CONF_TAVILY_COUNTRY] = "united states"
    tool.config[CONF_TAVILY_SEARCH_DEPTH] = depth
    session = mock_session(status=200, data=success_response)

    with patch(TAVILY_SESSION_PATCH, return_value=session):
        await tool.async_search("test query")

    payload = session.post.call_args[1]["json"]
    assert "country" not in payload
    assert payload["search_depth"] == depth


async def test_tavily_search_country_sent_for_advanced_depth(
    tool: TavilySearchTool, success_response: dict
) -> None:
    """Test the country boost is kept on the advanced depth."""
    tool.config[CONF_TAVILY_COUNTRY] = "united states"
    tool.config[CONF_TAVILY_SEARCH_DEPTH] = "advanced"
    session = mock_session(status=200, data=success_response)

    with patch(TAVILY_SESSION_PATCH, return_value=session):
        await tool.async_search("test query")

    payload = session.post.call_args[1]["json"]
    assert payload["country"] == "united states"
    assert payload["search_depth"] == "advanced"


async def test_tavily_search_country_omitted_for_news(
    tool: TavilySearchTool, success_response: dict
) -> None:
    """
    Test the country boost is dropped when the topic is not general.

    Tavily only supports the country parameter for general searches.
    """
    tool.config[CONF_TAVILY_COUNTRY] = "united states"
    session = mock_session(status=200, data=success_response)

    with patch(TAVILY_SESSION_PATCH, return_value=session):
        await tool.async_search("test query", topic="news")

    payload = session.post.call_args[1]["json"]
    assert "country" not in payload
    assert payload["topic"] == "news"


async def test_tavily_search_tool_arguments_reach_the_payload(
    tool: TavilySearchTool, success_response: dict
) -> None:
    """Test the optional tool arguments are forwarded."""
    session = mock_session(status=200, data=success_response)

    with patch(TAVILY_SESSION_PATCH, return_value=session):
        await tool.async_search("test query", topic="news", time_range="week")

    payload = session.post.call_args[1]["json"]
    assert payload["topic"] == "news"
    assert payload["time_range"] == "week"


async def test_tavily_search_depth_passthrough(
    hass: HomeAssistant, success_response: dict
) -> None:
    """Test each supported search depth is passed through untouched."""
    for depth in ("basic", "advanced", "fast", "ultra-fast"):
        config = {
            CONF_PROVIDER_API_KEYS: {PROVIDER_TAVILY: "tvly-test-key"},
            CONF_TAVILY_NUM_RESULTS: 2,
            CONF_TAVILY_SEARCH_DEPTH: depth,
        }
        tool = TavilySearchTool(config, hass)
        session = mock_session(status=200, data=success_response)

        with patch(TAVILY_SESSION_PATCH, return_value=session):
            await tool.async_search("test query")

        assert session.post.call_args[1]["json"]["search_depth"] == depth


async def test_tavily_search_tool_arguments_validated() -> None:
    """Test the tool argument schema only accepts known values."""
    schema = TavilySearchTool.parameters

    assert schema({"query": "q", "topic": "news"})["topic"] == "news"
    assert schema({"query": "q", "time_range": "day"})["time_range"] == "day"
    assert schema({"query": "q"}) == {"query": "q"}

    with pytest.raises(vol.Invalid):
        schema({"query": "q", "topic": "sport"})

    with pytest.raises(vol.Invalid):
        schema({"query": "q", "time_range": "yesterday"})


async def test_tavily_search_raw_content_is_used(
    hass: HomeAssistant, success_response: dict
) -> None:
    """Test the raw content is used in full, with no truncation."""
    config = {
        CONF_PROVIDER_API_KEYS: {PROVIDER_TAVILY: "tvly-test-key"},
        CONF_TAVILY_NUM_RESULTS: 1,
        CONF_TAVILY_INCLUDE_RAW_CONTENT: True,
    }
    tool = TavilySearchTool(config, hass)
    response = {
        "results": [
            {
                "title": "Raw Result",
                "content": "short snippet",
                "raw_content": "x" * 500,
            }
        ]
    }

    with patch(
        TAVILY_SESSION_PATCH,
        return_value=mock_session(status=200, data=response),
    ):
        result = await tool.async_search("test query")

    assert result[0]["content"] == "x" * 500


async def test_tavily_search_raw_content_is_normalised(
    hass: HomeAssistant,
) -> None:
    """
    Test raw content is whitespace-normalised, as the sibling providers are.

    Tavily returns raw content as markdown-ish text; the shared cleanup step
    collapses the whitespace and strips tags, so it does not arrive verbatim.
    """
    config = {
        CONF_PROVIDER_API_KEYS: {PROVIDER_TAVILY: "tvly-test-key"},
        CONF_TAVILY_NUM_RESULTS: 1,
        CONF_TAVILY_INCLUDE_RAW_CONTENT: True,
    }
    tool = TavilySearchTool(config, hass)
    response = {
        "results": [
            {
                "title": "Raw Result",
                "content": "short snippet",
                "raw_content": "# Heading\n\nSome <b>bold</b> text\n\nand more",
            }
        ]
    }

    with patch(
        TAVILY_SESSION_PATCH,
        return_value=mock_session(status=200, data=response),
    ):
        result = await tool.async_search("test query")

    assert result[0]["content"] == "# Heading Some bold text and more"


async def test_tavily_search_raw_content_falls_back_to_snippet(
    hass: HomeAssistant,
) -> None:
    """Test results without raw content fall back to the snippet."""
    config = {
        CONF_PROVIDER_API_KEYS: {PROVIDER_TAVILY: "tvly-test-key"},
        CONF_TAVILY_NUM_RESULTS: 1,
        CONF_TAVILY_INCLUDE_RAW_CONTENT: True,
    }
    tool = TavilySearchTool(config, hass)
    response = {
        "results": [{"title": "No Raw", "content": "snippet only", "raw_content": None}]
    }

    with patch(
        TAVILY_SESSION_PATCH,
        return_value=mock_session(status=200, data=response),
    ):
        result = await tool.async_search("test query")

    assert result[0]["content"] == "snippet only"


async def test_tavily_search_handles_the_real_response_shape(
    tool: TavilySearchTool,
) -> None:
    """
    Test a response captured from the live API parses correctly.

    The extra top-level fields (follow_up_questions, images, response_time) come
    back from Tavily and must be ignored rather than break the mapping.
    """
    captured = {
        "query": "capital of France",
        "follow_up_questions": None,
        "answer": None,
        "images": [],
        "results": [
            {
                "url": "https://en.wikipedia.org/wiki/Paris",
                "title": "Paris - Wikipedia",
                "content": "Paris is the capital and largest city of France.\n\n## Overview",
                "score": 0.98,
                "raw_content": None,
            },
            {
                "url": "https://example.org/france",
                "title": "France facts",
                "content": "The capital of France is Paris.",
                "score": 0.91,
                "raw_content": None,
            },
        ],
        "response_time": 1.42,
    }

    with patch(
        TAVILY_SESSION_PATCH,
        return_value=mock_session(status=200, data=captured),
    ):
        result = await tool.async_search("capital of France")

    assert len(result) == 2
    assert result[0] == {
        "title": "Paris - Wikipedia",
        "content": "Paris is the capital and largest city of France. ## Overview",
    }
    assert result[1]["title"] == "France facts"


async def test_tavily_search_chunks_per_source_reaches_the_payload(
    tool: TavilySearchTool, success_response: dict
) -> None:
    """Test the chunks per source setting is forwarded."""
    tool.config[CONF_TAVILY_CHUNKS_PER_SOURCE] = 3
    session = mock_session(status=200, data=success_response)

    with patch(TAVILY_SESSION_PATCH, return_value=session):
        await tool.async_search("test query")

    assert session.post.call_args[1]["json"]["chunks_per_source"] == 3


@pytest.mark.parametrize("depth", ["basic", "advanced", "fast"])
async def test_tavily_search_chunks_sent_on_supported_depths(
    tool: TavilySearchTool, success_response: dict, depth: str
) -> None:
    """Test chunks_per_source is sent on the depths that honour it."""
    tool.config[CONF_TAVILY_CHUNKS_PER_SOURCE] = 3
    tool.config[CONF_TAVILY_SEARCH_DEPTH] = depth
    session = mock_session(status=200, data=success_response)

    with patch(TAVILY_SESSION_PATCH, return_value=session):
        await tool.async_search("test query")

    assert session.post.call_args[1]["json"]["chunks_per_source"] == 3


async def test_tavily_search_chunks_omitted_on_ultra_fast(
    tool: TavilySearchTool, success_response: dict
) -> None:
    """
    Test chunks_per_source is not sent on ultra-fast.

    Verified against the live API: with the same query, chunks_per_source of 1
    and 3 return byte-identical content lengths on ultra-fast, which returns a
    single summary per result instead of chunks.
    """
    tool.config[CONF_TAVILY_CHUNKS_PER_SOURCE] = 3
    tool.config[CONF_TAVILY_SEARCH_DEPTH] = "ultra-fast"
    session = mock_session(status=200, data=success_response)

    with patch(TAVILY_SESSION_PATCH, return_value=session):
        await tool.async_search("test query")

    payload = session.post.call_args[1]["json"]
    assert "chunks_per_source" not in payload
    assert payload["search_depth"] == "ultra-fast"


async def test_tavily_search_request_failure(tool: TavilySearchTool) -> None:
    """Test that HTTP errors from Tavily raise RuntimeError."""
    with (
        patch(
            TAVILY_SESSION_PATCH,
            return_value=mock_session(
                status=401,
                data={"detail": {"error": "Unauthorized"}},
            ),
        ),
        pytest.raises(
            RuntimeError,
            match=re.escape(
                "Web search received a HTTP 401 error from Tavily: "
                '{"detail": {"error": "Unauthorized"}}'
            ),
        ),
    ):
        await tool.async_search("test query")


async def test_tavily_search_reports_a_non_json_error_body(
    tool: TavilySearchTool,
) -> None:
    """
    Test an error page from an intermediary is reported as an HTTP error.

    A 502 from a proxy is HTML, not JSON, so the status has to be checked before
    the body is parsed, and only a slice of the body is passed on.
    """
    session = mock_session(
        status=502,
        data=None,
        text="<html><body>Bad Gateway</body></html>",
    )

    with (
        patch(TAVILY_SESSION_PATCH, return_value=session),
        pytest.raises(RuntimeError, match="HTTP 502") as err,
    ):
        await tool.async_search("test query")

    assert "Bad Gateway" in str(err.value)


async def test_tavily_search_truncates_a_long_error_body(
    tool: TavilySearchTool,
) -> None:
    """Test a long error body does not travel to the model in full."""
    session = mock_session(status=429, data=None, text="x" * 5000)

    with (
        patch(TAVILY_SESSION_PATCH, return_value=session),
        pytest.raises(RuntimeError) as err,
    ):
        await tool.async_search("test query")

    assert len(str(err.value)) < 700


@pytest.mark.parametrize(
    "response",
    [
        {"query": "test query", "results": []},
        {"query": "test query"},
    ],
)
async def test_tavily_search_returns_nothing_when_there_are_no_results(
    tool: TavilySearchTool, response: dict
) -> None:
    """Test an empty or results-less response yields an empty list."""
    session = mock_session(status=200, data=response)

    with patch(TAVILY_SESSION_PATCH, return_value=session):
        assert await tool.async_search("test query") == []


async def test_tavily_search_missing_api_key(hass: HomeAssistant) -> None:
    """Test that a missing Tavily API key raises RuntimeError."""
    tool = TavilySearchTool({CONF_TAVILY_NUM_RESULTS: 2}, hass)

    with pytest.raises(
        RuntimeError,
        match="Tavily API key not configured",
    ):
        await tool.async_search("test query")


async def test_tavily_search_omits_answer_by_default(
    tool: TavilySearchTool, success_response: dict
) -> None:
    """Test that the generated answer is dropped when the option is off."""
    response = {**success_response, "answer": "An answer that should be ignored"}

    with patch(
        TAVILY_SESSION_PATCH,
        return_value=mock_session(status=200, data=response),
    ):
        result = await tool.async_search("test query")

    assert len(result) == 2
    assert all(item["title"] != "Tavily answer" for item in result)


async def test_tavily_search_includes_answer_when_enabled(
    hass: HomeAssistant,
) -> None:
    """Test that the generated answer is returned first when enabled."""
    config = {
        CONF_PROVIDER_API_KEYS: {PROVIDER_TAVILY: "tvly-test-key"},
        CONF_TAVILY_NUM_RESULTS: 2,
        CONF_TAVILY_SEARCH_DEPTH: "basic",
        CONF_TAVILY_INCLUDE_ANSWER: True,
    }
    tool = TavilySearchTool(config, hass)
    response = {
        "answer": "A generated answer",
        "results": [{"title": "Test Result", "content": "Test content"}],
    }

    with patch(
        TAVILY_SESSION_PATCH,
        return_value=mock_session(status=200, data=response),
    ):
        result = await tool.async_search("test query")

    assert result[0] == {"title": "Tavily answer", "content": "A generated answer"}
    assert result[1] == {"title": "Test Result", "content": "Test content"}
