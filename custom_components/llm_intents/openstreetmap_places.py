"""OpenStreetMap Places tool."""

import asyncio
import logging
import math
import re
from http import HTTPStatus
from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .base_places import FindPlacesBaseTool
from .cache import InMemoryCache
from .const import (
    CONF_OPENSTREETMAP_PLACES_LATITUDE,
    CONF_OPENSTREETMAP_PLACES_LONGITUDE,
    CONF_OPENSTREETMAP_PLACES_NUM_RESULTS,
    SERVICE_DEFAULTS,
)

_LOGGER = logging.getLogger(__name__)

# Pause before retrying a stage after a transient failure. Nominatim's
# usage policy allows at most one request per second, so the pause
# doubles as rate limiting.
_RETRY_DELAY_SECONDS = 1.5

# Each search stage is attempted at most this many times: the initial
# request plus one retry after a transient failure.
_MAX_ATTEMPTS = 2

# A leading superlative ("closest pharmacy", "the nearest CVS") is a
# ranking instruction, not part of the place name: as a search term it
# matches businesses literally named with the word. The search already
# ranks results by distance, so the word is dropped before searching.
_SUPERLATIVE_PATTERN = re.compile(r"^(?:the\s+)?(?:closest|nearest)\s+", re.IGNORECASE)

# Trailing location tails in Google-style phrasing ("Domino's Pizza
# near Cannington", "CVS in Carlisle"). Nominatim cannot parse these;
# when a search finds nothing, the fallback below handles the tail
# explicitly instead.
_NEAR_TAIL_PATTERN = re.compile(r"^(?P<head>.+?)\s+near\s+(?P<tail>.+)$", re.IGNORECASE)
_IN_TAIL_PATTERN = re.compile(r"^(?P<head>.+?)\s+in\s+(?P<tail>.+)$", re.IGNORECASE)


def _strip_superlative(query: str) -> str:
    """Drop a leading superlative ("closest", "nearest") from a query."""
    match = _SUPERLATIVE_PATTERN.match(query)
    if match and match.end() < len(query):
        return query[match.end() :]
    return query


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two coordinates."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def _fetch_stage(session: Any, base_params: dict, extra: dict) -> list:
    """
    Fetch one search stage from Nominatim, retrying a transient failure once.

    A transient failure (HTTP 429 or 5xx, or a request error such as a
    timeout) is retried after a short pause: a momentary failure should
    not widen or kill a search that would otherwise succeed. When the
    stage has definitively failed this raises the error the tool has
    always surfaced: HomeAssistantError for an HTTP status, the
    original exception for a request error.
    """
    for attempt in (1, _MAX_ATTEMPTS):
        status: int | None = None
        try:
            async with session.get(
                "https://nominatim.openstreetmap.org/search",
                params={**base_params, **extra},
                headers={
                    "User-Agent": "HomeAssistant-llm_intents (personal home automation)",
                },
            ) as resp:
                if resp.status == HTTPStatus.OK:
                    return await resp.json()
                status = resp.status
        except asyncio.CancelledError:
            raise
        except Exception as err:
            if attempt == _MAX_ATTEMPTS:
                raise
            _LOGGER.warning(
                "OpenStreetMap search request failed (%s); retrying",
                err,
            )
            await asyncio.sleep(_RETRY_DELAY_SECONDS)
            continue
        # The request completed with a non-200 status: retry the stage
        # once if the failure looks transient, otherwise fail the stage.
        transient = (
            status == HTTPStatus.TOO_MANY_REQUESTS
            or status >= HTTPStatus.INTERNAL_SERVER_ERROR
        )
        if transient and attempt < _MAX_ATTEMPTS:
            _LOGGER.warning(
                "OpenStreetMap search returned HTTP %s; retrying",
                status,
            )
            await asyncio.sleep(_RETRY_DELAY_SECONDS)
            continue
        msg = f"Places search error: {status}"
        raise HomeAssistantError(msg)
    return []  # Unreachable: the loop returns or raises.


async def _bounded_search(
    session: Any, base_params: dict, lat: float, lon: float
) -> list:
    """
    Search the two bounded stages around a point, smallest box first.

    A stage that fails (after its retry) widens the search like an
    empty stage does. Returns the first non-empty stage's results, or
    an empty list when both stages come back empty or failed.
    """
    for half_side in (0.1, 0.5):
        viewbox = (
            f"{lon - half_side},{lat + half_side},{lon + half_side},{lat - half_side}"
        )
        try:
            data = await _fetch_stage(
                session,
                base_params,
                {"viewbox": viewbox, "bounded": 1},
            )
        except Exception as err:
            _LOGGER.warning(
                "OpenStreetMap search stage failed (%s); widening the search",
                err,
            )
            data = []
        if data:
            return data
    return []


async def _staged_search(
    session: Any, base_params: dict, lat: float | None, lon: float | None
) -> list:
    """
    Search in stages: bounded boxes around the location, then unbounded.

    Nominatim ranks by prominence rather than distance and returns at
    most 50 results, so in a wide area the nearest match for a chain
    name may never make it into the results at all. A small box around
    home holds few enough matches for the pool to be complete; only
    widen the search when a stage comes back empty, and use an
    unbounded search last. An error from the final, unbounded stage
    propagates to the caller, as it always has.
    """
    if lat is not None and lon is not None:
        data = await _bounded_search(session, base_params, lat, lon)
        if data:
            return data
    return await _fetch_stage(session, base_params, {})


async def _geocode_place(session: Any, place: str) -> tuple[float, float] | None:
    """
    Resolve a place name to coordinates with one Nominatim lookup.

    Returns None when the place does not resolve, including when the
    lookup itself fails: the caller treats that as no fallback rather
    than guessing a location.
    """
    # Nominatim's usage policy allows at most one request per second,
    # and the search stages run back to back, so pause before adding
    # this extra request.
    await asyncio.sleep(_RETRY_DELAY_SECONDS)
    try:
        data = await _fetch_stage(
            session,
            {
                "q": place,
                "format": "jsonv2",
                "limit": 1,
                "accept-language": "en",
            },
            {},
        )
    except Exception as err:
        _LOGGER.warning("OpenStreetMap geocode of %r failed (%s)", place, err)
        return None
    if not data:
        return None
    try:
        return float(data[0]["lat"]), float(data[0]["lon"])
    except (KeyError, TypeError, ValueError):
        return None


async def _fallback_search(
    session: Any,
    base_params: dict,
    query: str,
    lat: float | None,
    lon: float | None,
) -> tuple[list, float | None, float | None]:
    """
    Retry a total miss with the query's location tail handled explicitly.

    A "near" tail (including "near me") is dropped and the head of the
    query is searched around the configured location. An "in <place>"
    tail is geocoded and the head is searched around that place, so
    the answer comes from the locality the user named rather than
    near home; if the place does not resolve, there is no fallback.
    Either way the fallback searches the bounded stages only, never
    unbounded, where a stripped query would match same-named places
    anywhere in the world. Returns the raw results and the point
    they should be measured from.
    """
    near = _NEAR_TAIL_PATTERN.match(query)
    if near is not None:
        if lat is None or lon is None:
            return [], None, None
        data = await _bounded_search(
            session, {**base_params, "q": near["head"]}, lat, lon
        )
        return data, lat, lon
    in_tail = _IN_TAIL_PATTERN.match(query)
    if in_tail is not None:
        point = await _geocode_place(session, in_tail["tail"])
        if point is None:
            return [], None, None
        data = await _bounded_search(
            session, {**base_params, "q": in_tail["head"]}, point[0], point[1]
        )
        return data, point[0], point[1]
    return [], None, None


def _build_results(
    data: list,
    center_lat: float | None,
    center_lon: float | None,
    num_results: int,
) -> list:
    """
    Sort raw Nominatim results by distance and build the result dicts.

    Each result carries its distance from the search center, so the
    model can tell a nearby result from a far one instead of having
    to guess from the address. (The Google provider's results carry
    no distance, so this field is OpenStreetMap only.) Selection and
    ordering are unchanged: nearest first, truncated to num_results.
    """
    if center_lat is not None and center_lon is not None:

        def _distance_sq(place: dict) -> float:
            try:
                plat = float(place["lat"])
                plon = float(place["lon"])
            except (KeyError, TypeError, ValueError):
                return float("inf")
            return (plat - center_lat) ** 2 + (plon - center_lon) ** 2

        data = sorted(data, key=_distance_sq)
    data = data[:num_results]

    results = []
    for place in data:
        extratags = place.get("extratags") or {}
        address = place.get("address") or {}
        street = " ".join(
            part for part in [address.get("house_number"), address.get("road")] if part
        )
        city = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("hamlet")
        )
        address_str = ", ".join(
            part
            for part in [
                street,
                city,
                address.get("state"),
                address.get("postcode"),
            ]
            if part
        )
        this_place = {
            "name": (place.get("namedetails") or {}).get("name")
            or place.get("display_name", "").split(",")[0],
            "address": address_str or place.get("display_name", ""),
            "rating": "Not rated",
            "phone": extratags.get("phone")
            or extratags.get("contact:phone")
            or "Not available",
            "source": "OpenStreetMap",
        }
        if center_lat is not None and center_lon is not None:
            try:
                distance = _distance_km(
                    center_lat,
                    center_lon,
                    float(place["lat"]),
                    float(place["lon"]),
                )
            except (KeyError, TypeError, ValueError):
                distance = None
            if distance is not None:
                this_place["distance_km"] = round(distance, 2)
        if extratags.get("opening_hours"):
            this_place["opening_hours"] = extratags["opening_hours"]
        website = extratags.get("website") or extratags.get("contact:website")
        if website:
            this_place["website"] = website
        results.append(this_place)

    return results


class OpenStreetMapPlacesTool(FindPlacesBaseTool):
    """Tool for finding places via OpenStreetMap (Nominatim)."""

    async def async_search(self, query: str, **kwargs: Any) -> list:
        """
        Search OpenStreetMap (Nominatim) for places, including opening hours.

        Data is ODbL (c) OpenStreetMap contributors. Nominatim's usage policy
        requires an identifying User-Agent and light, non-bulk use, which a
        voice assistant's occasional lookups satisfy.
        """
        hass = self.hass
        config_data = self.config

        def _number(value: Any) -> float | None:
            """Coerce a stored config value to a float, or None if unusable."""
            if value is None or value == "":
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        num_results = _number(
            config_data.get(CONF_OPENSTREETMAP_PLACES_NUM_RESULTS),
        )
        if num_results is None:
            num_results = SERVICE_DEFAULTS.get(
                CONF_OPENSTREETMAP_PLACES_NUM_RESULTS,
            )
        num_results = int(num_results)

        # The bounded stages below do arithmetic on the coordinates, so
        # anything that is not a usable number (a missing key, a blank
        # left by the config flow, a non-numeric stored value) must fall
        # back to the home location, and failing that to an unbounded
        # search, rather than failing the search outright.
        lat = _number(
            config_data.get(CONF_OPENSTREETMAP_PLACES_LATITUDE),
        )
        if lat is None:
            lat = _number(hass.config.latitude)
        lon = _number(
            config_data.get(CONF_OPENSTREETMAP_PLACES_LONGITUDE),
        )
        if lon is None:
            lon = _number(hass.config.longitude)

        # A leading superlative is a ranking instruction, and the
        # results are already ranked by distance; keeping it in the
        # query only matches businesses literally named with the word.
        search_query = _strip_superlative(query)

        # Cache like the Google Places tool: the inputs that determine
        # the result (query, search location, result count) form the
        # key, and only successful results are stored.
        cache = InMemoryCache()
        cache_params = {
            "q": search_query,
            "latitude": lat,
            "longitude": lon,
            "num_results": num_results,
        }
        cached_results = cache.get(__name__, cache_params)
        if cached_results:
            return cached_results

        base_params = {
            "q": search_query,
            "format": "jsonv2",
            "addressdetails": 1,
            "extratags": 1,
            "namedetails": 1,
            "limit": 50,
            "accept-language": "en",
        }
        session = async_get_clientsession(hass)

        data = await _staged_search(session, base_params, lat, lon)
        center_lat, center_lon = lat, lon
        if not data:
            # The query found nothing at any stage. Nominatim cannot
            # parse Google-style location text, so retry once with
            # the tail handled explicitly before reporting that no
            # places were found. A fallback result is cached under
            # this search's key, not under the derived query.
            fallback_data, fallback_lat, fallback_lon = await _fallback_search(
                session, base_params, search_query, lat, lon
            )
            if fallback_data:
                data = fallback_data
                center_lat, center_lon = fallback_lat, fallback_lon

        results = _build_results(data, center_lat, center_lon, num_results)

        if results:
            cache.set(__name__, cache_params, results)

        return results
