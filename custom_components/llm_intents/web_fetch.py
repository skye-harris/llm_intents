"""Web Fetch tool for retrieving and extracting content from web pages."""

import logging
import re
from html.parser import HTMLParser
from http import HTTPStatus
from typing import ClassVar

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util.json import JsonObjectType

from .base_tool import BaseTool
from .cache import SQLiteCache
from .const import (
    CONF_WEB_FETCH_MAX_CONTENT_LENGTH,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class HTMLToText(HTMLParser):
    """Convert HTML content to plain text."""

    # Tags whose text content should be preceded by a newline
    _block_tags: ClassVar[set[str]] = {
        "div",
        "p",
        "li",
        "ul",
        "ol",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "table",
        "tr",
        "td",
        "th",
        "blockquote",
        "pre",
        "section",
        "article",
        "header",
        "footer",
        "nav",
        "main",
        "aside",
        "figure",
        "figcaption",
    }

    # Tags to skip entirely (content not useful for reading)
    _skip_tags: ClassVar[set[str]] = {"script", "style", "noscript"}

    def __init__(self) -> None:
        super().__init__()
        self._result: list[str] = []
        self._skipping = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._skip_tags:
            self._skipping = True
            self._skip_depth += 1
        elif tag in self._block_tags:
            if self._result and self._result[-1] != "\n":
                self._result.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._skipping and tag in self._skip_tags:
            self._skip_depth -= 1
            if self._skip_depth <= 0:
                self._skipping = False
                self._skip_depth = 0

    def handle_data(self, data: str) -> None:
        if not self._skipping:
            text = data.strip()
            if text:
                self._result.append(text)

    def get_text(self) -> str:
        return " ".join(self._result)


def html_to_text(html_content: str) -> str:
    """Convert HTML content to readable plain text."""
    parser = HTMLToText()
    parser.feed(html_content)
    return parser.get_text()


class WebFetchTool(BaseTool):
    """Tool for fetching and extracting text content from web pages."""

    name = "web_fetch"
    description = (
        "Fetches the content of a web page at the given URL and returns "
        "the readable text. Use this to read articles, documentation, "
        "blog posts, or any other web page content."
    )
    prompt_description = None

    parameters = vol.Schema(
        {
            vol.Required(
                "url",
                description="The full URL of the web page to fetch (e.g. https://example.com/article)",
            ): str,
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Call the tool."""
        config_data = hass.data[DOMAIN].get("config", {})
        entry = next(iter(hass.config_entries.async_entries(DOMAIN)))
        config_data = {**config_data, **entry.options}

        url = tool_input.tool_args["url"]
        max_length = int(config_data.get(CONF_WEB_FETCH_MAX_CONTENT_LENGTH, 10000))

        _LOGGER.info("Web fetch requested for: %s", url)

        # Validate URL scheme
        if not url.startswith(("http://", "https://")):
            return {
                "error": f"Invalid URL scheme. Only HTTP and HTTPS are supported: {url}"
            }

        cache = SQLiteCache()
        cached_response = cache.get(__name__, {"url": url})
        if cached_response:
            return cached_response

        try:
            session = async_get_clientsession(hass)

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }

            async with session.get(url, headers=headers) as resp:
                if resp.status != HTTPStatus.OK:
                    _LOGGER.error(
                        "Web fetch received HTTP %s for URL: %s", resp.status, url
                    )
                    return {
                        "error": f"Failed to fetch page. HTTP status: {resp.status}",
                        "url": url,
                    }

                content_type = resp.headers.get("Content-Type", "")
                if (
                    "text/html" not in content_type
                    and "application/xhtml" not in content_type
                ):
                    # For non-HTML content, return as-is (e.g., plain text, markdown)
                    text_content = await resp.text()
                else:
                    html_content = await resp.text()
                    text_content = html_to_text(html_content)

                # Clean up extra whitespace
                text_content = re.sub(r"\s{2,}", " ", text_content).strip()

                if not text_content:
                    return {
                        "result": f"No readable text content found at {url}",
                        "url": url,
                    }

                # Truncate if too long
                if len(text_content) > max_length:
                    truncated_chars = len(text_content) - max_length
                    text_content = text_content[:max_length]
                    text_content += (
                        f"\n\n... [truncated, {truncated_chars} characters omitted]"
                    )

                result = {
                    "url": url,
                    "content": text_content,
                    "content_length": len(text_content),
                }

                cache.set(__name__, {"url": url}, result)
                return result

        except TimeoutError:
            _LOGGER.exception("Web fetch timeout for URL: %s", url)
            return {"error": f"Request timed out fetching: {url}", "url": url}
        except Exception as e:
            _LOGGER.exception("Web fetch error for URL %s", url)
            return {"error": f"Error fetching page: {e!s}", "url": url}
