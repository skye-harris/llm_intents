"""Tests for the GooglePlaces integration in the llm_intents custom component."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import aiohttp
import pytest
from homeassistant.helpers import intent as intent_helpers

from custom_components.llm_intents.google_places import (
    CONF_GOOGLE_PLACES_API_KEY,
    CONF_GOOGLE_PLACES_NUM_RESULTS,
    GooglePlaces,
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
    """Simulate aiohttp response context for testing."""

    def __init__(self, payload: Any, status: int = 200) -> None:
        """
        Initialize with payload and status.

        Args:
            payload: JSON serializable data to return.
            status (int): HTTP status code to simulate.

        """
        self._payload = payload
        self.status = status

    async def json(self) -> Any:
        """Return the payload."""
        return self._payload

    def raise_for_status(self) -> None:
        """Raise on bad status."""
        if not (200 <= self.status < 300):
            raise aiohttp.ClientResponseError(None, (), status=self.status)

    async def __aenter__(self) -> "FakeResponse":
        """Enter context, raising on error status."""
        self.raise_for_status()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        """Exit context without suppressing exceptions."""
        return False


class RecordingSession:
    """Capture POST requests and return preset FakeResponse."""

    def __init__(self, response: FakeResponse) -> None:
        """
        Initialize with a single FakeResponse to return on post().

        Args:
            response: The FakeResponse to return.

        """
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def post(
        self, url: str, json: dict[str, Any], headers: dict[str, Any]
    ) -> FakeResponse:
        """
        Record and return the fake response for a POST request.

        Args:
            url (str): The request URL.
            json (dict): The JSON payload.
            headers (dict): The request headers.

        Returns:
            FakeResponse: The fake response context manager.

        """
        self.calls.append({"url": url, "json": json, "headers": headers})
        return self.response


@asynccontextmanager
async def _patch_client_session(
    monkeypatch, session: RecordingSession
) -> AsyncIterator[None]:
    """Patch aiohttp.ClientSession to yield our RecordingSession."""
    @asynccontextmanager
    async def fake_session() -> AsyncIterator[RecordingSession]:
        yield session

    monkeypatch.setattr(aiohttp, "ClientSession", lambda: fake_session())
    yield


def test_constructor_defaults_and_config() -> None:
    """Constructor should set API key and num_results from config or use defaults."""
    cfg = {"api_key": "abc", "num_results": 5}
    gp = GooglePlaces(cfg)
    assert gp.api_key == "abc"
    assert gp.num_results == 5

    gp2 = GooglePlaces({})
    assert gp2.api_key is None
    assert gp2.num_results == 2  # default


@pytest.mark.asyncio
async def test_search_google_places_happy_path(monkeypatch):
    """Return formatted list on successful API response."""
    payload = {
        "places": [
            {"displayName": {"text": "Place A"}, "formattedAddress": "Addr A"},
            {"displayName": {"text": "Place B"}, "formattedAddress": "Addr B"},
        ]
    }
    fake_resp = FakeResponse(payload)
    session = RecordingSession(fake_resp)

    async with _patch_client_session(monkeypatch, session):
        gp = GooglePlaces({CONF_GOOGLE_PLACES_API_KEY: "key", CONF_GOOGLE_PLACES_NUM_RESULTS: 2})
        result = await gp.search_google_places("test")

    # verify returned structure
    assert result == [
        {"name": "Place A", "address": "Addr A"},
        {"name": "Place B", "address": "Addr B"},
    ]
    # verify payload and headers passed
    call = session.calls[0]
    assert call["json"] == {"textQuery": "test", "pageSize": 2}
    hdrs = call["headers"]
    assert hdrs["X-Goog-Api-Key"] == "key"
    assert "Accept" in hdrs
    assert "Accept-Encoding" in hdrs


@pytest.mark.asyncio
async def test_search_google_places_missing_fields(monkeypatch):
    """Missing displayName or formattedAddress should use defaults."""
    payload = {
        "places": [
            {},  # no fields
        ]
    }
    fake_resp = FakeResponse(payload)
    session = RecordingSession(fake_resp)

    async with _patch_client_session(monkeypatch, session):
        gp = GooglePlaces({CONF_GOOGLE_PLACES_API_KEY: "k", CONF_GOOGLE_PLACES_NUM_RESULTS: 1})
        result = await gp.search_google_places("x")

    assert result == [{"name": "No Name", "address": "No Address"}]


@pytest.mark.asyncio
async def test_search_google_places_empty(monkeypatch):
    """Empty 'places' list yields empty result."""
    fake_resp = FakeResponse({"places": []})
    session = RecordingSession(fake_resp)

    async with _patch_client_session(monkeypatch, session):
        gp = GooglePlaces({})
        result = await gp.search_google_places("none")

    assert result == []


@pytest.mark.asyncio
async def test_search_google_places_error(monkeypatch):
    """Non-2xx status should raise ClientResponseError."""
    fake_resp = FakeResponse({}, status=500)
    session = RecordingSession(fake_resp)

    async with _patch_client_session(monkeypatch, session):
        gp = GooglePlaces({})
        with pytest.raises(aiohttp.ClientResponseError):
            await gp.search_google_places("err")


@pytest.mark.asyncio
async def test_async_handle_formats_response(monkeypatch):
    """async_handle should wrap and speech-format the search results."""
    fake_output = [{"name": "N", "address": "A"}]

    async def fake_search(self, q: str) -> list[dict[str, str]]:
        return fake_output

    monkeypatch.setattr(GooglePlaces, "search_google_places", fake_search)

    intent_obj = DummyIntent("loc")
    gp = GooglePlaces({})
    resp = await gp.async_handle(intent_obj)

    assert resp.response_type is intent_helpers.IntentResponseType.QUERY_ANSWER
    assert intent_obj.data["speech"] == f"{fake_output}"
