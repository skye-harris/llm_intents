"""Tests for the Web Fetch tool."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from aiohttp import ClientSession
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from custom_components.llm_intents.const import (
    CONF_WEB_FETCH_MAX_CONTENT_LENGTH,
    DOMAIN,
)
from custom_components.llm_intents.web_fetch import (
    HTMLToText,
    WebFetchTool,
    html_to_text,
)

from .utils import MockContext

PATCH_CLIENT_SESSION_PATH = (
    "custom_components.llm_intents.web_fetch.async_get_clientsession"
)


# ---------------------------------------------------------------------------
# HTTP response/session helpers (text-based, not JSON-based)
# ---------------------------------------------------------------------------


def mock_text_response(
    status: int, text: str, content_type: str = "text/html"
) -> AsyncMock:
    """Mock HTTP response that returns text content (no JSON)."""
    response = AsyncMock()
    response.status = status
    response.text = AsyncMock(return_value=text)
    response.headers = {"Content-Type": content_type}
    return response


def mock_text_session(
    status: int, text: str, content_type: str = "text/html"
) -> ClientSession:
    """Mock aiohttp ClientSession returning a text response."""
    session = AsyncMock()

    def mock_get(*args: object, **kwargs: object) -> MockContext:
        return MockContext(mock_text_response(status, text, content_type))

    session.get = Mock(side_effect=mock_get)
    return session


def mock_error_session(error: Exception) -> ClientSession:
    """Mock aiohttp ClientSession whose GET call raises an exception."""
    session = AsyncMock()
    session.get = Mock(side_effect=error)
    return session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> dict[str, int]:
    """Default tool config."""
    return {CONF_WEB_FETCH_MAX_CONTENT_LENGTH: 10000}


@pytest.fixture
def small_max_config() -> dict[str, int]:
    """Config with a tiny content limit for truncation tests."""
    return {CONF_WEB_FETCH_MAX_CONTENT_LENGTH: 50}


@pytest.fixture
def tool(config: dict[str, int], mock_hass: HomeAssistant) -> WebFetchTool:
    """Create a WebFetchTool with a mocked HomeAssistant."""
    mock_hass.data = {DOMAIN: {"config": config}}
    entry = MagicMock()
    entry.options = {}
    mock_hass.config_entries.async_entries.return_value = [entry]
    return WebFetchTool(config, mock_hass)


@pytest.fixture
def tool_small_max(
    small_max_config: dict[str, int], mock_hass: HomeAssistant
) -> WebFetchTool:
    """WebFetchTool with a small max content length."""
    mock_hass.data = {DOMAIN: {"config": small_max_config}}
    entry = MagicMock()
    entry.options = {}
    mock_hass.config_entries.async_entries.return_value = [entry]
    return WebFetchTool(small_max_config, mock_hass)


@pytest.fixture
def tool_input() -> llm.ToolInput:
    """Mock ToolInput for web_fetch."""
    ti = MagicMock(spec=llm.ToolInput)
    ti.tool_args = {"url": "https://example.com"}
    return ti


@pytest.fixture
def llm_context() -> llm.LLMContext:
    """Mock LLMContext."""
    return MagicMock(spec=llm.LLMContext)


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------


async def test_web_fetch_invalid_scheme(
    tool: WebFetchTool, tool_input: llm.ToolInput, llm_context: llm.LLMContext
) -> None:
    """Non-http/https URLs should return an error."""
    tool_input.tool_args = {"url": "ftp://example.com/file"}

    result = await tool.async_call(tool.hass, tool_input, llm_context)

    assert "error" in result
    assert "Invalid URL scheme" in result["error"]


async def test_web_fetch_invalid_scheme_empty(
    tool: WebFetchTool, tool_input: llm.ToolInput, llm_context: llm.LLMContext
) -> None:
    """Empty string URL should return an error."""
    tool_input.tool_args = {"url": ""}

    result = await tool.async_call(tool.hass, tool_input, llm_context)

    assert "error" in result
    assert "Invalid URL scheme" in result["error"]


# ---------------------------------------------------------------------------
# Successful fetches
# ---------------------------------------------------------------------------


async def test_web_fetch_html_success(
    tool: WebFetchTool, tool_input: llm.ToolInput, llm_context: llm.LLMContext
) -> None:
    """HTML content should be converted to plain text."""
    html = "<html><body><p>Hello World</p><p>Second paragraph</p></body></html>"
    session = mock_text_session(200, html)

    with (
        patch(
            PATCH_CLIENT_SESSION_PATH,
            return_value=session,
        ),
        patch("custom_components.llm_intents.web_fetch.SQLiteCache.set") as mock_set,
    ):
        result = await tool.async_call(tool.hass, tool_input, llm_context)

    assert result["url"] == "https://example.com"
    assert "Hello World" in result["content"]
    assert "Second paragraph" in result["content"]
    assert result["content_length"] > 0
    assert mock_set.called


async def test_web_fetch_non_html_success(
    tool: WebFetchTool, tool_input: llm.ToolInput, llm_context: llm.LLMContext
) -> None:
    """Non-HTML content (e.g. text/plain) should be returned as-is."""
    text = "This is plain text content."
    session = mock_text_session(200, text, content_type="text/plain")

    with patch(
        PATCH_CLIENT_SESSION_PATH,
        return_value=session,
    ):
        result = await tool.async_call(tool.hass, tool_input, llm_context)

    assert result["content"] == "This is plain text content."


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


async def test_web_fetch_http_error(
    tool: WebFetchTool, tool_input: llm.ToolInput, llm_context: llm.LLMContext
) -> None:
    """Non-200 HTTP status should return an error message."""
    session = mock_text_session(404, "Not Found")

    with patch(
        PATCH_CLIENT_SESSION_PATH,
        return_value=session,
    ):
        result = await tool.async_call(tool.hass, tool_input, llm_context)

    assert "error" in result
    assert "HTTP status: 404" in result["error"]
    assert result["url"] == "https://example.com"


async def test_web_fetch_timeout(
    tool: WebFetchTool, tool_input: llm.ToolInput, llm_context: llm.LLMContext
) -> None:
    """TimeoutError should be caught and returned as error dict."""
    session = mock_error_session(TimeoutError("timed out"))

    with patch(
        PATCH_CLIENT_SESSION_PATH,
        return_value=session,
    ):
        result = await tool.async_call(tool.hass, tool_input, llm_context)

    assert "error" in result
    assert "timed out" in result["error"].lower()
    assert result["url"] == "https://example.com"


async def test_web_fetch_generic_exception(
    tool: WebFetchTool, tool_input: llm.ToolInput, llm_context: llm.LLMContext
) -> None:
    """Generic exceptions should be caught and returned as error dict."""
    session = mock_error_session(ConnectionError("Connection refused"))

    with patch(
        PATCH_CLIENT_SESSION_PATH,
        return_value=session,
    ):
        result = await tool.async_call(tool.hass, tool_input, llm_context)

    assert "error" in result
    assert "Error fetching page" in result["error"]
    assert result["url"] == "https://example.com"


async def test_web_fetch_empty_content(
    tool: WebFetchTool, tool_input: llm.ToolInput, llm_context: llm.LLMContext
) -> None:
    """Pages with no readable text should return a 'no content' result."""
    html = "<html><body><script>var x = 1;</script><style>.cls{}</style></body></html>"
    session = mock_text_session(200, html)

    with patch(
        PATCH_CLIENT_SESSION_PATH,
        return_value=session,
    ):
        result = await tool.async_call(tool.hass, tool_input, llm_context)

    assert "result" in result
    assert "No readable text content found" in result["result"]
    assert result["url"] == "https://example.com"


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------


async def test_web_fetch_truncation(
    tool_small_max: WebFetchTool, tool_input: llm.ToolInput, llm_context: llm.LLMContext
) -> None:
    """Content exceeding max_length should be truncated with a notice."""
    long_text = "word " * 200
    session = mock_text_session(200, long_text)

    with patch(
        PATCH_CLIENT_SESSION_PATH,
        return_value=session,
    ):
        result = await tool_small_max.async_call(
            tool_small_max.hass, tool_input, llm_context
        )

    assert "[truncated" in result["content"]
    assert result["content_length"] <= 50 + 45  # 50 max + truncation suffix


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------


async def test_web_fetch_cache_hit(
    tool: WebFetchTool, tool_input: llm.ToolInput, llm_context: llm.LLMContext
) -> None:
    """Cached results should be returned without making an HTTP request."""
    cached = {
        "url": "https://example.com",
        "content": "Cached content",
        "content_length": 14,
    }

    with (
        patch(
            PATCH_CLIENT_SESSION_PATH,
        ) as mock_session_fn,
        patch(
            "custom_components.llm_intents.web_fetch.SQLiteCache.get",
            return_value=cached,
        ),
    ):
        result = await tool.async_call(tool.hass, tool_input, llm_context)

    assert result == cached
    mock_session_fn.assert_not_called()


async def test_web_fetch_cache_miss_fetches_and_stores(
    tool: WebFetchTool,
    tool_input: llm.ToolInput,
    llm_context: llm.LLMContext,
) -> None:
    """A cache miss should fetch the page and store the result."""
    session = mock_text_session(200, "<p>fresh content</p>")

    with (
        patch(
            PATCH_CLIENT_SESSION_PATH,
            return_value=session,
        ),
        patch(
            "custom_components.llm_intents.web_fetch.SQLiteCache.set",
        ) as mock_set,
    ):
        result = await tool.async_call(tool.hass, tool_input, llm_context)

    assert result["content"] == "fresh content"
    mock_set.assert_called_once()
    args, _ = mock_set.call_args
    assert args[0] == "custom_components.llm_intents.web_fetch"
    assert args[1] == {"url": "https://example.com"}


# ---------------------------------------------------------------------------
# HTMLToText parser unit tests
# ---------------------------------------------------------------------------


class TestHTMLToText:
    """Unit tests for the HTMLToText parser."""

    def test_strips_tags(self) -> None:
        """Basic HTML tags should be stripped, text preserved."""
        result = html_to_text("<b>bold</b> and <i>italic</i>")
        assert "bold" in result
        assert "italic" in result

    def test_skips_script_style(self) -> None:
        """Content inside script/style/noscript tags should be omitted."""
        html = (
            "<p>visible</p><script>var x=1;</script>"
            "<style>.c{}</style><p>also visible</p>"
        )
        result = html_to_text(html)
        assert "visible" in result
        assert "also visible" in result
        assert "var x" not in result
        assert ".c{}" not in result

    def test_block_tags_separate_content(self) -> None:
        """Block-level tags should introduce separation between text blocks."""
        html = "<p>First</p><p>Second</p>"
        result = html_to_text(html)
        assert "First" in result
        assert "Second" in result

    def test_empty_input(self) -> None:
        """Empty string should produce empty output."""
        assert html_to_text("") == ""

    def test_no_readable_text(self) -> None:
        """Pages with only script/style content yield empty string."""
        html = "<html><script>a</script><style>b</style></html>"
        assert html_to_text(html) == ""

    def test_nested_skip_tags(self) -> None:
        """Nested script/style tags should be handled (depth tracking)."""
        html = "<div>ok</div><script>if(1){<script>2</script>}</script><p>visible</p>"
        result = html_to_text(html)
        assert "ok" in result
        assert "visible" in result

    def test_whitespace_handling(self) -> None:
        """Whitespace in data content should be collapsed."""
        html = "<div>  spaced   out  </div>"
        result = html_to_text(html)
        assert "spaced" in result

    def test_parser_class_directly(self) -> None:
        """Test the HTMLToText class directly."""
        parser = HTMLToText()
        parser.feed("<p>Hello</p>")
        result = parser.get_text()
        assert "Hello" in result
