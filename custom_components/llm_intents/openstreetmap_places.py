"""OpenStreetMap Places tool."""

import asyncio
import logging
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

        # Cache like the Google Places tool: the inputs that determine
        # the result (query, search location, result count) form the
        # key, and only successful results are stored.
        cache = InMemoryCache()
        cache_params = {
            "q": query,
            "latitude": lat,
            "longitude": lon,
            "num_results": num_results,
        }
        cached_results = cache.get(__name__, cache_params)
        if cached_results:
            return cached_results

        base_params = {
            "q": query,
            "format": "jsonv2",
            "addressdetails": 1,
            "extratags": 1,
            "namedetails": 1,
            "limit": 50,
            "accept-language": "en",
        }
        session = async_get_clientsession(hass)

        data = []
        if lat is not None and lon is not None:
            # Search in stages, smallest area first. Nominatim ranks by
            # prominence rather than distance and returns at most 50
            # results, so in a wide area the nearest match for a chain
            # name may never make it into the results at all. A small box
            # around home holds few enough matches for the pool to be
            # complete; only widen the search when a stage comes back
            # empty, and use an unbounded search last.
            for half_side in (0.1, 0.5):
                viewbox = (
                    f"{lon - half_side},{lat + half_side},"
                    f"{lon + half_side},{lat - half_side}"
                )
                try:
                    data = await _fetch_stage(
                        session,
                        base_params,
                        {"viewbox": viewbox, "bounded": 1},
                    )
                except Exception as err:
                    # A stage that failed (after its retry) widens the
                    # search like an empty stage does; only the final,
                    # unbounded search below surfaces the error.
                    _LOGGER.warning(
                        "OpenStreetMap search stage failed (%s); widening the search",
                        err,
                    )
                    data = []
                if data:
                    break
        if not data:
            data = await _fetch_stage(session, base_params, {})

        if lat is not None and lon is not None:

            def _distance_sq(place: dict) -> float:
                try:
                    plat = float(place["lat"])
                    plon = float(place["lon"])
                except (KeyError, TypeError, ValueError):
                    return float("inf")
                return (plat - lat) ** 2 + (plon - lon) ** 2

            data = sorted(data, key=_distance_sq)
        data = data[:num_results]

        results = []
        for place in data:
            extratags = place.get("extratags") or {}
            address = place.get("address") or {}
            street = " ".join(
                part
                for part in [address.get("house_number"), address.get("road")]
                if part
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
            if extratags.get("opening_hours"):
                this_place["opening_hours"] = extratags["opening_hours"]
            website = extratags.get("website") or extratags.get("contact:website")
            if website:
                this_place["website"] = website
            results.append(this_place)

        if results:
            cache.set(__name__, cache_params, results)

        return results
