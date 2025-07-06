"""
Tests for the BraveSearch integration in the llm_intents custom component.

This module contains unit tests for the BraveSearch class, including
search functionality, error handling, and intent response formatting.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import Mock

import aiohttp
import pytest
from homeassistant.helpers import intent as intent_helpers

from custom_components.llm_intents.brave_search import BraveSearch


# Minimal intent stub
class DummyIntent:
    """A minimal intent stub for testing BraveSearch intent handling."""

    def __init__(self, query_value: str) -> None:
        """
        Initialize a DummyIntent with a single query slot.

        Args:
            query_value: The value to assign to the "query" slot.

        """
        self.slots = {"query": {"value": query_value}}
        self.data: dict[str, Any] = {}

    def create_response(self) -> "DummyIntent":
        """Create and return a response object for the intent."""
        return self

    def async_set_speech(self, speech: str) -> None:
        """
        Set the speech response for the intent.

        Args:
            speech: The speech text to set in the response.

        """
        self.data["speech"] = speech


# Factory for handler
def make_brave(config: dict[str, Any] | None = None) -> BraveSearch:
    """
    Create a BraveSearch instance for testing.

    Args:
        config: Configuration dictionary for BraveSearch.

    Returns:
        An instance of the BraveSearch class.

    """
    cfg = config or {"api_key": "key", "num_results": 1}
    return BraveSearch(cfg)


# FakeResponse implements async context and JSON, error raised on entry
ErrorType = Exception


class FakeResponse:
    """A fake aiohttp response object for testing async context and JSON handling."""

    def __init__(self, json_data: Any, error: ErrorType | None = None) -> None:
        """
        Initialize a FakeResponse instance.

        Args:
            json_data: The JSON data to return from the response.
            error: An exception to raise on entry or when calling raise_for_status.

        """
        self._json = json_data
        self._error = error
        self.raise_for_status = Mock()
        if error:
            self.raise_for_status.side_effect = error

    async def json(self) -> Any:
        """Return the JSON data for the fake response."""
        return self._json

    async def __aenter__(self) -> "FakeResponse":
        """
        Enter the async context manager.

        Raises:
            Exception: If an error was provided during initialization.

        """
        if self._error:
            raise self._error
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        """Exit the async context manager without suppressing exceptions."""
        return False


# DummySession provides get() returning FakeResponse
class DummySession:
    """A dummy session object that mimics aiohttp.ClientSession for tests."""

    def __init__(self, response_cm: FakeResponse) -> None:
        """
        Initialize a DummySession with a given FakeResponse.

        Args:
            response_cm: The fake response context manager for get().

        """
        self._response_cm = response_cm

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
    ) -> FakeResponse:
        """
        Return the fake response for a GET request.

        Args:
            url: The request URL.
            params: Query parameters for the request.
            headers: Headers for the request.

        Returns:
            The fake response context manager.

        """
        return self._response_cm


# Helper to patch aiohttp.ClientSession as async contextmanager
def patch_session(monkeypatch: Any, response_cm: FakeResponse) -> None:
    """
    Patch aiohttp.ClientSession to yield a DummySession for testing.

    This helper replaces ClientSession with an async context manager
    that yields a DummySession initialized with the provided response.

    Args:
        monkeypatch: pytest fixture for modifying attributes.
        response_cm: FakeResponse to return from get().

    """
    dummy = DummySession(response_cm)

    @asynccontextmanager
    async def fake_client_session() -> AsyncIterator[DummySession]:
        """Yield the DummySession instead of a real aiohttp ClientSession."""
        yield dummy

    monkeypatch.setattr(aiohttp, "ClientSession", lambda: fake_client_session())


@pytest.mark.asyncio
async def test_search_happy_path(monkeypatch: Any) -> None:
    """
    Test that search_brave_ai returns formatted results on a successful search.

    Simulates a successful HTTP response with one result and asserts
    the output list matches the expected format.
    """
    data = {
        "web": {
            "results": [
                {"title": "A", "description": "B", "extra_snippets": ["X"], "url": "U"}
            ]
        }
    }
    fake_resp = FakeResponse(data)
    patch_session(monkeypatch, fake_resp)

    bs = make_brave({"api_key": "k", "num_results": 1})
    results = await bs.search_brave_ai("q")
    assert results == [
        {"title": "A", "description": "B", "snippets": ["X"], "url": "U"}
    ]


@pytest.mark.asyncio
async def test_search_empty_results(monkeypatch: Any) -> None:
    """
    Test that search_brave_ai returns an empty list when no results are found.

    Simulates an HTTP response with no results and verifies
    the return value is an empty list.
    """
    data = {"web": {"results": []}}
    fake_resp = FakeResponse(data)
    patch_session(monkeypatch, fake_resp)

    bs = make_brave()
    results = await bs.search_brave_ai("q")
    assert results == []


@pytest.mark.asyncio
async def test_search_error(monkeypatch: Any) -> None:
    """
    Test that search_brave_ai raises ClientResponseError on HTTP errors.

    Configures the fake session to raise an aiohttp error and asserts
    that the exception propagates.
    """
    error = aiohttp.ClientResponseError(None, (), status=500)
    fake_resp = FakeResponse({}, error=error)
    patch_session(monkeypatch, fake_resp)

    bs = make_brave()
    with pytest.raises(aiohttp.ClientResponseError):
        await bs.search_brave_ai("q")


@pytest.mark.asyncio
async def test_search_with_all_location_headers(monkeypatch: Any) -> None:
    """
    Test that search_brave_ai sets correct location headers and query parameters.

    Simulates configuration containing latitude, longitude, timezone,
    country_code, and post_code, then verifies those map to headers and params.
    """
    data = {"web": {"results": []}}
    fake_resp = FakeResponse(data)

    recorded: dict[str, Any] = {}

    class RecordingSession(DummySession):
        """A DummySession that records request details."""

        def __init__(self, response_cm: FakeResponse) -> None:
            super().__init__(response_cm)

        def get(
            self,
            url: str,
            params: dict[str, Any] | None = None,
            headers: dict[str, Any] | None = None,
        ) -> FakeResponse:
            """
            Record URL, params, headers and return the fake response.

            Returns:
                FakeResponse: The fake response context manager.

            """
            recorded["url"] = url
            recorded["params"] = params
            recorded["headers"] = headers
            return self._response_cm

    @asynccontextmanager
    async def fake_client_session() -> AsyncIterator[RecordingSession]:
        """Yield a RecordingSession instead of a real aiohttp ClientSession."""
        yield RecordingSession(fake_resp)

    monkeypatch.setattr(aiohttp, "ClientSession", lambda: fake_client_session())

    cfg = {
        "api_key": "k",
        "num_results": 5,
        "latitude": 1.23,
        "longitude": 4.56,
        "timezone": "UTC",
        "country_code": "US",
        "post_code": "12345",
    }
    bs = make_brave(cfg)
    await bs.search_brave_ai("q")

    hdr = recorded["headers"]
    assert hdr["X-Loc-Lat"] == "1.23"
    assert hdr["X-Loc-Long"] == "4.56"
    assert hdr["X-Loc-Timezone"] == "UTC"
    assert hdr["X-Loc-Country"] == "US"
    assert hdr["X-Loc-Postal-Code"] == "12345"

    prm = recorded["params"]
    assert prm["count"] == 5
    assert prm["country"] == "US"


@pytest.mark.asyncio
async def test_async_handle(monkeypatch: Any) -> None:
    """
    Test that async_handle processes and formats BraveSearch results correctly.

    Patches BraveSearch.search_brave_ai to return a fixed list of result
    dictionaries and asserts the formatted speech output matches expected content.
    """
    fake = [{"title": "T", "description": "D", "extra_snippets": ["S"], "url": "U"}]
    from unittest.mock import AsyncMock
    monkeypatch.setattr(
        BraveSearch,
        "search_brave_ai",
        AsyncMock(return_value=fake),
    )

    bs = make_brave()
    intent_obj = DummyIntent("foo")
    resp = await bs.async_handle(intent_obj)

    assert resp.response_type == intent_helpers.IntentResponseType.QUERY_ANSWER
    speech = resp.data.get("speech", "")
    assert "T" in speech
    assert "D" in speech
    assert "S" in speech
    assert "U" in speech
