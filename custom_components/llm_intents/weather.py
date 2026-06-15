"""Weather forecast tool."""

import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta
from http import HTTPStatus
from typing import Any
from zoneinfo import ZoneInfo

import voluptuous as vol
from homeassistant.components.weather import WeatherEntityFeature
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util.json import JsonObjectType
from homeassistant.util.unit_conversion import TemperatureConverter

from .base_tool import BaseTool
from .const import (
    CONF_DAILY_WEATHER_ENTITY,
    CONF_HOURLY_WEATHER_ENTITY,
    CONF_WEATHER_HOURLY_DEFAULT,
    CONF_WEATHER_SHOW_BOTH_UNITS,
    CONF_WEATHER_TEMPERATURE_SENSOR,
    DOMAIN,
    WEATHER_UNIT_CELSIUS,
    WEATHER_UNIT_FAHRENHEIT,
)

_LOGGER = logging.getLogger(__name__)

# Open-Meteo endpoints (free, no API key required)
OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Map our unit argument values to Home Assistant temperature unit constants.
# The HA unit constant string (e.g. "°C") doubles as the display symbol.
UNIT_TO_HA = {
    WEATHER_UNIT_CELSIUS: UnitOfTemperature.CELSIUS,
    WEATHER_UNIT_FAHRENHEIT: UnitOfTemperature.FAHRENHEIT,
}

# Map Home Assistant temperature unit constants to the Open-Meteo unit argument.
HA_TO_OPEN_METEO_UNIT = {
    UnitOfTemperature.CELSIUS: WEATHER_UNIT_CELSIUS,
    UnitOfTemperature.FAHRENHEIT: WEATHER_UNIT_FAHRENHEIT,
}

# WMO weather interpretation codes -> friendly condition text.
# https://open-meteo.com/en/docs#weathervariables
WMO_CONDITIONS: dict[int, str] = {
    0: "clear",
    1: "mainly clear",
    2: "partly cloudy",
    3: "cloudy",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    56: "light freezing drizzle",
    57: "dense freezing drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "heavy freezing rain",
    71: "slight snowfall",
    73: "moderate snowfall",
    75: "heavy snowfall",
    77: "snow grains",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    85: "slight snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}

# Precipitation chance thresholds for friendly categorization
PRECIPITATION_THRESHOLDS: dict[int, str] = {
    0: "none",
    5: "very unlikely",
    15: "unlikely",
    30: "possible",
    50: "moderate",
    70: "likely",
    85: "very likely",
    95: "extremely likely",
    100: "almost guaranteed",
}


class WeatherToolError(Exception):
    """Base exception for weather tool errors."""

    def __init__(self, message: str = "Weather tool encountered an error") -> None:
        """Init exception with default message."""
        super().__init__(message)


class WeatherEntityNotFoundError(WeatherToolError):
    """Raised when a weather entity is not found."""

    def __init__(self, message: str = "Weather entity not found") -> None:
        """Init exception with default message."""
        super().__init__(message)


class ForecastRetrievalError(WeatherToolError):
    """Raised when forecast data cannot be retrieved."""

    def __init__(self, message: str = "Failed to retrieve forecast") -> None:
        """Init exception with default message."""
        super().__init__(message)


def _friendly_precipitation_chance(precipitation_chance: int) -> str:
    """Format the precipitation chance into string categories for the LLM."""
    for threshold, value in PRECIPITATION_THRESHOLDS.items():
        if precipitation_chance <= threshold:
            return value
    return PRECIPITATION_THRESHOLDS[100]


class WeatherAttribute:
    """Represent a weather attribute."""

    def __init__(
        self,
        key: str,
        name: str,
        formatter: Callable[[Any], str] | None = None,
    ) -> None:
        """Init our WeatherAttribute."""
        super().__init__()
        self.formatter = formatter
        self.key: str = key
        self.name: str = name


def _build_attributes(
    attribute_list: list[WeatherAttribute],
    weather_data: dict,
) -> list[str]:
    """Build our attributes in a friendly manner for the LLM."""
    output = []
    for attribute in attribute_list:
        if attribute.key in weather_data:
            attr_data = weather_data.get(attribute.key)
            output.append(
                f"  {attribute.name}: {attribute.formatter(attr_data) if attribute.formatter else attr_data}",
            )
    return output


class WeatherForecastTool(BaseTool):
    """Tool for weather forecast data."""

    name = "GetWeatherForecast"
    description = (
        "Use this tool to retrieve weather forecasts for a particular period.\n"
        "If the user requests data for `tonight`, use the `today` argument."
    )
    prompt_description = None

    parameters = vol.Schema(
        {
            vol.Required(
                "range",
                description="Specify whether to receive data for the week ahead, or for a particular upcoming day",
            ): vol.In(
                [
                    "week",
                    "today",
                    "tomorrow",
                    "monday",
                    "tuesday",
                    "wednesday",
                    "thursday",
                    "friday",
                    "saturday",
                    "sunday",
                ],
            ),
            vol.Optional(
                "location",
                description=(
                    "Optional place name (e.g. a city or town) to get the weather "
                    "for. If omitted, the locally configured weather is used."
                ),
            ): str,
            vol.Optional(
                "unit",
                description=(
                    "Optional temperature unit. If omitted, the Home Assistant "
                    "configured unit system is used."
                ),
            ): vol.In([WEATHER_UNIT_CELSIUS, WEATHER_UNIT_FAHRENHEIT]),
            vol.Optional(
                "hourly",
                description=(
                    "Request hourly forecast data. If omitted, the integration "
                    "default is used."
                ),
            ): bool,
        },
    )

    def _resolve_target_unit(self, unit_arg: str | None) -> str:
        """Resolve the target HA temperature unit from the arg or HA settings."""
        if unit_arg and unit_arg.lower() in UNIT_TO_HA:
            return UNIT_TO_HA[unit_arg.lower()]
        return self.hass.config.units.temperature_unit

    @staticmethod
    def _convert_temperature(
        value: Any,
        source_unit: str | None,
        target_unit: str,
    ) -> int | None:
        """
        Convert a temperature value to the target unit and round it.

        When the source unit is unknown or not a recognised temperature unit,
        the value is assumed to already be in the target unit (HA entities
        typically report in the configured system unit).
        """
        if value is None:
            return None
        value = float(value)
        known_units = (UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT)
        if (
            source_unit in known_units
            and target_unit in known_units
            and source_unit != target_unit
        ):
            value = TemperatureConverter.convert(value, source_unit, target_unit)
        return round(value)

    def _format_single_temperature(
        self,
        value: Any,
        source_unit: str | None,
        target_unit: str,
    ) -> str | None:
        """Convert a temperature and format it with its unit symbol."""
        converted = self._convert_temperature(value, source_unit, target_unit)
        if converted is None:
            return None
        return f"{converted}{target_unit}"

    def _format_temperature(
        self,
        value: Any,
        source_unit: str | None,
        target_unit: str,
    ) -> str | None:
        """Convert a temperature and format it with its unit symbol."""
        converted = self._convert_temperature(value, source_unit, target_unit)
        if converted is None:
            return None

        if not getattr(self, "show_both_units", False):
            return f"{converted}{target_unit}"

        other_unit = (
            UnitOfTemperature.FAHRENHEIT
            if target_unit == UnitOfTemperature.CELSIUS
            else UnitOfTemperature.CELSIUS
        )
        other_converted = self._convert_temperature(value, source_unit, other_unit)
        if other_converted is None:
            return f"{converted}{target_unit}"
        return f"{converted}{target_unit} ({other_converted}{other_unit})"

    @staticmethod
    def _find_target_date(
        date_range: str,
        now: datetime | None = None,
    ) -> date | None:
        """Find our target date based on the input."""
        if now is None:
            now = datetime.now().astimezone()

        # Determine target date
        if date_range.lower() == "today":
            target_date = now.date()
        elif date_range.lower() == "tomorrow":
            target_date = (now + timedelta(days=1)).date()
        else:
            # Map weekday names to numbers
            weekdays = {
                "monday": 0,
                "tuesday": 1,
                "wednesday": 2,
                "thursday": 3,
                "friday": 4,
                "saturday": 5,
                "sunday": 6,
            }
            target_weekday = weekdays.get(date_range.lower())
            if target_weekday is None:
                return None

            # Find next matching weekday (not necessarily next calendar week)
            days_ahead = (target_weekday - now.weekday() + 7) % 7
            if days_ahead == 0:
                target_date = now.date()
            else:
                target_date = (now + timedelta(days=days_ahead)).date()
        return target_date

    @staticmethod
    def _filter_forecast_by_day(forecast: list[dict], target_date: date) -> list[dict]:
        """Filter forecast entries for the target date."""
        result = []
        for entry in forecast:
            dt = datetime.fromisoformat(entry["datetime"]).astimezone()
            if dt.date() == target_date:
                result.append(entry)

        return result

    @staticmethod
    def _format_time(iso_str: str) -> str:
        """Format our time nicely for the LLM."""
        dt = datetime.fromisoformat(iso_str).astimezone()
        next_hour = dt + timedelta(hours=1)
        return next_hour.strftime("%-I%p").lower()

    @staticmethod
    def _format_date(iso_str: str) -> str:
        """Format our date nicely for the LLM."""
        dt = datetime.fromisoformat(iso_str).astimezone()
        now = datetime.now().astimezone()
        date = dt.strftime("%A")

        if now.date() == dt.date():
            return f"Today ({date})"

        return date

    def has_twice_daily_data(self, entity_id: str) -> bool:
        """Check if our daily entity data provides twice-daily data."""
        entity = self.hass.states.get(entity_id)
        if entity is None:
            message = f"Weather entity {entity_id} not found."
            raise WeatherEntityNotFoundError(message)
        features = entity.attributes.get("supported_features", 0)
        return bool(features & WeatherEntityFeature.FORECAST_TWICE_DAILY)

    def _entity_temperature_unit(self, entity_id: str) -> str | None:
        """Return the native temperature unit reported by a weather entity."""
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        return state.attributes.get("temperature_unit")

    def _format_temperature_range(
        self,
        high: Any,
        low: Any,
        source_unit: str | None,
        target_unit: str,
    ) -> str | None:
        """Format a high/low temperature pair, converting to the target unit."""
        high_str = self._format_single_temperature(high, source_unit, target_unit)
        if high_str is None:
            return None
        low_str = self._format_single_temperature(low, source_unit, target_unit)

        if not getattr(self, "show_both_units", False):
            if low_str is not None:
                return f"{low_str} - {high_str}"
            return high_str

        other_unit = (
            UnitOfTemperature.FAHRENHEIT
            if target_unit == UnitOfTemperature.CELSIUS
            else UnitOfTemperature.CELSIUS
        )
        high_other = self._format_single_temperature(high, source_unit, other_unit)
        low_other = self._format_single_temperature(low, source_unit, other_unit)

        primary = f"{low_str} - {high_str}" if low_str is not None else high_str
        secondary = (
            f"{low_other} - {high_other}" if low_other is not None else high_other
        )

        return f"{primary} ({secondary})"

    async def _get_daily_forecast(
        self,
        hass: HomeAssistant,
        entity_id: str,
        target_date: date | None,
        target_unit: str,
    ) -> str:
        """Build the daily forecast data."""
        forecast = await hass.services.async_call(
            "weather",
            "get_forecasts",
            {"entity_id": entity_id, "type": "daily"},
            blocking=True,
            return_response=True,
        )
        forecast = forecast.get(entity_id, {}).get("forecast")
        if not forecast:
            raise ForecastRetrievalError

        if target_date:
            forecast = self._filter_forecast_by_day(forecast, target_date)

        source_unit = self._entity_temperature_unit(entity_id)
        daily_attributes = [
            WeatherAttribute(key="condition", name="General Condition", formatter=None),
            WeatherAttribute(
                key="precipitation_probability",
                name="Chance of Precipitation",
                formatter=_friendly_precipitation_chance,
            ),
        ]

        output = []
        for day in forecast:
            temperature = self._format_temperature_range(
                day["temperature"],
                day.get("templow"),
                source_unit,
                target_unit,
            )
            output.append(
                "\n".join(
                    [
                        f"- Date: {self._format_date(day['datetime'])}",
                        f"  Temperature: {temperature}",
                        *_build_attributes(daily_attributes, day),
                    ],
                ),
            )

        return "\n".join(output)

    async def _get_twice_daily_forecast(
        self,
        hass: HomeAssistant,
        entity_id: str,
        target_date: date | None,
        target_unit: str,
    ) -> str:
        """Build the twice daily forecast data."""
        forecast = await hass.services.async_call(
            "weather",
            "get_forecasts",
            {"entity_id": entity_id, "type": "twice_daily"},
            blocking=True,
            return_response=True,
        )
        forecast = forecast.get(entity_id, {}).get("forecast")
        if not forecast:
            raise ForecastRetrievalError

        if target_date:
            forecast = self._filter_forecast_by_day(forecast, target_date)

        source_unit = self._entity_temperature_unit(entity_id)
        daily_attributes = [
            WeatherAttribute(key="condition", name="General Condition", formatter=None),
            WeatherAttribute(
                key="precipitation_probability",
                name="Chance of Precipitation",
                formatter=_friendly_precipitation_chance,
            ),
        ]

        days = {}
        for day in forecast:
            dt = datetime.fromisoformat(day["datetime"]).astimezone()
            target_date = dt.date()
            day_night = "day" if day.get("is_daytime", True) else "night"
            date_str = target_date.strftime("%A %-d %B")

            days[date_str] = days.get(
                date_str,
                {
                    "day": {},
                    "night": {},
                },
            )

            days[date_str][day_night] = day

        output = []
        for day in forecast:
            temperature = self._format_temperature_range(
                day["temperature"],
                day.get("templow"),
                source_unit,
                target_unit,
            )
            output.append(
                "\n".join(
                    [
                        f"- Date: {self._format_date(day['datetime'])} {'daytime' if day['is_daytime'] else 'nighttime'}",
                        f"  Temperature: {temperature}",
                        *_build_attributes(daily_attributes, day),
                    ],
                ),
            )
        return "\n".join(output)

    async def _get_hourly_forecast(
        self,
        hass: HomeAssistant,
        entity_id: str,
        target_date: date,
        target_unit: str,
    ) -> str:
        """Build the hourly forecast data."""
        forecast = await hass.services.async_call(
            "weather",
            "get_forecasts",
            {"entity_id": entity_id, "type": "hourly"},
            blocking=True,
            return_response=True,
        )
        forecast = forecast.get(entity_id, {}).get("forecast")
        if not forecast:
            raise ForecastRetrievalError

        forecast = self._filter_forecast_by_day(forecast, target_date)

        source_unit = self._entity_temperature_unit(entity_id)
        hourly_attributes = [
            WeatherAttribute(name="General Condition", key="condition", formatter=None),
            WeatherAttribute(
                name="Chance of Precipitation",
                key="precipitation_probability",
                formatter=_friendly_precipitation_chance,
            ),
        ]

        output = []
        for hour in forecast:
            temperature = self._format_temperature(
                hour["temperature"],
                source_unit,
                target_unit,
            )
            output.append(
                "\n".join(
                    [
                        f"- Time: {self._format_time(hour['datetime'])}",
                        f"  Temperature: {temperature}",
                        *_build_attributes(hourly_attributes, hour),
                    ],
                ),
            )

        return "\n".join(output)

    def _get_current_temperature_sensor_data(
        self,
        hass: HomeAssistant,
        temperature_entity_id: str,
        target_unit: str,
    ) -> str | None:
        output = []
        # Add current temperature from sensor if provided and this is today's forecast
        sensor_state = hass.states.get(temperature_entity_id)
        if sensor_state and sensor_state.state not in ("unknown", "unavailable"):
            try:
                source_unit = sensor_state.attributes.get("unit_of_measurement")
                current_temp = self._format_temperature(
                    sensor_state.state,
                    source_unit,
                    target_unit,
                )
                output.append(
                    "\n".join(
                        [
                            "- Time: current",
                            f"  Temperature: {current_temp}",
                        ],
                    ),
                )
            except (ValueError, TypeError):
                _LOGGER.warning(
                    "Could not parse temperature sensor value: %s",
                    sensor_state.state,
                )
                return None
        return "\n".join(output)

    @staticmethod
    def _condition_from_code(code: Any) -> str:
        """Translate a WMO weather code into a friendly condition string."""
        try:
            return WMO_CONDITIONS.get(int(code), "unknown")
        except (ValueError, TypeError):
            return "unknown"

    @staticmethod
    def _format_location_label(place: dict) -> str:
        """Build a human-readable label for a geocoded place."""
        name = place.get("name")
        admin1 = place.get("admin1")
        country = place.get("country")
        parts = [name]
        if admin1 and admin1 != name:
            parts.append(admin1)
        if country:
            parts.append(country)
        return ", ".join(part for part in parts if part)

    @staticmethod
    def _format_om_date(
        day_date: date,
        timezone_str: str | None = None,
    ) -> str:
        """Format an Open-Meteo date nicely for the LLM."""
        name = day_date.strftime("%A")
        if timezone_str:
            try:
                now_date = datetime.now(ZoneInfo(timezone_str)).date()
            except Exception:
                now_date = datetime.now().astimezone().date()
        else:
            now_date = datetime.now().astimezone().date()
        if day_date == now_date:
            return f"Today ({name})"
        return name

    async def _geocode_location(self, location: str) -> dict | None:
        """Resolve a place name to coordinates via Open-Meteo geocoding."""
        session = async_get_clientsession(self.hass)
        params = {
            "name": location,
            "count": 1,
            "language": "en",
            "format": "json",
        }
        async with session.get(OPEN_METEO_GEOCODING_URL, params=params) as resp:
            if resp.status != HTTPStatus.OK:
                _LOGGER.warning(
                    "Open-Meteo geocoding returned HTTP %s for '%s'",
                    resp.status,
                    location,
                )
                return None
            data = await resp.json()

        results = data.get("results") or []
        return results[0] if results else None

    def _format_open_meteo_daily(
        self,
        data: dict,
        target_date: date | None,
        target_unit: str,
        timezone_str: str | None = None,
    ) -> str:
        """Format Open-Meteo daily data to match the entity output style."""
        daily = data.get("daily") or {}
        times = daily.get("time") or []
        highs = daily.get("temperature_2m_max") or []
        lows = daily.get("temperature_2m_min") or []
        codes = daily.get("weather_code") or []
        precs = daily.get("precipitation_probability_max") or []

        output = []
        for index, day_str in enumerate(times):
            day_date = date.fromisoformat(day_str)
            if target_date and day_date != target_date:
                continue

            high = highs[index] if index < len(highs) else None
            low = lows[index] if index < len(lows) else None
            # Data is already in the requested unit, so no conversion is needed.
            temperature = self._format_temperature_range(
                high,
                low,
                target_unit,
                target_unit,
            )
            lines = [
                f"- Date: {self._format_om_date(day_date, timezone_str)}",
                f"  Temperature: {temperature}",
            ]
            if index < len(codes) and codes[index] is not None:
                lines.append(
                    f"  General Condition: {self._condition_from_code(codes[index])}",
                )
            if index < len(precs) and precs[index] is not None:
                lines.append(
                    "  Chance of Precipitation: "
                    f"{_friendly_precipitation_chance(precs[index])}",
                )
            output.append("\n".join(lines))

        return "\n".join(output)

    def _format_open_meteo_hourly(
        self,
        data: dict,
        target_date: date | None,
        target_unit: str,
    ) -> str:
        """Format Open-Meteo hourly data to match the entity output style."""
        hourly = data.get("hourly") or {}
        times = hourly.get("time") or []
        temps = hourly.get("temperature_2m") or []
        codes = hourly.get("weather_code") or []
        precs = hourly.get("precipitation_probability") or []

        output = []
        for index, time_str in enumerate(times):
            dt = datetime.fromisoformat(time_str)
            if target_date and dt.date() != target_date:
                continue

            temp = temps[index] if index < len(temps) else None
            # Data is already in the requested unit, so no conversion is needed.
            temperature = self._format_temperature(temp, target_unit, target_unit)
            lines = [
                f"- Time: {dt.strftime('%-I%p').lower()}",
                f"  Temperature: {temperature}",
            ]
            if index < len(codes) and codes[index] is not None:
                lines.append(
                    f"  General Condition: {self._condition_from_code(codes[index])}",
                )
            if index < len(precs) and precs[index] is not None:
                lines.append(
                    "  Chance of Precipitation: "
                    f"{_friendly_precipitation_chance(precs[index])}",
                )
            output.append("\n".join(lines))

        return "\n".join(output)

    async def _get_open_meteo_forecast(
        self,
        location: str,
        date_range: str,
        target_date: date | None,
        target_unit: str,
        *,
        use_hourly: bool = True,
    ) -> str | None:
        """Fetch and format a forecast for a named location from Open-Meteo."""
        place = await self._geocode_location(location)
        if place is None:
            return None

        latitude = place.get("latitude")
        longitude = place.get("longitude")
        if latitude is None or longitude is None:
            return None

        # Recompute target_date in the target location's timezone so
        # filtering matches the dates returned by Open-Meteo.
        place_tz_str = place.get("timezone")
        if place_tz_str and target_date is not None:
            try:
                place_tz = ZoneInfo(place_tz_str)
                now_in_place = datetime.now(place_tz)
                target_date = self._find_target_date(date_range, now_in_place)
            except Exception:
                _LOGGER.debug(
                    "Failed to recompute target date in timezone '%s'",
                    place_tz_str,
                    exc_info=True,
                )

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": "auto",
            "temperature_unit": HA_TO_OPEN_METEO_UNIT.get(
                target_unit,
                WEATHER_UNIT_CELSIUS,
            ),
        }
        is_hourly = date_range != "week" and target_date is not None and use_hourly
        if is_hourly:
            params["hourly"] = "temperature_2m,weather_code,precipitation_probability"
        else:
            params["daily"] = (
                "temperature_2m_max,temperature_2m_min,"
                "weather_code,precipitation_probability_max"
            )

        session = async_get_clientsession(self.hass)
        async with session.get(OPEN_METEO_FORECAST_URL, params=params) as resp:
            if resp.status != HTTPStatus.OK:
                _LOGGER.error(
                    "Open-Meteo forecast returned HTTP %s for '%s'",
                    resp.status,
                    location,
                )
                raise ForecastRetrievalError
            data = await resp.json()

        if is_hourly:
            body = self._format_open_meteo_hourly(data, target_date, target_unit)
        else:
            body = self._format_open_meteo_daily(
                data, target_date, target_unit, place_tz_str
            )

        if not body:
            return None

        return f"Weather for {self._format_location_label(place)}:\n{body}"

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
        self.show_both_units = config_data.get(CONF_WEATHER_SHOW_BOTH_UNITS, False)

        date_range = tool_input.tool_args.get("range", "week").lower()
        location = tool_input.tool_args.get("location")
        unit_arg = tool_input.tool_args.get("unit")
        # If the LLM explicitly requests a unit, honour it exclusively.
        if unit_arg:
            self.show_both_units = False
        target_unit = self._resolve_target_unit(unit_arg)

        hourly_arg = tool_input.tool_args.get("hourly")
        hourly_default = config_data.get(CONF_WEATHER_HOURLY_DEFAULT, True)
        use_hourly = hourly_arg if hourly_arg is not None else hourly_default
        _LOGGER.info(
            "Weather forecast for the period: %s (location=%s, unit=%s)",
            date_range,
            location or "local",
            target_unit,
        )

        try:
            target_date = self._find_target_date(date_range)

            # A requested location is served by an external weather provider.
            if location:
                forecast = await self._get_open_meteo_forecast(
                    location,
                    date_range,
                    target_date,
                    target_unit,
                    use_hourly=use_hourly,
                )
                if not forecast:
                    return {
                        "error": (
                            f"Could not find weather data for location '{location}'"
                        ),
                    }
                return forecast

            hourly_entity_id = config_data.get(CONF_HOURLY_WEATHER_ENTITY)
            daily_entity_id = config_data.get(CONF_DAILY_WEATHER_ENTITY)
            current_temperature_entity_id = config_data.get(
                CONF_WEATHER_TEMPERATURE_SENSOR,
            )

            forecast = None

            if date_range != "week" and hourly_entity_id and target_date and use_hourly:
                forecast = await self._get_hourly_forecast(
                    hass,
                    hourly_entity_id,
                    target_date,
                    target_unit,
                )

            if not forecast and daily_entity_id:
                is_twice_daily = self.has_twice_daily_data(daily_entity_id)

                if is_twice_daily:
                    forecast = await self._get_twice_daily_forecast(
                        hass,
                        daily_entity_id,
                        target_date,
                        target_unit,
                    )
                else:
                    forecast = await self._get_daily_forecast(
                        hass,
                        daily_entity_id,
                        target_date,
                        target_unit,
                    )

            if (
                forecast
                and current_temperature_entity_id
                and target_date == datetime.now().astimezone().date()
            ):
                current_temperature_data = self._get_current_temperature_sensor_data(
                    hass,
                    current_temperature_entity_id,
                    target_unit,
                )
                if current_temperature_data:
                    forecast = current_temperature_data + "\n" + forecast

            if not forecast:
                forecast = "No weather forecast available for the selected range"

            return forecast
        except Exception as e:
            _LOGGER.exception(msg="Weather forecast encountered an error")
            return {"error": f"Error retrieving weather forecast: {e!s}"}
