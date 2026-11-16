"""Tests for the OpenStreetMap Places tool and places provider selection."""

import time
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
