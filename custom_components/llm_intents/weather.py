"""Weather forecast tool."""

import logging
from datetime import datetime, timedelta

import voluptuous as vol
from homeassistant.components.weather import WeatherEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.util.json import JsonObjectType

from .base_tool import BaseTool
from .const import (
    CONF_DAILY_WEATHER_ENTITY,
    CONF_HOURLY_WEATHER_ENTITY,
    CONF_WEATHER_TEMPERATURE_SENSOR,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _friendly_precipitation_chance(precipitation_chance: int) -> str:
    """Format the precipitation chance into string categories for the LLM."""
    return (
        "none"
        if precipitation_chance == 0
        else "very unlikely"
        if precipitation_chance <= 5
        else "unlikely"
        if precipitation_chance <= 15
        else "possible"
        if precipitation_chance <= 30
        else "moderate"
        if precipitation_chance <= 50
        else "likely"
        if precipitation_chance <= 70
        else "very likely"
        if precipitation_chance <= 85
        else "extremely likely"
        if precipitation_chance <= 95
        else "almost guaranteed"
    )


class WeatherAttribute:
    def __init__(self, key: str, name: str, formatter):
        """Init our WeatherAttribute."""
        super().__init__()
        self.formatter = formatter
        self.key: str = key
        self.name: str = name


def _build_attributes(
    attribute_list: list[WeatherAttribute], weather_data: dict
) -> list[str]:
    """Build our attributes in a friendly manner for the LLM."""
    output = []
    for attribute in attribute_list:
        if attribute.key in weather_data:
            attr_data = weather_data.get(attribute.key)
            output.append(
                f"  {attribute.name}: {attribute.formatter(attr_data) if attribute.formatter else attr_data}"
            )
    return output


class WeatherForecastTool(BaseTool):
    """Tool for weather forecast data."""

    name = "GetWeatherForecast"
    description = "\n".join(
        [
            "Use this tool to retrieve weather forecasts for a particular period",
            "If the user requests data for `tonight`, use the `today` argument",
        ]
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
                ]
            ),
        }
    )

    @staticmethod
    def _find_target_date(date_range: str):
        """Find our target date based on the input."""
        now = datetime.now()

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
                return []

            # Find next matching weekday (not necessarily next calendar week)
            days_ahead = (target_weekday - now.weekday() + 7) % 7
            if days_ahead == 0:
                target_date = now.date()
            else:
                target_date = (now + timedelta(days=days_ahead)).date()
        return target_date

    @staticmethod
    def _filter_forecast_by_day(forecast: list[dict], target_date) -> list[dict]:
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
        now = datetime.now()
        date = dt.strftime("%A")

        if now.date() == dt.date():
            return f"Today ({date})"

        return date

    def has_twice_daily_data(self, entity_id: str) -> bool:
        """Does our daily entity data provide twice-daily data?"""
        entity = self.hass.states.get(entity_id)
        if entity is None:
            raise Exception(f"Weather entity {entity_id} not found.")
        features = entity.attributes.get("supported_features", 0)
        return features & WeatherEntityFeature.FORECAST_TWICE_DAILY

    async def _get_daily_forecast(
        self, hass: HomeAssistant, entity_id: str, date
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
            raise Exception("Failed to retrieve daily forecast from entity")

        if date:
            forecast = self._filter_forecast_by_day(forecast, date)

        daily_attributes = [
            WeatherAttribute(key="condition", name="General Condition", formatter=None),
            WeatherAttribute(
                key="precipitation_probability",
                name="Precipitation",
                formatter=_friendly_precipitation_chance,
            ),
        ]

        output = []
        for day in forecast:
            temp_low = day.get("templow")
            temperature = (
                f"{round(temp_low)} - {round(day['temperature'])}"
                if temp_low is not None
                else round(day["temperature"])
            )
            output.append(
                "\n".join(
                    [
                        f"- Date: {self._format_date(day['datetime'])}",
                        f"  Temperature: {temperature}",
                    ]
                    + _build_attributes(daily_attributes, day),
                )
            )

        return "\n".join(output)

    async def _get_twice_daily_forecast(
        self, hass: HomeAssistant, entity_id: str, date
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
            raise Exception("Failed to retrieve twice-daily forecast from entity")

        if date:
            forecast = self._filter_forecast_by_day(forecast, date)

        daily_attributes = [
            WeatherAttribute(key="condition", name="General Condition", formatter=None),
            WeatherAttribute(
                key="precipitation_probability",
                name="Precipitation",
                formatter=_friendly_precipitation_chance,
            ),
        ]

        days = {}
        for day in forecast:
            dt = datetime.fromisoformat(day["datetime"]).astimezone()
            date = dt.date()
            day_night = "day" if day.get("is_daytime", True) else "night"
            date_str = date.strftime("%A %-d %B")

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
            temp_low = day.get("templow")
            temperature = (
                f"{round(temp_low)} - {round(day['temperature'])}"
                if temp_low is not None
                else round(day["temperature"])
            )
            output.append(
                "\n".join(
                    [
                        f"- Date: {self._format_date(day['datetime'])} {'daytime' if day['is_daytime'] else 'nighttime'}",
                        f"  Temperature: {temperature}",
                    ]
                    + _build_attributes(daily_attributes, day),
                )
            )
        return "\n".join(output)

    async def _get_hourly_forecast(
        self, hass: HomeAssistant, entity_id: str, date
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
            raise Exception("Failed to retrieve hourly forecast from entity")

        forecast = self._filter_forecast_by_day(forecast, date)

        hourly_attributes = [
            WeatherAttribute(name="General Condition", key="condition", formatter=None),
            WeatherAttribute(
                name="Precipitation",
                key="precipitation_probability",
                formatter=_friendly_precipitation_chance,
            ),
        ]

        output = []
        for hour in forecast:
            output.append(
                "\n".join(
                    [
                        f"- Time: {self._format_time(hour['datetime'])}",
                        f"  Temperature: {round(hour['temperature'])}",
                    ]
                    + _build_attributes(hourly_attributes, hour),
                )
            )

        return "\n".join(output)

    @staticmethod
    def _get_current_temperature_sensor_data(
        hass: HomeAssistant, temperature_entity_id: str
    ) -> str | None:
        output = []
        # Add current temperature from sensor if provided and this is today's forecast
        sensor_state = hass.states.get(temperature_entity_id)
        if sensor_state:
            if sensor_state.state not in ("unknown", "unavailable"):
                try:
                    current_temp = round(float(sensor_state.state))
                    output.append(
                        "\n".join(
                            [
                                "- Time: current",
                                f"  Temperature: {current_temp}",
                            ]
                        )
                    )
                except (ValueError, TypeError):
                    _LOGGER.warning(
                        f"Could not parse temperature sensor value: {sensor_state.state}"
                    )
                    return None
        return "\n".join(output)

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

        date_range = tool_input.tool_args.get("range", "week").lower()
        _LOGGER.info(f"Weather forecast for the period: {date_range}")

        try:
            hourly_entity_id = config_data.get(CONF_HOURLY_WEATHER_ENTITY)
            daily_entity_id = config_data.get(CONF_DAILY_WEATHER_ENTITY)
            current_temperature_entity_id = config_data.get(
                CONF_WEATHER_TEMPERATURE_SENSOR
            )

            forecast = None
            target_date = self._find_target_date(date_range)

            if date_range != "week" and hourly_entity_id:
                forecast = await self._get_hourly_forecast(
                    hass, hourly_entity_id, target_date
                )

            if not forecast and daily_entity_id:
                is_twice_daily = self.has_twice_daily_data(daily_entity_id)

                if is_twice_daily:
                    forecast = await self._get_twice_daily_forecast(
                        hass, daily_entity_id, target_date
                    )
                else:
                    forecast = await self._get_daily_forecast(
                        hass, daily_entity_id, target_date
                    )

            if (
                forecast
                and current_temperature_entity_id
                and target_date == datetime.today().date()
            ):
                current_temperature_data = self._get_current_temperature_sensor_data(
                    hass, current_temperature_entity_id
                )
                if current_temperature_data:
                    forecast = current_temperature_data + "\n" + forecast

            if not forecast:
                forecast = "No weather forecast available for the selected range"

            return forecast
        except Exception as e:
            _LOGGER.exception(e)
            return {"error": f"Error retrieving weather forecast: {e!s}"}
