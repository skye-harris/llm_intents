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
from .const import (
    CONF_GOOGLE_ROUTES_HOME_ADDRESS,
    CONF_GOOGLE_ROUTES_TRAVEL_MODES,
    CONF_PROVIDER_API_KEYS,
    DOMAIN,
    PROVIDER_GOOGLE,
)

_LOGGER = logging.getLogger(__name__)

_TRAVEL_MODES = list(CONF_GOOGLE_ROUTES_TRAVEL_MODES.keys())


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


class GetRouteTool(BaseTool):
    """Tool for computing routes from a configured home address."""

    name = "get_route"

    description = (
        "Use this tool to estimate travel distance and duration from the user's "
        "home to a destination, or to figure out when to leave to arrive on time. "
        "Use it for questions like:\n"
        "- 'how far is it to the airport'\n"
        "- 'how long would it take to drive to X'\n"
        "- 'when should I leave to get to X by 6pm'"
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
                    "Destination address, place name, or business name "
                    "(e.g. '123 Main St, Springfield' or 'SeaTac Airport')"
                ),
            ): str,
            vol.Optional(
                "departure_time",
                description=(
                    "Departure time in ISO 8601 format (e.g. '2026-05-01T17:30:00'). "
                    "Omit for an immediate departure."
                ),
            ): str,
            vol.Optional(
                "mode",
                default="DRIVE",
                description=(
                    "Travel mode. One of: DRIVE, WALK, BICYCLE, TRANSIT, TWO_WHEELER. "
                    "Defaults to DRIVE."
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

        if not api_key:
            return {"error": "Google API key not configured"}
        if not home_address:
            return {"error": "Home address for Routes is not configured"}

        destination = tool_input.tool_args["destination"]
        mode = tool_input.tool_args.get("mode", "DRIVE").upper()
        departure_time = self._resolve_departure_time(
            tool_input.tool_args.get("departure_time")
        )

        imperial = hass.config.units is US_CUSTOMARY_SYSTEM
        units = "IMPERIAL" if imperial else "METRIC"

        body: dict = {
            "origin": {"address": home_address},
            "destination": {"address": destination},
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
                    _LOGGER.error(
                        "Routes API HTTP %s: %s", resp.status, error_text
                    )
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
                "destination": destination,
                "travel_mode": mode,
                "distance": _format_distance(distance_meters, imperial=imperial),
                "duration": _format_duration(duration_seconds),
            }

            if mode in ("DRIVE", "TWO_WHEELER") and static_seconds != duration_seconds:
                result["duration_without_traffic"] = _format_duration(static_seconds)

            if departure_time:
                result["departure_time"] = departure_time
                arrival = datetime.strptime(
                    departure_time, "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=UTC) + timedelta(seconds=duration_seconds)
                result["estimated_arrival"] = (
                    dt_util.as_local(arrival).strftime("%Y-%m-%d %H:%M")
                )

            return {"result": result, "instruction": self.response_directive}

        except Exception:
            _LOGGER.exception("Routes API error")
            return {"error": "Error computing route"}
