"""Tests for the Google Places tool."""

from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import MockConfigEntry

from custom_components.llm_intents.const import (
    CONF_GOOGLE_PLACES_LATITUDE,
    CONF_GOOGLE_PLACES_LONGITUDE,
    CONF_GOOGLE_PLACES_NUM_RESULTS,
    CONF_GOOGLE_PLACES_RADIUS,
    CONF_GOOGLE_PLACES_RANKING,
    CONF_PROVIDER_API_KEYS,
    DOMAIN,
    PROVIDER_GOOGLE,
)
from custom_components.llm_intents.google_places import FindPlacesTool

from .utils import MockContext

PLACES_URL = "https://places.googleapis.com/v1/places:searchText"


def _places_response(places: list | None = None) -> dict:
    return {"places": places or []}


def _make_session(responses_by_url: dict[str, dict]) -> AsyncMock:
    """Build a mock session that dispatches POST responses by URL."""
    session = AsyncMock()

    def mock_post(url: str, **_kwargs: Any) -> MockContext:
        body = responses_by_url[url]
        response = AsyncMock()
        response.status = body["status"]
        response.json = AsyncMock(return_value=body["data"])
        response.text = AsyncMock(return_value=str(body.get("data")))
        return MockContext(response)

    session.post = Mock(side_effect=mock_post)
    return session


def _tool_input(**args: Any) -> Mock:
    tool_input = Mock()
    tool_input.tool_args = args
    return tool_input


@pytest.fixture
def config() -> dict:
    """Return default places config."""
    return {
        CONF_PROVIDER_API_KEYS: {PROVIDER_GOOGLE: "test_google_key"},
        CONF_GOOGLE_PLACES_NUM_RESULTS: 3,
        CONF_GOOGLE_PLACES_RANKING: "Distance",
        CONF_GOOGLE_PLACES_RADIUS: 5,
    }


@pytest.fixture
def places_hass(hass: HomeAssistant, config: dict) -> HomeAssistant:
    """Configure a mock HA instance for the places tool."""
    hass.data = {DOMAIN: {"config": config}}
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    hass.config = Mock()
    hass.config.latitude = 40.0
    hass.config.longitude = -74.0
    hass.config.time_zone = dt_util.UTC
    dt_util.set_default_time_zone(dt_util.UTC)
    return hass


@pytest.fixture
def tool(places_hass: HomeAssistant, config: dict) -> FindPlacesTool:
    """Construct the tool under test."""
    return FindPlacesTool(config, places_hass)


@pytest.fixture
def cache_miss() -> Any:
    """Patch InMemoryCache so every lookup is a miss."""
    with patch(
        "custom_components.llm_intents.google_places.InMemoryCache",
    ) as cache_cls:
        cache_cls.return_value.get.return_value = None
        yield cache_cls


@pytest.mark.parametrize(
    ("has_location", "has_ranking", "num_results", "expected_bias", "expected_rank"),
    [
        (False, False, 3, None, "DISTANCE"),
        (
            True,
            True,
            1,
            {
                "circle": {
                    "center": {"latitude": 40.0, "longitude": -74.0},
                    "radius": 5000,
                }
            },
            "RELEVANCE",
        ),
        (
            True,
            False,
            5,
            {
                "circle": {
                    "center": {"latitude": 40.0, "longitude": -74.0},
                    "radius": 5000,
                }
            },
            "DISTANCE",
        ),
        (
            True,
            "None",
            2,
            {
                "circle": {
                    "center": {"latitude": 40.0, "longitude": -74.0},
                    "radius": 5000,
                }
            },
            "NONE",
        ),
    ],
)
async def test_request_params(
    tool: FindPlacesTool,
    places_hass: HomeAssistant,
    cache_miss: Any,
    has_location: bool,
    has_ranking: str | bool,
    num_results: int,
    expected_bias: dict | None,
    expected_rank: str | None,
) -> None:
    """Request body reflects config: location bias and rank preference."""
    config = places_hass.data[DOMAIN]["config"]
    config[CONF_GOOGLE_PLACES_NUM_RESULTS] = num_results
    if has_location:
        config[CONF_GOOGLE_PLACES_LATITUDE] = 40.0
        config[CONF_GOOGLE_PLACES_LONGITUDE] = -74.0
    else:
        config[CONF_GOOGLE_PLACES_LATITUDE] = ""
        config[CONF_GOOGLE_PLACES_LONGITUDE] = ""
    if has_ranking is True:
        config[CONF_GOOGLE_PLACES_RANKING] = "Relevance"
    elif has_ranking == "None":
        config[CONF_GOOGLE_PLACES_RANKING] = "None"
    else:
        config[CONF_GOOGLE_PLACES_RANKING] = "Distance"

    session = _make_session({PLACES_URL: {"status": 200, "data": _places_response()}})

    with patch(
        "custom_components.llm_intents.google_places.async_get_clientsession",
        return_value=session,
    ):
        await tool.async_call(places_hass, _tool_input(query="cafe"), Mock())

    body = session.post.call_args.kwargs["json"]
    assert body["textQuery"] == "cafe"
    assert body["pageSize"] == num_results
    if expected_bias:
        assert body["locationBias"] == expected_bias
    else:
        assert "locationBias" not in body
    if expected_rank:
        assert body["rankPreference"] == expected_rank
    else:
        assert "rankPreference" not in body


async def test_missing_api_key(
    tool: FindPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """Missing Google API key surfaces a clear error."""
    places_hass.data[DOMAIN]["config"][CONF_PROVIDER_API_KEYS] = {}
    result = await tool.async_call(places_hass, _tool_input(query="x"), Mock())
    assert result == {"error": "Google Places API key not configured"}


@pytest.mark.parametrize(
    ("scenario", "places", "expected_result"),
    [
        (
            "full_place",
            [
                {
                    "displayName": {"text": "Blue Bottle Coffee"},
                    "shortFormattedAddress": "100 Main St",
                    "rating": 4.5,
                    "nationalPhoneNumber": "+1-555-0100",
                    "regularOpeningHours": {
                        "openNow": True,
                        "nextCloseTime": "2025-01-01T22:00:00Z",
                        "nextOpenTime": "2025-01-02T08:00:00Z",
                        "weekdayDescriptions": [
                            "Mon\u2009-\u2009Fri 8am\u2009-\u20096pm"
                        ],
                    },
                },
            ],
            {
                "results": [
                    {
                        "name": "Blue Bottle Coffee",
                        "address": "100 Main St",
                        "rating": "4.5 out of 5",
                        "phone": "+1-555-0100",
                        "open_now": True,
                        "next_closes_at": "2025-01-01 22:00",
                        "next_opens_at": "2025-01-02 08:00",
                        "regular_open_hours": ["Mon - Fri 8am - 6pm"],
                    },
                ],
                "instruction": FindPlacesTool.response_directive,
            },
        ),
        (
            "no_rating",
            [
                {
                    "displayName": {"text": "Uncrated Shop"},
                    "shortFormattedAddress": "200 Oak Ave",
                },
            ],
            {
                "results": [
                    {
                        "name": "Uncrated Shop",
                        "address": "200 Oak Ave",
                        "rating": "Not rated",
                        "phone": "Not available",
                    },
                ],
                "instruction": FindPlacesTool.response_directive,
            },
        ),
        (
            "no_phone",
            [
                {
                    "displayName": {"text": "Park"},
                    "shortFormattedAddress": "Central Park",
                    "rating": 4.0,
                },
            ],
            {
                "results": [
                    {
                        "name": "Park",
                        "address": "Central Park",
                        "rating": "4.0 out of 5",
                        "phone": "Not available",
                    },
                ],
                "instruction": FindPlacesTool.response_directive,
            },
        ),
        (
            "no_opening_hours",
            [
                {
                    "displayName": {"text": "24hr Diner"},
                    "shortFormattedAddress": "300 Elm St",
                    "rating": 3.8,
                    "nationalPhoneNumber": "+1-555-0200",
                },
            ],
            {
                "results": [
                    {
                        "name": "24hr Diner",
                        "address": "300 Elm St",
                        "rating": "3.8 out of 5",
                        "phone": "+1-555-0200",
                    },
                ],
                "instruction": FindPlacesTool.response_directive,
            },
        ),
        (
            "empty",
            [],
            {"result": "No places found"},
        ),
    ],
)
async def test_response_parsing(
    tool: FindPlacesTool,
    places_hass: HomeAssistant,
    cache_miss: Any,
    scenario: str,
    places: list,
    expected_result: dict,
) -> None:
    """Parse API response shapes correctly."""
    session = _make_session(
        {PLACES_URL: {"status": 200, "data": _places_response(places)}}
    )

    with patch(
        "custom_components.llm_intents.google_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(places_hass, _tool_input(query="food"), Mock())

    assert result == expected_result


async def test_http_error_returns_error(
    tool: FindPlacesTool,
    places_hass: HomeAssistant,
    cache_miss: Any,
) -> None:
    """Non-200 from Places is surfaced as a structured error."""
    session = _make_session({PLACES_URL: {"status": 500, "data": {"error": "boom"}}})

    with patch(
        "custom_components.llm_intents.google_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(places_hass, _tool_input(query="x"), Mock())

    assert result == {"error": "Places search error: 500"}


async def test_exception_returns_error(
    tool: FindPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """Network exception surfaces as a structured error."""
    session = AsyncMock()

    def mock_post(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("network error")

    session.post = Mock(side_effect=mock_post)

    with patch(
        "custom_components.llm_intents.google_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(places_hass, _tool_input(query="x"), Mock())

    assert result == {"error": "Error finding places: network error"}


async def test_cache_hit_skips_api(
    tool: FindPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """A cached response avoids hitting the Places API."""
    session = AsyncMock()
    cached = {"results": [{"name": "Cached"}], "instruction": tool.response_directive}

    with (
        patch(
            "custom_components.llm_intents.google_places.async_get_clientsession",
            return_value=session,
        ),
        patch(
            "custom_components.llm_intents.google_places.InMemoryCache",
        ) as cache_cls,
    ):
        cache_cls.return_value.get.return_value = cached
        result = await tool.async_call(places_hass, _tool_input(query="x"), Mock())

    assert session.post.call_count == 0
    assert result == cached


@freeze_time("2025-01-01 12:00:00")
async def test_cache_stores_result(
    tool: FindPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """A successful response is cached for future lookups."""
    places = [
        {
            "displayName": {"text": "Found Place"},
            "shortFormattedAddress": "1 Test St",
            "rating": 4.0,
            "nationalPhoneNumber": "+1-555-0000",
        },
    ]
    session = _make_session(
        {PLACES_URL: {"status": 200, "data": _places_response(places)}}
    )

    with (
        patch(
            "custom_components.llm_intents.google_places.async_get_clientsession",
            return_value=session,
        ),
        patch(
            "custom_components.llm_intents.google_places.InMemoryCache",
        ) as cache_cls,
    ):
        cache_cls.return_value.get.return_value = None
        await tool.async_call(places_hass, _tool_input(query="test"), Mock())

    cache_cls.return_value.set.assert_called_once()
    call_args = cache_cls.return_value.set.call_args
    assert call_args[0][0] == "custom_components.llm_intents.google_places"
    assert call_args[0][1]["textQuery"] == "test"
    stored = call_args[0][2]
    assert stored["results"][0]["name"] == "Found Place"
    assert stored["instruction"] == tool.response_directive
