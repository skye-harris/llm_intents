import logging
from collections import UserDict
from datetime import datetime, timedelta
from typing import Callable

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.util.json import JsonObjectType

from .const import (
    CONF_DAILY_WEATHER_ENTITY,
    CONF_HOURLY_WEATHER_ENTITY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _friendly_rain_chance(rain_chance) -> str:
    return (
        "none"
        if rain_chance == 0
        else "very unlikely"
        if rain_chance <= 5
        else "unlikely"
        if rain_chance <= 15
        else "possible"
        if rain_chance <= 30
        else "moderate"
        if rain_chance <= 50
        else "likely"
        if rain_chance <= 70
        else "very likely"
        if rain_chance <= 85
        else "extremely likely"
        if rain_chance <= 95
        else "almost guaranteed"
    )


class WeatherAttribute:
    def __init__(self, key: str, name: str, formatter):
        super().__init__()
        self.formatter = formatter
        self.key: str = key
        self.name: str = name

def _build_attributes(attribute_list: list[WeatherAttribute], weather_data: dict) -> list[str]:
    output = []
    for attribute in attribute_list:
        if attribute.key in weather_data:
            attr_data = weather_data.get(attribute.key)
            output.append(f"  {attribute.name}: {attribute.formatter(attr_data) if attribute.formatter else attr_data}")
    return output


class WeatherForecastTool(llm.Tool):
    """Tool for weather forecast data."""

    name = "get_weather_forecast"
    description = "Use this tool to retrieve weather forecasts for a particular period. Defaults to the weeks weather if `range` is not specified."

    parameters = vol.Schema(
        {
            vol.Optional(
                "range",
                description="One of 'week', 'today', 'tomorrow', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'.",
            ): str,
        }
    )

    @staticmethod
    def _find_target_date(date_range: str):
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
        # Filter forecast entries for the target date
        result = []
        for entry in forecast:
            dt = datetime.fromisoformat(entry["datetime"]).astimezone()
            if dt.date() == target_date:
                result.append(entry)

        return result

    @staticmethod
    def _format_time(iso_str: str) -> str:
        dt = datetime.fromisoformat(iso_str).astimezone()
        next_hour = dt + timedelta(hours=1)
        return f"{dt.strftime('%-I%p').lower()}-{next_hour.strftime('%-I%p').lower()}"

    @staticmethod
    def _format_date(iso_str: str) -> str:
        dt = datetime.fromisoformat(iso_str).astimezone()
        now = datetime.now()
        date = dt.strftime("%A")

        if now.date() == dt.date():
            return f"Today ({date}))"

        return date

    async def _get_daily_forecast(self, hass: HomeAssistant, entity_id: str, date):
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
            WeatherAttribute(key="precipitation_probability", name="Rain", formatter=_friendly_rain_chance),
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
                    ] + _build_attributes(daily_attributes, day),
                )
            )

        return "\n".join(output)

    async def _get_hourly_forecast(self, hass: HomeAssistant, entity_id: str, date):
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
            WeatherAttribute(name="Rain", key="precipitation_probability", formatter=_friendly_rain_chance),
        ]

        output = []
        for hour in forecast:
            output.append(
                "\n".join(
                    [
                        f"- Time: {self._format_time(hour['datetime'])}",
                        f"  Temperature: {round(hour['temperature'])}",
                    ] + _build_attributes(hourly_attributes, hour),
                )
            )

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
            hourly_entity_id = config_data.get(CONF_HOURLY_WEATHER_ENTITY, "None")
            daily_entity_id = config_data.get(CONF_DAILY_WEATHER_ENTITY)

            forecast = None
            target_date = None

            if date_range != "week" and hourly_entity_id != "None":
                target_date = self._find_target_date(date_range)
                forecast = await self._get_hourly_forecast(
                    hass, hourly_entity_id, target_date
                )

            if not forecast and daily_entity_id:
                forecast = await self._get_daily_forecast(
                    hass, daily_entity_id, target_date
                )

            if not forecast:
                forecast = "No weather forecast available for the selected range"

            return forecast
        except Exception as e:
            _LOGGER.error("Weather forecast error: %s", e)
            return {"error": f"Error retrieving weather forecast: {e!s}"}
