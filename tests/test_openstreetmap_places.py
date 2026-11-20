"""Tests for the OpenStreetMap Places tool and places provider selection."""

import time
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.llm import ToolResult
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import MockConfigEntry

from custom_components.llm_intents.cache import InMemoryCache
from custom_components.llm_intents.const import (
    CONF_OPENSTREETMAP_PLACES_LATITUDE,
    CONF_OPENSTREETMAP_PLACES_LONGITUDE,
    CONF_OPENSTREETMAP_PLACES_NUM_RESULTS,
    CONF_PLACES_PROVIDER,
    CONF_PLACES_PROVIDER_GOOGLE,
    CONF_PLACES_PROVIDER_OPENSTREETMAP,
    DOMAIN,
)
from custom_components.llm_intents.google_places import FindPlacesTool
from custom_components.llm_intents.llm_functions import SearchAPI
from custom_components.llm_intents.openstreetmap_places import (
    OpenStreetMapPlacesTool,
)

from .utils import MockContext


def _make_session(get_responses: list[tuple[int, list]]) -> AsyncMock:
    """Build a mock session that returns queued Nominatim GET responses."""
    session = AsyncMock()
    responses = list(get_responses)

    def mock_get(_url: str, **_kwargs: Any) -> MockContext:
        status, data = responses.pop(0)
        response = AsyncMock()
        response.status = status
        response.json = AsyncMock(return_value=data)
        return MockContext(response)

    session.get = Mock(side_effect=mock_get)
    return session


def _tool_input(**args: Any) -> Mock:
    tool_input = Mock()
    tool_input.tool_args = args
    return tool_input


@pytest.fixture
def config() -> dict:
    """Return default OpenStreetMap places config."""
    return {
        CONF_OPENSTREETMAP_PLACES_NUM_RESULTS: 3,
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
def tool(places_hass: HomeAssistant, config: dict) -> OpenStreetMapPlacesTool:
    """Construct the tool under test."""
    return OpenStreetMapPlacesTool(config, places_hass)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """Isolate tests from the shared in-memory cache store."""
    InMemoryCache._store.clear()


@pytest.fixture(autouse=True)
def _no_retry_delay() -> Iterator[None]:
    """Skip the Nominatim retry pause so failure-path tests stay fast."""
    with patch(
        "custom_components.llm_intents.openstreetmap_places._RETRY_DELAY_SECONDS",
        0,
    ):
        yield


OSM_EXAMPLE = {
    "lat": "40.05",
    "lon": "-73.95",
    "display_name": "Example Warehouse, 100 Main Street, Springfield, PA",
    "namedetails": {"name": "Example Warehouse"},
    "address": {
        "house_number": "100",
        "road": "Main Street",
        "city": "Springfield",
        "state": "Pennsylvania",
        "postcode": "99999",
    },
    "extratags": {
        "phone": "+1-212-555-0100",
        "opening_hours": "Mo-Fr 10:00-20:30",
        "website": "https://example.com",
    },
}

OSM_EXAMPLE_RESULT = {
    "name": "Example Warehouse",
    "address": "100 Main Street, Springfield, Pennsylvania, 99999",
    "rating": "Not rated",
    "phone": "+1-212-555-0100",
    "source": "OpenStreetMap",
    # The fixture home is (40.0, -74.0); the example place is 7.0 km away.
    "distance_km": 7.0,
    "opening_hours": "Mo-Fr 10:00-20:30",
    "website": "https://example.com",
}


async def test_osm_search_results(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """Nominatim results are parsed into the shared places result shape."""
    session = _make_session([(200, [OSM_EXAMPLE])])

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse"), Mock()
        )
        assert isinstance(result, ToolResult)

    assert result.data == {"results": [OSM_EXAMPLE_RESULT]}
    # The first Nominatim lookup is the small bounded box around home
    # (fixture home: 40.0, -74.0), and a hit there stops the search —
    # no wider fetch is made.
    assert session.get.call_count == 1
    first_get_params = session.get.call_args_list[0].kwargs["params"]
    assert first_get_params["bounded"] == 1
    assert first_get_params["limit"] == 50
    viewbox = [float(part) for part in first_get_params["viewbox"].split(",")]
    assert viewbox == pytest.approx([-74.1, 40.1, -73.9, 39.9])


async def test_osm_widens_when_small_box_empty(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """An empty small-box search widens to the larger bounded box."""
    session = _make_session([(200, []), (200, [OSM_EXAMPLE])])

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse"), Mock()
        )

    assert result.data == {"results": [OSM_EXAMPLE_RESULT]}
    assert session.get.call_count == 2
    second_get_params = session.get.call_args_list[1].kwargs["params"]
    assert second_get_params["bounded"] == 1
    viewbox = [float(part) for part in second_get_params["viewbox"].split(",")]
    assert viewbox == pytest.approx([-74.5, 40.5, -73.5, 39.5])


async def test_osm_unbounded_when_bounded_empty(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """When both bounded stages are empty, the search retries unbounded."""
    session = _make_session([(200, []), (200, []), (200, [OSM_EXAMPLE])])

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse"), Mock()
        )

    assert result.data == {"results": [OSM_EXAMPLE_RESULT]}
    assert session.get.call_count == 3
    third_get_params = session.get.call_args_list[2].kwargs["params"]
    assert "bounded" not in third_get_params
    assert "viewbox" not in third_get_params


async def test_osm_sorts_by_distance(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """Results are ordered nearest-first, not by prominence."""
    far = {
        "lat": "40.40",
        "lon": "-74.0",
        "display_name": "Far Store, Somewhere",
        "namedetails": {"name": "Far Store"},
        "address": {},
        "extratags": {},
    }
    near = {
        "lat": "40.01",
        "lon": "-74.0",
        "display_name": "Near Store, Nearby",
        "namedetails": {"name": "Near Store"},
        "address": {},
        "extratags": {},
    }
    session = _make_session([(200, [far, near])])

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(places_hass, _tool_input(query="store"), Mock())

    names = [place["name"] for place in result.data["results"]]
    assert names == ["Near Store", "Far Store"]
    # Each result carries its distance from the search center, in km.
    distances = [place["distance_km"] for place in result.data["results"]]
    assert distances == [1.11, 44.48]
    # Places without contact tags report the same placeholders as Google.
    near_result = result.data["results"][0]
    assert near_result["phone"] == "Not available"
    assert near_result["rating"] == "Not rated"
    assert "opening_hours" not in near_result
    assert "website" not in near_result


async def test_osm_no_results(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """No matches at any stage returns the shared no-places result."""
    session = _make_session([(200, []), (200, []), (200, [])])

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            places_hass, _tool_input(query="nowhere"), Mock()
        )

    assert result.data == {"result": "No places found"}
    assert session.get.call_count == 3


async def test_osm_transient_http_error_retried_on_same_stage(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """A transient HTTP error is retried once on the same stage."""
    session = _make_session([(503, []), (200, [OSM_EXAMPLE])])

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse"), Mock()
        )

    assert result.data == {"results": [OSM_EXAMPLE_RESULT]}
    # Exactly two requests, both to the first (small-box) stage: the
    # retry repeats the stage instead of widening the search.
    assert session.get.call_count == 2
    first_params = session.get.call_args_list[0].kwargs["params"]
    retry_params = session.get.call_args_list[1].kwargs["params"]
    assert retry_params == first_params
    assert retry_params["bounded"] == 1


async def test_osm_transient_request_error_retried_on_same_stage(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """A request error (e.g. a timeout) counts as transient and is retried."""
    session = AsyncMock()
    attempts = 0

    def mock_get(_url: str, **_kwargs: Any) -> MockContext:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionError("network down")
        response = AsyncMock()
        response.status = 200
        response.json = AsyncMock(return_value=[OSM_EXAMPLE])
        return MockContext(response)

    session.get = Mock(side_effect=mock_get)

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse"), Mock()
        )

    assert result.data == {"results": [OSM_EXAMPLE_RESULT]}
    assert session.get.call_count == 2


async def test_osm_stage_failure_widens_after_retry(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """A stage that fails twice widens to the next stage, like an empty one."""
    session = _make_session([(503, []), (503, []), (200, [OSM_EXAMPLE])])

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse"), Mock()
        )

    assert result.data == {"results": [OSM_EXAMPLE_RESULT]}
    # Two attempts on the small box, then the wider box succeeds.
    assert session.get.call_count == 3
    third_params = session.get.call_args_list[2].kwargs["params"]
    assert third_params["bounded"] == 1
    viewbox = [float(part) for part in third_params["viewbox"].split(",")]
    assert viewbox == pytest.approx([-74.5, 40.5, -73.5, 39.5])


async def test_osm_non_transient_error_widens_without_retry(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """A non-transient HTTP error widens at once, without a same-stage retry."""
    session = _make_session([(400, []), (200, [OSM_EXAMPLE])])

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse"), Mock()
        )

    assert result.data == {"results": [OSM_EXAMPLE_RESULT]}
    # Exactly one request to the failed stage, then the wider box.
    assert session.get.call_count == 2
    first_params = session.get.call_args_list[0].kwargs["params"]
    first_viewbox = [float(part) for part in first_params["viewbox"].split(",")]
    assert first_viewbox == pytest.approx([-74.1, 40.1, -73.9, 39.9])
    second_params = session.get.call_args_list[1].kwargs["params"]
    second_viewbox = [float(part) for part in second_params["viewbox"].split(",")]
    assert second_viewbox == pytest.approx([-74.5, 40.5, -73.5, 39.5])


async def test_osm_all_stages_fail_surfaces_error(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """Only when the final, unbounded stage fails is the error surfaced."""
    session = _make_session([(503, [])] * 6)

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse"), Mock()
        )

    assert result.error is True
    assert result.data == {"error": "Error finding places: Places search error: 503"}
    # Two attempts on each of the three stages.
    assert session.get.call_count == 6


async def test_osm_errors_not_cached(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """A failed search is not cached: the same search fetches again."""
    session = _make_session([(503, [])] * 6 + [(200, [OSM_EXAMPLE])])

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        failed = await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse"), Mock()
        )
        retried = await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse"), Mock()
        )

    assert failed.error is True
    assert retried.data == {"results": [OSM_EXAMPLE_RESULT]}
    assert session.get.call_count == 7


async def test_osm_request_failure_returns_error_result(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """A request error on every stage surfaces an error result."""
    session = AsyncMock()
    session.get = Mock(side_effect=ConnectionError("network down"))

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse"), Mock()
        )

    assert result.error is True
    assert result.data == {"error": "Error finding places: network down"}
    # Two attempts on each of the three stages before the error surfaces.
    assert session.get.call_count == 6


async def test_osm_config_location_overrides_home(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
    config: dict,
) -> None:
    """Configured coordinates, not the HA home location, anchor the search."""
    config[CONF_OPENSTREETMAP_PLACES_LATITUDE] = 41.0
    config[CONF_OPENSTREETMAP_PLACES_LONGITUDE] = -75.0
    session = _make_session([(200, [OSM_EXAMPLE])])

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse"), Mock()
        )

    first_get_params = session.get.call_args_list[0].kwargs["params"]
    viewbox = [float(part) for part in first_get_params["viewbox"].split(",")]
    assert viewbox == pytest.approx([-75.1, 41.1, -74.9, 40.9])


async def test_osm_string_coordinates_fall_back_to_home(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
    config: dict,
) -> None:
    """
    Non-numeric stored coordinates fall back to the home location.

    A stored value that is not a usable number must not fail every
    search: the bounded search anchors on the HA home location
    (fixture home: 40.0, -74.0) instead.
    """
    config[CONF_OPENSTREETMAP_PLACES_LATITUDE] = "not-a-number"
    config[CONF_OPENSTREETMAP_PLACES_LONGITUDE] = "not-a-number"
    session = _make_session([(200, [OSM_EXAMPLE])])

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse"), Mock()
        )

    assert result.data == {"results": [OSM_EXAMPLE_RESULT]}
    first_get_params = session.get.call_args_list[0].kwargs["params"]
    viewbox = [float(part) for part in first_get_params["viewbox"].split(",")]
    assert viewbox == pytest.approx([-74.1, 40.1, -73.9, 39.9])


async def test_osm_none_num_results_uses_default(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
    config: dict,
) -> None:
    """A stored num_results of None falls back to the service default."""
    config[CONF_OPENSTREETMAP_PLACES_NUM_RESULTS] = None
    session = _make_session([(200, [OSM_EXAMPLE])])

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse"), Mock()
        )

    assert result.data == {"results": [OSM_EXAMPLE_RESULT]}


async def test_osm_num_results_truncates(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
    config: dict,
) -> None:
    """Results are truncated to the configured number of results."""
    config[CONF_OPENSTREETMAP_PLACES_NUM_RESULTS] = 1
    other = dict(OSM_EXAMPLE)
    other["lat"] = "40.36"
    session = _make_session([(200, [OSM_EXAMPLE, other])])

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse"), Mock()
        )

    assert len(result.data["results"]) == 1


async def test_osm_cache_hit_avoids_second_fetch(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """A repeated identical search is served from cache, like Google's."""
    session = _make_session([(200, [OSM_EXAMPLE])])

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        first = await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse"), Mock()
        )
        second = await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse"), Mock()
        )

    assert first.data == {"results": [OSM_EXAMPLE_RESULT]}
    assert second.data == first.data
    assert session.get.call_count == 1


async def test_osm_cache_different_query_misses(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """A different query does not hit another query's cache entry."""
    session = _make_session([(200, [OSM_EXAMPLE]), (200, [OSM_EXAMPLE])])

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse"), Mock()
        )
        await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse Wholesale"), Mock()
        )

    assert session.get.call_count == 2


async def test_osm_cache_expired_entry_refetches(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """An entry older than the shared cache TTL is ignored and refetched."""
    cache = InMemoryCache()
    key = cache._make_key(
        "custom_components.llm_intents.openstreetmap_places",
        {
            "q": "Example Warehouse",
            "latitude": 40.0,
            "longitude": -74.0,
            "num_results": 3,
        },
    )
    InMemoryCache._store[key] = (
        time.time() - InMemoryCache.DEFAULT_MAX_AGE - 1,
        [{"name": "Stale"}],
    )
    session = _make_session([(200, [OSM_EXAMPLE])])

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse"), Mock()
        )

    assert result.data == {"results": [OSM_EXAMPLE_RESULT]}
    assert session.get.call_count == 1


async def test_osm_empty_results_not_cached(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """Empty results are not cached, mirroring the Google tool."""
    session = _make_session([(200, [])] * 6)

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        await tool.async_call(places_hass, _tool_input(query="nowhere"), Mock())
        await tool.async_call(places_hass, _tool_input(query="nowhere"), Mock())

    # Both searches run all three stages — nothing was served from cache.
    assert session.get.call_count == 6


@pytest.mark.parametrize(
    ("provider", "expected_type"),
    [
        (CONF_PLACES_PROVIDER_GOOGLE, FindPlacesTool),
        (CONF_PLACES_PROVIDER_OPENSTREETMAP, OpenStreetMapPlacesTool),
        (None, None),
    ],
)
async def test_places_provider_selection(
    hass: HomeAssistant,
    provider: str | None,
    expected_type: type | None,
) -> None:
    """The selected places provider decides which find_places tool is enabled."""
    config: dict = {}
    if provider is not None:
        config[CONF_PLACES_PROVIDER] = provider

    api = SearchAPI(hass, config, "Search Services")
    places_tools = [
        tool for tool in api.get_enabled_tools() if tool.name == "find_places"
    ]

    if expected_type is None:
        assert places_tools == []
    else:
        assert len(places_tools) == 1
        assert isinstance(places_tools[0], expected_type)


@pytest.mark.parametrize(
    ("query", "expected_q"),
    [
        ("closest pharmacy", "pharmacy"),
        ("the nearest pharmacy", "pharmacy"),
        ("Nearest Example Warehouse", "Example Warehouse"),
        ("pharmacy", "pharmacy"),
        ("Example Warehouse", "Example Warehouse"),
    ],
)
async def test_osm_superlative_stripped_from_query(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
    query: str,
    expected_q: str,
) -> None:
    """
    A leading superlative is dropped before searching; other queries pass through.

    "Closest" and "nearest" are ranking instructions (the results are
    already ranked by distance); as search terms they match businesses
    literally named with the word.
    """
    session = _make_session([(200, [OSM_EXAMPLE])])

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(places_hass, _tool_input(query=query), Mock())

    assert result.data == {"results": [OSM_EXAMPLE_RESULT]}
    assert session.get.call_count == 1
    assert session.get.call_args_list[0].kwargs["params"]["q"] == expected_q


async def test_osm_fallback_not_used_when_search_returns_results(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """A query with a location tail that returns results is searched as written."""
    session = _make_session([(200, [OSM_EXAMPLE])])

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            places_hass,
            _tool_input(query="Example Warehouse near Springfield"),
            Mock(),
        )

    assert result.data == {"results": [OSM_EXAMPLE_RESULT]}
    # One request, with the original query untouched: the tail
    # fallback only runs on a total miss.
    assert session.get.call_count == 1
    params = session.get.call_args_list[0].kwargs["params"]
    assert params["q"] == "Example Warehouse near Springfield"


async def test_osm_in_place_query_that_returns_results_not_rewritten(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """
    "Pharmacy in Pittsburgh" style queries that work are left alone.

    Nominatim parses a category plus a major place, so the raw query
    returns results at the unbounded stage; the fallback (and its
    geocode) must never run for it.
    """
    session = _make_session([(200, []), (200, []), (200, [OSM_EXAMPLE])])

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            places_hass, _tool_input(query="pharmacy in Pittsburgh"), Mock()
        )

    assert result.data == {"results": [OSM_EXAMPLE_RESULT]}
    assert session.get.call_count == 3
    for call in session.get.call_args_list:
        assert call.kwargs["params"]["q"] == "pharmacy in Pittsburgh"


@pytest.mark.parametrize(
    "query", ["Example Warehouse near me", "Example Warehouse near Springfield"]
)
async def test_osm_near_tail_fallback_searches_head_near_home(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
    query: str,
) -> None:
    """
    On a total miss, a "near" tail is dropped and the head is searched at home.

    Nominatim cannot parse the tail, so the original query fails every
    stage; the fallback retries with just the head, in the bounded
    stages around the configured location.
    """
    session = _make_session([(200, []), (200, []), (200, []), (200, [OSM_EXAMPLE])])

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(places_hass, _tool_input(query=query), Mock())

    assert result.data == {"results": [OSM_EXAMPLE_RESULT]}
    assert session.get.call_count == 4
    fallback_params = session.get.call_args_list[3].kwargs["params"]
    assert fallback_params["q"] == "Example Warehouse"
    assert fallback_params["bounded"] == 1
    viewbox = [float(part) for part in fallback_params["viewbox"].split(",")]
    assert viewbox == pytest.approx([-74.1, 40.1, -73.9, 39.9])


async def test_osm_fallback_never_searches_unbounded(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """The tail fallback widens through the bounded stages only, then stops."""
    session = _make_session([(200, [])] * 5)

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse near me"), Mock()
        )

    assert result.data == {"result": "No places found"}
    # Three stages for the original query, two bounded stages for the
    # fallback, and no unbounded fallback request.
    assert session.get.call_count == 5
    for call in session.get.call_args_list[3:]:
        params = call.kwargs["params"]
        assert params["bounded"] == 1
        assert "viewbox" in params
    last_viewbox = [
        float(part)
        for part in session.get.call_args_list[4].kwargs["params"]["viewbox"].split(",")
    ]
    assert last_viewbox == pytest.approx([-74.5, 40.5, -73.5, 39.5])


GEOCODE_EXAMPLE = [{"lat": "41.0", "lon": "-75.0", "display_name": "Springfield"}]

OSM_FAR_EXAMPLE = {
    "lat": "41.02",
    "lon": "-75.0",
    "display_name": "Far Warehouse, 200 Main Street, Springfield, PA",
    "namedetails": {"name": "Far Warehouse"},
    "address": {
        "house_number": "200",
        "road": "Main Street",
        "city": "Springfield",
        "state": "Pennsylvania",
        "postcode": "99999",
    },
    "extratags": {},
}

OSM_FAR_RESULT = {
    "name": "Far Warehouse",
    "address": "200 Main Street, Springfield, Pennsylvania, 99999",
    "rating": "Not rated",
    "phone": "Not available",
    "source": "OpenStreetMap",
    # Measured from the geocoded Springfield (41.0, -75.0), not from home.
    "distance_km": 2.22,
}


async def test_osm_in_place_fallback_geocodes_tail(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """
    On a total miss, an "in <place>" tail is geocoded and searched there.

    Stripping the tail and searching near home would answer with a
    place in the wrong locality; the fallback centers on the named
    place instead, and distances are measured from there.
    """
    session = _make_session(
        [
            (200, []),
            (200, []),
            (200, []),
            (200, GEOCODE_EXAMPLE),
            (200, [OSM_FAR_EXAMPLE]),
        ]
    )

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            places_hass,
            _tool_input(query="Example Warehouse in Springfield"),
            Mock(),
        )

    assert result.data == {"results": [OSM_FAR_RESULT]}
    assert session.get.call_count == 5
    # The fourth request is the geocode of the tail place alone.
    geocode_params = session.get.call_args_list[3].kwargs["params"]
    assert geocode_params["q"] == "Springfield"
    assert "viewbox" not in geocode_params
    assert "bounded" not in geocode_params
    # The fifth searches the head query in a bounded box around it.
    fallback_params = session.get.call_args_list[4].kwargs["params"]
    assert fallback_params["q"] == "Example Warehouse"
    assert fallback_params["bounded"] == 1
    viewbox = [float(part) for part in fallback_params["viewbox"].split(",")]
    assert viewbox == pytest.approx([-75.1, 41.1, -74.9, 40.9])


async def test_osm_in_place_fallback_geocode_miss_stays_not_found(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """A tail place that does not resolve leaves the honest not-found."""
    session = _make_session([(200, [])] * 4)

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse in Nowhere"), Mock()
        )

    assert result.data == {"result": "No places found"}
    # Three search stages plus the one geocode lookup; no fallback search.
    assert session.get.call_count == 4


async def test_osm_in_place_fallback_geocode_error_stays_not_found(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """A failed geocode lookup leaves the honest not-found, not an error."""
    session = _make_session([(200, [])] * 3 + [(503, [])] * 2)

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        result = await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse in Springfield"), Mock()
        )

    assert result.data == {"result": "No places found"}
    # Three search stages, then the geocode attempt and its one retry.
    assert session.get.call_count == 5


async def test_osm_fallback_result_cached_under_original_query(
    tool: OpenStreetMapPlacesTool,
    places_hass: HomeAssistant,
) -> None:
    """
    A fallback result is cached under the original query's key.

    Repeating the original query is served from cache, while the
    derived (tail-stripped) query is a different search and fetches
    for itself: the fallback result is not stored under its key.
    """
    session = _make_session(
        [(200, []), (200, []), (200, []), (200, [OSM_EXAMPLE]), (200, [OSM_EXAMPLE])]
    )

    with patch(
        "custom_components.llm_intents.openstreetmap_places.async_get_clientsession",
        return_value=session,
    ):
        first = await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse near me"), Mock()
        )
        second = await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse near me"), Mock()
        )
        derived = await tool.async_call(
            places_hass, _tool_input(query="Example Warehouse"), Mock()
        )

    assert first.data == {"results": [OSM_EXAMPLE_RESULT]}
    assert second.data == first.data
    assert derived.data == {"results": [OSM_EXAMPLE_RESULT]}
    # 4 requests for the first search (3 stages + fallback), none for
    # the cached repeat, 1 for the derived query's own search.
    assert session.get.call_count == 5
