"""Google Routes tool."""

import logging
from datetime import UTC, datetime, timedelta

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util
from homeassistant.util.json import JsonObjectType
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from .base_tool import BaseTool
from .cache import SQLiteCache
from .const import (
    CONF_GOOGLE_ROUTES_DEFAULT_TRAVEL_MODE,
    CONF_GOOGLE_ROUTES_HOME_ADDRESS,
    CONF_GOOGLE_ROUTES_TRAVEL_MODES,
    CONF_PROVIDER_API_KEYS,
    DOMAIN,
    PROVIDER_GOOGLE,
)

_LOGGER = logging.getLogger(__name__)

_TRAVEL_MODES = list(CONF_GOOGLE_ROUTES_TRAVEL_MODES.keys())

# Soft-bias radius (meters) applied to internal Places lookups.
_PLACES_LOCATION_BIAS_RADIUS_M = 50_000


class GetRouteTool(BaseTool):
    """Tool for computing routes from a configured home address."""

    name = "get_route"

    description = (
        "Estimate travel distance and duration from the user's home to a "
        "destination, or work out when to leave to arrive on time. Use it for "
        "questions about how far, how long, or when to leave."
    )

    prompt_description = (
        f"Use the `{name}` tool to compute travel routes from the user's home address. "
        "It returns distance and travel duration. To answer 'when should I leave to "
        "arrive at <time>', call this tool to get the duration and subtract it from "
        "the requested arrival time."
    )

    response_directive = (
        "Use the route information to answer the user's question directly. "
        "Report distance and duration concisely. "
        "If `departure_time` is present in the result, the duration is for "
        "that future departure - phrase it as 'with expected traffic'. "
        "If `departure_time` is NOT present, the duration is for leaving now - "
        "phrase it as 'with current traffic'. "
        "If the user asked when to leave, subtract the duration from their "
        "target arrival time."
    )

    parameters = vol.Schema(
        {
            vol.Required(
                "destination",
                description=(
                    "Destination address, place name, or business name as the "
                    "user described it. Pass the user's wording verbatim - do "
                    "not invent a specific address."
                ),
            ): str,
            vol.Optional(
                "departure_time",
                description=(
                    "Departure time in ISO 8601 format. Omit for an immediate "
                    "departure."
                ),
            ): str,
            vol.Optional(
                "mode",
                description=(
                    "Travel mode. One of: DRIVE, WALK, BICYCLE, TRANSIT, "
                    "TWO_WHEELER. Defaults to user's preferred mode of travel."
                ),
            ): vol.In(_TRAVEL_MODES),
        }
    )

    def _resolve_departure_time(self, value: str | None) -> str | None:
        """Convert an LLM-supplied departure time into an RFC3339 UTC string."""
        if not value:
            return None

        parsed = dt_util.parse_datetime(value)
        if parsed is None:
            _LOGGER.warning("Could not parse departure_time '%s', using now", value)
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)

        utc = parsed.astimezone(UTC)
        # Routes API requires departureTime to be in the future
        now_utc = datetime.now(UTC)
        if utc <= now_utc:
            utc = now_utc + timedelta(seconds=10)

        return utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    async def _resolve_destination_via_places(
        self,
        hass: HomeAssistant,
        api_key: str,
        query: str,
    ) -> dict | None:
        """Resolve a freeform destination to a precise address via Places."""
        body: dict = {
            "textQuery": query,
            "pageSize": 1,
            "rankPreference": "RELEVANCE",
            "languageCode": hass.config.language,
        }

        if hass.config.latitude and hass.config.longitude:
            body["locationBias"] = {
                "circle": {
                    "center": {
                        "latitude": hass.config.latitude,
                        "longitude": hass.config.longitude,
                    },
                    "radius": _PLACES_LOCATION_BIAS_RADIUS_M,
                },
            }

        cache = SQLiteCache()
        cache_key_params = {k: v for k, v in body.items() if k != "languageCode"}
        cached = cache.get(__name__ + ":places", cache_key_params)
        if cached is not None:
            return cached or None

        field_mask = (
            "places.displayName,"
            "places.shortFormattedAddress,"
            "places.formattedAddress"
        )
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": field_mask,
        }

        try:
            session = async_get_clientsession(hass)
            async with session.post(
                "https://places.googleapis.com/v1/places:searchText",
                json=body,
                headers=headers,
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning(
                        "Places resolution HTTP %s for '%s'", resp.status, query
                    )
                    return None
                data = await resp.json()
        except Exception:
            _LOGGER.exception("Places resolution failed for '%s'", query)
            return None

        places = data.get("places") or []
        if not places:
            cache.set(__name__ + ":places", cache_key_params, {})
            return None

        place = places[0]
        address = place.get("shortFormattedAddress") or place.get("formattedAddress")
        if not address:
            return None

        resolved = {
            "address": address,
            "name": (place.get("displayName") or {}).get("text"),
        }
        cache.set(__name__ + ":places", cache_key_params, resolved)
        return resolved

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Call the tool."""
        config_data = hass.data[DOMAIN].get("config", {})
        entry = next(iter(hass.config_entries.async_entries(DOMAIN)))
        config_data = {**config_data, **entry.options}

        provider_keys = config_data.get(CONF_PROVIDER_API_KEYS) or {}
        api_key = provider_keys.get(PROVIDER_GOOGLE, "")
        home_address = config_data.get(CONF_GOOGLE_ROUTES_HOME_ADDRESS, "").strip()
        default_mode = config_data.get(
            CONF_GOOGLE_ROUTES_DEFAULT_TRAVEL_MODE, "DRIVE"
        )

        if not api_key:
            return {"error": "Google API key not configured"}
        if not home_address:
            return {"error": "Home address for Routes is not configured"}

        destination_query = tool_input.tool_args["destination"]
        mode = tool_input.tool_args.get("mode", default_mode).upper()
        departure_time = self._resolve_departure_time(
            tool_input.tool_args.get("departure_time")
        )

        resolved = await self._resolve_destination_via_places(
            hass, api_key, destination_query
        )
        destination_address = (
            resolved["address"] if resolved else destination_query
        )

        imperial = hass.config.units is US_CUSTOMARY_SYSTEM
        units = "IMPERIAL" if imperial else "METRIC"

        body: dict = {
            "origin": {"address": home_address},
            "destination": {"address": destination_address},
            "travelMode": mode,
            "units": units,
            "languageCode": hass.config.language,
        }

        if mode in {"DRIVE", "TWO_WHEELER"}:
            body["routingPreference"] = "TRAFFIC_AWARE"

        if departure_time:
            body["departureTime"] = departure_time

        field_mask = (
            "routes.duration,"
            "routes.staticDuration,"
            "routes.distanceMeters,"
            "routes.description,"
            "routes.legs.startLocation,"
            "routes.legs.endLocation"
        )

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": field_mask,
        }

        try:
            session = async_get_clientsession(hass)
            async with session.post(
                "https://routes.googleapis.com/directions/v2:computeRoutes",
                json=body,
                headers=headers,
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    _LOGGER.error("Routes API HTTP %s: %s", resp.status, error_text)
                    return {"error": f"Routes API error: {resp.status}"}

                data = await resp.json()

            routes = data.get("routes") or []
            if not routes:
                return {"result": "No route found"}

            route = routes[0]
            distance_meters = int(route.get("distanceMeters", 0))
            duration_str = route.get("duration", "0s")
            static_duration_str = route.get("staticDuration", duration_str)

            # Routes API returns durations as e.g. "1234s"
            duration_seconds = int(duration_str.rstrip("s")) if duration_str else 0
            static_seconds = (
                int(static_duration_str.rstrip("s")) if static_duration_str else 0
            )

            result: dict = {
                "origin": home_address,
                "destination": destination_address,
                "travel_mode": mode,
                "distance": _format_distance(distance_meters, imperial=imperial),
                "duration": _format_duration(duration_seconds),
            }

            if resolved and resolved.get("name"):
                result["destination_name"] = resolved["name"]
            if destination_query != destination_address:
                result["destination_query"] = destination_query

            if mode in ("DRIVE", "TWO_WHEELER") and static_seconds != duration_seconds:
                result["duration_without_traffic"] = _format_duration(static_seconds)

            if departure_time:
                result["departure_time"] = departure_time
                arrival = datetime.strptime(
                    departure_time, "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=UTC) + timedelta(seconds=duration_seconds)
                result["estimated_arrival"] = dt_util.as_local(arrival).strftime(
                    "%Y-%m-%d %H:%M"
                )

            return {"result": result, "instruction": self.response_directive}

        except Exception:
            _LOGGER.exception("Routes API error")
            return {"error": "Error computing route"}


def _format_duration(seconds: int) -> str:
    """Format a duration in seconds as a human-readable string."""
    if seconds < 60:
        return f"{seconds} seconds"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min" + (f" {secs} sec" if secs else "")
    hours, minutes = divmod(minutes, 60)
    return f"{hours} hr" + (f" {minutes} min" if minutes else "")


def _format_distance(meters: int, *, imperial: bool) -> str:
    """Format a distance in meters using metric or US units."""
    if imperial:
        miles = meters / 1609.344
        if miles < 0.1:
            feet = round(meters * 3.28084)
            return f"{feet} ft"
        return f"{miles:.1f} mi"
    if meters < 1000:
        return f"{meters} m"
    return f"{meters / 1000:.1f} km"
