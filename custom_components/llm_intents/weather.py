"""Weather forecast tool."""

import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta, tzinfo
from http import HTTPStatus
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
    CONF_WEATHER_TEMPERATURE_SENSOR,
)

_LOGGER = logging.getLogger(__name__)

# Open-Meteo endpoints, used for locations that have no weather entity.
# Free for non-commercial use and requires no API key.
OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

UNIT_CELSIUS = "celsius"
UNIT_FAHRENHEIT = "fahrenheit"

# The tool's `unit` argument values, mapped to Home Assistant's own constants.
# The unit constant doubles as the symbol used when reporting a temperature.
UNIT_ARG_TO_HA: dict[str, str] = {
    UNIT_CELSIUS: UnitOfTemperature.CELSIUS,
    UNIT_FAHRENHEIT: UnitOfTemperature.FAHRENHEIT,
}

# The same mapping inverted, for the Open-Meteo request parameter. Open-Meteo
# returns temperatures in whichever unit it is asked for, so asking it for the
# unit being reported in means its data never needs converting afterwards.
HA_TO_UNIT_ARG: dict[str, str] = {
    ha_unit: arg for arg, ha_unit in UNIT_ARG_TO_HA.items()
}

# WMO weather interpretation codes mapped to the same condition wording that
# weather entities report. https://open-meteo.com/en/docs#weathervariables
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
            if attr_data is None:
                continue
            output.append(
                f"  {attribute.name}: {attribute.formatter(attr_data) if attribute.formatter else attr_data}",
            )
    return output


def _at_index(values: list, index: int) -> Any:
    """Return the value at an index, or None when the list does not reach it."""
    return values[index] if index < len(values) else None


def _format_temperature(
    value: float | str | None,
    source_unit: str | None,
    requested_unit: str | None,
) -> str | int | None:
    """
    Render a temperature for the LLM.

    Forecast data already arrives in the unit its source reports in, so it is
    reported as-is unless the LLM asked for a specific unit. Only then is it
    converted, and labelled with its symbol so the unit is never ambiguous.
    """
    if value is None:
        return None

    temperature = float(value)
    if requested_unit is None:
        return round(temperature)

    if source_unit is not None and source_unit != requested_unit:
        temperature = TemperatureConverter.convert(
            temperature,
            source_unit,
            requested_unit,
        )
    return f"{round(temperature)}{requested_unit}"


def _format_temperature_range(
    high: float | str | None,
    low: float | str | None,
    source_unit: str | None,
    requested_unit: str | None,
) -> str | int | None:
    """Render a high and low temperature pair, as the daily forecast does."""
    high_text = _format_temperature(high, source_unit, requested_unit)
    low_text = _format_temperature(low, source_unit, requested_unit)

    if low_text is None:
        return high_text
    return f"{low_text} - {high_text}"


def _forecast_attributes() -> list[WeatherAttribute]:
    """Build the attribute list shared by the forecast output formats."""
    return [
        WeatherAttribute(key="condition", name="General Condition", formatter=None),
        WeatherAttribute(
            key="precipitation_probability",
            name="Chance of Precipitation",
            formatter=_friendly_precipitation_chance,
        ),
    ]


class WeatherForecastTool(BaseTool):
    """Tool for weather forecast data."""

    name = "get_weather_forecast"
    description = (
        "Use this tool to retrieve weather forecasts from now up until a week in advance.\n"
        "If the user requests data for `tonight`, use the `today` argument.\n"
        "Cannot be used to retrieve past or historic weather data: local sensor history can be queried via the device history tool."
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
                    "Optional place name, such as a city or town, to retrieve the "
                    "weather for. Omit this to use the local weather entities "
                    "configured in Home Assistant."
                ),
            ): str,
            vol.Optional(
                "unit",
                description=(
                    "Optional temperature unit to report in, when the user asks "
                    "for one specifically. Omit this to use the unit Home "
                    "Assistant is configured with."
                ),
            ): vol.In([UNIT_CELSIUS, UNIT_FAHRENHEIT]),
        },
    )

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
        """
        Return the unit a weather entity reports its temperatures in.

        The forecast service converts entity data into this same unit, so it
        is the unit the forecast values themselves are already in.
        """
        entity = self.hass.states.get(entity_id)
        if entity is None:
            return None
        return entity.attributes.get("temperature_unit")

    async def _get_daily_forecast(
        self,
        hass: HomeAssistant,
        entity_id: str,
        target_date: date | None,
        requested_unit: str | None = None,
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
            temperature = _format_temperature_range(
                day["temperature"],
                day.get("templow"),
                source_unit,
                requested_unit,
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
        requested_unit: str | None = None,
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
            temperature = _format_temperature_range(
                day["temperature"],
                day.get("templow"),
                source_unit,
                requested_unit,
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
        requested_unit: str | None = None,
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
            temperature = _format_temperature(
                hour["temperature"],
                source_unit,
                requested_unit,
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

    @staticmethod
    def _get_current_temperature_sensor_data(
        hass: HomeAssistant,
        temperature_entity_id: str,
        requested_unit: str | None = None,
    ) -> str | None:
        output = []
        # Add current temperature from sensor if provided and this is today's forecast
        sensor_state = hass.states.get(temperature_entity_id)
        if sensor_state and sensor_state.state not in ("unknown", "unavailable"):
            try:
                current_temp = _format_temperature(
                    sensor_state.state,
                    sensor_state.attributes.get("unit_of_measurement"),
                    requested_unit,
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
    def _condition_from_code(code: Any) -> str | None:
        """Translate a WMO weather interpretation code into condition wording."""
        if code is None:
            return None
        try:
            return WMO_CONDITIONS.get(int(code))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _format_location_label(place: dict) -> str:
        """Build a human-readable label for a geocoded place."""
        name = place.get("name")
        region = place.get("admin1")
        country = place.get("country")

        parts = [name]
        if region and region != name:
            parts.append(region)
        if country:
            parts.append(country)

        return ", ".join(part for part in parts if part)

    @staticmethod
    def _place_timezone(place: dict) -> tzinfo | None:
        """Return the timezone a geocoded place reports, when it is usable."""
        timezone_str = place.get("timezone")
        if not timezone_str:
            return None

        try:
            return ZoneInfo(timezone_str)
        except (ZoneInfoNotFoundError, ValueError):
            _LOGGER.debug(
                "Open-Meteo returned an unusable timezone: %s",
                timezone_str,
            )
            return None

    @staticmethod
    def _format_remote_date(day_date: date, place_tz: tzinfo | None) -> str:
        """Format a date at the requested location nicely for the LLM."""
        day_name = day_date.strftime("%A")

        if day_date == datetime.now(place_tz).date():
            return f"Today ({day_name})"

        return day_name

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
                    "Open-Meteo geocoding returned a HTTP %s error for '%s'",
                    resp.status,
                    location,
                )
                return None
            data = await resp.json()

        results = data.get("results") or []
        return results[0] if results else None

    def _format_remote_daily_forecast(
        self,
        data: dict,
        target_date: date | None,
        place_tz: tzinfo | None,
        requested_unit: str | None = None,
    ) -> str:
        """Build the daily forecast data for a requested location."""
        daily = data.get("daily") or {}
        times = daily.get("time") or []
        highs = daily.get("temperature_2m_max") or []
        lows = daily.get("temperature_2m_min") or []
        codes = daily.get("weather_code") or []
        chances = daily.get("precipitation_probability_max") or []

        daily_attributes = _forecast_attributes()

        output = []
        for index, day_str in enumerate(times):
            day_date = date.fromisoformat(day_str)
            if target_date and day_date != target_date:
                continue

            high = _at_index(highs, index)
            if high is None:
                continue
            # Open-Meteo was asked for the unit being reported in, so its
            # values are already in it and need no conversion.
            temperature = _format_temperature_range(
                high,
                _at_index(lows, index),
                requested_unit,
                requested_unit,
            )

            output.append(
                "\n".join(
                    [
                        f"- Date: {self._format_remote_date(day_date, place_tz)}",
                        f"  Temperature: {temperature}",
                        *_build_attributes(
                            daily_attributes,
                            {
                                "condition": self._condition_from_code(
                                    _at_index(codes, index),
                                ),
                                "precipitation_probability": _at_index(chances, index),
                            },
                        ),
                    ],
                ),
            )

        return "\n".join(output)

    def _format_remote_hourly_forecast(
        self,
        data: dict,
        target_date: date | None,
        requested_unit: str | None = None,
    ) -> str:
        """Build the hourly forecast data for a requested location."""
        hourly = data.get("hourly") or {}
        times = hourly.get("time") or []
        temperatures = hourly.get("temperature_2m") or []
        codes = hourly.get("weather_code") or []
        chances = hourly.get("precipitation_probability") or []

        hourly_attributes = _forecast_attributes()

        output = []
        for index, time_str in enumerate(times):
            # Requested with `timezone=auto`, so these are local to the place
            # being asked about rather than to this Home Assistant instance.
            entry_dt = datetime.fromisoformat(time_str)
            if target_date and entry_dt.date() != target_date:
                continue

            value = _at_index(temperatures, index)
            if value is None:
                continue
            # Open-Meteo was asked for the unit being reported in, so its
            # values are already in it and need no conversion.
            temperature = _format_temperature(value, requested_unit, requested_unit)

            output.append(
                "\n".join(
                    [
                        f"- Time: {entry_dt.strftime('%-I%p').lower()}",
                        f"  Temperature: {temperature}",
                        *_build_attributes(
                            hourly_attributes,
                            {
                                "condition": self._condition_from_code(
                                    _at_index(codes, index),
                                ),
                                "precipitation_probability": _at_index(chances, index),
                            },
                        ),
                    ],
                ),
            )

        return "\n".join(output)

    async def _get_remote_forecast(
        self,
        location: str,
        date_range: str,
        target_date: date | None,
        requested_unit: str | None = None,
    ) -> str | None:
        """Build the forecast data for a location that has no weather entity."""
        place = await self._geocode_location(location)
        if place is None:
            return None

        latitude = place.get("latitude")
        longitude = place.get("longitude")
        if latitude is None or longitude is None:
            return None

        # The requested day is resolved against the destination's own clock,
        # where "today" can be a different calendar date than it is here.
        place_tz = self._place_timezone(place)
        if place_tz is not None and target_date is not None:
            target_date = self._find_target_date(date_range, datetime.now(place_tz))

        # Ask Open-Meteo for the unit being reported in, so that its data
        # arrives ready to report and never needs converting.
        report_unit = requested_unit or self.hass.config.units.temperature_unit
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": "auto",
            "temperature_unit": HA_TO_UNIT_ARG.get(report_unit, UNIT_CELSIUS),
        }

        # Matches the weather entity behaviour: a specific day is reported
        # hourly, while the week ahead is reported as daily summaries.
        is_hourly = date_range != "week" and target_date is not None
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
                    "Open-Meteo forecast returned a HTTP %s error for '%s'",
                    resp.status,
                    location,
                )
                raise ForecastRetrievalError
            data = await resp.json()

        forecast = (
            self._format_remote_hourly_forecast(data, target_date, requested_unit)
            if is_hourly
            else self._format_remote_daily_forecast(
                data,
                target_date,
                place_tz,
                requested_unit,
            )
        )
        if not forecast:
            return None

        return f"Weather for {self._format_location_label(place)}:\n{forecast}"

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Call the tool."""
        config_data = self.config

        date_range = tool_input.tool_args.get("range", "week").lower()
        location = tool_input.tool_args.get("location")
        unit_arg = tool_input.tool_args.get("unit")
        # Left as None unless the LLM asked for a unit, in which case the
        # forecast is converted into it and reported with its symbol.
        requested_unit = UNIT_ARG_TO_HA.get(unit_arg.lower()) if unit_arg else None
        _LOGGER.info(
            "Weather forecast for the period: %s (location: %s, unit: %s)",
            date_range,
            location or "local",
            requested_unit or "as configured",
        )

        try:
            # A weather entity cannot exist for every arbitrary place a user
            # might ask about, so a named location is served by Open-Meteo.
            if location:
                remote_forecast = await self._get_remote_forecast(
                    location,
                    date_range,
                    self._find_target_date(date_range),
                    requested_unit,
                )
                if not remote_forecast:
                    return {
                        "error": f"Could not find weather data for '{location}'",
                    }
                return remote_forecast

            hourly_entity_id = config_data.get(CONF_HOURLY_WEATHER_ENTITY)
            daily_entity_id = config_data.get(CONF_DAILY_WEATHER_ENTITY)
            current_temperature_entity_id = config_data.get(
                CONF_WEATHER_TEMPERATURE_SENSOR,
            )

            forecast = None
            target_date = self._find_target_date(date_range)

            if date_range != "week" and hourly_entity_id and target_date:
                forecast = await self._get_hourly_forecast(
                    hass,
                    hourly_entity_id,
                    target_date,
                    requested_unit,
                )

            if not forecast and daily_entity_id:
                is_twice_daily = self.has_twice_daily_data(daily_entity_id)

                if is_twice_daily:
                    forecast = await self._get_twice_daily_forecast(
                        hass,
                        daily_entity_id,
                        target_date,
                        requested_unit,
                    )
                else:
                    forecast = await self._get_daily_forecast(
                        hass,
                        daily_entity_id,
                        target_date,
                        requested_unit,
                    )

            if (
                forecast
                and current_temperature_entity_id
                and target_date == datetime.now().astimezone().date()
            ):
                current_temperature_data = self._get_current_temperature_sensor_data(
                    hass,
                    current_temperature_entity_id,
                    requested_unit,
                )
                if current_temperature_data:
                    forecast = current_temperature_data + "\n" + forecast

            if not forecast:
                forecast = "No weather forecast available for the selected range"

            return forecast
        except Exception as e:
            _LOGGER.exception(msg="Weather forecast encountered an error")
            return {"error": f"Error retrieving weather forecast: {e!s}"}
