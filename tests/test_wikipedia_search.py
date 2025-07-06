"""Tests for the WikipediaSearch component."""

import urllib.parse
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import aiohttp
import pytest
from homeassistant.helpers import intent as intent_helpers

from custom_components.llm_intents.wikipedia_search import (
    CONF_WIKIPEDIA_NUM_RESULTS,
    WikipediaSearch,
)


class DummyIntent:
    """Minimal stand-in for Home Assistant Intent objects."""

    def __init__(self, query_value: str) -> None:
        """
        Initialize with a single 'query' slot.

        Args:
            query_value (str): The value for the 'query' slot.

        """
        self.slots = {"query": {"value": query_value}}
        self.data: dict[str, Any] = {}

    def create_response(self) -> "DummyIntent":
        """Return self as the response object."""
        return self

    def async_set_speech(self, speech: str) -> None:
        """
        Store the speech text in self.data.

        Args:
            speech (str): The speech text to set.

        """
        self.data["speech"] = speech


class FakeResponse:
    """Simulate aiohttp responses for testing."""

    def __init__(self, payload: Any, status: int = 200) -> None:
        """
        Initialize with payload and status.

        Args:
            payload: JSON‐serializable data to return.
            status (int): HTTP status code to simulate.

        """
        self._payload = payload
        self.status = status

    async def json(self) -> Any:
        """Return the payload."""
        return self._payload

    def raise_for_status(self) -> None:
        """Raise error if status code is not 2xx."""
        if not (200 <= self.status < 300):
            raise aiohttp.ClientResponseError(None, (), status=self.status)

    async def __aenter__(self) -> "FakeResponse":
        """Enter context, raising on bad status."""
        self.raise_for_status()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        """Exit context without suppressing exceptions."""
        return False


class RecordingSession:
    """Capture GET requests and return preset FakeResponse objects."""

    def __init__(self, responses: dict[str, FakeResponse]) -> None:
        """
        Initialize with URL→FakeResponse mapping.

        Args:
            responses: Mapping from request URL to FakeResponse.

        """
        self._responses = responses
        self.requests: list[tuple[str, dict[str, Any] | None]] = []

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
    ) -> FakeResponse:
        """
        Record and return the FakeResponse for a GET request.

        Args:
            url (str): The request URL.
            params (dict, optional): Query parameters.
            headers (dict, optional): Request headers.

        Returns:
            FakeResponse: The corresponding fake response.

        """
        self.requests.append((url, params))
        return self._responses[url]


@asynccontextmanager
async def _patch_client_session(
    monkeypatch, session: RecordingSession
) -> AsyncIterator[None]:
    """Patch aiohttp.ClientSession to yield RecordingSession."""

    @asynccontextmanager
    async def fake_session() -> AsyncIterator[RecordingSession]:
        """Yield our RecordingSession instead of a real session."""
        yield session

    monkeypatch.setattr(aiohttp, "ClientSession", lambda: fake_session())
    yield


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ({}, 1),
        ({CONF_WIKIPEDIA_NUM_RESULTS: 3}, 3),
        (True, 1),
    ],
)
def test_constructor_sets_num_results(config, expected):
    """Constructor should set num_results from config."""
    ws = WikipediaSearch(config)  # type: ignore[arg-type]
    assert ws.num_results == expected


@pytest.mark.asyncio
async def test_search_wikipedia_no_hits(monkeypatch):
    """Return a 'no matches' message when no search hits are found."""
    search_url = (
        "https://en.wikipedia.org/w/api.php"
        "?action=query&format=json&list=search"
        f"&srsearch={urllib.parse.quote_plus('nothing')}"
    )
    fake_search = FakeResponse({"query": {"search": []}})
    session = RecordingSession({search_url: fake_search})

    async with _patch_client_session(monkeypatch, session):
        ws = WikipediaSearch({})
        result = await ws.search_wikipedia("nothing")

    assert result == "No search results matched the query"
    assert session.requests == [(search_url, None)]


@pytest.mark.asyncio
async def test_search_wikipedia_hits_with_summaries(monkeypatch):
    """Fetch and return summaries for each search hit."""
    titles = ["Foo", "Bar"]
    search_url = (
        "https://en.wikipedia.org/w/api.php"
        "?action=query&format=json&list=search"
        f"&srsearch={urllib.parse.quote_plus('topic')}"
    )
    summary_urls = {
        t: f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(t)}"
        for t in titles
    }

    fake_search = FakeResponse({"query": {"search": [{"title": t} for t in titles]}})
    fake_summaries = {
        summary_urls["Foo"]: FakeResponse({"extract": "Foo summary"}),
        summary_urls["Bar"]: FakeResponse({"extract": "Bar summary"}),
    }
    session = RecordingSession({search_url: fake_search, **fake_summaries})

    async with _patch_client_session(monkeypatch, session):
        ws = WikipediaSearch({CONF_WIKIPEDIA_NUM_RESULTS: 2})
        result = await ws.search_wikipedia("topic")

    requested = [req[0] for req in session.requests]
    assert search_url in requested
    assert summary_urls["Foo"] in requested
    assert summary_urls["Bar"] in requested

    assert {"title": "Foo", "summary": "Foo summary"} in result
    assert {"title": "Bar", "summary": "Bar summary"} in result


@pytest.mark.asyncio
async def test_search_wikipedia_summaries_empty(monkeypatch):
    """Use default message when 'extract' is missing from summary JSON."""
    title = "EmptyPage"
    search_url = (
        "https://en.wikipedia.org/w/api.php"
        "?action=query&format=json&list=search"
        f"&srsearch={urllib.parse.quote_plus(title)}"
    )
    summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"

    fake_search = FakeResponse({"query": {"search": [{"title": title}]}})
    fake_summary = FakeResponse({})
    session = RecordingSession({search_url: fake_search, summary_url: fake_summary})

    async with _patch_client_session(monkeypatch, session):
        ws = WikipediaSearch({CONF_WIKIPEDIA_NUM_RESULTS: 1})
        result = await ws.search_wikipedia(title)

    assert result == [{"title": title, "summary": "No summary available"}]


@pytest.mark.asyncio
async def test_search_wikipedia_zero_results_flag(monkeypatch):
    """Return 'No summaries available' when num_results is zero."""
    title = "Anything"
    search_url = (
        "https://en.wikipedia.org/w/api.php"
        "?action=query&format=json&list=search"
        f"&srsearch={urllib.parse.quote_plus(title)}"
    )
    fake_search = FakeResponse({"query": {"search": [{"title": title}]}})
    session = RecordingSession({search_url: fake_search})

    async with _patch_client_session(monkeypatch, session):
        ws = WikipediaSearch({CONF_WIKIPEDIA_NUM_RESULTS: 0})
        result = await ws.search_wikipedia(title)

    assert result == "No summaries available"
    assert [req[0] for req in session.requests] == [search_url]


@pytest.mark.asyncio
async def test_async_handle_formats_response(monkeypatch):
    """async_handle should wrap output in IntentResponse and set speech."""
    fake_output = [{"title": "T", "summary": "S"}]

    async def fake_search(self, q: str) -> list[dict[str, str]]:
        return fake_output

    monkeypatch.setattr(WikipediaSearch, "search_wikipedia", fake_search)

    intent_obj = DummyIntent("term")
    ws = WikipediaSearch({})
    resp = await ws.async_handle(intent_obj)

    assert resp.response_type is intent_helpers.IntentResponseType.QUERY_ANSWER
    assert intent_obj.data["speech"] == f"{fake_output}"
