"""Tests for the Google Routes tool."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.llm_intents.const import (
    CONF_GOOGLE_ROUTES_DEFAULT_TRAVEL_MODE,
    CONF_GOOGLE_ROUTES_HOME_ADDRESS,
    CONF_PROVIDER_API_KEYS,
    DOMAIN,
    PROVIDER_GOOGLE,
)
from custom_components.llm_intents.google_routes import (
    GetRouteTool,
    _format_distance,
    _format_duration,
)

from .utils import MockContext

PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"


def _places_response(places: list | None = None) -> dict:
    return {"places": places or []}


def _routes_response(
    *,
    duration_s: int = 600,
    static_s: int | None = None,
    distance_m: int = 5000,
) -> dict:
    static_s = duration_s if static_s is None else static_s
    return {
        "routes": [
            {
                "duration": f"{duration_s}s",
                "staticDuration": f"{static_s}s",
                "distanceMeters": distance_m,
            },
        ],
    }


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
    """Default routes config."""
    return {
        CONF_PROVIDER_API_KEYS: {PROVIDER_GOOGLE: "test_google_key"},
        CONF_GOOGLE_ROUTES_HOME_ADDRESS: "1 Test Lane, Test City",
        CONF_GOOGLE_ROUTES_DEFAULT_TRAVEL_MODE: "DRIVE",
    }


@pytest.fixture
def routes_hass(hass: HomeAssistant, config: dict) -> HomeAssistant:
    """Configure a mock HA instance for the routes tool."""
    hass.data = {DOMAIN: {"config": config}}
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    # `hass.config` is not a class attribute on the HA spec, so attach our own.
    hass.config = Mock()
    hass.config.language = "en"
    hass.config.latitude = 40.0
    hass.config.longitude = -74.0
    # Default to metric — anything that's not US_CUSTOMARY_SYSTEM
    hass.config.units = object()
    return hass


@pytest.fixture
def tool(routes_hass: HomeAssistant, config: dict) -> GetRouteTool:
    """Construct the tool under test."""
    return GetRouteTool(config, routes_hass)


@pytest.fixture
def cache_miss() -> Any:
    """Patch SQLiteCache so every lookup is a miss."""
    with patch(
        "custom_components.llm_intents.google_routes.SQLiteCache",
    ) as cache_cls:
        cache_cls.return_value.get.return_value = None
        yield cache_cls


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (45, "45 seconds"),
        (180, "3 min"),
        (125, "2 min 5 sec"),
        (7200, "2 hr"),
        (7320, "2 hr 2 min"),
    ],
)
def test_format_duration(seconds: int, expected: str) -> None:
    """Format durations in seconds to human-readable strings."""
    assert _format_duration(seconds) == expected


@pytest.mark.parametrize(
    ("metres", "imperial", "expected"),
    [
        (450, False, "450 m"),
        (15000, False, "15.0 km"),
        (50, True, "164 ft"),
        (8000, True, "5.0 mi"),
    ],
)
def test_format_distance(metres: int, imperial: bool, expected: str) -> None:
    """Format distances in metres to human-readable strings."""
    assert _format_distance(metres, imperial=imperial) == expected


async def test_returns_error_without_api_key(
    tool: GetRouteTool,
    routes_hass: HomeAssistant,
    config: dict,
) -> None:
    """Missing Google API key surfaces a clear error."""
    config[CONF_PROVIDER_API_KEYS] = {}
    result = await tool.async_call(
        routes_hass,
        _tool_input(destination="anywhere"),
        Mock(),
    )
    assert result == {"error": "Google API key not configured"}


async def test_returns_error_without_home_address(
    tool: GetRouteTool,
    routes_hass: HomeAssistant,
    config: dict,
) -> None:
    """Missing home address surfaces a clear error."""
    config[CONF_GOOGLE_ROUTES_HOME_ADDRESS] = ""
    result = await tool.async_call(
        routes_hass,
        _tool_input(destination="anywhere"),
        Mock(),
    )
    assert result == {"error": "Home address for Routes is not configured"}


async def test_resolves_via_places_then_routes(
    tool: GetRouteTool,
    routes_hass: HomeAssistant,
    cache_miss: Any,
) -> None:
    """Fuzzy destinations are resolved via Places before routing."""
    session = _make_session(
        {
            PLACES_URL: {
                "status": 200,
                "data": _places_response(
                    [
                        {
                            "displayName": {"text": "Aquarium"},
                            "shortFormattedAddress": "100 Water St",
                        },
                    ],
                ),
            },
            ROUTES_URL: {
                "status": 200,
                "data": _routes_response(duration_s=600, distance_m=5000),
            },
        },
    )

    with patch(
        "custom_components.llm_intents.google_routes.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            routes_hass,
            _tool_input(destination="the aquarium"),
            Mock(),
        )

    body = result["result"]
    assert body["destination"] == "100 Water St"
    assert body["destination_query"] == "the aquarium"
    assert body["destination_name"] == "Aquarium"
    assert body["travel_mode"] == "DRIVE"
    assert body["duration"] == "10 min"
    assert body["distance"] == "5.0 km"

    # Both Places and Routes were called, in order
    assert session.post.call_count == 2
    urls = [call.args[0] for call in session.post.call_args_list]
    assert urls == [PLACES_URL, ROUTES_URL]

    routes_body = session.post.call_args_list[1].kwargs["json"]
    assert routes_body["destination"] == {"address": "100 Water St"}
    assert routes_body["origin"] == {"address": "1 Test Lane, Test City"}
    assert routes_body["travelMode"] == "DRIVE"
    assert routes_body["routingPreference"] == "TRAFFIC_AWARE"


async def test_places_locationbias_uses_ha_home_coordinates(
    tool: GetRouteTool,
    routes_hass: HomeAssistant,
    cache_miss: Any,
) -> None:
    """Places lookup biases by HA home coordinates, not Places config."""
    session = _make_session(
        {
            PLACES_URL: {"status": 200, "data": _places_response()},
            ROUTES_URL: {"status": 200, "data": _routes_response()},
        },
    )

    with patch(
        "custom_components.llm_intents.google_routes.async_get_clientsession",
        return_value=session,
    ):
        await tool.async_call(
            routes_hass,
            _tool_input(destination="park"),
            Mock(),
        )

    places_body = session.post.call_args_list[0].kwargs["json"]
    assert places_body["pageSize"] == 1
    assert places_body["rankPreference"] == "RELEVANCE"
    bias = places_body["locationBias"]["circle"]
    assert bias["center"] == {"latitude": 40.0, "longitude": -74.0}


async def test_falls_back_to_raw_destination_on_places_miss(
    tool: GetRouteTool,
    routes_hass: HomeAssistant,
    cache_miss: Any,
) -> None:
    """An empty Places response leaves routing to use the raw destination."""
    session = _make_session(
        {
            PLACES_URL: {"status": 200, "data": _places_response()},
            ROUTES_URL: {"status": 200, "data": _routes_response()},
        },
    )

    with patch(
        "custom_components.llm_intents.google_routes.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            routes_hass,
            _tool_input(destination="500 Main St"),
            Mock(),
        )

    body = result["result"]
    assert body["destination"] == "500 Main St"
    assert "destination_query" not in body
    assert "destination_name" not in body
    routes_body = session.post.call_args_list[1].kwargs["json"]
    assert routes_body["destination"] == {"address": "500 Main St"}


async def test_uses_configured_default_mode_when_omitted(
    tool: GetRouteTool,
    routes_hass: HomeAssistant,
    config: dict,
    cache_miss: Any,
) -> None:
    """The configured default mode is used when the LLM omits one."""
    config[CONF_GOOGLE_ROUTES_DEFAULT_TRAVEL_MODE] = "WALK"
    session = _make_session(
        {
            PLACES_URL: {"status": 200, "data": _places_response()},
            ROUTES_URL: {"status": 200, "data": _routes_response()},
        },
    )

    with patch(
        "custom_components.llm_intents.google_routes.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            routes_hass,
            _tool_input(destination="park"),
            Mock(),
        )

    routes_body = session.post.call_args_list[1].kwargs["json"]
    assert routes_body["travelMode"] == "WALK"
    # Walking should not request traffic-aware routing
    assert "routingPreference" not in routes_body
    assert result["result"]["travel_mode"] == "WALK"


async def test_explicit_mode_overrides_default(
    tool: GetRouteTool,
    routes_hass: HomeAssistant,
    config: dict,
    cache_miss: Any,
) -> None:
    """An LLM-supplied mode overrides the configured default."""
    config[CONF_GOOGLE_ROUTES_DEFAULT_TRAVEL_MODE] = "WALK"
    session = _make_session(
        {
            PLACES_URL: {"status": 200, "data": _places_response()},
            ROUTES_URL: {"status": 200, "data": _routes_response()},
        },
    )

    with patch(
        "custom_components.llm_intents.google_routes.async_get_clientsession",
        return_value=session,
    ):
        await tool.async_call(
            routes_hass,
            _tool_input(destination="park", mode="BICYCLE"),
            Mock(),
        )

    routes_body = session.post.call_args_list[1].kwargs["json"]
    assert routes_body["travelMode"] == "BICYCLE"


async def test_routes_api_error_returns_error(
    tool: GetRouteTool,
    routes_hass: HomeAssistant,
    cache_miss: Any,
) -> None:
    """Non-200 from Routes is surfaced as a structured error."""
    session = _make_session(
        {
            PLACES_URL: {"status": 200, "data": _places_response()},
            ROUTES_URL: {"status": 500, "data": {"error": "boom"}},
        },
    )

    with patch(
        "custom_components.llm_intents.google_routes.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            routes_hass,
            _tool_input(destination="x"),
            Mock(),
        )
    assert result == {"error": "Routes API error: 500"}


async def test_places_failure_falls_back_to_raw_destination(
    tool: GetRouteTool,
    routes_hass: HomeAssistant,
    cache_miss: Any,
) -> None:
    """When Places returns an HTTP error, routing proceeds with raw input."""
    session = _make_session(
        {
            PLACES_URL: {"status": 503, "data": {"error": "down"}},
            ROUTES_URL: {"status": 200, "data": _routes_response()},
        },
    )

    with patch(
        "custom_components.llm_intents.google_routes.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            routes_hass,
            _tool_input(destination="raw place"),
            Mock(),
        )

    body = result["result"]
    assert body["destination"] == "raw place"
    routes_body = session.post.call_args_list[1].kwargs["json"]
    assert routes_body["destination"] == {"address": "raw place"}


async def test_places_cache_hit_skips_places_call(
    tool: GetRouteTool,
    routes_hass: HomeAssistant,
) -> None:
    """A cached Places resolution avoids hitting the Places API."""
    session = _make_session(
        {ROUTES_URL: {"status": 200, "data": _routes_response()}},
    )

    with (
        patch(
            "custom_components.llm_intents.google_routes.async_get_clientsession",
            return_value=session,
        ),
        patch(
            "custom_components.llm_intents.google_routes.SQLiteCache",
        ) as cache_cls,
    ):
        cache_cls.return_value.get.return_value = {
            "address": "Cached Address",
            "name": "Cached Place",
        }
        result = await tool.async_call(
            routes_hass,
            _tool_input(destination="something"),
            Mock(),
        )

    assert session.post.call_count == 1
    assert session.post.call_args_list[0].args[0] == ROUTES_URL
    body = result["result"]
    assert body["destination"] == "Cached Address"
    assert body["destination_name"] == "Cached Place"


async def test_imperial_units_render_in_miles(
    tool: GetRouteTool,
    routes_hass: HomeAssistant,
    cache_miss: Any,
) -> None:
    """When HA is set to US units, distances render in miles."""
    routes_hass.config.units = US_CUSTOMARY_SYSTEM
    session = _make_session(
        {
            PLACES_URL: {"status": 200, "data": _places_response()},
            ROUTES_URL: {
                "status": 200,
                "data": _routes_response(distance_m=16093),
            },
        },
    )

    with patch(
        "custom_components.llm_intents.google_routes.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            routes_hass,
            _tool_input(destination="x"),
            Mock(),
        )

    assert result["result"]["distance"] == "10.0 mi"
    assert session.post.call_args_list[1].kwargs["json"]["units"] == "IMPERIAL"


async def test_traffic_duration_emitted_when_different(
    tool: GetRouteTool,
    routes_hass: HomeAssistant,
    cache_miss: Any,
) -> None:
    """`duration_without_traffic` appears for DRIVE when static differs."""
    session = _make_session(
        {
            PLACES_URL: {"status": 200, "data": _places_response()},
            ROUTES_URL: {
                "status": 200,
                "data": _routes_response(duration_s=900, static_s=600),
            },
        },
    )

    with patch(
        "custom_components.llm_intents.google_routes.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            routes_hass,
            _tool_input(destination="x"),
            Mock(),
        )

    body = result["result"]
    assert body["duration"] == "15 min"
    assert body["duration_without_traffic"] == "10 min"


@pytest.mark.parametrize("value", [None, "not-a-date"])
def test_resolve_departure_time_none(tool: GetRouteTool, value: str | None) -> None:
    """None or unparseable input returns None."""
    assert tool._resolve_departure_time(value) is None


def test_resolve_departure_time_naive_utc(tool: GetRouteTool) -> None:
    """Naive datetime is treated as local time and converted to UTC."""
    result = tool._resolve_departure_time("2026-01-01T12:00:00")
    assert isinstance(result, str)
    assert result.endswith("Z")
    parsed = datetime.strptime(result, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    assert parsed > datetime.now(UTC)


@freeze_time("2025-01-01 00:00:00")
@pytest.mark.parametrize(
    ("input_time", "expected"),
    [
        ("2024-06-01T12:00:00Z", "2025-01-01T00:00:10Z"),
        ("2026-06-01T12:00:00Z", "2026-06-01T12:00:00Z"),
    ],
)
def test_resolve_departure_time_past_future(
    tool: GetRouteTool,
    input_time: str,
    expected: str,
) -> None:
    """Past departure time is bumped to now+10s; future time is unchanged."""
    result = tool._resolve_departure_time(input_time)
    assert result == expected


@freeze_time("2025-01-01 00:00:00")
@pytest.mark.parametrize(
    ("scenario", "places_response", "raise_on_places", "expected"),
    [
        (
            "happy_path",
            {
                "places": [
                    {
                        "displayName": {"text": "Aquarium"},
                        "shortFormattedAddress": "100 Water St",
                    },
                ],
            },
            False,
            {"address": "100 Water St", "name": "Aquarium"},
        ),
        (
            "exception",
            None,
            True,
            None,
        ),
    ],
)
async def test_resolve_destination_via_places(
    tool: GetRouteTool,
    routes_hass: HomeAssistant,
    cache_miss: Any,
    scenario: str,
    places_response: dict | None,
    raise_on_places: bool,
    expected: dict | None,
) -> None:
    """Resolve destination via Places API with caching and error handling."""
    session = AsyncMock()

    def mock_post(url: str, **_kwargs: Any) -> MockContext:
        if "places" in url:
            if raise_on_places:
                raise RuntimeError("network error")
            response = AsyncMock()
            response.status = 200
            response.json = AsyncMock(return_value=places_response or {})
            return MockContext(response)
        response = AsyncMock()
        response.status = 200
        response.json = AsyncMock(return_value=_routes_response())
        return MockContext(response)

    session.post = Mock(side_effect=mock_post)

    with patch(
        "custom_components.llm_intents.google_routes.async_get_clientsession",
        return_value=session,
    ):
        result = await tool._resolve_destination_via_places(
            routes_hass,
            "test_key",
            "Aquarium",
        )

    assert result == expected
    assert session.post.call_count == 1


@pytest.mark.parametrize(
    ("scenario", "routes_response", "raise_on_routes"),
    [
        (
            "with_departure_time",
            _routes_response(duration_s=600, distance_m=5000),
            False,
        ),
        (
            "no_routes",
            {"routes": []},
            False,
        ),
        (
            "exception",
            None,
            True,
        ),
    ],
)
@freeze_time("2025-01-01 00:00:00")
async def test_async_call_variants(
    tool: GetRouteTool,
    routes_hass: HomeAssistant,
    cache_miss: Any,
    scenario: str,
    routes_response: dict,
    raise_on_routes: bool,
) -> None:
    """Test async_call with departure time, no routes, and exception paths."""
    session = AsyncMock()

    def mock_post(url: str, **_kwargs: Any) -> MockContext:
        if "places" in url:
            response = AsyncMock()
            response.status = 200
            response.json = AsyncMock(return_value=_places_response())
            return MockContext(response)
        if raise_on_routes:
            raise RuntimeError("api error")
        response = AsyncMock()
        response.status = 200
        response.json = AsyncMock(return_value=routes_response)
        return MockContext(response)

    session.post = Mock(side_effect=mock_post)

    with patch(
        "custom_components.llm_intents.google_routes.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            routes_hass,
            _tool_input(
                destination="Aquarium",
                departure_time="2026-06-01T12:00:00Z",
            ),
            Mock(),
        )

    if scenario == "with_departure_time":
        assert "departure_time" in result["result"]
        assert "estimated_arrival" in result["result"]
        assert result["result"]["departure_time"] == "2026-06-01T12:00:00Z"
        routes_body = session.post.call_args_list[1].kwargs["json"]
        assert routes_body["departureTime"] == "2026-06-01T12:00:00Z"
    elif scenario == "no_routes":
        assert result.get("result") == "No route found"
    else:
        assert result.get("error") == "Error computing route"
