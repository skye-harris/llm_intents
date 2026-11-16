"""OpenStreetMap Places tool."""

import logging
from http import HTTPStatus
from typing import Any

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .base_places import FindPlacesBaseTool
from .const import (
    CONF_OPENSTREETMAP_PLACES_LATITUDE,
    CONF_OPENSTREETMAP_PLACES_LONGITUDE,
    CONF_OPENSTREETMAP_PLACES_NUM_RESULTS,
    SERVICE_DEFAULTS,
)

_LOGGER = logging.getLogger(__name__)


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

        num_results = int(
            config_data.get(
                CONF_OPENSTREETMAP_PLACES_NUM_RESULTS,
                SERVICE_DEFAULTS.get(CONF_OPENSTREETMAP_PLACES_NUM_RESULTS),
            ),
        )
        lat = (
            config_data.get(CONF_OPENSTREETMAP_PLACES_LATITUDE) or hass.config.latitude
        )
        lon = (
            config_data.get(CONF_OPENSTREETMAP_PLACES_LONGITUDE)
            or hass.config.longitude
        )

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

        async def _fetch(extra: dict) -> list:
            async with session.get(
                "https://nominatim.openstreetmap.org/search",
                params={**base_params, **extra},
                headers={
                    "User-Agent": "HomeAssistant-llm_intents (personal home automation)",
                },
            ) as resp:
                if resp.status != HTTPStatus.OK:
                    _LOGGER.warning(
                        "OpenStreetMap search returned HTTP %s",
                        resp.status,
                    )
                    return []
                return await resp.json()

        data = []
        if lat is not None and lon is not None:
            # Search in stages, smallest area first. Nominatim ranks by
            # prominence rather than distance and returns at most 50
            # results, so in a wide area the nearest match for a chain
            # name may never make it into the results at all. A small box
            # around home holds few enough matches for the pool to be
            # complete; only widen the search when a stage comes back
            # empty, and fall back to an unbounded search last.
            for half_side in (0.1, 0.5):
                viewbox = (
                    f"{lon - half_side},{lat + half_side},"
                    f"{lon + half_side},{lat - half_side}"
                )
                data = await _fetch({"viewbox": viewbox, "bounded": 1})
                if data:
                    break
        if not data:
            data = await _fetch({})

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

        return results
